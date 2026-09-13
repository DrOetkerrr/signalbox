# Signalbox — Progress Log

> Resume here. Check DESIGN_INTENT.md before making decisions.
> Add entries newest-first under the relevant phase.

---

## Current Status

**Phase: Installed and working — hardening the standalone experience**
Last session: 2026-09-13
Next action: optional polish — spoken IP/status at boot, DHCP reservation on the router,
drop the plain-text password from `sync.sh` (key auth is installed now), commit + push.

---

## Phase Checklist

### 1. Design & Planning
- [x] README written
- [x] DESIGN_INTENT.md created
- [x] Open questions resolved

### 2. Hardware
- [x] Pi Zero W (main) — in house, SSH confirmed (192.168.68.55, user: signalbox)
- [x] Pi Zero (backup, no WiFi) — in house
- [x] MicroSD card + mount — in house
- [x] 5V 3A power supply — in house
- [x] PSU chassis mount — in house
- [x] PAM8403 amp — confirmed in house
- [x] Two speakers — in house
- [x] MOSFET 4-channel PWM board — in house
- [ ] Power wiring: sacrificial Micro USB cable → red/black to chassis PSU
- [ ] Audio wiring: GPIO 18 (pin 12) → L, GPIO 13 (pin 33) → R, GND → middle pin on PAM8403
- [ ] RC filter: 150Ω + 10µF per channel (parts in house)
- [ ] Warm white LEDs — confirm
- [ ] Toggle switches ×2 — confirm
- [ ] Dupont wires — confirm
- [ ] Screw terminals — confirm

### 3. OS & Connectivity
- [x] OS flashed (Raspberry Pi OS Lite)
- [x] WiFi connected (JDM43)
- [x] SSH confirmed working
- [x] SSH key installed (passwordless)
- [ ] PWM audio overlay enabled in /boot/firmware/config.txt
- [ ] Python dependencies installed on Pi (pygame, etc.)

### 4. Software — Editor (Mac)
- [x] Flask + pygame scene editor
- [x] Piano roll / score view with colour-coded blocks
- [x] Drag to reposition blocks, click ruler to preview from position
- [x] Per-block: volume, pan, filter (low-pass), reverb (room + wet), offset, duration
- [x] Concurrent sounds on separate channels
- [x] Auto-scan sounds/ folder for new files
- [x] Ambient loop per atmosphere
- [x] Scene interval (min/max) settings
- [x] Config auto-migrated from delay-relative → absolute start times

### 5. Software — Pi Playback Engine
- [ ] Main playback script (signalbox.py)
- [ ] Audio files + config synced to Pi
- [ ] Ambient loop continuous playback
- [ ] Randomised scene scheduling
- [ ] Day/night atmosphere switching via GPIO toggle
- [ ] systemd service for auto-start on boot

### 6. Software — Lighting
- [ ] PWM steady glow (CH1)
- [ ] PWM flicker (CH2)
- [ ] Exterior lamp (CH3)
- [ ] Day/night lighting profiles

### 7. Integration & Install
- [ ] Full integrated test
- [ ] Wiring complete and tidy
- [ ] Installed in signal box model
- [ ] Running autonomously from mains

---

## Session Log

### 2026-09-13
- Problem: Pi boots and chimes but stays silent; the iPhone control-page link is dead.
- Diagnosis: (1) Pi is not on this LAN at all — full /22 scan found nothing on :5001,
  no mDNS. Wi-Fi not joined or joined elsewhere; no way to tell from the box.
  (2) By design nothing played until the phone pressed Play/Simulate — autoplay
  only ran on the Mac dev server.
- Fix (code, tested on Mac with `SIGNALBOX_AUTOPLAY=1`): runtime state persisted to
  `state.json`; boot restores it and resumes loops + scene scheduler after the chime;
  new `GET /api/state`; control page mirrors real server state on load and while polling.
- Verified: fresh boot → plays Day; Night+Stop → restart stays silent on Night;
  Simulate → restart resumes Night automatically.
- Not yet deployed to the Pi (unreachable). Run `./sync.sh` once it is back.
- Noted: repo `signalbox.service` is stale (user `pi`, `/home/pi`) vs `sync.sh`
  (`signalbox`, `/home/signalbox`); `sync.sh` has the password in plain text.
- Mac gotcha: the app preview runner can't read `~/Desktop` (macOS privacy), so the
  dev server was tested from a scratchpad copy.
- Later that day, via SD card + USB-C: found the Pi had NO Wi-Fi profile left (root cause).
  Recreated `JDM43` profile from the PSK on bootfs; enabled USB gadget mode with a fixed
  address (NetworkManager ignores gadget devices, so a systemd unit brings `usb0` up).
  Pi back on Wi-Fi (192.168.68.59) and reachable over USB (192.168.2.2). Deployed the
  autoplay change with `sync.sh`; confirmed the Pi resumes Day by itself after restart.
- Mac: the old launchd agent was crash-looping (missing `~/signalbox-start.sh`, and TCC
  blocks Desktop access anyway). Replaced by `Signalbox Editor.app` (double-click) +
  `tools/make-editor-app.sh`; agent disabled. SSH key installed on the Pi; `ssh signalbox`
  and `ssh signalbox-usb` aliases; `sync.sh` falls back to USB; repo `signalbox.service`
  now matches the Pi.

### 2026-05-02
- Pi Zero W connected via SSH (192.168.68.55), SSH key installed
- Audio output: decided on GPIO PWM (pin 12 L, pin 33 R) + RC filter (150Ω + 10µF per channel)
- Power: decided on sacrificial Micro USB cable wired to chassis PSU
- Editor completely rebuilt: piano roll score view replacing event list
- Data model migrated: events now use absolute `start` times (not relative delays)
- Concurrent sounds: each unique sound gets its own pygame channel
- Added: ruler click to play from position, sound duration + offset + trim window
- Added: reverb (pedalboard) with room size, wet level, peak limiter
- Added: auto-scan of sounds/ folder on config load + ↺ refresh button
- Fixed: sounds/ subdirectory path resolution

### 2026-04-26
- Established project folder structure
- Created DESIGN_INTENT.md and PROGRESS.md
- Attempted Pi SSH over WiFi and USB (OTG gadget mode) — unsuccessful (charge-only cables)
- USB data cable + monitor cable + keyboard ordered, in the mail
- Updated hardware inventory with all components in house
- Open questions logged in DESIGN_INTENT.md

---
