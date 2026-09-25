# YARGDoubleStrumPrevention

Prevents double strums/overstrums in the same direction by filtering guitar inputs and outputting a separate virtual Xbox Controller.

Tested using an overstrumming Xbox 360 Xplorer.

This project was inspired by **[CloneHeroStrumLimiter](https://github.com/20excal07/CloneHeroStrumLimiter)** by 20excal07, which uses vJoy. Unfortunately [YARG](https://github.com/YARC-Official/YARG) does not seem to detect strum inputs from vJoy, leading to the creation of this script which uses ViGEmBus instead.

## Requirements

* **[ViGEmBus](https://github.com/nefarius/ViGEmBus/releases)**
* Python 3
* `pygame`
* `vgamepad`

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### 1. Start the script

Run the Python script:

```bash
python double-strum-prevention.py
```

You should see something similar to:

```text
Found 1 joystick(s):
  [0] Xbox 360 Xplorer (buttons=8, axes=2, hats=1)

Strum the guitar to select it...
```

Strum the guitar to select it.

The script will then create the virtual Xbox 360 controller.

### 2. If using YARG: Change your profile

1. Go to **Profiles**
2. Select your current guitar profile
3. **Remove your current guitar/controller** from the profile
4. Add/select **Xbox Controller** instead
5. Configure the Xbox controller bindings for the virtual guitar inputs as necessary
    - Star Power must be set to RB (can tilt the controller to set this), but the rest of the default binds should work

Note: The physical guitar itself (ex. Xbox 360 Guitar Hero Xplorer) is being read by this Python program and is not the controller YARG should use directly

## Controller Mapping

| Guitar Input      | Virtual Xbox 360 |
| ----------------- | ---------------- |
| Green             | A                |
| Red               | B                |
| Yellow            | X                |
| Blue              | Y                |
| Orange            | LB               |
| Select            | Back             |
| Start             | Start            |
| Strum Up          | D-pad Up         |
| Strum Down        | D-pad Down       |
| Whammy            | Right Trigger    |
| Tilt / Star Power | RB               |

## Configuration

The main configuration values are:

```python
POLL_RATE = 250

STRUM_DEBOUNCE = 0.015
STRUM_COOLDOWN = 0.060

WHAMMY_AXIS = 1
STAR_POWER_AXIS = 0

WHAMMY_DEADZONE = -0.95

STAR_POWER_MIN = -1.0
STAR_POWER_MAX = 1.0
STAR_POWER_THRESHOLD = 0.9

DEBUG = False
```

| Constant               | Default | Description                            |
| ---------------------- | ------: | -------------------------------------- |
| `POLL_RATE`            |   `250` | Controller polling frequency           |
| `STRUM_DEBOUNCE`       | `0.015` | Time required for a stable strum state |
| `STRUM_COOLDOWN`       | `0.060` | Minimum time between accepted strums   |
| `WHAMMY_DEADZONE`      | `-0.95` | Whammy resting/deadzone threshold      |
| `STAR_POWER_THRESHOLD` |   `0.9` | Tilt activation threshold (sends RB when met)                  |
| `DEBUG`                | `False` | Diagnostic console output (slows down script, not intended for normal gameplay) |
