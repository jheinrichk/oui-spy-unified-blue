#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCHER="$SCRIPT_DIR/apply_ouispy_enhancements.py"
WORK="$HOME/ouispy-enhanced"
REPO="$WORK/oui-spy-unified-blue"
TPIO_SRC="$HOME/Termux-PlatformIO"
ENV_NAME="seeed_xiao_esp32s3"

echo "[*] OUI-SPY Enhanced build for Android/Termux"
echo "[*] Work dir: $WORK"

if [ ! -f "$PATCHER" ]; then
  echo "[-] Missing patcher: $PATCHER"
  exit 1
fi

pkg install -y git python proot-distro termux-api libusb

if ! command -v tpio >/dev/null 2>&1; then
  if [ ! -d "$TPIO_SRC/.git" ]; then
    git clone https://github.com/7wp81x/Termux-PlatformIO "$TPIO_SRC"
  else
    git -C "$TPIO_SRC" pull --ff-only
  fi
  (cd "$TPIO_SRC" && bash install.sh)
fi

tpio setup

mkdir -p "$WORK"
if [ -e "$REPO" ]; then
  echo "[-] $REPO already exists."
  echo "    Rename/remove it if you want a fresh reproducible checkout."
  exit 1
fi

git clone --depth 1 https://github.com/colonelpanichacks/oui-spy-unified-blue "$REPO"
python "$PATCHER" "$REPO"

cd "$REPO"
echo "[*] Building only; nothing will be flashed by this script."
tpio run -e "$ENV_NAME" --build-only

BUILD_DIR="$REPO/.pio/build/$ENV_NAME"
APP="$BUILD_DIR/firmware.bin"
if [ ! -f "$APP" ]; then
  echo "[-] Build completed but app binary was not found at:"
  echo "    $APP"
  exit 1
fi

OUT="$WORK/oui-spy-unified-blue-enhanced.bin"
cp "$APP" "$OUT"

echo
echo "[+] BUILD COMPLETE"
echo "[+] Application binary:"
echo "    $OUT"
echo
sha256sum "$OUT"
echo
echo "[*] The patch does not change bootloader or partition layout."
echo "[*] Recommended app-only flash, preserving existing NVS/settings:"
echo
echo "nrflash write --chip esp32s3 --offset 0x10000 \"$OUT\" --verify"
