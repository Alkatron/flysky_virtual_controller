# flysky_virtual_controller
I needed to add button to my rc-controller (flysky fs-i6x) so helped by Claude I created this python script that run on Debian Trixie that let you add button from keyboard as it were from the controller.

It works on Linux I don't know if it works on windows too, may be with some editing

Creates a virtual controller (uinput) combining:
  - Analog axes from the FlySky FS-i6X (or other rc.controller connected by USB HID dongle via pygame)
  - Buttons/switches from the keyboard (via evdev)

Dipendenze:
    pip install pygame evdev

Required permissions:
    sudo usermod -aG input $USER

Usage:
    python3 flysky_virtual_controller.py [--flysky-id 0] [--keyboard /dev/input/eventX]
    python3 flysky_virtual_controller.py --list-joysticks
    python3 flysky_virtual_controller.py --list-keyboards
    
    
    
    
    
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

## 2. Find your joystick index

Plug in your controller and run:

```bash
python3 flysky_virtual_controller.py --list-joysticks
```

Note the index number `[N]` next to your controller name.

---

## 3. Find your keyboard device

```bash
python3 flysky_virtual_controller.py --list-keyboards
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

## 4. Identify your physical axes

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

## 5. Edit AXIS_REMAP in the script

Open `flysky_virtual_controller.py` and find the `AXIS_REMAP` dictionary
near the top of the file:

```python
AXIS_REMAP = {
    0: 0,   # Roll     physical 0 → virtual 0
    1: 1,   # Pitch    physical 1 → virtual 1
    4: 2,   # Yaw      physical 4 → virtual 2
    2: 3,   # Throttle physical 2 → virtual 3
}
```

Change the **keys** (left side) to match your controller's physical axis
numbers. The **values** (right side) are the virtual axis positions the
simulator will see — keep them in the standard order:

- virtual 0 = Roll
- virtual 1 = Pitch
- virtual 2 = Yaw
- virtual 3 = Throttle

Example for a controller where Yaw is on axis 3 and Throttle on axis 2:

```python
AXIS_REMAP = {
    0: 0,   # Roll     physical 0 → virtual 0
    1: 1,   # Pitch    physical 1 → virtual 1
    3: 2,   # Yaw      physical 3 → virtual 2
    2: 3,   # Throttle physical 2 → virtual 3
}
```

---

## 6. Edit KEY_TO_BUTTON (optional)

Find the `KEY_TO_BUTTON` dictionary and assign keys to button slots as
you prefer:

```python
KEY_TO_BUTTON = {
    "KEY_SPACE": 0,   # arm / throttle cut
    "KEY_R":     1,   # reset
    ...
}
```

To find the exact name of any key, run:

```bash
python3 -c "
import evdev
kbd = evdev.InputDevice('/dev/input/eventX')  # replace X
for ev in kbd.read_loop():
    if ev.type == evdev.ecodes.EV_KEY and ev.value == 1:
        print(evdev.ecodes.KEY[ev.code])
"
```

---

## 7. Update vendor/product ID (recommended)

To avoid conflicts with the physical controller, set a unique vendor and
product ID in the script:

```python
VENDOR_ID  = 0x1209  # generic personal-use ID (pid.codes)
PRODUCT_ID = 0x0001  # change this if you run multiple virtual controllers
```

Do **not** reuse the same vendor/product ID as your physical dongle, or
SDL will give both devices the same name.

---

## 8. Run the script

```bash
python3 flysky_virtual_controller.py --flysky-id N --keyboard /dev/input/eventX
```

Replace `N` with the joystick index from step 2 and `eventX` with the
keyboard path from step 3.

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

In Steam, right-click the game → **Properties** → **Launch Options**:

```
SDL_GAMECONTROLLER_IGNORE_DEVICES=0xVVVV/0xPPPP SDL_GAMECONTROLLERCONFIG="GUID,Virtual Controller,platform:Linux,leftx:a0,lefty:a1,rightx:a2,righty:a3,lefttrigger:a6,righttrigger:a7,a:b0,b:b1,x:b2,y:b3," %command%
```

Replace:
- `0xVVVV/0xPPPP` with the **physical dongle** vendor/product ID
  (find it with `lsusb`), so SDL ignores the real controller
- `GUID` with the virtual controller GUID from step 9

Also disable Steam Input for the game:
**Properties → Controller → Disable Steam Input**

---

## Troubleshooting

**Axes not moving in the simulator**
: Run `jstest /dev/input/jsX` while moving sticks to confirm the virtual
  device is receiving data. If axes move there but not in the game, the
  issue is the `SDL_GAMECONTROLLERCONFIG` mapping.

**Buttons not working**
: Make sure you are using the correct keyboard `eventX` path (the one
  that actually produces key events — see step 3). If the grab fails,
  try running the script with `sudo`.

**Two controllers with the same name in the game**
: The virtual controller has the same vendor/product ID as the physical
  one. Change `VENDOR_ID` and `PRODUCT_ID` in the script (see step 7).

**Script does not respond to Ctrl+C**
: Make sure you press Ctrl+C in the **terminal window** where the script
  is running, not in the game window. The keyboard grab is exclusive only
  for keys listed in `KEY_TO_BUTTON`; Ctrl+C is passed through normally.

**`uinput` module not loaded**
: Run `sudo modprobe uinput`. On Debian/Ubuntu it is included in the
  default kernel but may not be loaded automatically.
