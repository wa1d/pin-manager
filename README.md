# Spotify Playlist Manager

A Python tool for managing fixed track positions (pins) in Spotify playlists with automated syncing.

## Features

- **Pin Management**: Add, remove, move, and list pinned tracks in playlists
- **Multi-Playlist Support**: Manage multiple playlists with separate configurations
- **Automated Syncing**: Daily cron job to keep playlists in sync
- **Duplicate Removal**: Automatically removes duplicate tracks
- **Server Deployment**: Ready for Ubuntu 22.04 server deployment

## Quick Start

### 1. Setup Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Set redirect URI to `http://localhost:8888/callback`
4. Note your Client ID and Client Secret

### 2. Get Refresh Token

```bash
python get_refresh_token.py
```

Follow the prompts to get your refresh token.

### 3. Set Environment Variables

```bash
# Windows PowerShell
$env:SPOTIFY_CLIENT_ID="your_client_id"
$env:SPOTIFY_CLIENT_SECRET="your_client_secret"
$env:SPOTIFY_REFRESH_TOKEN="your_refresh_token"

# Linux/Mac
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export SPOTIFY_REFRESH_TOKEN="your_refresh_token"
```

### 4. Create Playlist Configuration

```bash
python pin.py playlist-create
```

### 5. Add Pins

```bash
python pin.py pin-add --track "spotify:track:4aatgHBRBnAL1C3A4RL9SU" --position 3
```

### 6. Sync Playlist

```bash
python pin.py sync
```

## Commands

### Pin Management
- `pin-list` - Show all pins for a playlist
- `pin-add` - Add a new pin
- `pin-remove` - Remove a pin
- `pin-move` - Move a pin to a different position

### Playlist Management
- `playlist-create` - Create new playlist configuration
- `playlist-list` - List all managed playlists
- `playlist-set-default` - Set default playlist
- `playlist-delete` - Delete playlist configuration

### Operations
- `sync` - Apply pins to playlists
- `export-csv` - Export playlist tracks to CSV format
- `sort-pins` - Sort pins by position in playlist configuration

## Examples

```bash
# List pins for default playlist
python pin.py pin-list

# Add pin to specific playlist
python pin.py pin-add --playlist "my_playlist" --track "spotify:track:4aatgHBRBnAL1C3A4RL9SU" --position 5

# Sync all playlists
python pin.py sync

# Sync specific playlist
python pin.py sync --playlist "my_playlist"

# Export playlist to CSV
python pin.py export-csv --playlist "my_playlist"

# Export with custom output file
python pin.py export-csv --playlist "my_playlist" --output "my_export.csv"

# Sort pins by position for default playlist
python pin.py sort-pins

# Sort pins for specific playlist
python pin.py sort-pins --playlist "my_playlist"

# Sort pins for all managed playlists
python pin.py sort-pins --all
```

## Server Deployment

For automated syncing on Ubuntu 22.04, see [DEPLOYMENT.md](DEPLOYMENT.md).

## Configuration Files

- `playlists.json` - Registry of managed playlists
- `config_*.json` - Individual playlist configurations
- `.env` - Environment variables (on server)

## Requirements

- Python 3.7+
- `requests` library
- Spotify Developer App credentials

## License

MIT License
