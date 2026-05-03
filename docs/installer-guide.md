# Installing AlphaX POS Bridge from the Installer

This guide is for shopkeepers, cashiers, and IT installers who just
want to **install the bridge and have it work**, without dealing with
Python, pip, or the command line.

If you're a developer who'd rather use pip, see the main
[README](../README.md) for the developer install path.

## Before you start

- A computer that will live next to the cashier's screen (Windows, Mac,
  or Linux).
- The receipt printer and any other USB hardware, plugged in.
- An auth token will be generated for you — write it down or have a
  notepad open during install. You'll paste it into the cashier UI.
- Internet access on this computer for the install (the bridge itself
  works offline after that).

## Windows

1. Download `AlphaX-POS-Bridge-Setup-X.Y.Z.exe` from the
   [Releases page](https://github.com/alphax/alphax-pos-suite/releases).
2. Double-click the installer.
3. **Important:** if Windows shows "Windows protected your PC" warning
   (because we don't have an Extended Validation cert yet for code
   signing), click **More info** → **Run anyway**. We're working on
   getting a signed certificate; until then this warning is normal.
4. Accept the license, choose install location.
5. Check **Start AlphaX POS Bridge automatically when I sign in** if
   you want autostart (recommended).
6. Click Install.
7. The setup wizard launches. Walk through the 4 screens — port,
   auth token (copy this!), hardware scan, finish.
8. A small green dot appears in your system tray (bottom-right of
   the screen, near the clock). Right-click for status, restart,
   edit config, view logs.

To uninstall: Settings → Apps → AlphaX POS Bridge → Uninstall.

## macOS

1. Download `AlphaX-POS-Bridge-X.Y.Z.pkg`.
2. Double-click. **Important:** macOS may say "AlphaX POS Bridge can't
   be opened because it is from an unidentified developer" (because we
   don't yet have an Apple Developer ID). Workaround: right-click the
   .pkg → **Open** → click **Open** in the dialog.
3. Walk through the installer (Welcome → License → Install location → Install).
4. The bridge installs to `/Applications/AlphaX POS Bridge.app`.
5. The setup wizard launches. Walk through the 4 screens.
6. A small green dot appears in your menu bar (top-right). Click for
   options.

The bridge auto-starts on login via launchd. To disable autostart:
```
launchctl unload ~/Library/LaunchAgents/com.alphax.pos.bridge.plist
```

To uninstall:
```
launchctl unload ~/Library/LaunchAgents/com.alphax.pos.bridge.plist
rm ~/Library/LaunchAgents/com.alphax.pos.bridge.plist
sudo rm -rf "/Applications/AlphaX POS Bridge.app"
```

## Linux (Ubuntu / Debian / Linux Mint / Raspberry Pi OS)

### .deb (recommended on Debian-family distros)

```bash
sudo dpkg -i alphax-pos-bridge_X.Y.Z_amd64.deb
sudo apt --fix-broken install         # if dpkg complains about deps
```

The package installs to `/opt/alphax-pos-bridge/`, adds a desktop entry,
and registers a systemd user service (not enabled by default).

To enable autostart and start now:
```bash
systemctl --user enable --now alphax-pos-bridge
```

To use USB / serial hardware, your user needs to be in the `dialout`
and `plugdev` groups. **One-time** (then log out and back in):
```bash
sudo usermod -aG dialout $USER
sudo usermod -aG plugdev $USER
```

To uninstall:
```bash
systemctl --user disable --now alphax-pos-bridge
sudo dpkg -r alphax-pos-bridge
```

### AppImage (any distro, no install)

The AppImage is a single executable that needs no installer. Download,
make it executable, run it:

```bash
chmod +x AlphaX-POS-Bridge-X.Y.Z-x86_64.AppImage
./AlphaX-POS-Bridge-X.Y.Z-x86_64.AppImage
```

The AppImage doesn't auto-start on login — you'd need to add it to your
desktop's autostart yourself, or use the .deb method above which handles
that for you.

### Raspberry Pi

Use the arm64 .deb on Raspberry Pi OS (64-bit). On 32-bit Raspberry Pi
OS, install via `pip install alphax-pos-bridge` instead — the bundled
PyInstaller build is 64-bit only.

## After installing — connecting the cashier UI

1. Open your AlphaX cashier UI in a browser on the **same machine** as
   the bridge.
2. Click the hardware pill in the sidebar (the small icon shaped like
   a printer/dot).
3. Bridge URL: `http://localhost:8420` (this is the default).
4. Auth token: paste the one the wizard showed you.
5. Click **Connect**.
6. The hardware list should populate. Map each device to its role
   (Receipt printer, Cash drawer, Customer display, etc).
7. Click **Test print** to confirm it works end-to-end.

## Troubleshooting

**Tray icon never appears**
- Windows: check Task Manager → Background processes → look for
  `alphax-bridge.exe`. If not there, try launching from Start Menu.
- macOS: check Activity Monitor for `alphax-bridge`. Make sure your
  menu bar isn't hiding the icon (hold Cmd and drag).
- Linux: `systemctl --user status alphax-pos-bridge` → look for errors.

**Tray icon is red**
- Right-click → **View logs** to see what's wrong.
- Most common cause: another program is using port 8420. Edit the
  config (right-click → Edit configuration) and change `bind_port` to
  something else like 8421, then update the cashier UI to match.

**Hardware scan finds nothing**
- Make sure the device is plugged in and powered on.
- Windows: install the vendor's USB driver (Epson, Star, etc — they
  ship Windows drivers; without them the device shows up as "Unknown
  USB Device" and we can't read its IDs).
- Linux: check that you're in the `dialout` and `plugdev` groups
  (`groups | grep dialout`). If not, add yourself and log out + back in.

**Need help**
- File logs: `~/.alphax-bridge/logs/bridge.log`
- Config:    `~/.alphax-bridge/config.yaml`
- Auth token: `~/.alphax-bridge/auth.token`
- Open an issue at https://github.com/alphax/alphax-pos-suite/issues
  with the log output.
