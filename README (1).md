# GWR Signal Box — Ambient Electronics Project

## Project Overview

Gauge 0 scale 3D-printed GWR-style signal box with integrated ambient lighting and sound. Runs autonomously from mains power. No train interaction. Atmospheric and self-contained.

---

## Hardware

### Core Platform
- **Raspberry Pi 4** — headless Linux, Python, WiFi, 3.5mm audio jack
- **MicroSD card** — Raspberry Pi OS + audio files + app

### Audio
- **PAM8403 amplifier module** — 2×3W stereo Class D, 5V powered
- **Speakers (×2)** — stereo
- Audio routed via `~/.asoundrc` to ALSA card 0 (bcm2835 headphone jack)

### Lighting
- **4-channel PWM MOSFET board** (optocoupler isolated, direct GPIO PWM)
- All 4 channels wired and functioning:

| Channel | GPIO | Pin | Function |
|---------|------|-----|----------|
| CH1 | GPIO12 | Pin 32 | Upper ceiling lamp |
| CH2 | GPIO19 | Pin 35 | Lower ceiling lamp |
| CH3 | GPIO16 | Pin 36 | Stove / coal fire |
| CH4 | GPIO20 | Pin 38 | Exterior lamp |

### Controls
- **iPhone control page** at `http://signalbox.local:5001/control` — no physical buttons needed
- Day/Night switching, LED on/off/brightness/flicker, audio transport, scene strip — all via UI

---

## Software

### Stack
- Python 3 / Flask — serves editor + control page on port 5001
- `pygame` — audio playback (44100 Hz, buffer 2048)
- `RPi.GPIO` — software PWM at 200 Hz for LED control
- `pydub` + `audioop-lts` — audio processing

### Key Files
| File | Purpose |
|------|---------|
| `editor/app.py` | Main Flask app — audio engine, LED control, GPIO, all API routes |
| `editor/templates/index.html` | Mac atmosphere editor UI |
| `editor/templates/control.html` | iPhone control page (iOS PWA) |
| `config.json` | Single source of truth — atmospheres, scenes, sounds, LED states |
| `sounds/` | All audio files |
| `sync.sh` | Push Mac → Pi + restart Flask |

### Boot Behaviour
- `signalbox.service` systemd unit — enabled, starts Flask on boot after network is up
- Restarts automatically on crash (5s delay)
- Plays `[SF]Pi is up.mp3` at 30% volume 2 seconds after startup

### Development Workflow
1. Edit on Mac at `http://localhost:5001/`
2. Hit **Save** — auto-syncs editor + config + sounds to Pi via `sync.sh` and restarts Flask
3. Or run `./sync.sh` from the project root manually

---

## Access

| URL | What |
|-----|------|
| `http://signalbox.local:5001/` | Atmosphere editor (Mac) |
| `http://signalbox.local:5001/control` | iPhone control page |

Add `/control` to iPhone home screen (Share → Add to Home Screen) for full-screen PWA.

---

## Status

- [x] Hardware assembled and wired
- [x] OS flashed, SSH and WiFi configured
- [x] All 4 LED channels working (PWM flicker on stove)
- [x] Audio working via 3.5mm jack
- [x] Flask app auto-starts on boot
- [x] Atmosphere editor (Mac)
- [x] iPhone control page (iOS PWA)
- [x] Day/Night atmospheres with per-channel LED states
- [x] Ambient loops + randomised scenes
- [x] Mac → Pi auto-sync on save
- [x] Stove fire sound loops while stove LED is on
- [x] Startup chime on boot
