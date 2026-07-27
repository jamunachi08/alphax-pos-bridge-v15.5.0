#!/bin/bash
# Build a signed .pkg installer for AlphaX POS Bridge on macOS.
#
# Prereqs:
#   - PyInstaller has produced dist/AlphaX POS Bridge.app/
#   - For signing + notarization (optional but recommended for distribution):
#       export DEVELOPER_ID="Developer ID Installer: Your Name (TEAMID)"
#       export NOTARIZE_USER="apple-id@example.com"
#       export NOTARIZE_TEAM="TEAMID"
#       export NOTARIZE_PASSWORD="app-specific-password"
#
# Without those env vars set, builds an unsigned .pkg (still installs,
# user gets a "unverified developer" prompt unless they right-click open).
#
# Usage:  bash packaging/macos/build-pkg.sh
# Output: dist/installers/AlphaX-POS-Bridge-15.5.1.pkg

set -euo pipefail

VERSION="15.5.1"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/dist/AlphaX POS Bridge.app"
INSTALL_DIR="$ROOT/dist/installers"
PKG_OUT="$INSTALL_DIR/AlphaX-POS-Bridge-$VERSION.pkg"
LAUNCHD_PLIST="$HERE/com.alphax.pos.bridge.plist"

mkdir -p "$INSTALL_DIR"

if [[ ! -d "$APP" ]]; then
  echo "❌ $APP not found. Run PyInstaller first:"
  echo "   pyinstaller packaging/pyinstaller/alphax-bridge.spec --clean --noconfirm"
  exit 1
fi

# Stage the install layout
STAGING="$(mktemp -d)"
mkdir -p "$STAGING/Applications"
cp -R "$APP" "$STAGING/Applications/"

# Optional: codesign the .app
if [[ -n "${DEVELOPER_ID:-}" ]]; then
  echo "→ Code-signing app bundle"
  codesign --deep --force --options runtime \
           --sign "$DEVELOPER_ID" \
           "$STAGING/Applications/AlphaX POS Bridge.app"
fi

# Build the component pkg
COMPONENT_PKG="$INSTALL_DIR/component.pkg"
pkgbuild --identifier com.alphax.pos.bridge \
         --version "$VERSION" \
         --root "$STAGING" \
         --install-location "/" \
         --scripts "$HERE/scripts" \
         "$COMPONENT_PKG"

# Wrap in a productbuild archive (so we can show a license + welcome)
DIST_XML="$(mktemp).xml"
cat > "$DIST_XML" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>AlphaX POS Bridge</title>
  <license file="license.txt"/>
  <welcome file="welcome.html"/>
  <conclusion file="conclusion.html"/>
  <pkg-ref id="com.alphax.pos.bridge" version="$VERSION" onConclusion="none">component.pkg</pkg-ref>
  <choices-outline>
    <line choice="default">
      <line choice="com.alphax.pos.bridge"/>
    </line>
  </choices-outline>
  <choice id="default"/>
  <choice id="com.alphax.pos.bridge" visible="false">
    <pkg-ref id="com.alphax.pos.bridge"/>
  </choice>
</installer-gui-script>
EOF

# Resources for the installer UI
RES="$(mktemp -d)"
cp "$ROOT/license.txt" "$RES/license.txt" 2>/dev/null || echo "MIT" > "$RES/license.txt"
cat > "$RES/welcome.html" <<'EOF'
<html><body style="font-family:-apple-system,sans-serif">
<h2>AlphaX POS Bridge</h2>
<p>This installer puts the AlphaX POS Bridge in your Applications folder and configures it to launch on login.</p>
<p>The bridge runs in the background and lets your AlphaX cashier UI talk to your printer, drawer, and other USB hardware.</p>
<p>After install, look for a small green dot in your menu bar — right-click it for status and configuration.</p>
</body></html>
EOF
cat > "$RES/conclusion.html" <<'EOF'
<html><body style="font-family:-apple-system,sans-serif">
<h2>You're all set.</h2>
<p>The bridge is now running. Open the AlphaX cashier UI in your browser, go to Hardware Settings, and connect to <code>http://localhost:8420</code>.</p>
<p>Your auth token was generated during setup; check the menu bar icon → "Show auth token" to copy it.</p>
</body></html>
EOF

productbuild --distribution "$DIST_XML" \
             --resources "$RES" \
             --package-path "$INSTALL_DIR" \
             "$PKG_OUT"

rm "$COMPONENT_PKG"

# Optional: sign the productbuild output
if [[ -n "${DEVELOPER_ID:-}" ]]; then
  echo "→ Signing installer"
  SIGNED="$INSTALL_DIR/AlphaX-POS-Bridge-$VERSION-signed.pkg"
  productsign --sign "$DEVELOPER_ID" "$PKG_OUT" "$SIGNED"
  mv "$SIGNED" "$PKG_OUT"
fi

# Optional: notarize
if [[ -n "${NOTARIZE_USER:-}" && -n "${NOTARIZE_TEAM:-}" && -n "${NOTARIZE_PASSWORD:-}" ]]; then
  echo "→ Submitting for notarization (this can take 5-30 minutes)"
  xcrun notarytool submit "$PKG_OUT" \
        --apple-id "$NOTARIZE_USER" \
        --team-id  "$NOTARIZE_TEAM" \
        --password "$NOTARIZE_PASSWORD" \
        --wait
  echo "→ Stapling notarization ticket"
  xcrun stapler staple "$PKG_OUT"
fi

echo "✓ Built $PKG_OUT"
