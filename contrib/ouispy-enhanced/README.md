# OUI-SPY Unified Blue — Enhanced Detector Bundle

Date: 2026-10-01

## Changes

- Preserves the existing Unified Blue modes and current OUI/MAC detection.
- Adds a generic BLE Service Data matcher (new filter type 6).
- Adds ASTM/OpenDroneID Remote ID detection using UUID `0xFFFA` + payload prefix `0x0D`.
- Adds Mode-1 Flock BLE signals:
  - `B4:1E:52`
  - company ID `0x09C8`
  - `FS Ext Battery`
  - `FlockCam`
  - `Pigvision`
  - `Penguin-`
- Leaves dedicated Mode 3 Flock-You unchanged.
- Existing persisted filter IDs 0..5 are not renumbered.

## Build on Android / Termux

Keep these files in the same folder:

- `apply_ouispy_enhancements.py`
- `build_ouispy_enhanced_termux.sh`

Then:

```sh
cd <that-folder>
chmod +x build_ouispy_enhanced_termux.sh
./build_ouispy_enhanced_termux.sh
```

The script uses Termux-PlatformIO (`tpio`), which builds PlatformIO projects inside an Ubuntu/proot environment so ESP32-S3 Linux toolchains work on Android.

Output:

```text
~/ouispy-enhanced/oui-spy-unified-blue-enhanced.bin
```

## Flash

First verify the board is still visible:

```sh
nrflash probe
```

Then flash only the application partition:

```sh
nrflash write --chip esp32s3 --offset 0x10000 "$HOME/ouispy-enhanced/oui-spy-unified-blue-enhanced.bin" --verify
```

The source patch does not alter the current partition table or bootloader, so an application-only flash preserves NVS configuration.

The patcher fails closed if expected upstream source anchors have changed. A successful compile is the first validation gate. Passive fingerprints still depend on what fields a particular nearby device actually advertises.
