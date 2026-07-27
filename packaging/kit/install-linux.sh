#!/bin/bash
# =============================================================================
# AlphaX POS Bridge — one-command Linux installer (Ubuntu/Debian/mini-PCs)
#   sudo not required. Installs to ~/.local/share/alphax-bridge, registers a
#   systemd user service, launches the setup wizard.
# =============================================================================
set -e
cd "$(dirname "$0")"
APP_DIR="$HOME/.local/share/alphax-bridge"
WHEEL=$(ls alphax_pos_bridge-*.whl 2>/dev/null | head -1)
PORT=8720

echo "=== AlphaX POS Bridge Setup ==="
[ -z "$WHEEL" ] && { echo "Bridge package (.whl) not found next to the installer."; exit 1; }
command -v python3 >/dev/null || { echo "Install python3 first: sudo apt install python3 python3-venv"; exit 1; }

mkdir -p "$APP_DIR"
[ -x "$APP_DIR/env/bin/python3" ] || python3 -m venv "$APP_DIR/env"
echo "Installing the bridge…"
"$APP_DIR/env/bin/pip" install --upgrade pip --quiet
"$APP_DIR/env/bin/pip" install --upgrade "./$WHEEL[all]" --quiet
cp -R profiles "$APP_DIR/" 2>/dev/null || true

mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/alphax-bridge.service" << UNIT
[Unit]
Description=AlphaX POS Bridge
After=network.target

[Service]
ExecStart=$APP_DIR/env/bin/alphax-bridge
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now alphax-bridge
loginctl enable-linger "$USER" 2>/dev/null || true

echo ""
echo "Running the setup wizard — add your receipt and kitchen printers there."
if "$APP_DIR/env/bin/python3" -c "import tkinter" 2>/dev/null; then
  "$APP_DIR/env/bin/alphax-bridge-wizard" &
else
  echo "Note: the graphical wizard needs Tk. Either install Python from python.org"
  echo "(includes Tk) or configure printers by editing: $APP_DIR/config.yaml"
  echo "(see profiles/ for ready-made printer profiles). The bridge itself is running."
fi
echo ""
echo "Done. Bridge at http://localhost:$PORT, auto-starts with the machine."
echo "Remove later with: systemctl --user disable --now alphax-bridge && rm -rf $APP_DIR"
