#!/usr/bin/env bash
# Install and enable the cam_transmitter systemd service.
# Run from the project directory on the Raspberry Pi:
#   bash install_service.sh
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_USER="${SERVICE_USER:-$(whoami)}"
PYTHON="${PYTHON:-$PROJ_DIR/venv/bin/python}"
SERVICE_DST=/etc/systemd/system/cam_transmitter.service

if [[ ! -x "$PYTHON" ]]; then
    echo "ERROR: Python not found at $PYTHON"
    echo "       Create a venv first: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "Installing service with:"
echo "  Project dir : $PROJ_DIR"
echo "  User        : $SERVICE_USER"
echo "  Python      : $PYTHON"
echo ""

sudo tee "$SERVICE_DST" > /dev/null << EOF
[Unit]
Description=V2X CAM Transmitter
After=dev-ttyUSB1.device dev-ttyUSB2.device dev-ttyUSB4.device
Wants=dev-ttyUSB1.device dev-ttyUSB2.device dev-ttyUSB4.device

[Service]
Type=simple
WorkingDirectory=$PROJ_DIR
ExecStart=$PYTHON $PROJ_DIR/MainTx.py
Restart=on-failure
RestartSec=10
KillSignal=SIGINT
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
User=$SERVICE_USER
Group=dialout

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cam_transmitter
sudo systemctl start cam_transmitter

echo ""
echo "Done. Service is enabled and running."
echo "  Follow logs : journalctl -u cam_transmitter -f"
echo "  Status      : sudo systemctl status cam_transmitter"
