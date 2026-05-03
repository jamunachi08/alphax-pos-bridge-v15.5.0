"""
AlphaX POS Bridge — system tray wrapper.

Runs the bridge HTTP server in a background thread and shows a small
tray icon (green when running, red when stopped, amber on error).
Right-click for: status, restart, edit config, view logs, quit.

This is what the installer-built executable runs. The plain
`alphax-bridge` CLI command from the pip install is still available
for headless / server use.

Dependencies: pystray (cross-platform tray icon), Pillow (icon image).
Both are pulled in by `pip install alphax-pos-bridge[tray]`.
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as e:
    sys.stderr.write(
        "AlphaX POS Bridge tray needs pystray and Pillow.\n"
        "Install with: pip install alphax-pos-bridge[tray]\n"
        f"Original error: {e}\n"
    )
    sys.exit(1)

from alphax_bridge import __version__
from alphax_bridge.registry import DeviceRegistry
from alphax_bridge.server import serve

# Set up logging both to stderr and to a rotating file the tray's
# "View logs" command can open.
LOG_DIR = Path.home() / ".alphax-bridge" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "bridge.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("alphax.tray")


CONFIG_DIR = Path.home() / ".alphax-bridge"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Bridge daemon thread
# ---------------------------------------------------------------------------

class BridgeDaemon:
    """Wraps the bridge HTTP server in a thread so the tray can stop and
    restart it without exiting the process."""

    def __init__(self):
        self.httpd = None
        self.thread = None
        self.registry = None
        self.status = "stopped"   # "stopped" | "running" | "error"
        self.last_error = ""

    def start(self) -> bool:
        if self.status == "running":
            return True
        try:
            self.registry = DeviceRegistry()
            self.registry.load_default_profiles()
            # Load user config if it exists.
            if CONFIG_FILE.exists():
                self.registry.load_user_config(str(CONFIG_FILE))
            host = "127.0.0.1"
            port = 8420
            auth_token = self._read_auth_token()
            self.httpd = serve(self.registry, host=host, port=port,
                               auth_token=auth_token)
            self.thread = threading.Thread(
                target=self.httpd.serve_forever,
                daemon=True,
                name="alphax-bridge",
            )
            self.thread.start()
            self.status = "running"
            self.last_error = ""
            log.info("Bridge started on %s:%d", host, port)
            return True
        except Exception as e:
            self.status = "error"
            self.last_error = str(e)
            log.exception("Bridge failed to start")
            return False

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                log.exception("Error stopping bridge")
            self.httpd = None
        if self.registry:
            try:
                self.registry.close_all()
            except Exception:
                pass
            self.registry = None
        self.thread = None
        self.status = "stopped"
        log.info("Bridge stopped")

    def restart(self):
        self.stop()
        time.sleep(0.3)
        self.start()

    def _read_auth_token(self) -> str | None:
        """Auth token: first try AUTH_TOKEN env var, then a file at
        ~/.alphax-bridge/auth.token. Returns None for no auth (dev mode)."""
        token = os.environ.get("ALPHAX_BRIDGE_TOKEN")
        if token:
            return token.strip()
        tok_file = CONFIG_DIR / "auth.token"
        if tok_file.exists():
            return tok_file.read_text().strip() or None
        return None


# ---------------------------------------------------------------------------
# Tray icon
# ---------------------------------------------------------------------------


def make_icon_image(status: str) -> "Image.Image":
    """Generate a 64x64 tray icon. Color reflects status."""
    colors = {
        "running": (15, 110, 86),    # AlphaX green
        "stopped": (132, 132, 132),
        "error":   (200, 60, 60),
    }
    color = colors.get(status, colors["stopped"])
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Dot
    d.ellipse((10, 10, 54, 54), fill=color)
    # Inner highlight (simple fake-3D look)
    d.ellipse((20, 16, 38, 30), fill=(255, 255, 255, 60))
    return img


def open_logs():
    """Open the log file in the system default viewer."""
    if platform.system() == "Windows":
        os.startfile(str(LOG_FILE))  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(LOG_FILE)])
    else:
        subprocess.Popen(["xdg-open", str(LOG_FILE)])


def open_config():
    """Open the config file in the system default editor."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(_default_config_template())
    if platform.system() == "Windows":
        os.startfile(str(CONFIG_FILE))  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(CONFIG_FILE)])
    else:
        subprocess.Popen(["xdg-open", str(CONFIG_FILE)])


def open_status_page():
    """Open the bridge's HTTP status page in the default browser."""
    webbrowser.open("http://127.0.0.1:8420/")


def _default_config_template() -> str:
    return """\
# AlphaX POS Bridge configuration
# https://github.com/alphax/alphax-pos-suite/tree/main/alphax-pos-bridge/docs

devices: []
  # Example:
  # - name: receipt-printer
  #   kind: printer
  #   profile: epson-tm-t20iii
  #   transport:
  #     type: usb
  #     vendor: 0x04b8
  #     product: 0x0e15
  #
  # - name: cash-drawer
  #   kind: drawer
  #   profile: drawer-via-printer
  #   uses_printer: receipt-printer
  #
  # Run `alphax-bridge --discover` to see what's plugged in,
  # then map the IDs into this file.
"""


# ---------------------------------------------------------------------------
# Tray menu actions
# ---------------------------------------------------------------------------


def make_menu(daemon: BridgeDaemon, icon: pystray.Icon):
    def label_status():
        return {
            "running": "● Bridge running on :8420",
            "stopped": "○ Bridge stopped",
            "error":   "⚠ Bridge error — see logs",
        }.get(daemon.status, "Bridge: unknown")

    def on_toggle(_icon, _item):
        if daemon.status == "running":
            daemon.stop()
        else:
            daemon.start()
        _icon.icon = make_icon_image(daemon.status)
        _icon.update_menu()

    def on_restart(_icon, _item):
        daemon.restart()
        _icon.icon = make_icon_image(daemon.status)
        _icon.update_menu()

    def on_quit(_icon, _item):
        daemon.stop()
        _icon.stop()

    return pystray.Menu(
        pystray.MenuItem(label_status, lambda *_: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open status page", lambda *_: open_status_page()),
        pystray.MenuItem("Edit configuration…", lambda *_: open_config()),
        pystray.MenuItem("View logs", lambda *_: open_logs()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda _: ("Stop bridge" if daemon.status == "running" else "Start bridge"),
            on_toggle,
        ),
        pystray.MenuItem("Restart bridge", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"AlphaX POS Bridge v{__version__}",
                         lambda *_: None, enabled=False),
        pystray.MenuItem("Quit", on_quit),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    log.info("AlphaX POS Bridge tray starting (v%s on %s)",
             __version__, platform.system())

    daemon = BridgeDaemon()
    daemon.start()  # Try to start automatically.

    icon = pystray.Icon(
        "alphax-bridge",
        make_icon_image(daemon.status),
        title=f"AlphaX POS Bridge v{__version__}",
    )
    icon.menu = make_menu(daemon, icon)

    # Periodic status refresh so the icon color reflects reality
    # if the daemon dies on its own.
    def watcher():
        while True:
            time.sleep(5)
            try:
                # If the thread died, mark stopped.
                if daemon.status == "running" and (
                    not daemon.thread or not daemon.thread.is_alive()
                ):
                    log.warning("Bridge thread died unexpectedly")
                    daemon.status = "error"
                    daemon.last_error = "background thread died"
                expected = make_icon_image(daemon.status)
                icon.icon = expected
                icon.update_menu()
            except Exception:
                log.exception("Watcher loop error")

    threading.Thread(target=watcher, daemon=True, name="alphax-watcher").start()

    icon.run()  # Blocks until on_quit


if __name__ == "__main__":
    main()
