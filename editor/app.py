import glob
import hashlib
import json
import math
import os
import socket
import urllib.request
import re
import random
import subprocess
import threading
import time
from flask import Flask, render_template, request, jsonify

# ── Audio (optional — disabled on Pi until audio is wired) ───────────────────
try:
    import numpy as np
    import pygame
    from pydub import AudioSegment
    from pydub.effects import low_pass_filter
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
    pygame.mixer.set_num_channels(16)
    _AUDIO_AVAILABLE = True
except Exception as e:
    print(f"[audio] disabled — {e}")
    _AUDIO_AVAILABLE = False

if not _AUDIO_AVAILABLE:
    class _SoundStub:
        def __init__(self, *a, **k): pass
        def get_length(self): return 2.0
    class _ChannelStub:
        def play(self, *a, **k): pass
        def stop(self): pass
        def set_volume(self, *a): pass
        def get_busy(self): return False
        def fadeout(self, ms): pass
    class _MixerStub:
        Sound = _SoundStub
        def Channel(self, i): return _ChannelStub()
        def stop(self): pass
        def pause(self): pass
        def unpause(self): pass
    class _PygameStub:
        mixer = _MixerStub()
    pygame = _PygameStub()

try:
    from pedalboard import Pedalboard, Reverb as PedalReverb
    _REVERB_AVAILABLE = True
except ImportError:
    _REVERB_AVAILABLE = False

# ── GPIO (Pi only) ────────────────────────────────────────────────────────────
try:
    import RPi.GPIO as _GPIO_LIB
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False

PI_URL  = "http://signalbox.local:5001"
MAC_URL = "http://localhost:5001"

# Autoplay on boot: on by default on the Pi (GPIO present), off on the Mac dev
# server. Override either way with SIGNALBOX_AUTOPLAY=1 / 0.
_env_autoplay    = os.environ.get("SIGNALBOX_AUTOPLAY")
_AUTOPLAY        = (_env_autoplay.strip().lower() in ("1", "true", "yes")) if _env_autoplay else _GPIO_AVAILABLE
AUTOPLAY_DELAY_S = float(os.environ.get("SIGNALBOX_AUTOPLAY_DELAY", "6"))  # let the chime finish first
_BOOT_TIME       = time.time()

BASE           = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR     = os.path.join(BASE, "sounds")
CONFIG_PATH    = os.path.join(BASE, "config.json")
FILTER_CACHE   = os.path.join(BASE, ".filter_cache")
CONFIG_BACKUPS = os.path.join(BASE, "_config_backups")
os.makedirs(FILTER_CACHE, exist_ok=True)
os.makedirs(CONFIG_BACKUPS, exist_ok=True)
STATE_PATH     = os.path.join(BASE, "state.json")

# ── Runtime state (persisted across reboots) ──────────────────────────────────
# Written on every user action that changes what the box is doing, read once at
# boot so a standalone Pi resumes exactly where it was left. Default = playing
# the day atmosphere, so a fresh box makes sound without any phone involved.
_STATE_DEFAULTS = {"atmosphere": "day", "playing": True, "volume": 0.5, "stove_volume": 1.0,
                   "stories": {}}
_state_lock = threading.Lock()


def _load_state():
    st = dict(_STATE_DEFAULTS)
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
        if isinstance(data, dict):
            st.update({k: data[k] for k in _STATE_DEFAULTS if k in data})
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[state] unreadable, using defaults — {e}")
    return st


def _save_state(**updates):
    """Merge updates into state.json atomically. Never raises."""
    with _state_lock:
        try:
            st = _load_state()
            st.update(updates)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(st, f, indent=2)
            os.replace(tmp, STATE_PATH)
        except Exception as e:
            print(f"[state] save failed — {e}")


AUDIO_EXTS = {'.wav', '.mp3', '.ogg', '.flac', '.aiff', '.m4a'}

# ── Setup identity ────────────────────────────────────────────────────────────
# Short content fingerprints so Mac and Pi can be compared at a glance:
#   config_id  — sha256 of config.json minus its "meta" block (same content ⇒ same id)
#   sounds_id  — sha256 of the sorted (filename, size) list in sounds/
#   code_id    — sha256 of app.py + templates (fixed at startup; code changes need a restart)
PI_HOSTS = ["signalbox.local", "192.168.2.2", "169.254.11.2"]


def _sha8(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:8]


def config_identity(cfg) -> str:
    body = {k: v for k, v in cfg.items() if k != "meta"}
    return _sha8(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def sounds_identity():
    items = []
    try:
        for f in sorted(os.listdir(SOUNDS_DIR)):
            if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
                items.append((f, os.path.getsize(os.path.join(SOUNDS_DIR, f))))
    except FileNotFoundError:
        pass
    return _sha8(json.dumps(items).encode()), len(items)


def _code_identity() -> str:
    h = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for path in [os.path.abspath(__file__)] + sorted(glob.glob(os.path.join(here, "templates", "*.html"))):
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return h.hexdigest()[:8]


CODE_ID = _code_identity()


def _sound_id_from_filename(filename):
    name = os.path.splitext(filename)[0]
    name = re.sub(r'^\d+__[^_]+__', '', name)
    name = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    return name or os.path.splitext(filename)[0]


def _sync_sounds_dir(cfg):
    """Purge sounds whose files no longer exist; add new files; remove orphaned event refs."""
    if not os.path.isdir(SOUNDS_DIR):
        return
    # Only remove stale entries if the sounds dir has files — guards against
    # wiping the config on a fresh Pi where sounds haven't been copied yet
    sounds_on_disk = [f for f in os.listdir(SOUNDS_DIR)
                      if os.path.splitext(f)[1].lower() in AUDIO_EXTS]
    if not sounds_on_disk:
        return
    # Remove stale sound entries
    for sid in list(cfg.get('sounds', {}).keys()):
        s = cfg['sounds'][sid]
        filename = s.get('file', s) if isinstance(s, dict) else s
        if not os.path.exists(os.path.join(SOUNDS_DIR, filename)) \
                and not os.path.exists(os.path.join(BASE, filename)):
            del cfg['sounds'][sid]
    # Dedup: if multiple IDs point to the same file, keep only the one used in scenes/loops
    used_ids = set()
    for atmo_data in cfg.get('atmospheres', {}).values():
        for loop in atmo_data.get('loops', []):
            used_ids.add(loop.get('sound'))
        for scene in atmo_data.get('scenes', []):
            for evt in scene.get('events', []):
                used_ids.add(evt.get('sound'))
    used_ids.discard(None)
    seen_files: dict = {}
    for sid in sorted(cfg.get('sounds', {}).keys()):
        fname = cfg['sounds'][sid].get('file') if isinstance(cfg['sounds'][sid], dict) else None
        if fname is None:
            continue
        if fname in seen_files:
            loser = seen_files[fname] if sid in used_ids else sid
            winner = sid if sid in used_ids else seen_files[fname]
            seen_files[fname] = winner
            if loser in cfg['sounds'] and loser not in used_ids:
                del cfg['sounds'][loser]
        else:
            seen_files[fname] = sid
    # Add new files not yet in config
    existing_files = {v.get('file') for v in cfg.get('sounds', {}).values()
                      if isinstance(v, dict)}
    for filename in sorted(os.listdir(SOUNDS_DIR)):
        if os.path.splitext(filename)[1].lower() not in AUDIO_EXTS:
            continue
        if filename in existing_files:
            continue
        sound_id = _sound_id_from_filename(filename)
        base_id, n = sound_id, 2
        while sound_id in cfg['sounds']:
            sound_id = f"{base_id}_{n}"; n += 1
        cfg['sounds'][sound_id] = {"file": filename, "volume": 1.0, "pan": 0.0, "filter": 0}
    # Warn about scene events referencing sounds not on disk — but never delete them
    valid = set(cfg['sounds'].keys())
    for atmo_data in cfg.get('atmospheres', {}).values():
        for scene in atmo_data.get('scenes', []):
            for evt in scene.get('events', []):
                if evt.get('sound', '') not in valid:
                    print(f"[sync] WARNING: scene '{scene.get('name', '?')}' references missing sound '{evt.get('sound')}' — kept")
    # Remove loops referencing sounds no longer in cfg['sounds']
    for atmo_data in cfg.get('atmospheres', {}).values():
        atmo_data['loops'] = [l for l in atmo_data.get('loops', []) if l.get('sound', '') in valid]


app = Flask(__name__)

_preview_thread = None
_stop_preview   = threading.Event()
_preview_gen    = 0          # bumped per preview; a superseded thread sees the change and bows out
_preview_state  = {"elapsed": 0.0, "total": 0.0, "scene_id": None, "scene_name": None, "playing": False}

_simulate_thread = None
_stop_simulate   = threading.Event()
_simulate_state  = {"running": False, "atmosphere": None, "mode": "idle",
                    "scene_name": None, "scene_id": None, "next_in": 0.0, "remaining": 0,
                    "story": None, "story_step": None, "story_total": None}

_master_volume   = 0.5
_channel_volumes = {}

_LED_DEFAULTS = {
    "ceiling_upper": {"brightness": 70,  "enabled": False, "flicker": False, "flicker_speed": 1.5, "flicker_depth": 20},
    "ceiling_lower": {"brightness": 70,  "enabled": False, "flicker": False, "flicker_speed": 1.5, "flicker_depth": 20},
    "stove":         {"brightness": 100, "enabled": False, "flicker": True,  "flicker_speed": 4.5, "flicker_depth": 75},
    "exterior":      {"brightness": 60,  "enabled": False, "flicker": False, "flicker_speed": 2.0, "flicker_depth": 25},
}

# ── GPIO LED control ──────────────────────────────────────────────────────────

_LED_PINS = {
    "ceiling_upper": 12,   # GPIO12  Pin 32
    "ceiling_lower": 19,   # GPIO19  Pin 35
    "stove":         16,   # GPIO16  Pin 36
    "exterior":      20,   # GPIO20  Pin 38
}
_LED_PWM_FREQ    = 200    # Hz — software PWM, fine for 5V LEDs
_LED_PWM_OBJS: dict = {}  # channel -> GPIO.PWM instance
_current_atmosphere  = "day"
_led_live_state: dict = {}  # {atmo: {channel: led_cfg}} — in-memory mirror
_led_flicker_thread  = None
_stop_led_flicker    = threading.Event()

_led_test_running = False
_led_test_thread  = None
_stop_led_test    = threading.Event()
_led_test_state   = {"running": False, "step": ""}

_stove_sound_thread = None
_stop_stove_sound   = threading.Event()
STOVE_SOUND_CHANNEL = 10
STOVE_FIRE_SOUNDS   = ["sf_fire_3"]
_stove_sound_volume = 1.0
# True while the atmosphere loops are running. The stove crackle follows this,
# so the fire does not start on its own when the app boots and Stop silences it.
_playback_active    = False


def _refresh_led_state(cfg):
    global _led_live_state
    _led_live_state = {
        atmo_name: dict(atmo.get("leds", {}))
        for atmo_name, atmo in cfg.get("atmospheres", {}).items()
    }


def _init_leds():
    if not _GPIO_AVAILABLE:
        return
    _GPIO_LIB.setmode(_GPIO_LIB.BCM)
    for ch, pin in _LED_PINS.items():
        _GPIO_LIB.setup(pin, _GPIO_LIB.OUT)
        pwm = _GPIO_LIB.PWM(pin, _LED_PWM_FREQ)
        pwm.start(0)
        _LED_PWM_OBJS[ch] = pwm
    print(f"[led] GPIO ready — {len(_LED_PINS)} channels at {_LED_PWM_FREQ} Hz")


def _cleanup_leds():
    _stop_led_flicker.set()
    for pwm in _LED_PWM_OBJS.values():
        try:
            pwm.ChangeDutyCycle(0)
            pwm.stop()
        except Exception:
            pass
    if _GPIO_AVAILABLE:
        try:
            _GPIO_LIB.cleanup()
        except Exception:
            pass


def _flicker_duty(brightness, speed, depth, t):
    lo  = 1.0 - depth / 100.0
    raw = (0.50 * math.sin(t * speed * 6.28318)
         + 0.30 * math.sin(t * speed * 2.71828 * 6.28318)
         + 0.20 * math.sin(t * speed * 4.13169 * 6.28318))
    unit = max(0.0, min(1.0, 0.5 + 0.5 * raw))
    # Asymmetric power curve: at high depth the LED spends more time near the dim
    # floor with quick bright bursts — fire-like. At low depth it stays near-symmetric.
    power = 1.0 + (depth / 100.0) * 0.9
    unit  = unit ** power
    val   = lo + (1.0 - lo) * unit
    return max(0.0, min(100.0, brightness * val))


def _run_led_test():
    global _led_test_running
    _led_test_running = True
    _stop_led_test.clear()
    _led_test_state.update(running=True, step="starting")

    labels = {"ceiling_upper": "Upper", "ceiling_lower": "Lower",
              "stove": "Stove", "exterior": "Outside"}

    def ramp(ch, frm, to, dur=1.5):
        steps = 40
        for i in range(steps + 1):
            if _stop_led_test.is_set():
                return False
            _LED_PWM_OBJS[ch].ChangeDutyCycle(
                max(0.0, min(100.0, frm + (to - frm) * i / steps)))
            _stop_led_test.wait(timeout=dur / steps)
        return not _stop_led_test.is_set()

    def all_off():
        for pwm in _LED_PWM_OBJS.values():
            pwm.ChangeDutyCycle(0)

    try:
        # Each channel one at a time
        for ch in ["ceiling_upper", "ceiling_lower", "stove", "exterior"]:
            if _stop_led_test.is_set():
                break
            _led_test_state["step"] = labels[ch]
            if not ramp(ch, 0, 100, 1.2):
                break
            if _stop_led_test.wait(timeout=0.5):
                break
            if not ramp(ch, 100, 0, 1.2):
                break
            _stop_led_test.wait(timeout=0.3)

        # All on together
        if not _stop_led_test.is_set():
            _led_test_state["step"] = "All on"
            steps = 50
            for i in range(steps + 1):
                if _stop_led_test.is_set():
                    break
                for pwm in _LED_PWM_OBJS.values():
                    pwm.ChangeDutyCycle(100.0 * i / steps)
                _stop_led_test.wait(timeout=2.0 / steps)
            _stop_led_test.wait(timeout=1.5)
            for i in range(steps + 1):
                if _stop_led_test.is_set():
                    break
                for pwm in _LED_PWM_OBJS.values():
                    pwm.ChangeDutyCycle(100.0 * (1 - i / steps))
                _stop_led_test.wait(timeout=2.0 / steps)

        # Stove flicker demo
        if not _stop_led_test.is_set():
            _led_test_state["step"] = "Stove flicker"
            t     = 0.0
            step  = 0.04
            t_end = time.time() + 8.0
            while not _stop_led_test.is_set() and time.time() < t_end:
                lo  = 0.25
                raw = (0.50 * math.sin(t * 4.5 * 6.28318)
                     + 0.30 * math.sin(t * 4.5 * 2.71828 * 6.28318)
                     + 0.20 * math.sin(t * 4.5 * 4.13169 * 6.28318))
                val = lo + (1.0 - lo) * (0.5 + 0.5 * raw)
                _LED_PWM_OBJS["stove"].ChangeDutyCycle(100 * max(lo, min(1.0, val)))
                t += step
                _stop_led_test.wait(timeout=step)
    finally:
        all_off()
        _led_test_running = False
        _led_test_state.update(running=False, step="")


def _led_flicker_loop():
    t = 0.0
    while not _stop_led_flicker.is_set():
        if _led_test_running:
            _stop_led_flicker.wait(timeout=0.1)
            continue
        leds = _led_live_state.get(_current_atmosphere, {})
        for ch, pwm in _LED_PWM_OBJS.items():
            led = leds.get(ch, {})
            if not led.get("enabled", False):
                pwm.ChangeDutyCycle(0)
                continue
            br = float(led.get("brightness", 70))
            if led.get("flicker", False):
                duty = _flicker_duty(
                    br,
                    float(led.get("flicker_speed", 2.0)),
                    float(led.get("flicker_depth", 40)),
                    t,
                )
            else:
                duty = br
            pwm.ChangeDutyCycle(max(0.0, min(100.0, duty)))
        t += 0.05
        _stop_led_flicker.wait(timeout=0.05)


def _stove_sound_loop():
    global _stove_sound_volume
    playing = False
    last_vol = _stove_sound_volume
    ch = pygame.mixer.Channel(STOVE_SOUND_CHANNEL)
    while not _stop_stove_sound.is_set():
        stove = _led_live_state.get(_current_atmosphere, {}).get("stove", {})
        stove_on = (stove.get("enabled", False) and not _led_test_running
                    and _playback_active)
        if stove_on and not playing:
            try:
                cfg = load_config()
                sound_id = random.choice(STOVE_FIRE_SOUNDS)
                fp = sound_file(cfg, sound_id)
                if fp and os.path.exists(fp) and _AUDIO_AVAILABLE:
                    snd = pygame.mixer.Sound(fp)
                    ch.play(snd, loops=-1)
                    ch.set_volume(_stove_sound_volume)
                    last_vol = _stove_sound_volume
                    playing = True
            except Exception as e:
                print(f"[stove sound] {e}")
        elif not stove_on and playing:
            ch.stop()
            playing = False
        elif playing and _stove_sound_volume != last_vol:
            ch.set_volume(_stove_sound_volume)
            last_vol = _stove_sound_volume
        _stop_stove_sound.wait(timeout=0.2)
    ch.stop()


LOOP_CHANNEL_START  = 0
LOOP_CHANNEL_COUNT  = 2
SCENE_CHANNEL_START = 2
SCENE_CHANNEL_COUNT = 8


# ── Config ────────────────────────────────────────────────────────────────────

def _migrate_events(events):
    """Convert old delay-relative events to absolute start times."""
    if not events or all('start' in e for e in events):
        return events
    t = 0.0
    result = []
    for ev in events:
        t += ev.get('delay', 0)
        new_ev = {k: v for k, v in ev.items() if k != 'delay'}
        new_ev['start'] = round(t, 3)
        result.append(new_ev)
    return result


def load_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    for sid, val in list(cfg.get("sounds", {}).items()):
        if isinstance(val, str):
            cfg["sounds"][sid] = {"file": val, "volume": 1.0, "pan": 0.0, "filter": 0}
    for atmo_name, atmo in cfg.get("atmospheres", {}).items():
        for scene in atmo.get("scenes", []):
            scene['events'] = _migrate_events(scene.get('events', []))
        leds = atmo.setdefault("leds", {})
        for ch, defaults in _LED_DEFAULTS.items():
            d = dict(defaults)
            if atmo_name == "night":
                d["enabled"] = True
            leds.setdefault(ch, d)
    _sync_sounds_dir(cfg)
    _refresh_led_state(cfg)
    return cfg


def save_config(cfg):
    # Rolling backup — keep last 20 versions before every write
    if os.path.exists(CONFIG_PATH):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        import shutil
        shutil.copy2(CONFIG_PATH, os.path.join(CONFIG_BACKUPS, f"config_{stamp}.json"))
        backups = sorted(os.listdir(CONFIG_BACKUPS))
        for old in backups[:-20]:
            os.remove(os.path.join(CONFIG_BACKUPS, old))
    cfg["meta"] = {
        "config_id": config_identity(cfg),
        "saved_at":  time.strftime("%Y-%m-%d %H:%M:%S"),
        "saved_on":  socket.gethostname(),
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def sound_file(cfg, sound_id):
    s = cfg["sounds"].get(sound_id)
    if s is None:
        return ""
    filename = s.get("file", "") if isinstance(s, dict) else s
    if not filename or not isinstance(filename, str):
        return ""
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        path = os.path.join(BASE, "sounds", filename)
    return path


def event_params(event):
    return {
        "volume": event.get("volume", 1.0),
        "pan":    event.get("pan",    0.0),
        "filter": event.get("filter", 0),
    }


# ── Audio processing cache ────────────────────────────────────────────────────

def get_processed_path(sound_id, filepath, cutoff_hz, offset_s, duration_s,
                       reverb_room=0.0, reverb_wet=0.0):
    if not _AUDIO_AVAILABLE:
        return filepath
    has_reverb = _REVERB_AVAILABLE and reverb_wet > 0
    if not (cutoff_hz > 0 or offset_s > 0 or duration_s > 0 or has_reverb):
        return filepath
    mtime = int(os.path.getmtime(filepath) * 1000)
    cache_key = (f"{sound_id}_c{int(cutoff_hz)}_o{offset_s}_d{duration_s}"
                 f"_rr{reverb_room}_rw{reverb_wet}_m{mtime}.wav")
    cached = os.path.join(FILTER_CACHE, cache_key)
    if not os.path.exists(cached):
        # Purge any older cached variants for this sound_id
        prefix = f"{sound_id}_c{int(cutoff_hz)}_o{offset_s}_d{duration_s}_rr{reverb_room}_rw{reverb_wet}_m"
        for old in os.listdir(FILTER_CACHE):
            if old.startswith(prefix) and old != os.path.basename(cached):
                try:
                    os.remove(os.path.join(FILTER_CACHE, old))
                except OSError:
                    pass
        seg = AudioSegment.from_file(filepath)
        if offset_s > 0 or duration_s > 0:
            start_ms = int(offset_s * 1000)
            end_ms   = int((offset_s + duration_s) * 1000) if duration_s > 0 else len(seg)
            seg = seg[start_ms:end_ms]
        if cutoff_hz > 0:
            seg = low_pass_filter(seg, cutoff_hz)
        if has_reverb:
            sr      = seg.frame_rate
            samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
            samples /= float(2 ** (seg.sample_width * 8 - 1))
            if seg.channels == 2:
                samples = samples.reshape(-1, 2).T
            board    = Pedalboard([PedalReverb(
                room_size = float(reverb_room),
                wet_level = float(reverb_wet),
                dry_level = 1.0,
                damping   = 0.5,
            )])
            effected = board(samples, sr)
            peak = np.max(np.abs(effected))
            if peak > 0.98:
                effected = effected * (0.98 / peak)
            if seg.channels == 2:
                effected = (effected.T * 32767).astype(np.int16)
            else:
                effected = (effected.flatten() * 32767).astype(np.int16)
            seg = AudioSegment(
                effected.tobytes(),
                frame_rate=sr,
                sample_width=2,
                channels=seg.channels,
            )
        seg.export(cached, format="wav")
    return cached


# ── Pan / volume helpers ──────────────────────────────────────────────────────

def pan_volumes(volume, pan):
    pan = max(-1.0, min(1.0, pan))
    left  = volume * min(1.0, 1.0 - pan)
    right = volume * min(1.0, 1.0 + pan)
    return left, right


def _load_sound_for_event(cfg, sound_id, event, scrub_offset=0.0):
    filepath    = sound_file(cfg, sound_id)
    params      = event_params(event)
    cutoff      = int(params["filter"])
    offset      = float(event.get("offset",      0) or 0) + scrub_offset
    duration    = float(event.get("duration",    0) or 0)
    if scrub_offset > 0 and duration > 0:
        duration = max(0.0, duration - scrub_offset)
    reverb_room = float(event.get("reverb_room", 0) or 0)
    reverb_wet  = float(event.get("reverb_wet",  0) or 0)
    path = get_processed_path(sound_id, filepath, cutoff, offset, duration,
                              reverb_room, reverb_wet)
    return pygame.mixer.Sound(path), params


def _load_sound(cfg, sound_id):
    return pygame.mixer.Sound(sound_file(cfg, sound_id)), {"volume": 1.0, "pan": 0.0, "filter": 0}


def _set_ch_vol(ch_idx, l, r):
    _channel_volumes[ch_idx] = (l, r)
    pygame.mixer.Channel(ch_idx).set_volume(l * _master_volume, r * _master_volume)


def _reapply_master_volume():
    for ch_idx, (l, r) in _channel_volumes.items():
        pygame.mixer.Channel(ch_idx).set_volume(l * _master_volume, r * _master_volume)


def _apply_params(ch_idx, sound, params):
    l, r = pan_volumes(params["volume"], params["pan"])
    _set_ch_vol(ch_idx, l, r)


# ── Loops ─────────────────────────────────────────────────────────────────────

def _start_loops(atmosphere, cfg):
    global _playback_active
    _playback_active = True
    loops = cfg["atmospheres"].get(atmosphere, {}).get("loops", [])
    for i, loop in enumerate(loops[:LOOP_CHANNEL_COUNT]):
        fp = sound_file(cfg, loop["sound"])
        if not fp or not os.path.exists(fp):
            continue
        try:
            ch_idx = LOOP_CHANNEL_START + i
            ch = pygame.mixer.Channel(ch_idx)
            if ch.get_busy():
                continue
            sound, _ = _load_sound(cfg, loop["sound"])
            ch.play(sound, loops=-1)
            l, r = pan_volumes(loop.get("volume", 1.0), 0.0)
            _set_ch_vol(ch_idx, l, r)
        except Exception as e:
            print(f"loop error: {e}")


def _stop_scene_channels(fade_ms=160):
    """Silence whatever scene is sounding. Firing a scene by hand overrides the
    current one rather than layering on top of it."""
    for i in range(SCENE_CHANNEL_COUNT):
        pygame.mixer.Channel(SCENE_CHANNEL_START + i).fadeout(fade_ms)


def _stop_loops():
    global _playback_active
    _playback_active = False
    for i in range(LOOP_CHANNEL_COUNT):
        pygame.mixer.Channel(LOOP_CHANNEL_START + i).stop()


# ── Timeline / durations ──────────────────────────────────────────────────────

def _sound_duration(cfg, sound_id):
    if not _AUDIO_AVAILABLE:
        return 2.0
    fp = sound_file(cfg, sound_id)
    try:
        return pygame.mixer.Sound(fp).get_length() if fp and os.path.exists(fp) else 2.0
    except Exception:
        return 2.0


def _build_timeline(scene, cfg):
    events, positions, total = scene.get("events", []), [], 0.0
    for ev in events:
        t = ev.get("start", 0)
        positions.append({"t": t, "sound": ev.get("sound", "")})
        eff_dur = ev.get("duration") or _sound_duration(cfg, ev["sound"])
        total = max(total, t + eff_dur)
    return positions, total


# ── Storylines ────────────────────────────────────────────────────────────────
# A scene may belong to a named story and carry a step number. Ordered beats are
# guaranteed to play in sequence, while the story as a whole still surfaces at
# random moments: the scheduler shuffles standalone scenes together with one
# token per unfinished story, and drawing that token plays the story's next beat.

STORY_DEFAULTS = {
    # Pacing, as one dial: advance the story roughly every N scenes. The scheduler
    # turns this into a number of story tokens per shuffled round plus a floor, so
    # small values tell the story quickly and large ones stretch it over hours.
    "pace_scenes":     15,
    "min_gap_seconds": 0,      # extra wall-clock spacing, 0 = none
    "on_finish":       "rest", # "rest" = sleep then tell it again, "once" = stop
    "rest_seconds":    3600,
}


def story_pacing(cfg, name, standalone_count):
    """Turn the single 'advance every N scenes' dial into (tokens per shuffled
    round, minimum scenes between beats).

    Tokens set how often the story is offered; the floor stops beats bunching.
    Calibrated against the real scheduler: the delivered gap tracks the dial to
    within roughly a fifth across 2..60, and is always monotonic."""
    n      = max(1, standalone_count)
    pace   = max(1, int(story_settings(cfg, name).get("pace_scenes") or 15))
    tokens = max(1, min(n, -(-n // pace)))                 # ceil(n / pace)
    floor  = max(1, round(pace * (0.5 if tokens > 1 else 0.85)))
    return tokens, floor

# session-local pacing, keyed by story name
_scenes_played   = 0
_story_last_seen = {}          # story -> (scene counter, wall clock) of its last beat


def story_settings(cfg, name):
    s = dict(STORY_DEFAULTS)
    s.update((cfg.get("stories") or {}).get(name, {}))
    return s


def story_beats(cfg, name):
    """Every scene in this story, across all atmospheres, in step order."""
    beats = []
    for atmo_name, atmo in cfg.get("atmospheres", {}).items():
        for scene in atmo.get("scenes", []):
            if scene.get("story") == name:
                beats.append((int(scene.get("story_step", 0)), atmo_name, scene))
    beats.sort(key=lambda b: b[0])
    return beats


def story_names(cfg):
    names = []
    for atmo in cfg.get("atmospheres", {}).values():
        for scene in atmo.get("scenes", []):
            n = scene.get("story")
            if n and n not in names:
                names.append(n)
    return names


def _story_progress():
    return dict(_load_state().get("stories") or {})


def _set_story_progress(name, **fields):
    all_ = _story_progress()
    entry = dict(all_.get(name) or {})
    entry.update(fields)
    all_[name] = entry
    _save_state(stories=all_)


def next_story_beat(cfg, name, atmosphere, progress=None, min_gap=None):
    """The beat this story owes next, or None if it is finished, resting,
    still spacing itself out, or waiting for the other atmosphere."""
    beats = story_beats(cfg, name)
    if not beats:
        return None
    cfgs = story_settings(cfg, name)
    if min_gap is None:
        standalone = sum(1 for a in cfg.get("atmospheres", {}).values()
                         for sc in a.get("scenes", []) if not sc.get("story"))
        _, min_gap = story_pacing(cfg, name, standalone)
    prog = (progress if progress is not None else _story_progress()).get(name) or {}
    step = int(prog.get("step", 0))

    if step >= len(beats):                                   # told in full
        if cfgs["on_finish"] == "once":
            return None
        done_at = prog.get("finished_at") or 0
        if time.time() - done_at < cfgs["rest_seconds"]:
            return None
        step = 0                                             # rested: tell it again

    last_count, last_time = _story_last_seen.get(name, (-10**9, 0.0))
    if _scenes_played - last_count < min_gap:
        return None
    if cfgs["min_gap_seconds"] and time.time() - last_time < cfgs["min_gap_seconds"]:
        return None

    _, beat_atmo, scene = beats[step]
    if beat_atmo != atmosphere:                              # belongs to the other mode
        return None
    return {"name": name, "step": step, "total": len(beats), "scene": scene}


def advance_story(cfg, name, step):
    total = len(story_beats(cfg, name))
    nxt   = step + 1
    fields = {"step": nxt}
    if nxt >= total:
        fields["finished_at"] = time.time()
    _set_story_progress(name, **fields)
    _story_last_seen[name] = (_scenes_played, time.time())


# ── Preview ───────────────────────────────────────────────────────────────────

def _run_preview(scene, atmosphere, cfg, start_at=0.0, gen=0):
    _stop_preview.clear()
    mine = lambda: gen == _preview_gen
    events     = sorted(scene.get("events", []), key=lambda e: e.get("start", 0))
    _, total = _build_timeline(scene, cfg)
    _preview_state.update(elapsed=start_at, total=total, scene_id=scene["id"],
                          scene_name=scene.get("name") or scene["id"], playing=True)
    _start_loops(atmosphere, cfg)

    sound_to_ch = {}
    start_time  = time.time() - start_at
    event_idx   = next((i for i, e in enumerate(events) if e.get("start", 0) >= start_at), len(events))

    if start_at > 0:
        for ev in events:
            ev_start = ev.get("start", 0)
            if ev_start >= start_at:
                break
            sound_id = ev.get("sound", "")
            full_dur = _sound_duration(cfg, sound_id)
            ev_dur   = (ev.get("duration") or full_dur)
            if ev_start + ev_dur <= start_at:
                continue
            if sound_id not in sound_to_ch:
                sound_to_ch[sound_id] = SCENE_CHANNEL_START + (len(sound_to_ch) % SCENE_CHANNEL_COUNT)
            ch_idx = sound_to_ch[sound_id]
            ch     = pygame.mixer.Channel(ch_idx)
            fp     = sound_file(cfg, sound_id)
            if fp and os.path.exists(fp):
                try:
                    scrub = start_at - ev_start
                    sound, params = _load_sound_for_event(cfg, sound_id, ev, scrub_offset=scrub)
                    ch.play(sound)
                    _apply_params(ch_idx, sound, params)
                except Exception as e:
                    print(f"scrub error: {e}")

    while not _stop_preview.is_set() and mine():
        now = time.time() - start_time
        _preview_state["elapsed"] = now

        while event_idx < len(events) and now >= events[event_idx].get("start", 0):
            ev       = events[event_idx]
            sound_id = ev.get("sound", "")
            if sound_id not in sound_to_ch:
                sound_to_ch[sound_id] = SCENE_CHANNEL_START + (len(sound_to_ch) % SCENE_CHANNEL_COUNT)
            ch_idx = sound_to_ch[sound_id]
            ch = pygame.mixer.Channel(ch_idx)
            fp = sound_file(cfg, sound_id)
            if fp and os.path.exists(fp):
                try:
                    sound, params = _load_sound_for_event(cfg, sound_id, ev)
                    fade_in_ms = int(ev.get("fade_in", 0) * 1000)
                    ch.play(sound, fade_ms=fade_in_ms)
                    _apply_params(ch_idx, sound, params)
                    if ev.get("fade_out", 0) > 0:
                        wait = max(0.0, sound.get_length() - ev["fade_out"])
                        def _fo(c=ch, ms=int(ev["fade_out"] * 1000)):
                            if not _stop_preview.is_set():
                                c.fadeout(ms)
                        threading.Timer(wait, _fo).start()
                except Exception as e:
                    print(f"preview error: {e}")
            event_idx += 1

        if now >= total and event_idx >= len(events):
            break
        time.sleep(0.05)

    # Only the current preview may clear the state: a superseded thread that is
    # still winding down would otherwise wipe out the one that replaced it.
    if mine():
        _preview_state.update(elapsed=0.0, playing=False)


# ── Simulate ──────────────────────────────────────────────────────────────────

def _run_simulate(atmosphere, cfg):
    _stop_simulate.clear()
    _simulate_state.update(running=True, atmosphere=atmosphere, mode="starting",
                           scene_name=None, scene_id=None, next_in=0.0, remaining=0)
    _start_loops(atmosphere, cfg)

    global _scenes_played
    queue = []

    while not _stop_simulate.is_set():
        scenes = cfg["atmospheres"].get(atmosphere, {}).get("scenes", [])
        if not scenes:
            _stop_simulate.wait(timeout=5)
            continue

        # Standalone scenes shuffle as before. Each unfinished story joins the
        # shuffle as a single token, so it turns up at an unpredictable moment
        # but always plays its next beat rather than a random one.
        if not queue:
            standalone = [sc for sc in scenes if not sc.get("story")]
            queue = [("scene", sc) for sc in standalone]
            for n in story_names(cfg):
                tokens, _ = story_pacing(cfg, n, len(standalone))
                queue += [("story", n)] * tokens
            random.shuffle(queue)

        kind, item = queue.pop(0)
        story = None
        if kind == "story":
            story = next_story_beat(cfg, item, atmosphere)
            if not story:                 # resting, finished, spacing out, or other atmosphere
                continue
            scene = story["scene"]
        else:
            scene = item

        min_s  = scene.get("min_interval", 900)
        max_s  = scene.get("max_interval", 2400)
        wait_s = random.uniform(min_s, max_s)

        _simulate_state.update(mode="waiting",
                               scene_name=scene.get("name", scene["id"]),
                               scene_id=scene["id"],
                               story=story["name"] if story else None,
                               story_step=(story["step"] + 1) if story else None,
                               story_total=story["total"] if story else None,
                               next_in=round(wait_s, 1),
                               remaining=len(queue))
        deadline = time.time() + wait_s
        while not _stop_simulate.is_set() and time.time() < deadline:
            _simulate_state["next_in"] = round(max(0.0, deadline - time.time()), 1)
            time.sleep(0.2)

        if _stop_simulate.is_set():
            break

        _simulate_state.update(mode="playing", next_in=0.0)
        _run_preview(scene, atmosphere, cfg, start_at=0.0)
        _scenes_played += 1
        if story:
            advance_story(cfg, story["name"], story["step"])

    _simulate_state.update(running=False, mode="idle",
                           scene_name=None, scene_id=None, next_in=0.0)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/backups")
def list_backups():
    files = sorted(os.listdir(CONFIG_BACKUPS), reverse=True)
    return jsonify(files)


@app.route("/api/backups/<filename>", methods=["POST"])
def restore_backup(filename):
    path = os.path.join(CONFIG_BACKUPS, filename)
    if not os.path.exists(path) or not filename.startswith("config_"):
        return jsonify({"error": "not found"}), 404
    import shutil
    save_config(load_config())   # backup current state first
    shutil.copy2(path, CONFIG_PATH)
    return jsonify({"ok": True, "restored": filename})

@app.route("/api/health")
def health():
    cfg = load_config()
    return jsonify({
        "ok": True,
        "audio": _AUDIO_AVAILABLE,
        "gpio": _GPIO_AVAILABLE,
        "sounds": len(cfg.get("sounds", {})),
    })


GEOM_EDITOR = os.path.join(BASE, "design", "editor-geometry.json")
_ed_geom = {"mtime": 0, "data": None}


def editor_geometry():
    try:
        m = os.path.getmtime(GEOM_EDITOR)
        if m != _ed_geom["mtime"]:
            with open(GEOM_EDITOR) as f:
                _ed_geom.update(mtime=m, data=json.load(f))
    except Exception as e:
        print(f"[editor geometry] {e}")
    return _ed_geom["data"]


@app.route("/")
def index_panel():
    """The panel editor. Falls back to the plain one if the layout file is missing."""
    geo = editor_geometry()
    if not geo:
        return index()
    return render_template("ed/index.html", geometry=geo)


@app.route("/classic")
def index():
    peer = MAC_URL if _GPIO_AVAILABLE else PI_URL
    return render_template("index.html", is_pi=_GPIO_AVAILABLE,
                           peer_url=peer, peer_label="Mac" if _GPIO_AVAILABLE else "Pi")


@app.route("/api/config")
def get_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
def post_config():
    save_config(request.get_json())
    return jsonify({"ok": True})


@app.route("/api/sounds")
def get_sounds():
    cfg = load_config()
    return jsonify(cfg["sounds"])


@app.route("/api/sound_durations")
def sound_durations():
    cfg = load_config()
    return jsonify({sid: _sound_duration(cfg, sid) for sid in cfg.get("sounds", {})})


@app.route("/api/scene_durations")
def scene_durations():
    cfg, result = load_config(), {}
    for atmo in cfg.get("atmospheres", {}).values():
        for scene in atmo.get("scenes", []):
            positions, total = _build_timeline(scene, cfg)
            result[scene["id"]] = {"total": total, "events": positions}
    return jsonify(result)


@app.route("/api/preview/<atmosphere>/<scene_id>", methods=["POST"])
def preview_scene(atmosphere, scene_id):
    global _preview_thread, _preview_gen
    cfg   = load_config()
    scene = next((s for s in cfg["atmospheres"].get(atmosphere, {}).get("scenes", [])
                  if s["id"] == scene_id), None)
    if not scene:
        return jsonify({"error": "scene not found"}), 404
    body     = request.get_json(silent=True) or {}
    start_at = max(0.0, float(body.get("start_at", 0)))
    _preview_gen += 1                      # the old thread may be busy loading a sound and outlive the join
    _stop_preview.set()
    if _preview_thread and _preview_thread.is_alive():
        _preview_thread.join(timeout=1)
    _stop_scene_channels()
    _preview_state.update(playing=True, scene_id=scene_id, elapsed=start_at)
    _preview_thread = threading.Thread(target=_run_preview,
                                       args=(scene, atmosphere, cfg, start_at, _preview_gen), daemon=True)
    _preview_thread.start()
    return jsonify({"ok": True})


@app.route("/api/preview/status")
def preview_status():
    return jsonify(_preview_state)


@app.route("/api/debug/mixer")
def debug_mixer():
    # Report every channel, not the first ten: the stove crackle lives on 10 and
    # was invisible here, which made it hard to tell what was actually sounding.
    def role(i):
        if i < LOOP_CHANNEL_START + LOOP_CHANNEL_COUNT:                     return "loop"
        if i < SCENE_CHANNEL_START + SCENE_CHANNEL_COUNT:                   return "scene"
        if i == STOVE_SOUND_CHANNEL:                                        return "stove fire"
        return "spare"
    channels = [{"ch": i, "role": role(i), "busy": pygame.mixer.Channel(i).get_busy(),
                 "vol": _channel_volumes.get(i)}
                for i in range(pygame.mixer.get_num_channels())]
    return jsonify({"initialized": pygame.mixer.get_init(), "channels": channels,
                    "master_vol": _master_volume, "playback_active": _playback_active})


@app.route("/api/preview/stop", methods=["POST"])
def stop_preview():
    _stop_preview.set()
    for i in range(SCENE_CHANNEL_START, SCENE_CHANNEL_START + SCENE_CHANNEL_COUNT):
        pygame.mixer.Channel(i).stop()
    _preview_state.update(elapsed=0.0, playing=False)
    return jsonify({"ok": True})


@app.route("/api/stop_all", methods=["POST"])
def stop_all():
    global _playback_active
    _playback_active = False
    _stop_simulate.set()
    _stop_preview.set()
    pygame.mixer.stop()
    _simulate_state.update(running=False, mode="idle", scene_name=None, scene_id=None, next_in=0.0)
    _preview_state.update(elapsed=0.0, playing=False)
    _save_state(playing=False)
    return jsonify({"ok": True})


@app.route("/api/simulate/<atmosphere>", methods=["POST"])
def start_simulate(atmosphere):
    global _simulate_thread, _current_atmosphere
    cfg = load_config()
    _current_atmosphere = atmosphere
    _save_state(atmosphere=atmosphere, playing=True)
    _stop_simulate.set()
    _stop_preview.set()
    if _simulate_thread and _simulate_thread.is_alive():
        _simulate_thread.join(timeout=1)
    _simulate_thread = threading.Thread(target=_run_simulate,
                                        args=(atmosphere, cfg), daemon=True)
    _simulate_thread.start()
    return jsonify({"ok": True})


@app.route("/api/simulate/stop", methods=["POST"])
def stop_simulate_route():
    global _playback_active
    _playback_active = False
    _stop_simulate.set()
    _stop_preview.set()
    pygame.mixer.stop()
    _simulate_state.update(running=False, mode="idle", scene_name=None, scene_id=None, next_in=0.0)
    _preview_state.update(elapsed=0.0, playing=False)
    _save_state(playing=False)
    return jsonify({"ok": True})


@app.route("/api/simulate/status")
def get_simulate_status():
    return jsonify(_simulate_state)


@app.route("/api/volume", methods=["GET", "POST"])
def master_volume():
    global _master_volume
    if request.method == "POST":
        val = float(request.get_json(silent=True).get("volume", _master_volume))
        _master_volume = max(0.0, min(1.0, val))
        _reapply_master_volume()
        _save_state(volume=_master_volume)
        return jsonify({"ok": True, "volume": _master_volume})
    return jsonify({"volume": _master_volume})


@app.route("/api/transport/play/<atmosphere>", methods=["POST"])
def transport_play(atmosphere):
    global _current_atmosphere
    cfg = load_config()
    _stop_loops()
    _start_loops(atmosphere, cfg)
    _current_atmosphere = atmosphere
    _save_state(atmosphere=atmosphere, playing=True)
    return jsonify({"ok": True})


@app.route("/api/transport/pause", methods=["POST"])
def transport_pause():
    pygame.mixer.pause()
    return jsonify({"ok": True})


@app.route("/api/transport/unpause", methods=["POST"])
def transport_unpause():
    pygame.mixer.unpause()
    return jsonify({"ok": True})


@app.route("/api/play/<sound_id>", methods=["POST"])
def play_sound(sound_id):
    cfg = load_config()
    fp  = sound_file(cfg, sound_id)
    if not os.path.exists(fp):
        return jsonify({"error": "file not found"}), 404
    body = request.get_json(silent=True) or {}
    ev   = {"volume":      body.get("volume",      1.0),
            "pan":         body.get("pan",         0.0),
            "filter":      body.get("filter",      0),
            "offset":      body.get("offset",      0),
            "duration":    body.get("duration",    0),
            "reverb_room": body.get("reverb_room", 0),
            "reverb_wet":  body.get("reverb_wet",  0)}
    try:
        ch_idx = SCENE_CHANNEL_START + SCENE_CHANNEL_COUNT - 1
        pygame.mixer.Channel(ch_idx).stop()
        sound, params = _load_sound_for_event(cfg, sound_id, ev)
        pygame.mixer.Channel(ch_idx).play(sound)
        _apply_params(ch_idx, sound, params)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


GEOMETRY_PATH = os.path.join(BASE, "design", "phone", "geometry.json")
_geometry_cache = {"mtime": 0, "data": None}


def phone_geometry():
    """Panel layout measured from the Affinity artboard. Re-read when it changes."""
    try:
        m = os.path.getmtime(GEOMETRY_PATH)
        if m != _geometry_cache["mtime"]:
            with open(GEOMETRY_PATH) as f:
                _geometry_cache.update(mtime=m, data=json.load(f))
    except Exception as e:
        print(f"[geometry] {e}")
    return _geometry_cache["data"]


@app.route("/control")
def control_phone():
    geo = phone_geometry()
    if not geo:
        return render_template("control.html", is_pi=_GPIO_AVAILABLE,
                               peer_url=(MAC_URL if _GPIO_AVAILABLE else PI_URL) + "/control",
                               peer_label="Mac" if _GPIO_AVAILABLE else "Pi")
    return render_template("phone/control.html", geometry=geo, is_pi=_GPIO_AVAILABLE)


@app.route("/control/classic")
def control():
    peer = MAC_URL + "/control" if _GPIO_AVAILABLE else PI_URL + "/control"
    return render_template("control.html", is_pi=_GPIO_AVAILABLE,
                           peer_url=peer, peer_label="Mac" if _GPIO_AVAILABLE else "Pi")


@app.route("/api/led", methods=["POST"])
def set_led():
    global _led_live_state
    body       = request.get_json(silent=True) or {}
    atmosphere = body.get("atmosphere")
    channel    = body.get("channel")
    led_vals   = body.get("led", {})
    if not atmosphere or channel not in _LED_PINS:
        return jsonify({"error": "bad request"}), 400
    cfg = load_config()
    cfg["atmospheres"].setdefault(atmosphere, {}).setdefault("leds", {})[channel] = led_vals
    save_config(cfg)
    # Mirror change into live state so flicker thread picks it up immediately
    _led_live_state.setdefault(atmosphere, {})[channel] = led_vals
    return jsonify({"ok": True})


@app.route("/api/led/test", methods=["POST"])
def start_led_test():
    global _led_test_thread
    if not _LED_PWM_OBJS:
        return jsonify({"error": "GPIO not available — not running on Pi"}), 503
    _stop_led_test.set()
    if _led_test_thread and _led_test_thread.is_alive():
        _led_test_thread.join(timeout=1)
    _led_test_thread = threading.Thread(target=_run_led_test, daemon=True)
    _led_test_thread.start()
    return jsonify({"ok": True})


@app.route("/api/led/test/stop", methods=["POST"])
def stop_led_test():
    _stop_led_test.set()
    return jsonify({"ok": True})


@app.route("/api/led/test/status")
def led_test_status():
    return jsonify(_led_test_state)


@app.route("/api/reboot", methods=["POST"])
def reboot():
    if not _GPIO_AVAILABLE:
        return jsonify({"error": "Pi only"}), 403
    # The service has no terminal, so sudo can never ask for a password. Check the
    # rule first (tools/pi/sudoers-signalbox) and say so, rather than blinking the
    # lamp at a reboot that silently never happens.
    allowed = subprocess.run(["sudo", "-n", "-l", "/usr/sbin/reboot"],
                             capture_output=True).returncode == 0
    if not allowed:
        return jsonify({"error": "Reboot not permitted: install tools/pi/sudoers-signalbox"}), 500
    threading.Timer(1.0, lambda: subprocess.run(["sudo", "-n", "/usr/sbin/reboot"])).start()
    return jsonify({"ok": True})


@app.route("/api/stove/volume", methods=["GET", "POST"])
def stove_volume():
    global _stove_sound_volume
    if request.method == "POST":
        val = float(request.get_json(silent=True).get("volume", _stove_sound_volume))
        _stove_sound_volume = max(0.0, min(1.0, val))
        _save_state(stove_volume=_stove_sound_volume)
        return jsonify({"ok": True, "volume": _stove_sound_volume})
    return jsonify({"volume": _stove_sound_volume})


@app.route("/api/atmosphere", methods=["POST"])
def set_atmosphere():
    global _current_atmosphere
    body = request.get_json(silent=True) or {}
    atmo = body.get("atmosphere", "day")
    _current_atmosphere = atmo
    _save_state(atmosphere=atmo)
    return jsonify({"ok": True, "atmosphere": atmo})


def setup_identity():
    cfg = load_config()
    sounds_id, n = sounds_identity()
    return {
        "role":         "pi" if _GPIO_AVAILABLE else "mac",
        "host":         socket.gethostname(),
        "config_id":    config_identity(cfg),
        "config_meta":  cfg.get("meta", {}),
        "sounds_id":    sounds_id,
        "sounds_count": n,
        "code_id":      CODE_ID,
    }


@app.route("/api/version")
def get_version():
    """Fingerprint of the setup on THIS machine (config, sounds, code)."""
    return jsonify(setup_identity())


_pi_last_host = None


@app.route("/api/pi/status")
def pi_status():
    """Mac only: is the Pi reachable, and does its setup match ours?"""
    global _pi_last_host
    if _GPIO_AVAILABLE:
        return jsonify({"error": "Mac only"}), 403
    mac = setup_identity()
    hosts = ([_pi_last_host] if _pi_last_host else []) + [h for h in PI_HOSTS if h != _pi_last_host]
    pi, host, err = None, None, None
    for h in hosts:
        try:
            with urllib.request.urlopen(f"http://{h}:5001/api/version", timeout=2) as r:
                pi, host = json.loads(r.read().decode()), h
                break
        except urllib.error.HTTPError as e:
            if e.code == 404:                 # reachable, but running code without /api/version
                pi, host, err = {"config_id": None, "sounds_id": None, "code_id": None}, h, "old code on Pi"
                break
            err = str(e)
        except Exception as e:
            err = str(e)
    _pi_last_host = host
    if not pi:
        return jsonify({"reachable": False, "error": err, "mac": mac, "checked_at": time.strftime("%H:%M:%S")})
    cmp = {k: (pi.get(k) == mac[k]) for k in ("config_id", "sounds_id", "code_id")}
    return jsonify({
        "reachable": True, "host": host, "error": err,
        "pi": pi, "mac": mac,
        "config_in_sync": cmp["config_id"], "sounds_in_sync": cmp["sounds_id"], "code_in_sync": cmp["code_id"],
        "in_sync": all(cmp.values()),
        "checked_at": time.strftime("%H:%M:%S"),
    })


@app.route("/api/scenes/<atmosphere>")
def scenes_for_atmosphere(atmosphere):
    """The scene list the phone's selector drum shows: name, id and length."""
    cfg = load_config()
    out = []
    for sc in cfg["atmospheres"].get(atmosphere, {}).get("scenes", []):
        _, total = _build_timeline(sc, cfg)
        out.append({"id": sc["id"], "name": sc.get("name", sc["id"]),
                    "length": round(total, 1),
                    "story": sc.get("story"), "story_step": sc.get("story_step")})
    return jsonify(out)


@app.route("/api/stories")
def get_stories():
    """Every storyline, its beats in order, where it has got to, and any problems."""
    cfg  = load_config()
    prog = _story_progress()
    out  = []
    for name in story_names(cfg):
        beats  = story_beats(cfg, name)
        steps  = [b[0] for b in beats]
        issues = []
        if len(set(steps)) != len(steps):
            dupes = sorted({x for x in steps if steps.count(x) > 1})
            issues.append(f"duplicate step number(s): {', '.join(map(str, dupes))}")
        if steps and sorted(steps) != list(range(1, len(steps) + 1)):
            issues.append(f"steps are {steps}, expected 1..{len(steps)}")
        entry = prog.get(name) or {}
        at    = int(entry.get("step", 0))
        standalone = sum(1 for a in cfg.get("atmospheres", {}).values()
                         for sc in a.get("scenes", []) if not sc.get("story"))
        tokens, min_gap = story_pacing(cfg, name, standalone)
        out.append({
            "name": name,
            "settings": story_settings(cfg, name),
            "beats": [{"step": st, "atmosphere": a, "scene": sc.get("name", sc["id"]),
                       "scene_id": sc["id"]} for st, a, sc in beats],
            "at_step": at,
            "finished": at >= len(beats),
            "finished_at": entry.get("finished_at"),
            "issues": issues,
            "pacing": {"tokens_per_round": tokens, "min_gap_scenes": min_gap,
                       "standalone_scenes": standalone},
        })
    return jsonify(out)


@app.route("/api/stories/<name>/settings", methods=["POST"])
def set_story_settings(name):
    """Save a storyline's pacing and ending. Stored in config.json under 'stories'."""
    body = request.get_json(silent=True) or {}
    cfg  = load_config()
    stories = cfg.setdefault("stories", {})
    entry   = stories.setdefault(name, {})
    if "pace_scenes" in body:
        entry["pace_scenes"] = max(1, min(200, int(body["pace_scenes"])))
    if "on_finish" in body and body["on_finish"] in ("rest", "once"):
        entry["on_finish"] = body["on_finish"]
    if "rest_seconds" in body:
        entry["rest_seconds"] = max(0, int(body["rest_seconds"]))
    if "min_gap_seconds" in body:
        entry["min_gap_seconds"] = max(0, int(body["min_gap_seconds"]))
    save_config(cfg)
    return jsonify({"ok": True, "settings": story_settings(cfg, name)})


@app.route("/api/stories/<name>/reset", methods=["POST"])
def reset_story(name):
    """Put a storyline back to its first beat."""
    _set_story_progress(name, step=0, finished_at=None)
    _story_last_seen.pop(name, None)
    return jsonify({"ok": True, "story": name})


@app.route("/api/phone/status")
def phone_status():
    """Everything the control page polls, in one call — the Pi is a single core."""
    return jsonify({
        "atmosphere":   _current_atmosphere,
        "volume":       _master_volume,
        "stove_volume": _stove_sound_volume,
        "led_test":     bool(_led_test_state.get("running")),
        "stories":      _story_progress(),
        "leds":         _led_live_state.get(_current_atmosphere, {}),
        "simulate":     _simulate_state,
        "preview":      _preview_state,
        "audio":        _AUDIO_AVAILABLE,
        "gpio":         _GPIO_AVAILABLE,
    })


@app.route("/api/state")
def get_state():
    """What the box is doing right now — used by the control page on load."""
    return jsonify({
        "atmosphere":   _current_atmosphere,
        "playing":      bool(_simulate_state.get("running")),
        "volume":       _master_volume,
        "stove_volume": _stove_sound_volume,
        "autoplay":     _AUTOPLAY,
        "uptime_s":     round(time.time() - _BOOT_TIME, 1),
        "audio":        _AUDIO_AVAILABLE,
        "gpio":         _GPIO_AVAILABLE,
    })


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    if _GPIO_AVAILABLE:
        return jsonify({"error": "shutdown only available on Mac"}), 403
    import signal as _sig
    threading.Thread(target=lambda: (time.sleep(0.3), os.kill(os.getpid(), _sig.SIGTERM)), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/restart", methods=["POST"])
def api_restart():
    if _GPIO_AVAILABLE:
        return jsonify({"error": "restart only available on Mac"}), 403
    import signal as _sig
    def _do_restart():
        time.sleep(0.5)
        subprocess.Popen(
            ["bash", "/Users/willem-jan/signalbox-start.sh"],
            stdout=open("/tmp/signalbox-editor.log", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        os.kill(os.getpid(), _sig.SIGTERM)
    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/sync", methods=["POST"])
def api_sync():
    if _GPIO_AVAILABLE:
        return jsonify({"error": "sync only available on Mac"}), 403
    sync_script = os.path.join(BASE, "sync.sh")
    if not os.path.exists(sync_script):
        return jsonify({"error": "sync.sh not found"}), 404
    try:
        result = subprocess.run(
            ["bash", sync_script],
            capture_output=True, text=True, timeout=90,
            env={**os.environ, "PATH": os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin"}
        )
        return jsonify({
            "ok": result.returncode == 0,
            "output": result.stdout + result.stderr
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "sync timed out"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import atexit
    cfg0 = load_config()

    # Restore persisted state (volume / atmosphere) before any thread starts,
    # so LED flicker and stove-sound loops see the right atmosphere from t=0.
    _st0 = _load_state()
    _master_volume      = max(0.0, min(1.0, float(_st0.get("volume", 0.5))))
    _stove_sound_volume = max(0.0, min(1.0, float(_st0.get("stove_volume", 1.0))))
    _current_atmosphere = _st0.get("atmosphere", "day")
    print(f"[state] atmosphere={_current_atmosphere} playing={_st0.get('playing')} "
          f"volume={_master_volume:.2f} autoplay={_AUTOPLAY}", flush=True)

    _refresh_led_state(cfg0)
    _init_leds()
    if _LED_PWM_OBJS:
        _stop_led_flicker.clear()
        _led_flicker_thread = threading.Thread(target=_led_flicker_loop, daemon=True)
        _led_flicker_thread.start()
    _stop_stove_sound.clear()
    _stove_sound_thread = threading.Thread(target=_stove_sound_loop, daemon=True)
    _stove_sound_thread.start()
    atexit.register(_cleanup_leds)

    if _AUTOPLAY:
        # Standalone appliance: resume ambience + scene scheduler after the chime.
        if _st0.get("playing", True) and _AUDIO_AVAILABLE:
            def _autoplay():
                time.sleep(AUTOPLAY_DELAY_S)
                print(f"[autoplay] resuming '{_current_atmosphere}' atmosphere", flush=True)
                with app.app_context():
                    start_simulate(_current_atmosphere)
            threading.Thread(target=_autoplay, daemon=True).start()
        else:
            print("[autoplay] state says stopped — staying silent until told otherwise", flush=True)
    # The Mac editor opens silent. It is an authoring tool, so nothing plays
    # until Play, Simulate or a scene preview asks for it.

    def _play_startup_chime():
        time.sleep(2)
        try:
            cfg = load_config()
            fp = sound_file(cfg, "sf_pi_is_up")
            if fp and os.path.exists(fp) and _AUDIO_AVAILABLE:
                snd = pygame.mixer.Sound(fp)
                snd.set_volume(0.3)
                pygame.mixer.Channel(SCENE_CHANNEL_START).play(snd)
        except Exception as e:
            print(f"[startup chime] {e}")

    # "Pi is up" is how the box tells you it has booted. On the Mac there is
    # nothing to announce, and the editor should open silent.
    if _GPIO_AVAILABLE:
        threading.Thread(target=_play_startup_chime, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=False)
