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
| Raspberry Pi Zero W (main) | In house | WiFi, no audio jack — audio via GPIO PWM, primary controller |
| Raspberry Pi Pico 2W (backup) | In transit | Microcontroller — backup or spare |
| MicroSD card | In house | OS + audio files |
| MicroSD card mount | In house | |

### Power
| Item | Status | Notes |
|---|---|---|
| 5V USB power supply | In house | Primary power source |
| PSU chassis mount | In house | Physical mounting in model |
| 5V–12V boost converter PCB | In house | **Not needed** — LEDs are 5V, spare/unused |

### Audio
| Item | Status | Notes |
|---|---|---|
| PAM8403 amplifier module | In house | 2×3W stereo Class D, 5V powered |
| Speakers (×2) | In house | Stereo confirmed (PAM8403 is stereo) |

### Lighting
| Item | Status | Notes |
|---|---|---|
| MOSFET 4-channel PWM board | In house | Direct PWM (not I2C) — pin layout confirmed |
| Warm white LEDs | ⚠️ confirm | 5V, 3mm/5mm SMD, count TBD |

### Controls
| Item | Status | Notes |
|---|---|---|
| SPDT toggle switch ×2 | ~~Not needed~~ | Day/night and all controls handled via iPhone control page UI |

### Development / Connectivity
| Item | Status | Notes |
|---|---|---|
| Micro USB data cable | In the mail | Required for SSH / OTG access |
| Micro USB to monitor cable | In the mail | Direct display connection |
| USB keyboard | In the mail | Direct Pi input |
| Female-to-female Dupont wires | ⚠️ confirm | |
| 2-pin screw terminal blocks ×5 | ⚠️ confirm | |

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
⚠️ **Open question**: define exact brightness levels and flicker intensity per mode.

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

### Single Python boot script — responsibilities:
1. Loop ambient audio continuously
2. PWM lighting — steady warm glow (CH1)
3. PWM flicker pattern (CH2)
4. Serve Flask editor + iPhone control page
5. Switch between day/night profiles via control page UI

### Libraries (provisional)
- `pygame` or `simpleaudio` — audio
- `RPi.GPIO` or `gpiozero` — GPIO / PWM

### Boot behaviour
- Script auto-starts on boot via systemd service
- WiFi + SSH for development access (once connected)

---

## Open Questions

- [x] Main controller: Pi Zero W (no audio jack — audio via GPIO PWM → PAM8403) — Pico 2W is backup
- [x] Stereo: 2 speakers via PAM8403 (in house)
- [x] LEDs are 5V — 5V–12V booster not needed
- [x] Audio model: ambient loops + randomised scenes, one scene at a time, atmosphere-specific
- [x] Per-event params (volume, pan, filter, fade in/out) — NOT per sound globally
- [x] Day/Night switching: via iPhone control page UI — no physical switch needed
- [ ] Day vs night: which loops play in each? Define scenes for each atmosphere.
- [ ] Day vs night: exact LED brightness % and flicker settings?
- [x] CH4 = exterior lamp (outside door / platform) — all 4 channels assigned

---

## Out of Scope (for now)
- Train interaction / DCC integration
- Remote control beyond SSH
- Any display output
