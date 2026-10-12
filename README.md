# flysky_virtual_controller
I needed to add buttons to my rc-controller (flysky fs-i6x) so helped by Claude I created this python script that run on Debian Trixie that let you add buttons from keyboard as they were from the controller.

It works on Linux I don't know if it works on windows too, may be with some editing

Creates a virtual controller (uinput) combining:
  - Analog axes from the FlySky FS-i6X (or other rc.controller connected by USB HID dongle via pygame)
  - Buttons/switches from the keyboard (via evdev)
    
    
# How to use flysky_virtual_controller.py with a different controller

This guide explains how to adapt the script to any RC controller connected
via USB dongle on Linux.

---

## 1. Install dependencies

```bash
pip install pygame evdev
```

Add your user to the `input` group (required to read `/dev/input` devices):

```bash
sudo usermod -aG input $USER
# log out and back in for the change to take effect
```

---

## 2. File layout

The script requires two files in the **same directory**:

```
source/
├── flysky_virtual_controller.py
└── controller_profiles.json
```

If you launch the script via a symlink (e.g. from a `bin/` folder in your
PATH), the script automatically resolves the symlink and looks for
`controller_profiles.json` next to the **real** source file, not the link.

```bash
# example symlink setup
ln -s /path/to/source/flysky_virtual_controller.py ~/bin/flysky
```

---

## 3. Find your joystick index

Plug in your controller and run:

```bash
flysky --list-joysticks
```

Note the index number `[N]` next to your controller name.

---

## 4. Find your keyboard device

```bash
flysky --list-keyboards
```

This lists all devices that send key events. To confirm which one sends
the keys you want to map, run this and press a few keys:

```bash
python3 -c "
import evdev, selectors
devices = [evdev.InputDevice(p) for p in evdev.list_devices()
           if evdev.ecodes.EV_KEY in evdev.InputDevice(p).capabilities()]
sel = selectors.DefaultSelector()
for d in devices: sel.register(d, selectors.EVENT_READ)
print('Press keys...')
for _ in range(20):
    for key, _ in sel.select(timeout=5):
        for ev in key.fileobj.read():
            if ev.type == evdev.ecodes.EV_KEY and ev.value == 1:
                print(f'{key.fileobj.path}: {evdev.ecodes.KEY[ev.code]}')
"
```

Note the `/dev/input/eventX` path of the device that responds.

---

## 5. Identify your physical axes

Run `jstest` on your controller's joystick device (usually `/dev/input/js0`):

```bash
jstest /dev/input/js0
```

Move each stick and note which axis number moves and what its range is.
Write down the mapping, for example:

| Physical axis | Stick/channel |
|---------------|---------------|
| 0             | Roll          |
| 1             | Pitch         |
| 2             | Throttle      |
| 3             | Yaw           |

---

## 6. Create a profile in controller_profiles.json

Open `controller_profiles.json` and add a new entry to the `profiles` array.
Copy an existing profile as a template and adjust `name`, `description`,
`axis_remap` and `key_to_button` for your controller and game.

```json
{
  "name": "My Simulator",
  "description": "Short description shown in the menu",
  "axis_remap": {
    "0": 0,
    "1": 1,
    "3": 2,
    "2": 3
  },
  "key_to_button": {
    "KEY_SPACE": 0,
    "KEY_R":     1,
    "KEY_F":     2,
    "KEY_G":     3
  },
  "sdl_note": ""
}
```

### axis_remap

Keys are the **physical** axis numbers from step 5 (as strings in JSON).
Values are the **virtual** axis positions the simulator will see.
Standard order for simulators (Mode 2):

- virtual 0 = Roll
- virtual 1 = Pitch
- virtual 2 = Yaw
- virtual 3 = Throttle

### key_to_button

Key names follow the evdev convention (`KEY_*`). To find the exact name
of any key, run:

```bash
python3 -c "
import evdev
kbd = evdev.InputDevice('/dev/input/eventX')  # replace X
for ev in kbd.read_loop():
    if ev.type == evdev.ecodes.EV_KEY and ev.value == 1:
        print(evdev.ecodes.KEY[ev.code])
"
```

### sdl_note

Optional free-text field. Use it to store the Steam launch options for
this game (see step 9). It is printed on screen when the profile is
selected but has no effect on the script's behaviour.

---

## 7. Update vendor/product ID (recommended)

To avoid conflicts with the physical controller, set a unique vendor and
product ID at the top of the script:

```python
VENDOR_ID  = 0x1209  # generic personal-use ID (pid.codes)
PRODUCT_ID = 0x0001  # change this if you run multiple virtual controllers
```

Do **not** reuse the same vendor/product ID as your physical dongle, or
SDL will give both devices the same name.

---

## 8. Run the script

```bash
flysky --flysky-id N --keyboard /dev/input/eventX
```

Replace `N` with the joystick index from step 3 and `eventX` with the
keyboard path from step 4.

At startup, a numbered menu is shown listing all profiles in
`controller_profiles.json`. Select the one matching the game you are
about to play, or press `q` to quit.

```
┌──────────────────────────────────────────────────┐
│ FlySky Virtual Controller - Profiles             │
├──────────────────────────────────────────────────┤
│ [0] Ukrainian Fight Drone Simulator              │
│      UFDS - SDL GameController mode, Mode 2      │
│ [1] FPV Kamikaze Drone Simulator                 │
│      Kamikaze - SDL GameController mode, Mode 2  │
│ [2] Generic / Default                            │
│ [q] Quit                                         │
└──────────────────────────────────────────────────┘
Select profile [0-2] or q to quit: _
```

To skip the menu and load a profile directly (useful for autostart):

```bash
flysky --profile 0 --flysky-id N --keyboard /dev/input/eventX
```

To list available profiles without starting the script:

```bash
flysky --list-profiles
```

Press **Ctrl+C** in the terminal to stop the script and release the
keyboard grab.

---

## 9. Find the virtual controller GUID (for Steam games)

With the script running, execute:

```bash
python3 -c "
import pygame
pygame.init(); pygame.joystick.init()
for i in range(pygame.joystick.get_count()):
    j = pygame.joystick.Joystick(i); j.init()
    print(f'[{i}] {j.get_name()} — GUID: {j.get_guid()}')
pygame.quit()
"
```

Note the GUID of `FlySky Virtual Controller` (or whatever name you set).

---

## 10. Configure Steam launch options

In Steam, right-click the game → **Properties** → **Controller**:
set **Disable Steam Input** for this game.

Then go to **Properties** → **Launch Options** and add:

```
SDL_GAMECONTROLLER_IGNORE_DEVICES=0xVVVV/0xPPPP SDL_GAMECONTROLLERCONFIG="GUID,Virtual Controller,platform:Linux,leftx:a0,lefty:a1,rightx:a2,righty:a3,lefttrigger:a6,righttrigger:a7,a:b0,b:b1,x:b2,y:b3," %command%
```

Replace:
- `0xVVVV/0xPPPP` with the **physical dongle** vendor/product ID
  (find it with `lsusb`)
- `GUID` with the virtual controller GUID from step 9

You can store this string in the profile's `sdl_note` field for reference.

---

## Troubleshooting

**Axes not moving in the simulator**
: Run `jstest /dev/input/jsX` while moving sticks to confirm the virtual
  device is receiving data. If axes move there but not in the game, the
  issue is the `SDL_GAMECONTROLLERCONFIG` mapping or the wrong profile
  was selected.

**Buttons not working**
: Make sure you are using the correct keyboard `eventX` path (the one
  that actually produces key events — see step 4). If the grab fails,
  try running the script with `sudo`.

**Two controllers with the same name in the game**
: The virtual controller has the same vendor/product ID as the physical
  one. Change `VENDOR_ID` and `PRODUCT_ID` in the script (see step 7).

**Script does not respond to Ctrl+C**
: Make sure you press Ctrl+C in the **terminal window** where the script
  is running, not in the game window. The keyboard grab is exclusive only
  for keys listed in `key_to_button`; Ctrl+C is passed through normally.

**controller_profiles.json not found when launched via symlink**
: The script uses `os.path.realpath(__file__)` to resolve the symlink and
  always looks for the JSON file next to the real source file. Make sure
  both files are in the same directory.

**`uinput` module not loaded**
: Run `sudo modprobe uinput`. On Debian/Ubuntu it is included in the
  default kernel but may not be loaded automatically.    
    
    

