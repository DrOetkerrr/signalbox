#!/usr/bin/env python3
"""
Standalone LED test — run this on the Pi before starting the full app.

GPIO pin assignments (BCM numbering):
  GPIO12  →  PWM1  →  CH1  ceiling upper
  GPIO19  →  PWM2  →  CH2  ceiling lower
  GPIO16  →  PWM3  →  CH3  stove (fire)
  GPIO20  →  PWM4  →  CH4  exterior lamp

MOSFET board signal inputs (bottom row):
  PWM1/GND1  PWM2/GND2  PWM3/GND3  PWM4/GND4

Run with:
  python3 led_test.py           — full test sequence
  python3 led_test.py flicker   — flicker demo only (Ctrl+C to stop)
"""

import math
import signal
import sys
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("RPi.GPIO not found. Are you running this on the Pi?")
    print("Install with:  pip3 install RPi.GPIO")
    sys.exit(1)

# ── Pin map ────────────────────────────────────────────────────────────────────
CHANNELS = {
    "ceiling_upper": 12,
    "ceiling_lower": 19,
    "stove":         16,
    "exterior":      20,
}
PWM_FREQ = 200   # Hz — high enough to avoid LED flicker on camera
RAMP_HZ  = 60   # steps per second for brightness ramps

_pwms: dict = {}


# ── Setup / teardown ───────────────────────────────────────────────────────────

def setup():
    GPIO.setmode(GPIO.BCM)
    for ch, pin in CHANNELS.items():
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, PWM_FREQ)
        pwm.start(0)
        _pwms[ch] = pwm
    print(f"GPIO ready — {len(CHANNELS)} channels initialised at {PWM_FREQ} Hz PWM")


def cleanup():
    print("Turning all LEDs off and releasing GPIO...")
    for pwm in _pwms.values():
        try:
            pwm.ChangeDutyCycle(0)
            pwm.stop()
        except Exception:
            pass
    GPIO.cleanup()
    print("Done.")


def _on_exit(sig, frame):
    print()
    cleanup()
    sys.exit(0)


# ── Low-level helpers ──────────────────────────────────────────────────────────

def set_brightness(channel, pct):
    """Set one channel to a fixed brightness (0–100%)."""
    _pwms[channel].ChangeDutyCycle(max(0.0, min(100.0, pct)))


def all_off():
    for ch in _pwms:
        set_brightness(ch, 0)


def ramp(channel, from_pct, to_pct, duration=1.5):
    """Smoothly ramp one channel between two brightness levels."""
    steps = max(2, int(RAMP_HZ * duration))
    for i in range(steps + 1):
        val = from_pct + (to_pct - from_pct) * (i / steps)
        set_brightness(channel, val)
        time.sleep(duration / steps)


def flicker(channel, brightness=100, speed=4.5, depth=75, duration=10.0):
    """
    Organic fire flicker using overlapping sine waves.
      speed  — cycles per second (1=slow pulse, 5=fast fire)
      depth  — how far brightness dips (10=subtle, 90=dramatic)
      duration — seconds to run (None = run until Ctrl+C)
    """
    lo    = 1.0 - depth / 100.0
    t     = 0.0
    step  = 0.04   # 25 Hz update rate
    t_end = (time.time() + duration) if duration else None

    while (t_end is None or time.time() < t_end):
        raw = (0.50 * math.sin(t * speed * 6.28318)
             + 0.30 * math.sin(t * speed * 2.71828 * 6.28318)
             + 0.20 * math.sin(t * speed * 4.13169 * 6.28318))
        val    = lo + (1.0 - lo) * (0.5 + 0.5 * raw)
        duty   = brightness * max(lo, min(1.0, val))
        set_brightness(channel, duty)
        t    += step
        time.sleep(step)

    set_brightness(channel, 0)


# ── Test sequences ─────────────────────────────────────────────────────────────

def test_each_channel():
    """Ramp each channel up and down one at a time."""
    print("\n── Test 1: each channel in sequence ────────────────────")
    for ch, pin in CHANNELS.items():
        print(f"  [{ch}]  GPIO{pin}  →  ramp up…", end="", flush=True)
        ramp(ch, 0, 100, duration=1.2)
        time.sleep(0.4)
        print(" hold…", end="", flush=True)
        time.sleep(0.6)
        print(" ramp down…", end="", flush=True)
        ramp(ch, 100, 0, duration=1.2)
        time.sleep(0.3)
        print(" off")


def test_all_together():
    """Bring all channels up simultaneously."""
    print("\n── Test 2: all channels together ───────────────────────")
    # Ramp all up
    steps = int(RAMP_HZ * 2.0)
    for i in range(steps + 1):
        t = i / steps
        for ch in _pwms:
            set_brightness(ch, 100 * t)
        time.sleep(2.0 / steps)
    print("  All at 100% — check all 4 LEDs are lit")
    time.sleep(2.0)

    # Ramp all down
    for i in range(steps + 1):
        t = i / steps
        for ch in _pwms:
            set_brightness(ch, 100 * (1 - t))
        time.sleep(2.0 / steps)
    print("  All off")


def test_stove_flicker():
    """Demo fire flicker on the stove channel."""
    print("\n── Test 3: stove flicker (10 s) ────────────────────────")
    print("  Expect: orange LED with organic fire-like variation")
    set_brightness("ceiling_upper", 40)   # dim background for contrast
    set_brightness("ceiling_lower", 40)
    flicker("stove", brightness=100, speed=4.5, depth=75, duration=10.0)
    all_off()
    print("  Flicker done")


def test_nighttime_scene():
    """Simulate the night atmosphere: all on, stove flickering."""
    print("\n── Test 4: night scene (15 s) ──────────────────────────")
    print("  Ceiling lamps steady, stove flickering, exterior on")
    set_brightness("ceiling_upper", 70)
    set_brightness("ceiling_lower", 70)
    set_brightness("exterior",      60)

    lo    = 1.0 - 75 / 100.0
    t     = 0.0
    step  = 0.04
    t_end = time.time() + 15.0
    while time.time() < t_end:
        raw  = (0.50 * math.sin(t * 4.5 * 6.28318)
              + 0.30 * math.sin(t * 4.5 * 2.71828 * 6.28318)
              + 0.20 * math.sin(t * 4.5 * 4.13169 * 6.28318))
        val  = lo + (1.0 - lo) * (0.5 + 0.5 * raw)
        set_brightness("stove", 100 * max(lo, min(1.0, val)))
        t   += step
        time.sleep(step)

    all_off()
    print("  Night scene done")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    signal.signal(signal.SIGINT,  _on_exit)
    signal.signal(signal.SIGTERM, _on_exit)

    setup()

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    try:
        if mode == "flicker":
            print("Flicker demo — Ctrl+C to stop")
            flicker("stove", brightness=100, speed=4.5, depth=75, duration=None)
        elif mode == "night":
            test_nighttime_scene()
        else:
            test_each_channel()
            test_all_together()
            test_stove_flicker()
            test_nighttime_scene()
            print("\n✓ All tests complete — LEDs off")
    finally:
        cleanup()
