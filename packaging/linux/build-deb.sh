#!/bin/bash
# Build a Debian .deb for AlphaX POS Bridge (Ubuntu/Debian/Mint/RPi).
#
# Prereqs:
#   - PyInstaller has produced dist/alphax-bridge/ folder
#   - dpkg-deb installed (ships with Debian; on RPM systems: apt install dpkg)
#
# Usage:  bash packaging/linux/build-deb.sh
# Output: dist/installers/alphax-pos-bridge_15.5.2_amd64.deb

set -euo pipefail

VERSION="15.5.2"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PYI_OUT="$ROOT/dist/alphax-bridge"
INSTALL_DIR="$ROOT/dist/installers"
STAGING="$(mktemp -d)"

if [[ ! -d "$PYI_OUT" ]]; then
  echo "❌ $PYI_OUT not found. Run PyInstaller first:"
  echo "   pyinstaller packaging/pyinstaller/alphax-bridge.spec --clean --noconfirm"
  exit 1
fi

mkdir -p "$INSTALL_DIR"

# Layout:
#   /opt/alphax-pos-bridge/         the PyInstaller bundle
#   /usr/bin/alphax-bridge           symlink → /opt/.../alphax-bridge
#   /usr/share/applications/...      .desktop file
#   /etc/systemd/user/...            systemd user unit
#   /usr/share/doc/alphax-pos-bridge/   docs

mkdir -p "$STAGING/DEBIAN"
mkdir -p "$STAGING/opt/alphax-pos-bridge"
mkdir -p "$STAGING/usr/bin"
mkdir -p "$STAGING/usr/share/applications"
mkdir -p "$STAGING/etc/systemd/user"
mkdir -p "$STAGING/usr/share/doc/alphax-pos-bridge"

cp -r "$PYI_OUT"/* "$STAGING/opt/alphax-pos-bridge/"

# Symlink for command-line use (alphax-bridge --discover etc)
ln -s /opt/alphax-pos-bridge/alphax-bridge "$STAGING/usr/bin/alphax-bridge"

# Desktop entry — appears in the application menu
cat > "$STAGING/usr/share/applications/alphax-pos-bridge.desktop" <<'EOF'
[Desktop Entry]
Name=AlphaX POS Bridge
Comment=Hardware bridge daemon for AlphaX POS
Exec=/opt/alphax-pos-bridge/alphax-bridge
Icon=alphax-pos-bridge
Terminal=false
Type=Application
Categories=Utility;System;
StartupWMClass=alphax-pos-bridge
X-GNOME-Autostart-enabled=true
EOF

# systemd user service — runs in user session (not as root, so it can
# access USB devices the user owns).
cat > "$STAGING/etc/systemd/user/alphax-pos-bridge.service" <<'EOF'
[Unit]
Description=AlphaX POS Bridge
After=graphical-session.target

[Service]
ExecStart=/opt/alphax-pos-bridge/alphax-bridge
Restart=on-failure
RestartSec=5
StandardOutput=append:%h/.alphax-bridge/logs/systemd.out
StandardError=append:%h/.alphax-bridge/logs/systemd.err

[Install]
WantedBy=default.target
EOF

# Docs
cp "$ROOT/README.md" "$STAGING/usr/share/doc/alphax-pos-bridge/" 2>/dev/null || true
cp "$ROOT/license.txt" "$STAGING/usr/share/doc/alphax-pos-bridge/copyright" 2>/dev/null || \
  echo "MIT" > "$STAGING/usr/share/doc/alphax-pos-bridge/copyright"

# Control file
cat > "$STAGING/DEBIAN/control" <<EOF
Package: alphax-pos-bridge
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: AlphaX <support@alphax.example>
Depends: libc6, libusb-1.0-0, python3-tk
Recommends: cups
Description: Hardware bridge daemon for AlphaX POS
 Runs as a small local daemon on the cashier device, letting the
 browser-based AlphaX POS cashier UI talk to receipt printers,
 cash drawers, customer pole displays, weighing scales, and card
 terminals over USB, serial, or network.
 .
 After install: launch from your application menu, or run
 'systemctl --user start alphax-pos-bridge' to start now and
 'systemctl --user enable alphax-pos-bridge' to start on login.
EOF

# Postinst — make the user a member of dialout (USB serial access)
# and remind about systemd user enable.
cat > "$STAGING/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e

# Add the user who's logged in to dialout group (for serial port access).
# We can't safely guess WHO that is during package install, so we just
# print instructions instead.

echo ""
echo "✓ AlphaX POS Bridge installed."
echo ""
echo "To enable autostart on login:"
echo "  systemctl --user enable --now alphax-pos-bridge"
echo ""
echo "To allow USB / serial port access (one-time, then log out and back in):"
echo "  sudo usermod -aG dialout \$USER"
echo "  sudo usermod -aG plugdev \$USER"
echo ""
echo "Then open the app from your application menu, or run:"
echo "  alphax-bridge --discover    # see what hardware is plugged in"
echo "  alphax-bridge               # start the daemon"
echo ""
exit 0
EOF
chmod 755 "$STAGING/DEBIAN/postinst"

# Build the .deb
DEB_OUT="$INSTALL_DIR/alphax-pos-bridge_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$STAGING" "$DEB_OUT"

echo "✓ Built $DEB_OUT"
