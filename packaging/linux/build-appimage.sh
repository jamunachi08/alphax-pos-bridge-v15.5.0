#!/bin/bash
# Build an AppImage for AlphaX POS Bridge — runs on any Linux distro
# without an install (just chmod +x and double-click).
#
# Prereqs:
#   - PyInstaller has produced dist/alphax-bridge/
#   - appimagetool from https://github.com/AppImage/AppImageKit/releases
#       (download appimagetool-x86_64.AppImage, chmod +x it, put in PATH)
#
# Usage:  bash packaging/linux/build-appimage.sh
# Output: dist/installers/AlphaX-POS-Bridge-15.5.2-x86_64.AppImage

set -euo pipefail

VERSION="15.5.2"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYI_OUT="$ROOT/dist/alphax-bridge"
INSTALL_DIR="$ROOT/dist/installers"
APPDIR="$ROOT/dist/AlphaX_POS_Bridge.AppDir"

if [[ ! -d "$PYI_OUT" ]]; then
  echo "❌ $PYI_OUT not found. Run PyInstaller first."
  exit 1
fi

if ! command -v appimagetool >/dev/null && ! [[ -x ./appimagetool ]]; then
  echo "❌ appimagetool not found in PATH."
  echo "   Download from: https://github.com/AppImage/AppImageKit/releases"
  exit 1
fi

mkdir -p "$INSTALL_DIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Bundle the PyInstaller output
cp -r "$PYI_OUT"/* "$APPDIR/usr/bin/"

# Icon (PNG; AppImage requires a PNG even if you have an SVG)
ICON_SRC="$HERE/../assets/alphax-bridge.png"
if [[ -f "$ICON_SRC" ]]; then
  cp "$ICON_SRC" "$APPDIR/alphax-bridge.png"
  cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/alphax-bridge.png"
else
  # Generate a placeholder so the build doesn't fail
  python3 -c "
from PIL import Image
img = Image.new('RGBA', (256, 256), (15, 110, 86, 255))
img.save('$APPDIR/alphax-bridge.png')
img.save('$APPDIR/usr/share/icons/hicolor/256x256/apps/alphax-bridge.png')
" 2>/dev/null || touch "$APPDIR/alphax-bridge.png"
fi

# Desktop file
cat > "$APPDIR/alphax-bridge.desktop" <<EOF
[Desktop Entry]
Name=AlphaX POS Bridge
Exec=alphax-bridge
Icon=alphax-bridge
Type=Application
Categories=Utility;System;
Comment=Hardware bridge for AlphaX POS
EOF
cp "$APPDIR/alphax-bridge.desktop" "$APPDIR/usr/share/applications/"

# AppRun — entry point AppImage uses to launch the binary.
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/alphax-bridge" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Build the AppImage
ARCH="x86_64"
OUTPUT="$INSTALL_DIR/AlphaX-POS-Bridge-${VERSION}-${ARCH}.AppImage"
appimagetool "$APPDIR" "$OUTPUT" 2>&1 | tail -3

echo "✓ Built $OUTPUT"
echo "  Users run it with: chmod +x $(basename $OUTPUT) && ./$(basename $OUTPUT)"
