#!/bin/bash
# Push editor code to Pi. Run from anywhere inside the Signalbox project.
set -e

# Reach the Pi over Wi-Fi by name, or over the USB-C gadget link as fallback.
PI_HOST="${PI_HOST:-}"
if [ -z "$PI_HOST" ]; then
  for h in signalbox.local 192.168.2.2 169.254.11.2; do
    if ping -c 1 -W 1 "$h" >/dev/null 2>&1; then PI_HOST="$h"; break; fi
  done
fi
[ -n "$PI_HOST" ] || { echo "✗ Pi not reachable (Wi-Fi name or USB link). Is it on? Cable in?"; exit 1; }
echo "→ Pi at $PI_HOST"
PI="signalbox@$PI_HOST"
PI_DIR="/home/signalbox/signalbox/editor"
LOCAL_DIR="$(cd "$(dirname "$0")/editor" && pwd)"

echo "→ syncing $LOCAL_DIR → $PI:$PI_DIR"

sshpass -p signalbox rsync -av --checksum \
  -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR" \
  --exclude='*.pyc' --exclude='__pycache__' \
  "$LOCAL_DIR/" "$PI:$PI_DIR/"

echo "→ syncing config.json"
sshpass -p signalbox rsync -av --checksum \
  -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR" \
  "$(dirname "$LOCAL_DIR")/config.json" "$PI:/home/signalbox/signalbox/config.json"

echo "→ syncing panel geometry"
# The phone UI reads design/phone/geometry.json at render time. Without it the Pi
# silently falls back to the old control page, which looks like nothing synced.
sshpass -p signalbox ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR "$PI" \
  "mkdir -p /home/signalbox/signalbox/design/phone"
sshpass -p signalbox rsync -av --checksum \
  -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR" \
  "$(dirname "$LOCAL_DIR")/design/phone/geometry.json" \
  "$PI:/home/signalbox/signalbox/design/phone/geometry.json"

echo "→ syncing sounds"
sshpass -p signalbox rsync -av --checksum \
  -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR" \
  "$(dirname "$LOCAL_DIR")/sounds/" "$PI:/home/signalbox/signalbox/sounds/"

echo "→ restarting Flask"
sshpass -p signalbox ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR "$PI" \
  "echo signalbox | sudo -S systemctl restart signalbox"

echo "✓ done — http://$PI_HOST:5001/control"
