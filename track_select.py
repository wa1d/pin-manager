#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
track_select.py — Interactive track selection for Spotify playlist pinning.

This module provides interactive functionality to browse tracks from playlists
and select them for pinning to specific positions.

Functions:
  - track_select()           — Main interactive track selection function
  - display_tracks_page()    — Display paginated tracks with current pins
  - select_track_position()  — Interactive position selection
  - preview_changes()        — Show pending changes before saving
"""

import sys
from typing import Dict, List, Optional, Tuple
from pin import SpotifyClient, load_playlist_config, save_playlist_config, normalize_track_id


def display_tracks_page(tracks: List[Dict], page: int = 0, page_size: int = 20, 
                       pinned_tracks: List[str] = None) -> None:
    """
    Display a page of tracks with pagination info.
    
    Args:
        tracks: List of track items from Spotify API
        page: Current page number (0-based)
        page_size: Number of tracks per page
        pinned_tracks: List of track URIs that are already pinned
    """
    if pinned_tracks is None:
        pinned_tracks = []
    
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tracks))
    page_tracks = tracks[start_idx:end_idx]
    
    print(f"\n📋 Tracks (Page {page + 1}/{(len(tracks) + page_size - 1) // page_size})")
    print("=" * 80)
    print(f"{'#':<3} {'Track Name - Artist':<50} {'Duration':<8} {'Status':<10}")
    print("-" * 80)
    
    for i, track_item in enumerate(page_tracks, start_idx + 1):
        track = track_item.get('track', {})
        track_name = track.get('name', 'Unknown')
        artists = ", ".join([artist.get('name', '') for artist in track.get('artists', [])])
        duration_ms = track.get('duration_ms', 0)
        duration_str = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
        
        # Truncate long track names
        full_name = f"{track_name} - {artists}" if artists else track_name
        if len(full_name) > 47:
            full_name = full_name[:44] + "..."
        
        # Check if track is pinned
        track_uri = track_item.get('uri', '')
        status = "📌 PINNED" if track_uri in pinned_tracks else ""
        
        print(f"{i:<3} {full_name:<50} {duration_str:<8} {status:<10}")
    
    print("-" * 80)
    print(f"Showing {start_idx + 1}-{end_idx} of {len(tracks)} tracks")


def get_track_selection(tracks: List[Dict], page: int = 0, page_size: int = 20) -> Optional[int]:
    """
    Get track selection from user.
    
    Args:
        tracks: List of track items
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


def preview_changes(track_info: Dict, position: int, playlist_name: str) -> bool:
    """
    Show preview of changes and get confirmation.
    
    Args:
        track_info: Track information dict
        position: Selected position
        playlist_name: Name of the playlist
    
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
    print("=" * 50)
    
    confirm = input("Add this pin? [Y/n]: ").lower().strip()
    return confirm != 'n'


def track_select(playlist_name: str) -> None:
    """
    Main interactive track selection function.
    
    Args:
        playlist_name: Name of the playlist to work with
    """
    print(f"🎵 Interactive Track Selection for: {playlist_name}")
    print("=" * 60)
    
    # Load playlist config
    config = load_playlist_config(playlist_name)
    playlist_id = config.get('playlist_id')
    if not playlist_id:
        print(f"❌ Playlist '{playlist_name}' not found!")
        return
    
    # Get Spotify client
    sp = SpotifyClient()
    
    # Get playlist tracks
    print("📡 Loading tracks from Spotify...")
    tracks, _ = sp.get_playlist_items(playlist_id)
    if not tracks:
        print("❌ No tracks found in playlist!")
        return
    
    # Get current pins
    current_pins = config.get('pins', [])
    pinned_tracks = [normalize_track_id(pin['track_id']) for pin in current_pins]
    
    print(f"✅ Loaded {len(tracks)} tracks")
    print(f"📌 Currently pinned: {len(current_pins)} tracks")
    
    # Interactive browsing
    page = 0
    page_size = 20
    
    while True:
        # Display current page
        display_tracks_page(tracks, page, page_size, pinned_tracks)
        
        # Get selection
        selection = get_track_selection(tracks, page, page_size)
        
        if selection is None:  # Quit
            print("👋 Goodbye!")
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
            selected_track_item = tracks[selection]
            selected_track = selected_track_item['track']
            track_uri = selected_track_item['uri']
            
            # Check if already pinned
            if track_uri in pinned_tracks:
                print(f"⚠️ This track is already pinned!")
                continue
            
            # Select position
            position = select_track_position(current_pins, len(tracks))
            
            # Preview and confirm
            if preview_changes(selected_track, position, playlist_name):
                # Create track name
                track_name = selected_track.get('name', 'Unknown')
                artists = ", ".join([artist.get('name', '') for artist in selected_track.get('artists', [])])
                full_track_name = f"{track_name} - {artists}" if artists else track_name
                
                # Add pin with track name
                new_pin = {
                    'track_id': track_uri,
                    'position': position,
                    'track_name': full_track_name
                }
                
                # Remove any existing pin at this position
                current_pins = [p for p in current_pins if int(p['position']) != position]
                current_pins.append(new_pin)
                
                # Save config
                config['pins'] = current_pins
                save_playlist_config(playlist_name, config)
                
                print(f"✅ Pinned: {selected_track['name']} at position {position}")
                
                # Update pinned tracks list for display
                pinned_tracks.append(track_uri)
            else:
                print("❌ Cancelled")


if __name__ == "__main__":
    # For testing purposes
    if len(sys.argv) > 1:
        track_select(sys.argv[1])
    else:
        print("Usage: python track_select.py <playlist_name>")
