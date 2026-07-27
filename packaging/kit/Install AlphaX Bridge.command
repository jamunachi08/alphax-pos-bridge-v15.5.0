#!/bin/bash
# =============================================================================
# AlphaX POS Bridge — one-click macOS installer (double-click in Finder)
#   1. Uses the Mac's Python 3 (offers Command Line Tools install if missing)
#   2. Installs the bridge into its own private environment
#   3. Registers a LaunchAgent (tray app starts at every login)
#   4. Launches the setup wizard to add your printers
# Safe to re-run: upgrades in place.
# =============================================================================
set -e
cd "$(dirname "$0")"
APP_DIR="$HOME/Library/Application Support/AlphaXBridge"
WHEEL=$(ls alphax_pos_bridge-*.whl 2>/dev/null | head -1)
PORT=8720

echo "=== AlphaX POS Bridge Setup ==="
[ -z "$WHEEL" ] && { echo "Bridge package (.whl) not found next to the installer."; exit 1; }

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. macOS will now offer to install the Command Line Tools —"
  echo "accept the dialog, then double-click this installer again."
  xcode-select --install 2>/dev/null || true
  exit 1
fi
PYV=$(python3 -c 'import sys; print(sys.version_info >= (3, 9))')
[ "$PYV" != "True" ] && { echo "Python 3.9+ required. Install from python.org and re-run."; exit 1; }

mkdir -p "$APP_DIR"
[ -x "$APP_DIR/env/bin/python3" ] || python3 -m venv "$APP_DIR/env"
echo "Installing the bridge (this may take a minute)…"
"$APP_DIR/env/bin/pip" install --upgrade pip --quiet
"$APP_DIR/env/bin/pip" install --upgrade "./$WHEEL[all]" --quiet
cp -R profiles "$APP_DIR/" 2>/dev/null || true

PLIST="$HOME/Library/LaunchAgents/ai.neotec.alphax-bridge.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" << PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.neotec.alphax-bridge</string>
  <key>ProgramArguments</key><array><string>$APP_DIR/env/bin/alphax-bridge-tray</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo ""
echo "Launching the setup wizard — add your receipt and kitchen printers there."
if "$APP_DIR/env/bin/python3" -c "import tkinter" 2>/dev/null; then
  "$APP_DIR/env/bin/alphax-bridge-wizard" &
else
  echo "Note: the graphical wizard needs Tk. Either install Python from python.org"
  echo "(includes Tk) or configure printers by editing: $APP_DIR/config.yaml"
  echo "(see profiles/ for ready-made printer profiles). The bridge itself is running."
fi
echo ""
echo "Done. The bridge runs at http://localhost:$PORT and starts automatically at login."
echo "To remove it later: run 'Uninstall AlphaX Bridge.command' from this folder."
