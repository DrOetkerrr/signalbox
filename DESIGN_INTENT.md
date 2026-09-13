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
7. Persist runtime state and resume it on boot (standalone autoplay)

### Libraries
- `pygame` — audio playback (44100 Hz, 16-channel mixer, buffer 2048)
- `RPi.GPIO` — software PWM at 200 Hz
- `pydub` + `audioop-lts` — audio processing (Python 3.13 compatible)
- `Flask` — web server + Jinja2 templates

### Boot behaviour
- `signalbox.service` systemd unit, enabled, `After=network-online.target`
- Auto-restarts on crash (5s delay)
- **Standalone autoplay (2026-09-13):** the Pi needs no phone to make sound.
  Runtime state (`atmosphere`, `playing`, `volume`, `stove_volume`) is persisted
  to `state.json` next to `config.json` on every control-page action. On boot the
  app restores it, plays the chime, and ~6 s later resumes the ambient loops and
  the random scene scheduler for the saved atmosphere. If the last action was
  Stop, it stays silent until told otherwise. A fresh box with no `state.json`
  plays the Day atmosphere.
- Autoplay is on where GPIO is present (the Pi) and off on the Mac dev server;
  override with `SIGNALBOX_AUTOPLAY=1|0`, delay with `SIGNALBOX_AUTOPLAY_DELAY`.
- `/api/state` reports what the box is doing; the control page reads it on load
  so the buttons always mirror reality (boot autoplay, another phone, etc.).
- `state.json` is not synced by `sync.sh` and is git-ignored — it belongs to the box.
- Development: edit on Mac, **Save** writes `config.json` locally; **⇅ Sync** (editor
  top bar) or `./sync.sh` pushes code + config + sounds to the Pi and restarts its app.
  Save alone does NOT reach the Pi.

### Setup identity — "is the Pi up to date?" (2026-09-13)
- Every machine reports `GET /api/version`: `config_id` (sha256 of `config.json`
  without its `meta` block, 8 hex chars), `sounds_id` (sorted filenames + sizes),
  `code_id` (app.py + templates, fixed at start), hostname and role.
- `config.json` carries a `meta` block written on every save: `config_id`, `saved_at`,
  `saved_on` (hostname). The Pi also saves when lamp settings change from the phone, so
  the Pi can legitimately be *ahead* of the Mac — the ids show it either way.
- The Mac editor polls `GET /api/pi/status` (server-side probe of the Pi over Wi-Fi,
  then the USB addresses) and shows a **Pi link LED**: green = connected and identical,
  amber = connected but config/sounds/code differ (tooltip says which and where each was
  saved), red = Pi not reachable. The phone page shows the Pi's own `config_id` in its badge.

### Reaching the Pi (2026-09-13)
- **Wi-Fi (normal):** `signalbox.local`, NetworkManager profile `JDM43` in
  `/etc/NetworkManager/system-connections/` (powersave off, unlimited retries).
  The May 2026 profile had vanished, which is why the box went silent/unreachable.
- **USB-C (maintenance fallback, always available):** the Pi's USB-C port is a USB
  network gadget (`dtoverlay=dwc2,dr_mode=peripheral` + `modules-load=dwc2,g_ether`
  on bootfs). NetworkManager ignores gadget interfaces, so `usb0-gadget.service`
  gives `usb0` fixed addresses: `192.168.2.2` (works with Mac Internet Sharing on)
  and `169.254.11.2` (direct link). SSH aliases on the Mac: `ssh signalbox`,
  `ssh signalbox-usb`. Key-based login installed.
- `sync.sh` tries `signalbox.local`, then the two USB addresses; `PI_HOST=` overrides.
- One-shot changes to the Pi's root filesystem without a screen: drop a script on
  bootfs and add `systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot
  systemd.unit=kernel-command-line.target` to `cmdline.txt` (see `tools/pi-firstrun-usb-wifi.sh`).

### iPhone control app (2026-09-13)
Five swipeable pages at `/control`, built from the Affinity artboard
(`design/phone/geometry.json` holds every measured position; the template reads it).
- Page 0: main panel — atmosphere, transport, master volume, now playing, LED test, reboot.
- Pages 1-4: one per lighting channel, so every light is commanded individually.
  1 Outside = exterior (CH4), 2 Lamp = upper ceiling (CH1), 3 Stove = stove (CH3),
  4 Lantern = lower ceiling (CH2).
- Each lamp page: on/off lever, brightness, flicker speed, flicker depth, fire-sound
  volume (wired on the stove page only), plus a strip showing the other three lamps
  with their own lit/dark indicator art and a live `ON n%` reading.
- Dials read 0 at the 135 deg mark and sweep 270 deg. The master volume interpolates
  between the five printed reference marks instead (its scale is not linear).
- Artwork is raster: 15 layers re-encoded as retina WebP, 1.2 MB in total.
  Live text sits on masks painted over the printed labels. Font is Oswald, bundled.
- The old page is still served at `/control/classic`.

### Starting the editor on the Mac
- Double-click **`Signalbox Editor.app`** in the project folder (or keep it in the Dock).
  It starts the server if needed via `~/signalbox-start.sh` and opens `http://localhost:5001`.
  First run asks for Desktop-folder access once; macOS privacy rules block a plain
  launchd agent from reading the project, which is why the old `com.signalbox.editor`
  agent was crash-looping and is now disabled (`.plist.disabled`).
- Rebuild the app after editing `tools/editor-launcher.applescript` with `tools/make-editor-app.sh`.

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
