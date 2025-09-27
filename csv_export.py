#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
csv_export.py — Export playlist tracks to CSV format.

This module provides functionality to export playlist tracks to CSV format
with columns: Artist - Title, Popularity score, Pinned, Genre.

Functions:
  - export_playlist_to_csv() — Main export function
  - get_track_genres()       — Get genre information for tracks
  - format_csv_data()        — Format track data for CSV output
"""

import csv
import sys
from typing import Dict, List, Optional, Tuple
from pin import SpotifyClient, load_playlist_config, normalize_track_id


def get_track_genres(sp: SpotifyClient, track_ids: List[str]) -> Tuple[Dict[str, List[str]], Dict[str, int]]:
    """
    Get genre and popularity information for multiple tracks.
    
    Args:
        sp: Spotify client instance
        track_ids: List of track IDs (without spotify:track: prefix)
    
    Returns:
        Tuple of (genres_dict, popularity_dict) where:
        - genres_dict maps track IDs to list of genres
        - popularity_dict maps track IDs to popularity scores
    """
    if not track_ids:
        return {}, {}
    
    # Spotify API allows up to 50 tracks per request
    batch_size = 50
    all_genres = {}
    all_popularity = {}
    
    for i in range(0, len(track_ids), batch_size):
        batch = track_ids[i:i + batch_size]
        
        try:
            # Get track details including artists
            track_ids_str = ",".join(batch)
            resp = sp._req("GET", f"/tracks?ids={track_ids_str}")
            
            if resp.status_code != 200:
                print(f"⚠️ Warning: Could not get track details: {resp.status_code}")
                continue
            
            data = resp.json()
            tracks = data.get("tracks", [])
            
            # Collect unique artist IDs
            artist_ids = set()
            track_artist_map = {}
            
            for track in tracks:
                if not track:
                    continue
                    
                track_id = track.get("id")
                artists = track.get("artists", [])
                popularity = track.get("popularity", 0)
                
                track_artist_map[track_id] = [artist.get("id") for artist in artists if artist.get("id")]
                all_popularity[track_id] = popularity
                artist_ids.update(track_artist_map[track_id])
            
            # Get artist details in batches (50 artists max per request)
            artist_genres = {}
            artist_list = list(artist_ids)
            
            for j in range(0, len(artist_list), 50):
                artist_batch = artist_list[j:j + 50]
                artist_ids_str = ",".join(artist_batch)
                
                resp = sp._req("GET", f"/artists?ids={artist_ids_str}")
                
                if resp.status_code == 200:
                    artist_data = resp.json()
                    for artist in artist_data.get("artists", []):
                        if artist:
                            artist_id = artist.get("id")
                            genres = artist.get("genres", [])
                            artist_genres[artist_id] = genres
                else:
                    print(f"⚠️ Warning: Could not get artist details: {resp.status_code}")
            
            # Map track IDs to genres
            for track_id, artist_ids in track_artist_map.items():
                track_genres = set()
                for artist_id in artist_ids:
                    if artist_id in artist_genres:
                        track_genres.update(artist_genres[artist_id])
                all_genres[track_id] = list(track_genres)
                
        except Exception as e:
            print(f"⚠️ Warning: Error getting genres for batch: {e}")
            continue
    
    return all_genres, all_popularity


def format_csv_data(tracks: List[Dict], pins: List[Dict], genres: Dict[str, List[str]], popularity: Dict[str, int]) -> List[Dict]:
    """
    Format track data for CSV export.
    
    Args:
        tracks: List of track items from Spotify API
        pins: List of pinned tracks from config
        genres: Dictionary mapping track IDs to genres
        popularity: Dictionary mapping track IDs to popularity scores
    
    Returns:
        List of formatted track data dictionaries
    """
    # Create a set of pinned track URIs for quick lookup
    pinned_uris = {normalize_track_id(pin['track_id']) for pin in pins}
    
    formatted_data = []
    
    for track_item in tracks:
        track = track_item.get('track', {})
        track_uri = track_item.get('uri', '')
        
        # Extract track information
        track_name = track.get('name', 'Unknown')
        artists = [artist.get('name', '') for artist in track.get('artists', [])]
        artist_name = ', '.join(artists) if artists else 'Unknown Artist'
        
        # Get popularity from our separate API call
        track_id = track.get('id', '')
        track_popularity = popularity.get(track_id, 0)
        
        # Check if track is pinned
        is_pinned = track_uri in pinned_uris
        
        # Get genre information
        track_genres = genres.get(track_id, [])
        genre_str = ', '.join(track_genres) if track_genres else 'Unknown'
        
        # Create combined artist-title field
        artist_title = f"{artist_name} - {track_name}"
        
        formatted_data.append({
            'artist_title': artist_title,
            'popularity': track_popularity,
            'pinned': 'Yes' if is_pinned else 'No',
            'genre': genre_str
        })
    
    return formatted_data


def export_playlist_to_csv(playlist_name: str, output_file: Optional[str] = None) -> bool:
    """
    Export playlist tracks to CSV format.
    
    Args:
        playlist_name: Name of the playlist to export
        output_file: Optional output file path (defaults to playlist_name.csv)
    
    Returns:
        True if successful, False otherwise
    """
    print(f"📊 Exporting playlist '{playlist_name}' to CSV...")
    
    # Load playlist config
    config = load_playlist_config(playlist_name)
    playlist_id = config.get('playlist_id')
    
    if not playlist_id:
        print(f"❌ Playlist '{playlist_name}' not found!")
        return False
    
    # Get Spotify client
    try:
        sp = SpotifyClient()
    except Exception as e:
        print(f"❌ Failed to initialize Spotify client: {e}")
        return False
    
    # Get playlist tracks
    print("📡 Loading tracks from Spotify...")
    try:
        tracks, _ = sp.get_playlist_items(playlist_id)
        if not tracks:
            print("❌ No tracks found in playlist!")
            return False
    except Exception as e:
        print(f"❌ Failed to load playlist tracks: {e}")
        return False
    
    # Get pinned tracks
    pins = config.get('pins', [])
    print(f"✅ Loaded {len(tracks)} tracks ({len(pins)} pinned)")
    
    # Get genre information
    print("🎵 Getting genre information...")
    track_ids = [track_item.get('track', {}).get('id', '') for track_item in tracks]
    track_ids = [tid for tid in track_ids if tid]  # Filter out empty IDs
    
    try:
        genres, popularity_data = get_track_genres(sp, track_ids)
        print(f"✅ Retrieved genres and popularity for {len(genres)} tracks")
    except Exception as e:
        print(f"⚠️ Warning: Could not get all genre/popularity information: {e}")
        genres = {}
        popularity_data = {}
    
    # Format data for CSV
    print("📝 Formatting data...")
    csv_data = format_csv_data(tracks, pins, genres, popularity_data)
    
    # Determine output file
    if not output_file:
        output_file = f"{playlist_name}_export.csv"
    
    # Write CSV file
    print(f"💾 Writing to {output_file}...")
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Artist - Title', 'Popularity Score', 'Pinned', 'Genre']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for row in csv_data:
                writer.writerow({
                    'Artist - Title': row['artist_title'],
                    'Popularity Score': row['popularity'],
                    'Pinned': row['pinned'],
                    'Genre': row['genre']
                })
        
        print(f"✅ Successfully exported {len(csv_data)} tracks to {output_file}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to write CSV file: {e}")
        return False


def main():
    """Main function for command-line usage."""
    if len(sys.argv) < 2:
        print("Usage: python csv_export.py <playlist_name> [output_file]")
        print("\nExample:")
        print("  python csv_export.py best_vocal_drum__bass")
        print("  python csv_export.py best_vocal_drum__bass my_export.csv")
        return
    
    playlist_name = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = export_playlist_to_csv(playlist_name, output_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
