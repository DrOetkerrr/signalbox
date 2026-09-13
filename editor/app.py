import json
import math
import os
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
_STATE_DEFAULTS = {"atmosphere": "day", "playing": True, "volume": 0.5, "stove_volume": 1.0}
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
_preview_state  = {"elapsed": 0.0, "total": 0.0, "scene_id": None, "playing": False}

_simulate_thread = None
_stop_simulate   = threading.Event()
_simulate_state  = {"running": False, "atmosphere": None, "mode": "idle",
                    "scene_name": None, "scene_id": None, "next_in": 0.0, "remaining": 0}

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
        stove_on = stove.get("enabled", False) and not _led_test_running
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


def _stop_loops():
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


# ── Preview ───────────────────────────────────────────────────────────────────

def _run_preview(scene, atmosphere, cfg, start_at=0.0):
    _stop_preview.clear()
    events     = sorted(scene.get("events", []), key=lambda e: e.get("start", 0))
    _, total = _build_timeline(scene, cfg)
    _preview_state.update(elapsed=start_at, total=total, scene_id=scene["id"], playing=True)
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

    while not _stop_preview.is_set():
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

    _preview_state.update(elapsed=0.0, playing=False)


# ── Simulate ──────────────────────────────────────────────────────────────────

def _run_simulate(atmosphere, cfg):
    _stop_simulate.clear()
    _simulate_state.update(running=True, atmosphere=atmosphere, mode="starting",
                           scene_name=None, scene_id=None, next_in=0.0, remaining=0)
    _start_loops(atmosphere, cfg)

    queue = []

    while not _stop_simulate.is_set():
        scenes = cfg["atmospheres"].get(atmosphere, {}).get("scenes", [])
        if not scenes:
            _stop_simulate.wait(timeout=5)
            continue

        if not queue:
            queue = list(scenes)
            random.shuffle(queue)

        scene  = queue.pop(0)
        min_s  = scene.get("min_interval", 900)
        max_s  = scene.get("max_interval", 2400)
        wait_s = random.uniform(min_s, max_s)

        _simulate_state.update(mode="waiting",
                               scene_name=scene.get("name", scene["id"]),
                               scene_id=scene["id"],
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


@app.route("/")
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
    global _preview_thread
    cfg   = load_config()
    scene = next((s for s in cfg["atmospheres"].get(atmosphere, {}).get("scenes", [])
                  if s["id"] == scene_id), None)
    if not scene:
        return jsonify({"error": "scene not found"}), 404
    body     = request.get_json(silent=True) or {}
    start_at = max(0.0, float(body.get("start_at", 0)))
    _stop_preview.set()
    if _preview_thread and _preview_thread.is_alive():
        _preview_thread.join(timeout=1)
    _preview_state.update(playing=True, scene_id=scene_id, elapsed=start_at)
    _preview_thread = threading.Thread(target=_run_preview,
                                       args=(scene, atmosphere, cfg, start_at), daemon=True)
    _preview_thread.start()
    return jsonify({"ok": True})


@app.route("/api/preview/status")
def preview_status():
    return jsonify(_preview_state)


@app.route("/api/debug/mixer")
def debug_mixer():
    channels = []
    for i in range(10):
        ch = pygame.mixer.Channel(i)
        channels.append({"ch": i, "busy": ch.get_busy(), "vol": _channel_volumes.get(i)})
    return jsonify({"initialized": pygame.mixer.get_init(), "channels": channels, "master_vol": _master_volume})


@app.route("/api/preview/stop", methods=["POST"])
def stop_preview():
    _stop_preview.set()
    for i in range(SCENE_CHANNEL_START, SCENE_CHANNEL_START + SCENE_CHANNEL_COUNT):
        pygame.mixer.Channel(i).stop()
    _preview_state.update(elapsed=0.0, playing=False)
    return jsonify({"ok": True})


@app.route("/api/stop_all", methods=["POST"])
def stop_all():
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


@app.route("/control")
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
    threading.Timer(1.0, lambda: os.system("sudo reboot")).start()
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
    elif _AUDIO_AVAILABLE:
        # Mac dev server: loops only, no scene scheduler, as before.
        _start_loops(_current_atmosphere, cfg0)

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

    threading.Thread(target=_play_startup_chime, daemon=True).start()
    app.run(host="0.0.0.0", port=5001, debug=False)
