<p align="center"><img alt="YADoubleStrumFix Icon" src="https://github.com/user-attachments/assets/3a1ff5cf-7b6b-407c-a370-3d45d6dcf36a" width="175" height="175"></a></p>

<h1 align="center">YADoubleStrumFix: Yet Another Double Strum Fix</h1>
<p align="center">Fix same-direction double strums/overstrums in guitar controllers</p>

---

Fixes double strums/overstrums in the same direction by creating a virtual Xbox Controller which filters out the extra strums.

Tested and working with my overstrumming Xplorer.

This was created because [YARG](https://github.com/YARC-Official/YARG) does not have a double strum prevention feature as of writing this.

Note that the fix is intended to prevent same-direction double strums/overstrums, **not** alternating-direction overstrumming.

This project was inspired by **[CloneHeroStrumLimiter](https://github.com/20excal07/CloneHeroStrumLimiter)** by 20excal07, which uses vJoy. Unfortunately YARG does not seem to detect strum inputs from vJoy, leading to the creation of this program which uses ViGEmBus instead.

## Usage

1. Install [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases)
2. Download the latest [YADoubleStrumFix release](https://github.com/Sim0nV/YADoubleStrumFix/releases)
3. Run YADoubleStrumFix.exe
4. Select your guitar controller in the dropdown and click Start

<p align="center"><img alt="YADoubleStrumFix Program" src="https://github.com/user-attachments/assets/68580b2c-57d4-4aac-80fa-7abf7cf4a1b3" height="450"></a></p>

### If using YARG: Change your profile to use the virtual controller

1. Go to **Profiles** and select your current guitar profile
2. Select **Remove Device** and remove your current guitar/controller from the profile if it's there
3. Select **Add Device** and add **Xbox Controller**
4. Configure the Xbox Controller bindings for the virtual guitar inputs as necessary
   - **Default binds should work, EXCEPT for Star Power** which must be set to your configured Star Power output (default `RB`, can tilt the controller to set this)
   - Click **Controller Mapping/Calibration** in YADoubleStrumFix to view or customize virtual controller binds and view live guitar inputs
5. Delete any other profiles that are using your guitar's device, if any exist

## Notes

- **If inputs stop working after restarting the script**: Remove and re-add the virtual Xbox Controller device from your YARG profile
- Your guitar controller should NOT be used as the device in YARG, since that's the raw input which contains overstrums. Use the Xbox Controller device instead since that has the fix applied

## Configuration

Settings can be directly configured in the app UI, including:

- **Strum Cooldown**: Minimum time in milliseconds between recognized strums (default `30` ms)
- **Poll Rate**: Controller polling frequency (default `250` Hz)
- **Controller Mapping & Calibration**: Fully customizable fret button IDs, hat strum values, whammy deadzones, and tilt thresholds.

<p align="center"><img alt="Controller Mapping UI" src="https://github.com/user-attachments/assets/d6c48345-d6a8-472c-abde-f5362af96913" height="400"></a></p>

## Development

Install Python 3.11+ and run:

```powershell
pip install -r requirements.txt
python main.py
```

To create `dist\YADoubleStrumFix.exe`, run:

```powershell
.\build.ps1
```
