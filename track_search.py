#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
track_search.py — Spotify track search and pinning functionality.

This module provides functionality to search for tracks on Spotify and pin them
to specific playlists, handling both existing and new tracks intelligently.

Functions:
  - track_search()           — Main interactive track search function
  - search_spotify_tracks()  — Search tracks on Spotify
  - display_search_results() — Display search results with pagination
  - select_track_from_search() — Interactive track selection
  - handle_track_pinning()   — Handle pinning logic for existing/new tracks
"""

import sys
from typing import Dict, List, Optional, Tuple
from pin import SpotifyClient, load_playlist_config, save_playlist_config, normalize_track_id


def search_spotify_tracks(sp: SpotifyClient, query: str, limit: int = 20) -> List[Dict]:
    """
    Search for tracks on Spotify.
    
    Args:
        sp: Spotify client instance
        query: Search query (track name, artist, etc.)
        limit: Maximum number of results to return
    
    Returns:
        List of track objects from Spotify API
    """
    try:
        # URL encode the query
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        
        resp = sp._req("GET", f"/search?q={encoded_query}&type=track&limit={limit}")
        if resp.status_code == 200:
            data = resp.json()
            return data.get("tracks", {}).get("items", [])
        else:
            print(f"❌ Search failed: {resp.status_code} {resp.text}")
            return []
    except Exception as e:
        print(f"❌ Search error: {e}")
        return []


def display_search_results(tracks: List[Dict], page: int = 0, page_size: int = 10) -> None:
    """
    Display search results with pagination.
    
    Args:
        tracks: List of track objects from Spotify
        page: Current page number (0-based)
        page_size: Number of tracks per page
    """
    if not tracks:
        print("❌ No tracks found!")
        return
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tracks))
    page_tracks = tracks[start_idx:end_idx]
    
    print(f"\n🔍 Search Results (Page {page + 1}/{(len(tracks) + page_size - 1) // page_size})")
    print("=" * 90)
    print(f"{'#':<3} {'Track Name - Artist':<60} {'Album':<25}")
    print("-" * 90)
    
    for i, track in enumerate(page_tracks, start_idx + 1):
        track_name = track.get('name', 'Unknown')
        artists = ", ".join([artist.get('name', '') for artist in track.get('artists', [])])
        album = track.get('album', {}).get('name', 'Unknown')
        
        # Truncate long names
        full_name = f"{track_name} - {artists}" if artists else track_name
        if len(full_name) > 57:
            full_name = full_name[:54] + "..."
        
        if len(album) > 22:
            album = album[:19] + "..."
        
        print(f"{i:<3} {full_name:<60} {album:<25}")
    
    print("-" * 90)
    print(f"Showing {start_idx + 1}-{end_idx} of {len(tracks)} results")


def get_search_selection(tracks: List[Dict], page: int = 0, page_size: int = 10) -> Optional[int]:
    """
    Get track selection from search results.
    
    Args:
        tracks: List of track objects
        page: Current page number
        page_size: Number of tracks per page
    
    Returns:
        Selected track index (0-based) or None if cancelled
    """
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tracks))
    
    while True:
        try:
            choice = input(f"\nSelect track number ({start_idx + 1}-{end_idx}) or 'n' for next page, 'p' for previous, 'q' to quit: ").strip().lower()
            
            if choice == 'q':
                return None
            elif choice == 'n':
                return 'next'
            elif choice == 'p':
                return 'prev'
            else:
                track_num = int(choice)
                if start_idx + 1 <= track_num <= end_idx:
                    return track_num - 1  # Convert to 0-based index
                else:
                    print(f"Please enter a number between {start_idx + 1} and {end_idx}")
        except ValueError:
            print("Please enter a valid number, 'n', 'p', or 'q'")


def check_track_in_playlist(sp: SpotifyClient, playlist_id: str, track_uri: str) -> Optional[int]:
    """
    Check if a track exists in the playlist and return its current position.
    
    Args:
        sp: Spotify client instance
        playlist_id: Playlist ID
        track_uri: Track URI to search for
    
    Returns:
        Current position (0-based) if found, None if not found
    """
    try:
        tracks, _ = sp.get_playlist_items(playlist_id)
        for i, track_item in enumerate(tracks):
            if track_item.get('uri') == track_uri:
                return i
        return None
    except Exception as e:
        print(f"❌ Error checking playlist: {e}")
        return None


def select_track_position(current_pins: List[Dict], total_tracks: int) -> int:
    """
    Interactive position selection with conflict detection.
    
    Args:
        current_pins: List of current pins with positions
        total_tracks: Total number of tracks in playlist
    
    Returns:
        Selected position (1-based)
    """
    print(f"\n📍 Position Selection")
    print("=" * 50)
    
    # Show current pin structure
    pinned_positions = {int(pin['position']) for pin in current_pins}
    print("Current pinned positions:")
    for pos in sorted(pinned_positions):
        print(f"  Position {pos}: 📌")
    
    print(f"\nAvailable positions: 1 to {total_tracks + 1}")
    
    while True:
        try:
            pos = int(input("Enter position (1-based): ").strip())
            if 1 <= pos <= total_tracks + 1:
                if pos in pinned_positions:
                    print(f"⚠️ Position {pos} is already pinned!")
                    confirm = input("Replace existing pin? [y/N]: ").lower().strip()
                    if confirm == 'y':
                        return pos
                else:
                    return pos
            else:
                print(f"Please enter a position between 1 and {total_tracks + 1}")
        except ValueError:
            print("Please enter a valid number")


def preview_track_changes(track_info: Dict, position: int, playlist_name: str, is_existing: bool = False) -> bool:
    """
    Show preview of changes and get confirmation.
    
    Args:
        track_info: Track information dict
        position: Selected position
        playlist_name: Name of the playlist
        is_existing: Whether track already exists in playlist
    
    Returns:
        True if user confirms, False otherwise
    """
    track_name = track_info.get('name', 'Unknown')
    artists = ", ".join([artist.get('name', '') for artist in track_info.get('artists', [])])
    
    print(f"\n📋 Preview Changes")
    print("=" * 50)
    print(f"Track: {track_name} - {artists}")
    print(f"Position: {position}")
    print(f"Playlist: {playlist_name}")
    
    if is_existing:
        print("Action: Move existing track to pinned position")
    else:
        print("Action: Add new track to playlist and pin")
    
    print("=" * 50)
    
    confirm = input("Proceed with this pin? [Y/n]: ").lower().strip()
    return confirm != 'n'


def handle_track_pinning(sp: SpotifyClient, playlist_id: str, track_info: Dict, position: int, 
                        playlist_name: str, config: Dict) -> bool:
    """
    Handle the pinning logic for a track.
    
    Args:
        sp: Spotify client instance
        playlist_id: Playlist ID
        track_info: Track information dict
        position: Selected position
        playlist_name: Name of the playlist
        config: Playlist configuration
    
    Returns:
        True if successful, False otherwise
    """
    track_uri = track_info.get('uri')
    if not track_uri:
        print("❌ Invalid track URI")
        return False
    
    # Check if track exists in playlist
    current_position = check_track_in_playlist(sp, playlist_id, track_uri)
    
    # Create track name
    track_name = track_info.get('name', 'Unknown')
    artists = ", ".join([artist.get('name', '') for artist in track_info.get('artists', [])])
    full_track_name = f"{track_name} - {artists}" if artists else track_name
    
    # Preview changes
    is_existing = current_position is not None
    if not preview_track_changes(track_info, position, playlist_name, is_existing):
        print("❌ Cancelled")
        return False
    
    # Add pin to config
    new_pin = {
        'track_id': track_uri,
        'position': position,
        'track_name': full_track_name
    }
    
    # Remove any existing pin at this position
    current_pins = config.get('pins', [])
    current_pins = [p for p in current_pins if int(p['position']) != position]
    current_pins.append(new_pin)
    
    # Save config
    config['pins'] = current_pins
    save_playlist_config(playlist_name, config)
    
    if is_existing:
        print(f"✅ Pinned existing track: {full_track_name} at position {position}")
        print("   Track will be moved to pinned position on next sync")
    else:
        print(f"✅ Pinned new track: {full_track_name} at position {position}")
        print("   Track will be added to playlist and pinned on next sync")
    
    return True


def track_search(playlist_name: str) -> None:
    """
    Main interactive track search function.
    
    Args:
        playlist_name: Name of the playlist to work with
    """
    print(f"🔍 Track Search for Playlist: {playlist_name}")
    print("=" * 60)
    
    # Load playlist config
    config = load_playlist_config(playlist_name)
    playlist_id = config.get('playlist_id')
    if not playlist_id:
        print(f"❌ Playlist '{playlist_name}' not found!")
        return
    
    # Get Spotify client
    sp = SpotifyClient()
    
    # Get current pins for position selection
    current_pins = config.get('pins', [])
    
    print(f"📌 Currently pinned: {len(current_pins)} tracks")
    
    while True:
        # Get search query
        query = input("\n🔍 Enter track name or artist to search (or 'q' to quit): ").strip()
        
        if query.lower() == 'q':
            print("👋 Goodbye!")
            break
        
        if not query:
            print("❌ Please enter a search query")
            continue
        
        print(f"🔍 Searching for: '{query}'...")
        
        # Search tracks
        tracks = search_spotify_tracks(sp, query, limit=50)
        
        if not tracks:
            print("❌ No tracks found. Try a different search term.")
            continue
        
        print(f"✅ Found {len(tracks)} tracks")
        
        # Interactive browsing
        page = 0
        page_size = 10
        
        while True:
            # Display current page
            display_search_results(tracks, page, page_size)
            
            # Get selection
            selection = get_search_selection(tracks, page, page_size)
            
            if selection is None:  # Quit
                break
            elif selection == 'next':  # Next page
                max_page = (len(tracks) + page_size - 1) // page_size - 1
                if page < max_page:
                    page += 1
                else:
                    print("📄 Already on last page!")
            elif selection == 'prev':  # Previous page
                if page > 0:
                    page -= 1
                else:
                    print("📄 Already on first page!")
            else:  # Track selected
                selected_track = tracks[selection]
                
                # Get playlist info for position selection
                try:
                    playlist_tracks, _ = sp.get_playlist_items(playlist_id)
                    total_tracks = len(playlist_tracks)
                except Exception as e:
                    print(f"❌ Error getting playlist info: {e}")
                    break
                
                # Select position
                position = select_track_position(current_pins, total_tracks)
                
                # Handle pinning
                if handle_track_pinning(sp, playlist_id, selected_track, position, playlist_name, config):
                    # Update current pins for next iteration
                    current_pins = config.get('pins', [])
                
                # Ask if user wants to search again
                continue_search = input("\n🔍 Search for another track? [Y/n]: ").lower().strip()
                if continue_search == 'n':
                    print("👋 Goodbye!")
                    return
                else:
                    break  # Break out of pagination loop to start new search


if __name__ == "__main__":
    # For testing purposes
    if len(sys.argv) > 1:
        track_search(sys.argv[1])
    else:
        print("Usage: python track_search.py <playlist_name>")
