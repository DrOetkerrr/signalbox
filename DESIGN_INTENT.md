# Signalbox — Design Intent

> This document is the design authority. All code and wiring decisions are checked against it.
> Update it when progressive insights change the design — don't just change the code.

---

## Project Vision

A Gauge 0 scale, 3D-printed GWR-style signal box with integrated ambient sound and lighting.
Runs autonomously from mains power. No train interaction. Atmospheric and self-contained.

---

## Hardware Inventory

### Compute
| Item | Status | Notes |
|---|---|---|
| Raspberry Pi 4 | ✅ Installed | WiFi + 3.5mm audio jack, primary controller |
| MicroSD card | ✅ Installed | OS + audio files |

### Power
| Item | Status | Notes |
|---|---|---|
| 5V USB power supply | ✅ Installed | Primary power source |
| PSU chassis mount | ✅ Installed | Physical mounting in model |
| 5V–12V boost converter PCB | Not needed | LEDs are 5V — spare/unused |

### Audio
| Item | Status | Notes |
|---|---|---|
| PAM8403 amplifier module | ✅ Installed | 2×3W stereo Class D, 5V powered |
| Speakers (×2) | ✅ Installed | Stereo, routed via ~/.asoundrc to ALSA card 0 |

### Lighting
| Item | Status | Notes |
|---|---|---|
| MOSFET 4-channel PWM board | ✅ Installed | Direct PWM (not I2C) — all 4 channels wired and working |
| Warm white LEDs | ✅ Installed | Wired to all 4 channels |

### Controls
| Item | Status | Notes |
|---|---|---|
| Physical buttons | Not needed | All controls via iPhone control page UI |

---

## Audio Design

### Three-layer model

| Layer | Behaviour |
|---|---|
| **Ambient loops** | Always playing under everything. Background texture (e.g. outdoor ambience, distant sounds). |
| **Scenes** | Scripted sequences of sound events with timing — mini stories. One scene at a time. Trigger randomly within a configurable interval range. Loops continue underneath. |
| **Atmospheres** | Named modes (e.g. Day, Night). Each defines its own ambient loops and pool of eligible scenes. Toggle via GPIO switch SW1. |

### Scene format
A scene is an ordered list of events. Each event: a sound file + a delay from the previous event (with optional randomisation range). Example:

```
Scene: "Morning brew"  [day only]
  trigger: every 15–40 min (random)
  events:
    0s    → footsteps.mp3
    +6s   → door open/close
    +12s  → kettle placed (implied by atmosphere)
    +45s  → kettle whistle
    +4s   → footsteps.mp3
    +3s   → voice: "Having a nice brew, Jimmy! How are ya"
```

### Rules
- Only one scene plays at a time; a new scene will not start until the current one finishes
- Ambient loops always play underneath scenes
- Scenes are atmosphere-specific (day scenes don't play at night and vice versa)
- Randomised intervals prevent repetition feeling mechanical

### Sound files in folder
| File | Type | Notes |
|---|---|---|
| Railway switch lever | Scene / occasional | |
| Natural pool / outdoor ambience | Ambient loop | |
| Walking on wooden floor | Scene event | |
| Airplane flyover | Scene / occasional | |
| Man whistling (other room) | Scene event | |
| Tea kettle whistle | Scene event | |
| Door open/close | Scene event | |
| 1970s telephone ring | Scene / occasional | |
| ElevenLabs voice ×2 (Scottish) | Scene event | dialogue |

---

## Lighting Design

### PWM Channels
| Channel | Config key | Function | Day mode | Night mode |
|---|---|---|---|---|
| CH1 | `ceiling_upper` | Upper floor ceiling lamp | Dim / off | On, warm steady |
| CH2 | `ceiling_lower` | Lower floor ceiling lamp | Dim / off | On, warm steady |
| CH3 | `stove` | Stove / coal fire glow | Off | Slow flicker |
| CH4 | `exterior` | Exterior lamp (door / platform) | Off | On, steady |

### Day / Night Modes
Switched via the Day/Night tabs on the iPhone control page (`/control`). No physical switch needed.
Brightness levels and flicker settings are configured per-channel in the editor and stored in `config.json`.

### MOSFET Board Pin Layout (confirmed from board markings)

**Top row — load output terminals (left → right):**
```
DC+  DC−  OUT1+  OUT1−  OUT2+  OUT2−  OUT3+  OUT3−  OUT4+  OUT4−
```
- `DC+` / `DC−` — 5V supply for the load side (LEDs)
- `OUTn+` — connect to LED anode (via 100Ω resistor)
- `OUTn−` — MOSFET low-side sink; connect to LED cathode

**Bottom row — signal input terminals (left → right):**
```
PWM1  GND1  PWM2  GND2  PWM3  GND3  PWM4  GND4
```
- `PWMn` — PWM signal from Pi GPIO
- `GNDn` — signal ground reference; connect to Pi GND

**This board uses direct GPIO PWM — NOT I2C.**

### Pi GPIO → MOSFET Pin Assignments
| Pi GPIO | Pi Pin | Board terminal | LED channel |
|---|---|---|---|
| GPIO12 | Pin 32 | PWM1 | CH1 — ceiling upper |
| GPIO19 | Pin 35 | PWM2 | CH2 — ceiling lower |
| GPIO16 | Pin 36 | PWM3 | CH3 — stove |
| GPIO20 | Pin 38 | PWM4 | CH4 — exterior |
| GND | Pin 34 (shared) | GND1–GND4 | all channels |

### Audio PWM Pins (do not use for LEDs)
| Pi GPIO | Pi Pin | Function |
|---|---|---|
| GPIO18 | Pin 12 | Audio L → RC filter → PAM8403 L_IN |
| GPIO13 | Pin 33 | Audio R → RC filter → PAM8403 R_IN |

---

## Software Architecture

### Flask app — `editor/app.py`
Single Python process, responsibilities:
1. Serve atmosphere editor (`/`) and iPhone control page (`/control`)
2. Loop ambient audio per atmosphere (pygame channels)
3. PWM LED control — steady and fire-flicker patterns per channel
4. Play stove fire sound (`[SF] fire 3.wav`) on loop while stove LED is on
5. Play startup chime (`[SF]Pi is up.mp3`) at 30% volume on boot
6. Switch between Day/Night atmospheres via API

### Libraries
- `pygame` — audio playback (44100 Hz, 16-channel mixer, buffer 2048)
- `RPi.GPIO` — software PWM at 200 Hz
- `pydub` + `audioop-lts` — audio processing (Python 3.13 compatible)
- `Flask` — web server + Jinja2 templates

### Boot behaviour
- `signalbox.service` systemd unit, enabled, `After=network-online.target`
- Auto-restarts on crash (5s delay)
- Development: edit on Mac, Save button auto-syncs to Pi via `sync.sh`

---

## Open Questions

- [x] Main controller: Raspberry Pi 4 with 3.5mm audio jack
- [x] Stereo: 2 speakers via PAM8403
- [x] LEDs are 5V — 5V–12V booster not needed
- [x] Audio model: ambient loops + randomised scenes, one scene at a time, atmosphere-specific
- [x] Per-event params (volume, pan, filter, fade in/out) — NOT per sound globally
- [x] Day/Night switching: via iPhone control page UI — no physical switch needed
- [x] Day vs night: loops and scenes defined in config.json, editable in atmosphere editor
- [x] Day vs night: LED brightness and flicker settings configured per-channel in editor
- [x] CH4 = exterior lamp (outside door / platform) — all 4 channels assigned and wired

---

## Out of Scope (for now)
- Train interaction / DCC integration
- Remote control beyond SSH
- Any display output
