#!/bin/bash
# Deployment script for Spotify Playlist Manager on Ubuntu 22.04

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="spotify-playlist-manager"
APP_DIR="/opt/$APP_NAME"
SERVICE_USER="spotify-pins"
LOG_DIR="/var/log/$APP_NAME"

echo -e "${GREEN}🚀 Starting deployment of Spotify Playlist Manager${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Update system packages
echo -e "${YELLOW}📦 Updating system packages...${NC}"
apt update && apt upgrade -y

# Install required system packages
echo -e "${YELLOW}📦 Installing system dependencies...${NC}"
apt install -y python3 python3-pip python3-venv git cron

# Create service user
echo -e "${YELLOW}👤 Creating service user...${NC}"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$APP_DIR" "$SERVICE_USER"
    echo -e "${GREEN}✅ Created user: $SERVICE_USER${NC}"
else
    echo -e "${YELLOW}⚠️ User $SERVICE_USER already exists${NC}"
fi

# Create application directory
echo -e "${YELLOW}📁 Creating application directory...${NC}"
mkdir -p "$APP_DIR"
mkdir -p "$LOG_DIR"

# Clone or update repository
if [ -d "$APP_DIR/.git" ]; then
    echo -e "${YELLOW}🔄 Updating existing repository...${NC}"
    cd "$APP_DIR"
    git pull origin master
else
    echo -e "${YELLOW}📥 Cloning repository...${NC}"
    git clone https://github.com/wa1d/pin-manager.git "$APP_DIR"
fi

# Set up Python virtual environment
echo -e "${YELLOW}🐍 Setting up Python virtual environment...${NC}"
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Set proper ownership
echo -e "${YELLOW}🔐 Setting file permissions...${NC}"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
chmod +x "$APP_DIR/pin.py"
chmod +x "$APP_DIR/get_refresh_token.py"

# Create environment file template
echo -e "${YELLOW}📝 Creating environment file template...${NC}"
cat > "$APP_DIR/.env.template" << EOF
# Spotify API Credentials
# Get these from https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REFRESH_TOKEN=your_refresh_token_here

# Optional: Custom log path
SPOTIFY_PINS_LOG=$LOG_DIR/spotify_pins.log
EOF

# Create systemd service file
echo -e "${YELLOW}⚙️ Creating systemd service...${NC}"
cat > "/etc/systemd/system/$APP_NAME.service" << EOF
[Unit]
Description=Spotify Playlist Manager
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/pin.py sync
StandardOutput=append:$LOG_DIR/service.log
StandardError=append:$LOG_DIR/service.log

[Install]
WantedBy=multi-user.target
EOF

# Create cron job
echo -e "${YELLOW}⏰ Setting up cron job...${NC}"
cat > "/etc/cron.d/$APP_NAME" << EOF
# Spotify Playlist Manager - Sync every day at 22:00 (Sofia timezone)
0 22 * * * $SERVICE_USER TZ=Europe/Sofia $APP_DIR/venv/bin/python $APP_DIR/pin.py sync >> $LOG_DIR/cron.log 2>&1
EOF

# Reload systemd and enable service
echo -e "${YELLOW}🔄 Reloading systemd...${NC}"
systemctl daemon-reload
systemctl enable "$APP_NAME.service"

# Create log rotation configuration
echo -e "${YELLOW}📋 Setting up log rotation...${NC}"
cat > "/etc/logrotate.d/$APP_NAME" << EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload $APP_NAME.service > /dev/null 2>&1 || true
    endscript
}
EOF

echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo ""
echo -e "${YELLOW}📋 Next steps:${NC}"
echo "1. Copy your Spotify credentials to $APP_DIR/.env:"
echo "   cp $APP_DIR/.env.template $APP_DIR/.env"
echo "   nano $APP_DIR/.env"
echo ""
echo "2. Test the installation:"
echo "   sudo -u $SERVICE_USER $APP_DIR/venv/bin/python $APP_DIR/pin.py playlist-list"
echo ""
echo "3. Run a manual sync to test:"
echo "   sudo -u $SERVICE_USER $APP_DIR/venv/bin/python $APP_DIR/pin.py sync"
echo ""
echo "4. Check logs:"
echo "   tail -f $LOG_DIR/spotify_pins.log"
echo ""
echo -e "${GREEN}🎉 Your Spotify Playlist Manager is now deployed and will sync daily at 22:00 Sofia time!${NC}"
