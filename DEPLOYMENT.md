# Spotify Playlist Manager - Deployment Guide

This guide will help you deploy your Spotify Playlist Manager to an Ubuntu 22.04 server with automated syncing via cron jobs.

## Prerequisites

- Ubuntu 22.04 server with root/sudo access
- Git repository (GitHub, GitLab, etc.)
- Spotify Developer App credentials

## Step-by-Step Deployment

### 1. Prepare Your Local Repository

First, initialize Git and push your code to a remote repository:

```bash
# Initialize Git repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: Spotify Playlist Manager"

# Add remote repository
git remote add origin https://github.com/wa1d/pin-manager.git

# Push to remote
git push -u origin main
```

### 2. Server Setup

SSH into your Ubuntu 22.04 server:

```bash
ssh user@your-server-ip
```

### 3. Download and Run Deployment Script

```bash
# Download the deployment script
wget https://raw.githubusercontent.com/wa1d/pin-manager/master/deploy.sh

# Make it executable
chmod +x deploy.sh

# Run the deployment script
sudo ./deploy.sh
```

**Important**: Before running the script, you need to edit it and replace the git clone command with your actual repository URL.

### 4. Configure Environment Variables

After deployment, set up your Spotify credentials:

```bash
# Copy the template
sudo cp /opt/spotify-playlist-manager/.env.template /opt/spotify-playlist-manager/.env

# Edit the environment file
sudo nano /opt/spotify-playlist-manager/.env
```

Add your Spotify credentials:
```
SPOTIFY_CLIENT_ID=your_actual_client_id
SPOTIFY_CLIENT_SECRET=your_actual_client_secret
SPOTIFY_REFRESH_TOKEN=your_actual_refresh_token
```

### 5. Test the Installation

```bash
# Test playlist listing
sudo -u spotify-pins /opt/spotify-playlist-manager/venv/bin/python /opt/spotify-playlist-manager/pin.py playlist-list

# Test manual sync
sudo -u spotify-pins /opt/spotify-playlist-manager/venv/bin/python /opt/spotify-playlist-manager/pin.py sync
```

### 6. Verify Cron Job

Check that the cron job is set up correctly:

```bash
# View cron job
sudo cat /etc/cron.d/spotify-playlist-manager

# Check cron service status
sudo systemctl status cron
```

### 7. Monitor Logs

```bash
# View application logs
sudo tail -f /var/log/spotify-playlist-manager/spotify_pins.log

# View cron logs
sudo tail -f /var/log/spotify-playlist-manager/cron.log

# View system logs
sudo journalctl -u spotify-playlist-manager.service -f
```

## Manual Deployment (Alternative)

If you prefer to deploy manually without the script:

### 1. Install Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git cron
```

### 2. Create Service User

```bash
sudo useradd -r -s /bin/false -d /opt/spotify-playlist-manager spotify-pins
```

### 3. Clone Repository

```bash
sudo mkdir -p /opt/spotify-playlist-manager
sudo git clone https://github.com/wa1d/pin-manager.git /opt/spotify-playlist-manager
```

### 4. Set Up Python Environment

```bash
cd /opt/spotify-playlist-manager
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt
```

### 5. Set Permissions

```bash
sudo chown -R spotify-pins:spotify-pins /opt/spotify-playlist-manager
sudo chmod +x /opt/spotify-playlist-manager/pin.py
```

### 6. Configure Environment

```bash
sudo cp /opt/spotify-playlist-manager/.env.template /opt/spotify-playlist-manager/.env
sudo nano /opt/spotify-playlist-manager/.env
```

### 7. Set Up Cron Job

```bash
sudo crontab -e
```

Add this line:
```
0 22 * * * TZ=Europe/Sofia /opt/spotify-playlist-manager/venv/bin/python /opt/spotify-playlist-manager/pin.py sync >> /var/log/spotify-playlist-manager/cron.log 2>&1
```

## Updating the Application

To update your application:

```bash
# SSH into server
ssh user@your-server-ip

# Navigate to app directory
cd /opt/spotify-playlist-manager

# Pull latest changes
sudo git pull origin main

# Update dependencies if needed
sudo venv/bin/pip install -r requirements.txt

# Restart service if using systemd
sudo systemctl restart spotify-playlist-manager.service
```

## Troubleshooting

### Check Service Status
```bash
sudo systemctl status spotify-playlist-manager.service
```

### View Service Logs
```bash
sudo journalctl -u spotify-playlist-manager.service -f
```

### Test Manual Execution
```bash
sudo -u spotify-pins /opt/spotify-playlist-manager/venv/bin/python /opt/spotify-playlist-manager/pin.py sync
```

### Check Cron Job Execution
```bash
sudo grep CRON /var/log/syslog | grep spotify-playlist-manager
```

### Verify Environment Variables
```bash
sudo -u spotify-pins bash -c 'cd /opt/spotify-playlist-manager && source .env && env | grep SPOTIFY'
```

## Security Notes

- The service runs as a non-privileged user (`spotify-pins`)
- Environment variables are stored in `/opt/spotify-playlist-manager/.env`
- Logs are rotated daily and kept for 30 days
- The application only has access to Spotify playlists (no system-level permissions)

## Cron Schedule

The default cron job runs daily at 22:00 Sofia time. To change the schedule, edit `/etc/cron.d/spotify-playlist-manager`:

```bash
sudo nano /etc/cron.d/spotify-playlist-manager
```

Cron format: `minute hour day month weekday`
- `0 22 * * *` = Daily at 22:00
- `0 */6 * * *` = Every 6 hours
- `0 22 * * 1` = Every Monday at 22:00

## Support

If you encounter issues:

1. Check the logs in `/var/log/spotify-playlist-manager/`
2. Verify your Spotify credentials are correct
3. Ensure your playlists are properly configured
4. Test manual execution before relying on cron

For additional help, check the application logs and ensure all dependencies are properly installed.
