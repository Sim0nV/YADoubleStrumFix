<p align="center"><img alt="YADoubleStrumFix" src="https://github.com/user-attachments/assets/3a1ff5cf-7b6b-407c-a370-3d45d6dcf36a" width="175" height="175"></a></p>

<h1 align="center">YADoubleStrumFix: Yet Another Double Strum Fix</h1>
<p align="center">Prevent double strums/overstrums occurring from same-direction strumming</p>

---

Fixes double strums/overstrums in the same direction by filtering guitar inputs and outputting a separate virtual Xbox Controller.

Tested using an overstrumming Xbox 360 Xplorer.

This project was inspired by **[CloneHeroStrumLimiter](https://github.com/20excal07/CloneHeroStrumLimiter)** by 20excal07, which uses vJoy. Unfortunately [YARG](https://github.com/YARC-Official/YARG) does not seem to detect strum inputs from vJoy, leading to the creation of this program which uses ViGEmBus instead.

## Usage

1. Install [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases)
2. Download the latest [YADoubleStrumFix release](https://github.com/nefarius/ViGEmBus/releases)
3. Run YADoubleStrumFix.exe
4. Select your guitar controller in the dropdown and click Start 

<p align="center"><img alt="YADoubleStrumFix" src="https://github.com/user-attachments/assets/f725e2d1-9ed2-4ae3-b499-878c4c682930" height="600"></a></p>

### If using YARG: Change your profile to use the virtual controller

1. Go to **Profiles**
2. Select your current guitar profile
3. Select **Remove Device** and remove your current guitar/controller from the profile
4. Select **Add Device** and add **Xbox Controller**
5. Configure the Xbox Controller bindings for the virtual guitar inputs as necessary
    - **Default binds should work, EXCEPT for Star Power** which must be set to **RB** (can tilt the controller to set this)
    - Click **Controller Mapping** in YADoubleStrumFix to view virtual controller binds if needed

Notes:

- Your guitar controller should NOT be used as the device in YARG, since that's the raw input which contains overstrums. Use the Xbox Controller device instead since that has the fix applied
- If inputs stop working after restarting the script: you may have to add/remove the virtual Xbox Controller device from your YARG profile 

## Configuration

| Constant               | Default | Description                            |
| ---------------------- | ------: | -------------------------------------- |
| `STRUM_DEBOUNCE`       | `0.015` | Time required for a stable strum state |
| `STRUM_COOLDOWN`       | `0.060` | Minimum time between accepted strums   |
| `POLL_RATE`            |   `250` | Controller polling frequency           |
| `WHAMMY_DEADZONE`      | `-0.95` | Whammy resting/deadzone threshold      |
| `STAR_POWER_THRESHOLD` |   `0.9` | Tilt activation threshold (sends RB when met)                  |
| `DEBUG`                | `False` | Diagnostic console output (slows down script, not intended for normal gameplay) |

## Development

Install Python 3.11+ and run:

```powershell
pip install -r requirements.txt
python main.py
```

To create ``dist\YADoubleStrumFix.exe``, run:
```powershell
.\build.ps1
```
