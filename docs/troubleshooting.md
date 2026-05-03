# Troubleshooting

The bridge tries to fail loudly with useful errors, but hardware is hardware
— sometimes the problem is in the OS or the cable. This file covers the
common cases.

## "USB device 04b8:0e15 not found"

The bridge can't see your printer over USB. Possible causes, in order of
likelihood:

1. **The printer is off.** Check the power LED.
2. **The cable is loose** (especially on the printer-end RJ-11 / USB-B
   connector). Reseat it.
3. **Wrong vendor/product ID.** Run `alphax-bridge --discover` again with
   the device powered on and the bridge user account; copy the IDs as-is.
4. **A driver from the vendor is holding the device** on Windows. Open
   Device Manager, find the printer, change its driver to "WinUSB" via
   Zadig (https://zadig.akeo.ie/). Many cheap thermal printers come with
   a "POS80" driver that blocks raw USB access.
5. **Permissions on Linux** — see the next section.

## Linux USB permissions

By default Linux gives raw USB device nodes 660 root:root. The bridge
running as your user account can't open them. Two clean fixes:

### Option A: udev rule (recommended)

Create `/etc/udev/rules.d/99-alphax-bridge.rules`:

```
# Epson TM-* receipt printers
SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", MODE="0666", GROUP="plugdev"

# Star Micronics
SUBSYSTEM=="usb", ATTRS{idVendor}=="0519", MODE="0666", GROUP="plugdev"

# Bixolon
SUBSYSTEM=="usb", ATTRS{idVendor}=="1504", MODE="0666", GROUP="plugdev"

# Citizen
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d90", MODE="0666", GROUP="plugdev"

# (add more lines for other brands as you adopt them)
```

Then:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and re-plug the printer. Verify:
```bash
lsusb -v -d 04b8: | grep iManufacturer
```

### Option B: run the bridge as root

Quick and dirty. Put `User=root` in the systemd unit. **Don't do this in
production** — the bridge listens on a port and you don't want it
running as root.

## Linux serial-port permissions

Add the bridge user to the `dialout` group (Debian/Ubuntu) or `uucp`
(Arch / older distros):

```bash
sudo usermod -aG dialout $USER
# log out and back in
```

## "Permission denied: '/dev/ttyUSB0'"

Same as above. The bridge user is not in `dialout`/`uucp`.

## Receipt prints garbage characters

Codepage mismatch. The printer is writing bytes you sent as if they
were a different character table.

The two most common cases in KSA / GCC:

- **Latin text comes out as accented gibberish.** Use codepage 0 (PC437)
  with encoding `cp437`, or codepage 16 (WPC1252) with encoding `cp1252`.
- **Arabic text comes out as boxes or random Latin.** Your printer
  probably has codepage 22 (PC864 Arabic). Set:
  ```yaml
  protocol_options:
    codepage: 22
    encoding: cp864
  ```
  If the printer doesn't have an Arabic codepage at all (cheap ESC/POS
  clones), install the `arabic` extra:
  ```bash
  pip install alphax-pos-bridge[arabic]
  ```
  And set:
  ```yaml
  protocol_options:
    arabic_shape: true
  ```
  This pre-shapes Arabic text in software so it prints visually correct
  on a Latin-only printer.

The full list of ESC/POS codepages is in the Epson FS-D documentation;
the values you'll usually need are:
| Code | Name              |
|------|-------------------|
| 0    | PC437 (USA)       |
| 16   | WPC1252           |
| 17   | PC866 Cyrillic    |
| 18   | PC852 Latin 2     |
| 19   | PC858 (Euro)      |
| 22   | PC864 Arabic      |
| 23   | PC862 Hebrew      |
| 36   | PC1257 Baltic     |

## Cutter doesn't cut, just feeds paper

Try `cut_kind: full` in `protocol_options`. Some printers ignore the
partial-cut command. Also confirm the cutter isn't physically jammed —
the LED on most printers blinks red if so.

## Drawer doesn't open

In order of likelihood:

1. **Cable plugged into wrong jack on the printer.** Most printers have
   one RJ-11 jack labelled "DK" or "Cash Drawer." If your printer has
   two, you may need `drawer_pin: 1` instead of the default `0`.
2. **Wrong drawer voltage.** Some old drawers need 24V; most printers
   only output 12V. Check the drawer's spec sheet.
3. **Wrong bridge config.** Confirm your `drawer-1` device's `via:` field
   names a printer that's actually connected and printing.
4. **Drawer key is in "lock" position.** Turn it to the middle position.

## Pole display shows nothing

1. Confirm the cable is the data cable, not the power-only USB cable
   (some Posiflex displays come with both — they look identical).
2. Try the fallback `generic-vfd-text` profile. Many cheap displays
   don't speak full CD5220 but do accept plain CR-LF lines.
3. Verify baud rate. Default is 9600 but some displays ship at 19200 or
   even 2400.
4. Try swapping `parity` between `N` and `E`. Some Posiflex units
   default to even parity.

## Scale always returns null

1. Run `alphax-bridge --verbose` to see what raw bytes are arriving.
2. Try toggling `continuous: true` in the scale's `protocol_options`.
   Some scales never wait for an ENQ; they push weight readings ten
   times a second on their own.
3. Try the other scale profile. If `toledo-9091` doesn't parse, try
   `cas-ad` and `bizerba-bp`.
4. Check the scale's menu for "RS-232 protocol" or "comms format" — set
   it to "8217" / "Toledo continuous" / "BPlus" depending on which
   profile you're targeting.

## Auto-start the bridge on boot

### Linux (systemd)

`/etc/systemd/system/alphax-bridge.service`:

```ini
[Unit]
Description=AlphaX POS Hardware Bridge
After=network.target

[Service]
Type=simple
User=alphax
Group=plugdev
ExecStart=/home/alphax/.alphax-bridge/venv/bin/alphax-bridge
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now alphax-bridge
sudo systemctl status alphax-bridge
```

### macOS (launchd)

`~/Library/LaunchAgents/com.alphax.bridge.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0"><dict>
  <key>Label</key>     <string>com.alphax.bridge</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/alphax/.alphax-bridge/venv/bin/alphax-bridge</string>
  </array>
  <key>RunAtLoad</key>          <true/>
  <key>KeepAlive</key>          <true/>
  <key>StandardOutPath</key>    <string>/tmp/alphax-bridge.log</string>
  <key>StandardErrorPath</key>  <string>/tmp/alphax-bridge.err</string>
</dict></plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.alphax.bridge.plist
```

### Windows

The simplest path is **NSSM** (https://nssm.cc/):

```
nssm install alphax-bridge
   Path:        C:\path\to\python.exe
   Arguments:   -m alphax_bridge
   Startup directory: C:\path\to\AlphaXPOS-main\alphax_pos_suite\bridge
nssm start alphax-bridge
```

Or the built-in Task Scheduler with "At startup" trigger.

## "Address already in use"

Another process is using port 8420. Either kill it or change the bridge
port in `config.yaml` (and tell the Vue UI the new port in
**Settings → Hardware**).

```bash
# find what's on the port
lsof -i :8420   # macOS / Linux
netstat -ano | findstr :8420   # Windows
```

## Where are the logs?

The bridge logs to stdout by default. If you ran it via systemd:

```bash
sudo journalctl -u alphax-bridge -f
```

NSSM on Windows: configure the I/O tab to send stdout/stderr to log files.

For verbose output, run with `-v`:

```bash
alphax-bridge --verbose --config ~/.alphax-bridge/config.yaml
```
