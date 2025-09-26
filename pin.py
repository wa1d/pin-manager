#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pins.py — Fixed track positions in Spotify playlists.

Functions:
  - pin add/list/remove/move       — manage pins in config.json
  - select-playlist                — choose default playlist
  - sync                           — apply config.json to real playlists (daily/cron)

ENV (required):
  SPOTIFY_CLIENT_ID
  SPOTIFY_CLIENT_SECRET
  SPOTIFY_REFRESH_TOKEN

Config (config.json example):
{
  "timezone": "Europe/Sofia",
  "default_playlist_id": "spotify:playlist:XXXXXXXX",
  "playlists": [
    {
      "playlist_id": "spotify:playlist:XXXXXXXX",
      "on_conflict": "replace",
      "pins": [
        { "track_id": "spotify:track:AAA", "position": 3 },
        { "track_id": "spotify:track:BBB", "position": 6 }
      ]
    }
  ]
}

Cron example (Sofia 22:00):
0 22 * * * TZ=Europe/Sofia /usr/bin/python3 /opt/spotify-pins/pins.py sync >> /var/log/spotify_pins.log 2>&1
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests  # pyright: ignore[reportMissingModuleSource]

# Import track selection functionality
try:
    from track_select import track_select
except ImportError:
    track_select = None

def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(".env")
    if env_file.exists():
        with env_file.open("r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

# Load environment variables from .env file
load_env_file()

PLAYLISTS_REGISTRY = Path("playlists.json")
DEFAULT_LOG_PATH = os.environ.get("SPOTIFY_PINS_LOG", "spotify_pins.log")

# ---------- Logging ----------
logger = logging.getLogger("spotify_pins")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(DEFAULT_LOG_PATH, encoding='utf-8')
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)

console = logging.StreamHandler(sys.stdout)
console.setFormatter(logging.Formatter("%(message)s"))
console.setLevel(logging.INFO)
logger.addHandler(console)

# ---------- Utilities ----------

def die(msg: str, code: int = 1):
    logger.error(msg)
    sys.exit(code)

SPOTIFY_ID_RX = re.compile(r"(?:spotify:(?:track|playlist):)?([A-Za-z0-9]{22})")
TRACK_URL_RX = re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]{22})")
PLAYLIST_URL_RX = re.compile(r"open\.spotify\.com/playlist/([A-Za-z0-9]{22})")

def normalize_track_id(s: str) -> str:
    s = s.strip()
    m = TRACK_URL_RX.search(s) or SPOTIFY_ID_RX.search(s)
    if not m:
        raise ValueError(f"Cannot recognize track_id from: {s}")
    return f"spotify:track:{m.group(1)}"

def normalize_playlist_id(s: str) -> str:
    s = s.strip()
    m = PLAYLIST_URL_RX.search(s) or SPOTIFY_ID_RX.search(s)
    if not m:
        raise ValueError(f"Cannot recognize playlist_id from: {s}")
    return f"spotify:playlist:{m.group(1)}"


def load_playlists_registry() -> Dict:
    """Load the playlists registry that tracks all managed playlists."""
    if not PLAYLISTS_REGISTRY.exists():
        return {"playlists": {}, "default": None}
    with PLAYLISTS_REGISTRY.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_playlists_registry(registry: Dict):
    """Save the playlists registry."""
    with PLAYLISTS_REGISTRY.open("w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    logger.info("✅ Playlists registry saved: %s", PLAYLISTS_REGISTRY)

def get_playlist_config_path(playlist_name: str) -> Path:
    """Get the config file path for a specific playlist."""
    return Path(f"config_{playlist_name}.json")

def load_playlist_config(playlist_name: str) -> Dict:
    """Load configuration for a specific playlist."""
    config_path = get_playlist_config_path(playlist_name)
    if not config_path.exists():
        return {"timezone": "Europe/Sofia", "playlist_name": playlist_name, "pins": []}
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_playlist_config(playlist_name: str, config: Dict):
    """Save configuration for a specific playlist."""
    config_path = get_playlist_config_path(playlist_name)
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    logger.info("✅ Playlist config saved: %s", config_path)


# ---------- Spotify API Client ----------

class SpotifyClient:
    BASE = "https://api.spotify.com/v1"

    def __init__(self):
        self.client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        self.client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
        self.refresh_token = os.environ.get("SPOTIFY_REFRESH_TOKEN")
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            die("Need to set ENV: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN")
        self._access_token = None
        self._token_exp = 0

    def _refresh_access_token(self):
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            die(f"Failed to refresh access_token: {resp.status_code} {resp.text}")
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600)) - 60

    def _headers(self):
        if not self._access_token or time.time() > self._token_exp:
            self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    def _req(self, method: str, path: str, **kwargs):
        url = f"{self.BASE}{path}"
        for attempt in range(5):
            resp = requests.request(method, url, headers=self._headers(), timeout=60, **kwargs)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", "1"))
                time.sleep(retry)
                continue
            if resp.status_code in (500, 502, 503, 504):
                time.sleep(1 + attempt)
                continue
            if resp.status_code == 401:
                # try to refresh token
                self._refresh_access_token()
                continue
            return resp
        return resp

    # --- API helpers ---

    def me_playlists(self, limit=50) -> List[Dict]:
        items = []
        url = f"/me/playlists?limit={limit}"
        while url:
            resp = self._req("GET", url)
            if resp.status_code != 200:
                die(f"Error reading playlists: {resp.status_code} {resp.text}")
            data = resp.json()
            items.extend(data.get("items", []))
            url = None
            if data.get("next"):
                # next — absolute URL; extract base
                url = data["next"].replace(self.BASE, "")
        return items

    def get_my_user_id(self) -> str:
        """Get the current user's Spotify ID."""
        resp = self._req("GET", "/me")
        if resp.status_code != 200:
            die(f"Error getting user info: {resp.status_code} {resp.text}")
        return resp.json()["id"]

    def my_owned_playlists(self, limit=50) -> List[Dict]:
        """Get only playlists owned by the current user."""
        my_id = self.get_my_user_id()
        all_playlists = self.me_playlists(limit)
        return [p for p in all_playlists if p.get("owner", {}).get("id") == my_id]

    def get_playlist(self, playlist_id: str) -> Dict:
        pid = normalize_playlist_id(playlist_id).split(":")[-1]
        resp = self._req("GET", f"/playlists/{pid}")
        if resp.status_code != 200:
            die(f"Error reading playlist: {resp.status_code} {resp.text}")
        return resp.json()

    def get_playlist_items(self, playlist_id: str) -> Tuple[List[Dict], str]:
        """Returns (list of items, snapshot_id). Each item: { 'track': {...}, 'uri': 'spotify:track:...' }"""
        pid = normalize_playlist_id(playlist_id).split(":")[-1]
        items = []
        url = f"/playlists/{pid}/tracks?limit=100&fields=items(track(uri,id,name,artists(name))),next,snapshot_id,total"
        snapshot_id = None
        while url:
            resp = self._req("GET", url)
            if resp.status_code != 200:
                die(f"Error reading tracks: {resp.status_code} {resp.text}")
            data = resp.json()
            if snapshot_id is None:
                snapshot_id = data.get("snapshot_id")
            items.extend(data.get("items", []))
            url = data.get("next")
            if url:
                url = url.replace(self.BASE, "")
        # normalize
        norm = []
        for it in items:
            tr = it.get("track") or {}
            uri = tr.get("uri")
            if not uri:
                # local tracks etc. — skip
                continue
            norm.append({"track": tr, "uri": uri})
        return norm, snapshot_id

    def add_tracks(self, playlist_id: str, uris: List[str], position: Optional[int] = None) -> str:
        pid = normalize_playlist_id(playlist_id).split(":")[-1]
        payload = {"uris": uris}
        if position is not None:
            payload["position"] = position
        resp = self._req("POST", f"/playlists/{pid}/tracks", json=payload)
        if resp.status_code not in (201, 200):
            die(f"Error adding tracks: {resp.status_code} {resp.text}")
        return resp.json()["snapshot_id"]

    def reorder(self, playlist_id: str, range_start: int, insert_before: int, range_length: int, snapshot_id: Optional[str] = None) -> str:
        pid = normalize_playlist_id(playlist_id).split(":")[-1]
        payload = {
            "range_start": range_start,
            "insert_before": insert_before,
            "range_length": range_length,
        }
        if snapshot_id:
            payload["snapshot_id"] = snapshot_id
        resp = self._req("PUT", f"/playlists/{pid}/tracks", json=payload)
        if resp.status_code != 200:
            die(f"Error reordering: {resp.status_code} {resp.text}")
        return resp.json()["snapshot_id"]

    def remove_all_occurrences(self, playlist_id: str, uris: List[str]) -> str:
        """Removes ALL occurrences of specified tracks (for cleaning duplicates)."""
        pid = normalize_playlist_id(playlist_id).split(":")[-1]
        payload = {"tracks": [{"uri": u} for u in uris]}
        resp = self._req("DELETE", f"/playlists/{pid}/tracks", json=payload)
        if resp.status_code != 200:
            die(f"Error removing tracks: {resp.status_code} {resp.text}")
        return resp.json()["snapshot_id"]

# ---------- Domain Operations ----------

def ensure_no_duplicates(sp: SpotifyClient, playlist_id: str) -> None:
    items, snap = sp.get_playlist_items(playlist_id)
    seen = set()
    dups = []
    for idx, it in enumerate(items):
        uri = it["uri"]
        if uri in seen:
            dups.append(uri)
        else:
            seen.add(uri)
    if dups:
        sp.remove_all_occurrences(playlist_id, list(set(dups)))
        # return first occurrences? Not needed: we removed all, including the first.
        # So we'll add back ONE copy of each unique track from seen in original order.
        # To not lose order, re-read playlist (now it's without removed ones)
        # and we won't ADD — that would shift order. Instead
        # simpler to remove only extra copies, keeping the first:
        # Rewrite more correctly: remove by positions all repeated occurrences.
        # ---- Rewriting correctly:
        # 1) Read all items again
        items2, _ = sp.get_playlist_items(playlist_id)
        # 2) Collect positions of repeats (second+)
        first_seen = {}
        remove_positions = []
        for i, it2 in enumerate(items2):
            uri = it2["uri"]
            if uri not in first_seen:
                first_seen[uri] = i
            else:
                remove_positions.append((uri, i))
        if remove_positions:
            # Spotify API doesn't remove by index; already removed all occurrences above — so rollback:
            # Simple correct approach: go through original list again and remove specific "extra" by URI,
            # but that way we'll lose the first. To avoid complexity — implement cleanup by URI without removing first:
            # Solution: remove all URIs (as above), then add back exactly one copy each in first_seen order.
            unique_order = sorted(first_seen.items(), key=lambda kv: kv[1])
            sp.remove_all_occurrences(playlist_id, [u for u, _ in unique_order])  # remove all
            sp.add_tracks(playlist_id, [u for u, _ in unique_order], position=None)  # add one copy each
            logger.info("remove-dup: reduced to one copy, unique count=%d", len(unique_order))
        else:
            logger.info("remove-dup: no duplicates found after second check")
    else:
        logger.info("remove-dup: no duplicates")

def sync_playlist_new(sp: SpotifyClient, config: Dict):
    """Applies pins to one playlist using the new config format. Top to bottom."""
    playlist_id = config["playlist_id"]
    playlist_name = config.get("playlist_name", "unknown")

    # 1) remove duplicates (exactly one copy of each track in the end)
    ensure_no_duplicates(sp, playlist_id)

    # 2) current state
    items, snapshot = sp.get_playlist_items(playlist_id)
    uris = [it["uri"] for it in items]

    # helper: find track index (first occurrence) or None
    def find_index(uri: str) -> Optional[int]:
        try:
            return uris.index(uri)
        except ValueError:
            return None

    # 3) go through pins in ascending position order
    pins = sorted(config.get("pins", []), key=lambda p: int(p["position"]))
    for pin in pins:
        uri = normalize_track_id(pin["track_id"])
        target_pos_1based = int(pin["position"])
        # convert to 0-based insert_before
        # In Spotify reorder/add insertion position — 0-based index (insert_before)
        insert_before = max(0, target_pos_1based - 1)

        current_idx = find_index(uri)
        n = len(uris)

        # if position > len+1 -> insert at end
        if target_pos_1based > n + (0 if current_idx is not None else 1):
            insert_before = n  # end

        if current_idx is None:
            # not in playlist -> add
            snapshot = sp.add_tracks(playlist_id, [uri], position=insert_before if insert_before <= n else None)
            uris.insert(insert_before if insert_before <= n else n, uri)
            logger.info("insert: %s -> pos %d", uri, (insert_before + 1 if insert_before <= n else n + 1))
        else:
            # already exists: if not in right place — move
            desired_idx = min(insert_before, len(uris))  # 0..n
            if current_idx != desired_idx:
                # In Spotify reorder: range_start=current_idx, insert_before=desired_idx, range_length=1
                snapshot = sp.reorder(playlist_id, range_start=current_idx, insert_before=desired_idx, range_length=1, snapshot_id=snapshot)
                # locally update list
                moved_uri = uris.pop(current_idx)
                if desired_idx > current_idx:
                    desired_idx -= 1  # after pop indices shifted
                uris.insert(desired_idx, moved_uri)
                logger.info("move: %s %d -> %d", uri, current_idx + 1, desired_idx + 1)
            else:
                logger.info("skip: %s already at position %d", uri, current_idx + 1)

# ---------- CLI Commands ----------



def cmd_pin_list(args):
    # Determine which playlist to use
    if args.playlist:
        # Use specific playlist name
        playlist_name = args.playlist
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")
        if not playlist_id:
            die(f"Playlist '{playlist_name}' not found. Create it first with 'playlist-create'.")
    else:
        # Use default playlist
        registry = load_playlists_registry()
        if not registry["default"]:
            die("No default playlist set. Create one with 'playlist-create' or specify --playlist.")
        playlist_name = registry["default"]
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")
    
    pins = sorted(config.get("pins", []), key=lambda p: int(p["position"]))
    if not pins:
        print(f"No pins for playlist '{playlist_name}'.")
        return
    
    print(f"Pins for playlist: {config.get('playlist_display_name', playlist_name)}")
    print("#  pos  track_name")
    print("-" * 80)
    
    for i, p in enumerate(pins, 1):
        position = int(p['position'])
        track_name = p.get('track_name', 'Unknown Track')
        
        # Truncate long names
        if len(track_name) > 70:
            track_name = track_name[:67] + "..."
        
        print(f"{i:2d} {position:4d} {track_name}")

def cmd_pin_add(args):
    # Determine which playlist to use
    if args.playlist:
        playlist_name = args.playlist
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")
        if not playlist_id:
            die(f"Playlist '{playlist_name}' not found. Create it first with 'playlist-create'.")
    else:
        registry = load_playlists_registry()
        if not registry["default"]:
            die("No default playlist set. Create one with 'playlist-create' or specify --playlist.")
        playlist_name = registry["default"]
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")

    track = args.track or input("Paste track link/ID: ").strip()
    uri = normalize_track_id(track)
    pos = args.position or int(input("Position (1-based): ").strip())

    # check for conflicts
    pins = config.get("pins", [])
    conflict = next((p for p in pins if int(p["position"]) == int(pos) and normalize_track_id(p["track_id"]) != uri), None)
    if conflict:
        print(f"⚠️ Position {pos} already pinned: {normalize_track_id(conflict['track_id'])}")
        if not args.confirm:
            ans = input("Replace? [y/N]: ").lower().strip()
            if ans != "y":
                print("Cancelled.")
                return
        # replace mode: remove previous PIN at this position
        pins = [p for p in pins if int(p["position"]) != int(pos)]

    # Get track name from Spotify
    sp = SpotifyClient()
    track_spotify_id = uri.split(":")[-1]
    try:
        resp = sp._req("GET", f"/tracks/{track_spotify_id}")
        if resp.status_code == 200:
            track_data = resp.json()
            track_name = track_data.get("name", "Unknown")
            artists = ", ".join([artist["name"] for artist in track_data.get("artists", [])])
            full_track_name = f"{track_name} - {artists}" if artists else track_name
        else:
            full_track_name = "Unknown Track"
    except Exception:
        full_track_name = "Unknown Track"

    # if PIN already exists for this track — update position
    existed = next((p for p in pins if normalize_track_id(p["track_id"]) == uri), None)
    if existed:
        existed["position"] = int(pos)
        existed["track_name"] = full_track_name
    else:
        pins.append({"track_id": uri, "position": int(pos), "track_name": full_track_name})

    config["pins"] = pins
    save_playlist_config(playlist_name, config)
    print(f"✅ Pinned: {uri} at position {pos} (playlist {playlist_name})")

def cmd_pin_remove(args):
    # Determine which playlist to use
    if args.playlist:
        playlist_name = args.playlist
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")
        if not playlist_id:
            die(f"Playlist '{playlist_name}' not found. Create it first with 'playlist-create'.")
    else:
        registry = load_playlists_registry()
        if not registry["default"]:
            die("No default playlist set. Create one with 'playlist-create' or specify --playlist.")
        playlist_name = registry["default"]
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")

    track = args.track or input("Paste track link/ID to remove PIN: ").strip()
    uri = normalize_track_id(track)
    pins = config.get("pins", [])
    before = len(pins)
    pins = [p for p in pins if normalize_track_id(p["track_id"]) != uri]
    if len(pins) == before:
        print("PIN for this track not found.")
    else:
        config["pins"] = pins
        save_playlist_config(playlist_name, config)
        print(f"✅ Removed PIN: {uri}")

def cmd_pin_move(args):
    # Determine which playlist to use
    if args.playlist:
        playlist_name = args.playlist
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")
        if not playlist_id:
            die(f"Playlist '{playlist_name}' not found. Create it first with 'playlist-create'.")
    else:
        registry = load_playlists_registry()
        if not registry["default"]:
            die("No default playlist set. Create one with 'playlist-create' or specify --playlist.")
        playlist_name = registry["default"]
        config = load_playlist_config(playlist_name)
        playlist_id = config.get("playlist_id")

    track = args.track or input("Track (link/ID) to move: ").strip()
    uri = normalize_track_id(track)
    pos = args.position or int(input("New position (1-based): ").strip())

    pins = config.get("pins", [])
    pin = next((p for p in pins if normalize_track_id(p["track_id"]) == uri), None)
    if not pin:
        die("This track has no PIN — add it first with `pin add`.")
    
    # position conflict
    conflict = next((p for p in pins if int(p["position"]) == int(pos) and normalize_track_id(p["track_id"]) != uri), None)
    if conflict:
        print(f"⚠️ Position {pos} already pinned: {normalize_track_id(conflict['track_id'])}")
        if not args.confirm:
            ans = input("Replace? [y/N]: ").lower().strip()
            if ans != "y":
                print("Cancelled.")
                return
        pins = [p for p in pins if p is not conflict]

    pin["position"] = int(pos)
    # Ensure track_name is preserved
    if "track_name" not in pin:
        # Get track name from Spotify if missing
        sp = SpotifyClient()
        track_spotify_id = uri.split(":")[-1]
        try:
            resp = sp._req("GET", f"/tracks/{track_spotify_id}")
            if resp.status_code == 200:
                track_data = resp.json()
                track_name = track_data.get("name", "Unknown")
                artists = ", ".join([artist["name"] for artist in track_data.get("artists", [])])
                pin["track_name"] = f"{track_name} - {artists}" if artists else track_name
            else:
                pin["track_name"] = "Unknown Track"
        except Exception:
            pin["track_name"] = "Unknown Track"
    
    config["pins"] = pins
    save_playlist_config(playlist_name, config)
    print(f"✅ Moved PIN: {uri} → position {pos}")

def cmd_sync(args):
    sp = SpotifyClient()
    registry = load_playlists_registry()
    
    if args.playlist:
        # Sync specific playlist
        if args.playlist not in registry["playlists"]:
            die(f"Playlist '{args.playlist}' not found. Create it first with 'playlist-create'.")
        config = load_playlist_config(args.playlist)
        sync_playlist_new(sp, config)
    else:
        # Sync all playlists
        if not registry["playlists"]:
            die("No playlists configured. Create one first with 'playlist-create'.")
        for playlist_name in registry["playlists"]:
            config = load_playlist_config(playlist_name)
            sync_playlist_new(sp, config)

def cmd_playlist_create(args):
    """Create a new playlist configuration."""
    sp = SpotifyClient()
    pls = sp.my_owned_playlists()
    if not pls:
        die("You have no owned playlists available.")
    
    # Show playlists
    print("Your owned playlists:")
    for i, p in enumerate(pls, 1):
        name = p.get("name", "?")
        pid = p.get("id")
        tracks = p.get("tracks", {}).get("total", "?")
        print(f"{i:2d}. {name}  ({tracks} tracks)  id={pid}")
    
    sel = input("Choose playlist number: ").strip()
    idx = int(sel) - 1
    if idx < 0 or idx >= len(pls):
        die("Invalid choice.")
    
    chosen_playlist = pls[idx]
    playlist_id = chosen_playlist["id"]
    playlist_name = chosen_playlist.get("name", "Unknown")
    
    # Create safe filename from playlist name
    safe_name = "".join(c for c in playlist_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name.replace(' ', '_').lower()
    
    # Check if already exists
    registry = load_playlists_registry()
    if safe_name in registry["playlists"]:
        print(f"⚠️ Playlist '{safe_name}' already exists!")
        ans = input("Overwrite? [y/N]: ").lower().strip()
        if ans != "y":
            print("Cancelled.")
            return
    
    # Create playlist config
    config = {
        "timezone": "Europe/Sofia",
        "playlist_name": safe_name,
        "playlist_id": f"spotify:playlist:{playlist_id}",
        "playlist_display_name": playlist_name,
        "pins": []
    }
    save_playlist_config(safe_name, config)
    
    # Update registry
    registry["playlists"][safe_name] = {
        "playlist_id": f"spotify:playlist:{playlist_id}",
        "display_name": playlist_name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Set as default if it's the first one
    if registry["default"] is None:
        registry["default"] = safe_name
        print(f"✅ Set as default playlist.")
    
    save_playlists_registry(registry)
    print(f"✅ Created playlist config: {safe_name}")
    print(f"   Display name: {playlist_name}")
    print(f"   Config file: config_{safe_name}.json")

def cmd_playlist_list(args):
    """List all managed playlists."""
    registry = load_playlists_registry()
    if not registry["playlists"]:
        print("No playlists configured.")
        return
    
    print("Managed playlists:")
    print("-" * 60)
    for name, info in registry["playlists"].items():
        default_marker = " (DEFAULT)" if name == registry["default"] else ""
        print(f"📁 {name}{default_marker}")
        print(f"   Display: {info['display_name']}")
        print(f"   ID: {info['playlist_id']}")
        print(f"   Created: {info['created']}")
        print()

def cmd_playlist_set_default(args):
    """Set default playlist."""
    registry = load_playlists_registry()
    if not registry["playlists"]:
        die("No playlists configured. Create one first with 'playlist-create'.")
    
    print("Available playlists:")
    for i, (name, info) in enumerate(registry["playlists"].items(), 1):
        default_marker = " (CURRENT DEFAULT)" if name == registry["default"] else ""
        print(f"{i:2d}. {name} — {info['display_name']}{default_marker}")
    
    sel = input("Choose playlist number: ").strip()
    idx = int(sel) - 1
    playlist_names = list(registry["playlists"].keys())
    if idx < 0 or idx >= len(playlist_names):
        die("Invalid choice.")
    
    chosen_name = playlist_names[idx]
    registry["default"] = chosen_name
    save_playlists_registry(registry)
    print(f"✅ Set default playlist: {chosen_name}")

def cmd_playlist_delete(args):
    """Delete a playlist configuration."""
    registry = load_playlists_registry()
    if not registry["playlists"]:
        die("No playlists configured.")
    
    print("Available playlists:")
    for i, (name, info) in enumerate(registry["playlists"].items(), 1):
        default_marker = " (DEFAULT)" if name == registry["default"] else ""
        print(f"{i:2d}. {name} — {info['display_name']}{default_marker}")
    
    sel = input("Choose playlist number to delete: ").strip()
    idx = int(sel) - 1
    playlist_names = list(registry["playlists"].keys())
    if idx < 0 or idx >= len(playlist_names):
        die("Invalid choice.")
    
    chosen_name = playlist_names[idx]
    print(f"⚠️ This will delete playlist '{chosen_name}' and its configuration!")
    ans = input("Are you sure? [y/N]: ").lower().strip()
    if ans != "y":
        print("Cancelled.")
        return
    
    # Delete config file
    config_path = get_playlist_config_path(chosen_name)
    if config_path.exists():
        config_path.unlink()
        print(f"✅ Deleted config file: {config_path}")
    
    # Remove from registry
    del registry["playlists"][chosen_name]
    
    # Update default if needed
    if registry["default"] == chosen_name:
        registry["default"] = list(registry["playlists"].keys())[0] if registry["playlists"] else None
        if registry["default"]:
            print(f"✅ Set new default: {registry['default']}")
    
    save_playlists_registry(registry)
    print(f"✅ Deleted playlist: {chosen_name}")

def cmd_select_playlist(args):
    """Select a playlist from your owned playlists to manage."""
    sp = SpotifyClient()
    pls = sp.my_owned_playlists()
    if not pls:
        die("You have no owned playlists available.")
    
    # Show playlists
    print("Your owned playlists:")
    for i, p in enumerate(pls, 1):
        name = p.get("name", "?")
        pid = p.get("id")
        tracks = p.get("tracks", {}).get("total", "?")
        print(f"{i:2d}. {name}  ({tracks} tracks)  id={pid}")
    
    sel = input("Choose playlist number: ").strip()
    idx = int(sel) - 1
    if idx < 0 or idx >= len(pls):
        die("Invalid choice.")
    
    chosen_playlist = pls[idx]
    playlist_id = chosen_playlist["id"]
    playlist_name = chosen_playlist.get("name", "Unknown")
    
    # Create safe filename from playlist name
    safe_name = "".join(c for c in playlist_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_name = safe_name.replace(' ', '_').lower()
    
    # Check if already exists
    registry = load_playlists_registry()
    if safe_name in registry["playlists"]:
        print(f"⚠️ Playlist '{safe_name}' already exists!")
        ans = input("Overwrite? [y/N]: ").lower().strip()
        if ans != "y":
            print("Cancelled.")
            return
    
    # Create playlist config
    config = {
        "timezone": "Europe/Sofia",
        "playlist_name": safe_name,
        "playlist_id": f"spotify:playlist:{playlist_id}",
        "playlist_display_name": playlist_name,
        "pins": []
    }
    save_playlist_config(safe_name, config)
    
    # Update registry
    registry["playlists"][safe_name] = {
        "playlist_id": f"spotify:playlist:{playlist_id}",
        "display_name": playlist_name,
        "created": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Set as default if it's the first one
    if registry["default"] is None:
        registry["default"] = safe_name
        print(f"✅ Set as default playlist.")
    
    save_playlists_registry(registry)
    print(f"✅ Selected playlist: {safe_name}")
    print(f"   Display name: {playlist_name}")
    print(f"   Config file: config_{safe_name}.json")

def cmd_track_select(args):
    """Interactive track selection for pinning."""
    if track_select is None:
        die("Track selection module not available. Make sure track_select.py is in the same directory.")
    
    # Determine which playlist to use
    if args.playlist:
        playlist_name = args.playlist
    else:
        # Use default playlist
        registry = load_playlists_registry()
        if not registry["default"]:
            die("No default playlist set. Create one with 'playlist-create' or specify --playlist.")
        playlist_name = registry["default"]
    
    # Check if playlist exists
    config = load_playlist_config(playlist_name)
    if not config.get("playlist_id"):
        die(f"Playlist '{playlist_name}' not found. Create it first with 'playlist-create'.")
    
    # Start interactive track selection
    track_select(playlist_name)

# ---------- main ----------

def build_parser():
    p = argparse.ArgumentParser(description="Spotify playlist pins")
    sub = p.add_subparsers(dest="cmd", required=True)


    sp_list = sub.add_parser("pin-list", help="Show pins for playlist")
    sp_list.add_argument("--playlist", help="Playlist name (if not set — default)")
    sp_list.set_defaults(func=cmd_pin_list)

    sp_add = sub.add_parser("pin-add", help="Add/update PIN")
    sp_add.add_argument("--playlist", help="Playlist name (if not set — default)")
    sp_add.add_argument("--track", help="Track ID/URL")
    sp_add.add_argument("--position", type=int, help="Position 1-based")
    sp_add.add_argument("--confirm", action="store_true", help="Don't ask questions (yes)")
    sp_add.set_defaults(func=cmd_pin_add)

    sp_rm = sub.add_parser("pin-remove", help="Remove PIN from track")
    sp_rm.add_argument("--playlist", help="Playlist name (if not set — default)")
    sp_rm.add_argument("--track", help="Track ID/URL")
    sp_rm.set_defaults(func=cmd_pin_remove)

    sp_mv = sub.add_parser("pin-move", help="Move PIN to different position")
    sp_mv.add_argument("--playlist", help="Playlist name (if not set — default)")
    sp_mv.add_argument("--track", help="Track ID/URL")
    sp_mv.add_argument("--position", type=int, help="New position 1-based")
    sp_mv.add_argument("--confirm", action="store_true", help="Don't ask questions (yes)")
    sp_mv.set_defaults(func=cmd_pin_move)

    sp_sync = sub.add_parser("sync", help="Apply pins to playlists")
    sp_sync.add_argument("--playlist", help="Playlist name (if not set — all managed playlists)")
    sp_sync.set_defaults(func=cmd_sync)

    # Playlist management commands
    sp_create = sub.add_parser("playlist-create", help="Create new playlist configuration")
    sp_create.set_defaults(func=cmd_playlist_create)

    sp_select = sub.add_parser("select-playlist", help="Select a playlist from your owned playlists")
    sp_select.set_defaults(func=cmd_select_playlist)

    sp_list = sub.add_parser("playlist-list", help="List all managed playlists")
    sp_list.set_defaults(func=cmd_playlist_list)

    sp_default = sub.add_parser("playlist-set-default", help="Set default playlist")
    sp_default.set_defaults(func=cmd_playlist_set_default)

    sp_delete = sub.add_parser("playlist-delete", help="Delete playlist configuration")
    sp_delete.set_defaults(func=cmd_playlist_delete)

    # Track selection command
    sp_track_select = sub.add_parser("track-select", help="Interactive track selection for pinning")
    sp_track_select.add_argument("--playlist", help="Playlist name (if not set — default)")
    sp_track_select.set_defaults(func=cmd_track_select)

    return p

if __name__ == "__main__":
    try:
        parser = build_parser()
        args = parser.parse_args()
        args.func(args)
    except KeyboardInterrupt:
        print("\nStopped.")
