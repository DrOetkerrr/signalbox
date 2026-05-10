#!/bin/bash
# Push editor code to Pi. Run from anywhere inside the Signalbox project.
set -e

PI="signalbox@signalbox.local"
PI_DIR="/home/signalbox/signalbox/editor"
LOCAL_DIR="$(cd "$(dirname "$0")/editor" && pwd)"

echo "→ syncing $LOCAL_DIR → $PI:$PI_DIR"

sshpass -p signalbox rsync -av --checksum \
  -e "ssh -o StrictHostKeyChecking=no" \
  --exclude='*.pyc' --exclude='__pycache__' \
  "$LOCAL_DIR/" "$PI:$PI_DIR/"

echo "→ syncing config.json"
sshpass -p signalbox rsync -av --checksum \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$(dirname "$LOCAL_DIR")/config.json" "$PI:/home/signalbox/signalbox/config.json"

echo "→ syncing sounds"
sshpass -p signalbox rsync -av --checksum \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$(dirname "$LOCAL_DIR")/sounds/" "$PI:/home/signalbox/signalbox/sounds/"

echo "→ restarting Flask"
sshpass -p signalbox ssh -o StrictHostKeyChecking=no "$PI" \
  "echo signalbox | sudo -S systemctl restart signalbox"

echo "✓ done — http://signalbox.local:5001/control"
