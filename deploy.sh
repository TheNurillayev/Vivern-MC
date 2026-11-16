#!/bin/bash
# Vivern MC - Production Linux Server Deployment Script
set -e

echo "=== Deploying Vivern MC to 24/7 Cloud Server ==="

# 1. Update system packages
sudo apt update && sudo apt install -y python3 python3-pip python3-venv ffmpeg git nginx

# 2. Setup project directory
APP_DIR="/opt/vivern-mc"
if [ ! -d "$APP_DIR" ]; then
    sudo mkdir -p $APP_DIR
    sudo chown $USER:$USER $APP_DIR
fi

# 3. Create virtual environment
python3 -m venv $APP_DIR/venv
source $APP_DIR/venv/bin/activate
pip install --upgrade pip
pip install -r $APP_DIR/backend/requirements.txt

# 4. Create systemd service for 24/7 background execution
cat <<EOF | sudo tee /etc/systemd/system/vivern-mc.service
[Unit]
Description=Vivern MC 24/7 Audio Production Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/run_server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 5. Reload and start systemd service
sudo systemctl daemon-reload
sudo systemctl enable vivern-mc
sudo systemctl restart vivern-mc

echo "=== Vivern MC is now running 24/7 as a background system service! ==="
echo "Check status with: sudo systemctl status vivern-mc"
