#!/bin/bash
# One-shot boot script v2: bring usb0 up independently of NetworkManager.
# Installs a tiny systemd service that sets a fixed link-local address on usb0
# at every boot, and tells NetworkManager to leave usb0 alone.
set +e
cat > /etc/systemd/system/usb0-gadget.service <<'UNIT'
[Unit]
Description=USB gadget interface usb0 with fixed link-local address
After=systemd-modules-load.service
Wants=systemd-modules-load.service
Before=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for i in $(seq 1 30); do [ -d /sys/class/net/usb0 ] && break; sleep 1; done; ip link set usb0 up; ip addr replace 169.254.11.2/16 dev usb0; ip addr replace 192.168.2.2/24 dev usb0; ip -6 addr show dev usb0 >/dev/null'

[Install]
WantedBy=multi-user.target
UNIT
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/90-usb0-unmanaged.conf <<'NM'
[keyfile]
unmanaged-devices=interface-name:usb0
NM
rm -f /etc/NetworkManager/system-connections/usb0-gadget.nmconnection
ln -sf /etc/systemd/system/usb0-gadget.service /etc/systemd/system/multi-user.target.wants/usb0-gadget.service


# ── Wi-Fi profile (recreated from the boot partition's network-config) ──────
rfkill unblock wifi 2>/dev/null || true
WIFI=/etc/NetworkManager/system-connections/JDM43.nmconnection
cat > "$WIFI" <<'WF'
[connection]
id=JDM43
type=wifi
interface-name=wlan0
autoconnect=true
autoconnect-retries=0
autoconnect-priority=20

[wifi]
mode=infrastructure
ssid=JDM43
powersave=2

[wifi-security]
key-mgmt=wpa-psk
psk=<64-hex PSK from bootfs network-config>

[ipv4]
method=auto

[ipv6]
method=auto
addr-gen-mode=default
WF
chmod 600 "$WIFI"

D=/boot/firmware/diag.txt
{
  echo "== firstrun-v3 $(date) =="
  uname -a
  echo "-- /sys/class/net:"; ls /sys/class/net
  echo "-- lsmod dwc2/g_ether/libcomposite:"; lsmod 2>/dev/null | grep -E "dwc2|g_ether|libcomposite|u_ether"
  echo "-- NM connections:"; ls -la /etc/NetworkManager/system-connections
  for f in /etc/NetworkManager/system-connections/*; do echo "--- $f"; grep -v -i "psk\|password" "$f"; done
  echo "-- NM conf.d:"; ls -la /etc/NetworkManager/conf.d; cat /etc/NetworkManager/conf.d/* 2>/dev/null
  echo "-- gadget-related units:"; ls /etc/systemd/system/*.wants/ 2>/dev/null | grep -i "gadget\|usb"; ls /usr/lib/systemd/system 2>/dev/null | grep -i "gadget\|rpi-usb"
  echo "-- rfkill:"; rfkill list 2>&1
  echo "-- NetworkManager.conf:"; cat /etc/NetworkManager/NetworkManager.conf 2>/dev/null
  echo "-- /usr/lib/NetworkManager/conf.d:"; cat /usr/lib/NetworkManager/conf.d/* 2>/dev/null
  echo "-- cloud-init net rendering:"; ls -la /var/lib/cloud/instance/ 2>/dev/null; cat /var/lib/cloud/instance/network-config* 2>/dev/null | grep -v -i "password"
  echo "-- wlan0 present:"; ls -d /sys/class/net/wlan0 2>&1
  echo "-- hostname: $(cat /etc/hostname)"
  echo "-- signalbox.service:"; cat /etc/systemd/system/signalbox.service 2>/dev/null
  echo "-- previous boot NM log (if persistent journal):"; journalctl -D /var/log/journal -b -1 -u NetworkManager --no-pager 2>/dev/null | tail -40
} > "$D" 2>&1

for C in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
  [ -f "$C" ] && sed -i 's| systemd\.run[^ ]*||g; s| systemd\.unit=kernel-command-line\.target||g' "$C"
done
rm -f /boot/firmware/firstrun.sh /boot/firstrun.sh
sync
exit 0
