#!/usr/bin/env python3
"""
flysky_virtual_controller.py
-----------------------------
Creates a virtual controller (uinput) combining:
  - Analog axes from the FlySky FS-i6X (USB HID dongle via pygame)
  - Buttons/switches from the keyboard (via evdev)

Dependencies:
    pip install pygame evdev

Required permissions:
    sudo usermod -aG input $USER

Usage:
    python3 flysky_virtual_controller.py [--flysky-id 0] [--keyboard /dev/input/eventX]
    python3 flysky_virtual_controller.py [--profile N]   (skip menu, load profile by index)
    python3 flysky_virtual_controller.py --list-joysticks
    python3 flysky_virtual_controller.py --list-keyboards

Profiles are loaded from controller_profiles.json in the same directory.
"""

import argparse
import sys
import time
import threading
import signal
import os
import json
from pathlib import Path

# Suppress pygame AVX2 warning (cosmetic only, does not affect performance)
os.environ.setdefault("PYGAME_DETECT_AVX2", "1")

# ── Constants ───────────────────────────────────────────────────────────────
AXIS_MIN    = -32767
AXIS_MAX    =  32767
AXIS_FUZZ   = 16
AXIS_FLAT   = 128
NUM_AXES    = 8

DEVICE_NAME  = "FlySky Virtual Controller"
VENDOR_ID    = 0x1209   # pid.codes — generic ID for personal use
PRODUCT_ID   = 0x0001
VERSION      = 0x0001

#PROFILES_FILE = Path(__file__).parent / "controller_profiles.json"
PROFILES_FILE = Path(os.path.realpath(__file__)).parent / "controller_profiles.json"

# ────────────────────────────────────────────────────────────────────────────
def load_profiles() -> list:
    """Load profiles from controller_profiles.json."""
    if not PROFILES_FILE.exists():
        print(f"[Profile] '{PROFILES_FILE}' not found — using built-in defaults.")
        return []
    with open(PROFILES_FILE, "r") as f:
        data = json.load(f)
    return data.get("profiles", [])


def select_profile(profiles: list, preselect: int = None) -> dict:
    """
    Show a numbered text menu and return the chosen profile dict.
    If preselect is given, skip the menu and return that index directly.
    """
    if not profiles:
        print("[Profile] No profiles found — using script defaults.")
        return {}

    if preselect is not None:
        if 0 <= preselect < len(profiles):
            p = profiles[preselect]
            print(f"[Profile] Auto-selected [{preselect}] {p['name']}")
            return p
        else:
            print(f"[Profile] Index {preselect} out of range — showing menu.")

    print()
    W = 50  # inner width (between the two │)
    def row(text=""):
        return "│ " + text.ljust(W - 2) + " │"
    print("┌" + "─" * W + "┐")
    print(row("FlySky Virtual Controller - Profiles"))
    print("├" + "─" * W + "┤")
    for i, p in enumerate(profiles):
        print(row(f"[{i}] {p['name']}"))
        desc = p.get("description", "")
        if desc:
            print(row(f"     {desc}"))
    print(row("[q] Quit"))
    print("└" + "─" * W + "┘")
    print()

    while True:
        try:
            choice = input(f"Select profile [0-{len(profiles)-1}] or q to quit: ").strip().lower()
            if choice == "q":
                print("Exiting.")
                sys.exit(0)
            idx = int(choice)
            if 0 <= idx < len(profiles):
                p = profiles[idx]
                print(f"[Profile] Loaded: {p['name']}")
                if p.get("sdl_note"):
                    print(f"[Profile] SDL note: {p['sdl_note']}")
                print()
                return p
            else:
                print(f"  Please enter a number between 0 and {len(profiles)-1}.")
        except (ValueError, EOFError):
            print("  Invalid input — please enter a number or q.")


def apply_profile(profile: dict):
    """
    Return (axis_remap, key_to_button) from a profile dict.
    JSON keys are strings so we convert axis keys to int.
    """
    if not profile:
        # Fall back to built-in defaults
        axis_remap = {0: 0, 1: 1, 4: 2, 2: 3, 3: 4}
        key_to_button = {
            "KEY_SPACE": 0, "KEY_R": 1, "KEY_F": 2,  "KEY_G": 3,
            "KEY_1":     4, "KEY_2": 5, "KEY_3": 6,  "KEY_4": 7,
            "KEY_Q":     8, "KEY_E": 9, "KEY_Z": 10, "KEY_X": 11,
        }
        return axis_remap, key_to_button

    axis_remap    = {int(k): v for k, v in profile.get("axis_remap", {}).items()}
    key_to_button = profile.get("key_to_button", {})
    return axis_remap, key_to_button


# ────────────────────────────────────────────────────────────────────────────
def list_joysticks():
    import pygame
    pygame.init()
    pygame.joystick.init()
    count = pygame.joystick.get_count()
    if count == 0:
        print("No joystick found.")
    for i in range(count):
        j = pygame.joystick.Joystick(i)
        j.init()
        print(f"  [{i}] {j.get_name()}  —  {j.get_numaxes()} axes, {j.get_numbuttons()} buttons")
    pygame.quit()


def list_keyboards():
    from evdev import list_devices, InputDevice
    for path in list_devices():
        try:
            d = InputDevice(path)
            caps = d.capabilities(verbose=True)
            if ("EV_KEY", 1) in caps:
                print(f"  {path}  —  {d.name}")
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────
class VirtualController:
    """Wrapper around uinput exposing axes and buttons."""

    def __init__(self):
        from evdev import UInput, AbsInfo, ecodes as e

        BTN_LIST = [
            e.BTN_TRIGGER, e.BTN_THUMB,  e.BTN_THUMB2, e.BTN_TOP,
            e.BTN_TOP2,    e.BTN_PINKIE, e.BTN_BASE,   e.BTN_BASE2,
            e.BTN_BASE3,   e.BTN_BASE4,  e.BTN_BASE5,  e.BTN_BASE6,
        ]

        cap = {
            e.EV_KEY: BTN_LIST,
            e.EV_ABS: [
                (e.ABS_X,        AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
                (e.ABS_Y,        AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
                (e.ABS_Z,        AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
                (e.ABS_RX,       AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
                (e.ABS_RY,       AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
                (e.ABS_RZ,       AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
                (e.ABS_THROTTLE, AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
                (e.ABS_RUDDER,   AbsInfo(0, AXIS_MIN, AXIS_MAX, AXIS_FUZZ, AXIS_FLAT, 0)),
            ],
        }

        self._ui = UInput(
            cap,
            name=DEVICE_NAME,
            vendor=VENDOR_ID,
            product=PRODUCT_ID,
            version=VERSION,
        )
        self._e = e
        self._btn_codes = BTN_LIST
        self._axis_codes = [
            e.ABS_X, e.ABS_Y, e.ABS_Z, e.ABS_RX,
            e.ABS_RY, e.ABS_RZ, e.ABS_THROTTLE, e.ABS_RUDDER,
        ]
        print(f"[uinput] Virtual device created: {self._ui.device.path}")

    def set_axis(self, index: int, value: float):
        """value in [-1.0, 1.0]; scaled to [-32767, 32767]."""
        if index >= len(self._axis_codes):
            return
        raw = int(max(-1.0, min(1.0, value)) * AXIS_MAX)
        self._ui.write(self._e.EV_ABS, self._axis_codes[index], raw)

    def set_button(self, index: int, pressed: bool):
        if index >= len(self._btn_codes):
            return
        self._ui.write(self._e.EV_KEY, self._btn_codes[index], 1 if pressed else 0)

    def sync(self):
        self._ui.syn()

    def close(self):
        self._ui.close()


# ────────────────────────────────────────────────────────────────────────────
class FlySkyReader(threading.Thread):
    """Reads axes from the FlySky via pygame and remaps them according to axis_remap."""

    def __init__(self, joystick_index: int, virtual: VirtualController, axis_remap: dict):
        super().__init__(daemon=True)
        self._js_index  = joystick_index
        self._virtual   = virtual
        self._axis_remap = axis_remap
        self._running   = True

    def run(self):
        import pygame
        pygame.init()
        pygame.joystick.init()

        count = pygame.joystick.get_count()
        if count == 0:
            print("[FlySky] No joystick found. Check the USB connection.")
            return
        if self._js_index >= count:
            print(f"[FlySky] Index {self._js_index} is invalid (found {count} joystick(s)).")
            return

        js = pygame.joystick.Joystick(self._js_index)
        js.init()
        num_axes = js.get_numaxes()
        print(f"[FlySky] Connected: '{js.get_name()}' — {num_axes} physical axes")
        print(f"[FlySky] Active axis remap: {self._axis_remap}")

        clock = pygame.time.Clock()
        while self._running:
            pygame.event.pump()
            for src, dst in self._axis_remap.items():
                if src < num_axes:
                    val = js.get_axis(src)  # range [-1.0, 1.0]
                    self._virtual.set_axis(dst, val)
            self._virtual.sync()
            clock.tick(100)  # ~100 Hz

        pygame.quit()

    def stop(self):
        self._running = False


# ────────────────────────────────────────────────────────────────────────────
class KeyboardReader(threading.Thread):
    """
    Reads keys from the keyboard via evdev with exclusive grab.
    - Keys mapped in key_to_button → buttons on the virtual controller
    - All other keys → re-injected via uinput passthrough (Ctrl+C works normally)
    """

    def __init__(self, keyboard_path: str, virtual: VirtualController, key_to_button: dict):
        super().__init__(daemon=True)
        self._path          = keyboard_path
        self._virtual       = virtual
        self._key_to_button = key_to_button
        self._running       = True

    def run(self):
        from evdev import InputDevice, UInput, ecodes
        try:
            kbd = InputDevice(self._path)
        except Exception as ex:
            print(f"[Keyboard] Cannot open {self._path}: {ex}")
            print("  Try running with sudo or add your user to the 'input' group.")
            return

        print(f"[Keyboard] Listening on: {kbd.name} ({self._path})")

        from evdev import ecodes as e
        key_map = {}
        for key_name, btn_idx in self._key_to_button.items():
            code = getattr(e, key_name, None)
            if code is not None:
                key_map[code] = btn_idx
            else:
                print(f"[Keyboard] Warning: key '{key_name}' not recognized, skipping.")

        # Passthrough: re-injects unmapped keys back to the system
        try:
            passthrough = UInput.from_device(kbd, name=kbd.name + " (passthrough)")
            print(f"[Keyboard] Passthrough uinput created: {passthrough.device.path}")
        except Exception as ex:
            print(f"[Keyboard] Passthrough unavailable ({ex}) — unmapped keys will be lost.")
            passthrough = None

        # Exclusive grab AFTER creating the passthrough
        try:
            kbd.grab()
            print("[Keyboard] Exclusive grab OK — mapped keys → joystick | others → system")
        except Exception as ex:
            print(f"[Keyboard] grab() failed ({ex}) — continuing without grab.")

        import selectors
        sel = selectors.DefaultSelector()
        sel.register(kbd, selectors.EVENT_READ)

        try:
            while self._running:
                ready = sel.select(timeout=0.1)
                if not ready:
                    continue
                for event in kbd.read():
                    if event.type == ecodes.EV_KEY and event.code in key_map:
                        if event.value in (0, 1):
                            btn_idx = key_map[event.code]
                            pressed = (event.value == 1)
                            self._virtual.set_button(btn_idx, pressed)
                            self._virtual.sync()
                            action = "▼" if pressed else "▲"
                            print(f"[Keyboard] {action} btn{btn_idx} (key code={event.code})")
                    else:
                        # Unmapped key → passthrough to system
                        if passthrough is not None:
                            passthrough.write(event.type, event.code, event.value)
        finally:
            sel.close()
            try:
                kbd.ungrab()
                print("[Keyboard] Grab released.")
            except Exception:
                pass
            if passthrough is not None:
                try:
                    passthrough.close()
                except Exception:
                    pass

    def stop(self):
        self._running = False


# ────────────────────────────────────────────────────────────────────────────
def auto_detect_keyboard():
    """Returns the path of the first device with EV_KEY but without EV_ABS."""
    from evdev import list_devices, InputDevice, ecodes
    for path in list_devices():
        try:
            d = InputDevice(path)
            caps = d.capabilities()
            if ecodes.EV_KEY in caps and ecodes.EV_ABS not in caps:
                return path
        except Exception:
            pass
    return None


# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Virtual controller: FlySky axes + keyboard keys → uinput"
    )
    parser.add_argument("--flysky-id", type=int, default=0,
                        help="FlySky joystick index (default: 0).")
    parser.add_argument("--keyboard", type=str, default=None,
                        help="Keyboard device path, e.g. /dev/input/event5.")
    parser.add_argument("--profile", type=int, default=None,
                        help="Profile index to load directly, skipping the menu.")
    parser.add_argument("--list-joysticks", action="store_true",
                        help="List available joysticks and exit.")
    parser.add_argument("--list-keyboards", action="store_true",
                        help="List available keyboards and exit.")
    parser.add_argument("--list-profiles", action="store_true",
                        help="List available profiles and exit.")
    args = parser.parse_args()

    if args.list_joysticks:
        list_joysticks()
        return
    if args.list_keyboards:
        list_keyboards()
        return

    # Load profiles and show menu
    profiles = load_profiles()

    if args.list_profiles:
        if not profiles:
            print("No profiles found.")
        for i, p in enumerate(profiles):
            print(f"  [{i}] {p['name']} — {p.get('description', '')}")
        return

    profile       = select_profile(profiles, preselect=args.profile)
    axis_remap, key_to_button = apply_profile(profile)

    # Keyboard detection
    kbd_path = args.keyboard
    if kbd_path is None:
        kbd_path = auto_detect_keyboard()
        if kbd_path:
            print(f"[Auto] Keyboard detected: {kbd_path}")
        else:
            print("[Auto] No keyboard detected. Specify --keyboard /dev/input/eventX")
            sys.exit(1)

    virtual         = VirtualController()
    flysky_thread   = FlySkyReader(args.flysky_id, virtual, axis_remap)
    keyboard_thread = KeyboardReader(kbd_path, virtual, key_to_button)

    flysky_thread.start()
    keyboard_thread.start()

    def shutdown(sig, frame):
        print("\n[Main] Shutting down...")
        flysky_thread.stop()
        keyboard_thread.stop()
        try:
            virtual.close()
        except Exception:
            pass
        print("[Main] Virtual device removed. Exiting.")
        os._exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    profile_name = profile.get("name", "built-in defaults") if profile else "built-in defaults"
    print("\n" + "─"*55)
    print(f"  Active virtual controller: '{DEVICE_NAME}'")
    print(f"  Profile:  {profile_name}")
    print(f"  Axes:     from FlySky (joystick #{args.flysky_id})")
    print(f"  Buttons:  from keyboard ({kbd_path})")
    print(f"  Axis remapping:")
    for src, dst in axis_remap.items():
        print(f"    physical axis {src} → virtual {dst}")
    print(f"  Key map:")
    for k, v in key_to_button.items():
        print(f"    {k:<18} → btn{v}")
    print("─"*55)
    print("  Press Ctrl+C to exit.\n")

    while True:
        time.sleep(0.1)


if __name__ == "__main__":
    main()