# Signalbox — Progress Log

> Resume here. Check DESIGN_INTENT.md before making decisions.
> Add entries newest-first under the relevant phase.

---

## Current Status

**Phase: Editor refinement complete — ready for Pi deployment**
Last session: 2026-05-02
Next action: Deploy playback engine to Pi, wire GPIO day/night toggle, PWM lighting.

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
