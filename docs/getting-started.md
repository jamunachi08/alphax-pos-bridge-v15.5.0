# Getting Started — AlphaX POS Bridge

The bridge is a tiny Python daemon that runs on your cashier device
(Windows / macOS / Linux / Raspberry Pi) and lets the AlphaX POS Vue UI
talk to your physical hardware: receipt printers, cash drawers, customer
pole displays, weighing scales.

It does **not** require root, does **not** install any kernel drivers,
does **not** lock you into specific hardware brands. Any device that
speaks one of the standard protocols (ESC/POS, Star line-mode, CD5220,
Toledo, CAS, Bizerba, plain-text serial) works through configuration.

## 1. Prerequisites

- Python 3.10 or newer.
- The user account that runs the bridge needs read/write access to your
  USB / serial devices. Linux: see [troubleshooting](./troubleshooting.md#linux-usb-permissions);
  Windows: install your printer's USB driver from the vendor first.

## 2. Install

```bash
# Recommended: virtualenv
python3 -m venv ~/.alphax-bridge/venv
source ~/.alphax-bridge/venv/bin/activate     # Linux/macOS
# or:  ~\.alphax-bridge\venv\Scripts\activate   # Windows PowerShell

pip install --upgrade pip
pip install alphax-pos-bridge[yaml]
```

If the package isn't on PyPI yet (early access), install from the source
folder shipped in the AlphaX POS Suite zip:

```bash
cd path/to/AlphaXPOS-main/alphax_pos_suite/bridge
pip install -e .[yaml]
```

For Arabic-only environments where your printer doesn't have an Arabic
codepage, also install:

```bash
pip install alphax-pos-bridge[arabic]
```

## 3. See what's connected

Plug in your devices and run:

```bash
alphax-bridge --discover
```

You'll get a JSON dump of every USB device and serial port the OS sees,
e.g.:

```json
{
  "usb": [
    {"vendor_id":"0x04b8","product_id":"0x0e15",
     "manufacturer":"EPSON","product":"TM-T20III"}
  ],
  "serial": [
    {"port":"/dev/ttyUSB0","description":"USB Serial","manufacturer":"FTDI"}
  ]
}
```

Note the values that match your hardware — you'll use them in the next step.

## 4. Pick a config

The bridge ships with example configs for cafés, restaurants, grocery
lanes, and a "dev-mock" config that uses no real hardware (good for
testing). Copy the closest match:

```bash
mkdir -p ~/.alphax-bridge
cp docs/example-configs/cafe.yaml ~/.alphax-bridge/config.yaml
$EDITOR ~/.alphax-bridge/config.yaml
```

Adjust three things:

1. `auth_token` — pick a long random string. The Vue SPA needs the same value.
2. The `port:` lines under each `connection:` — replace with what
   `--discover` showed you.
3. (Optional) Pick a different printer / display / scale profile if you
   have a different model. Run `alphax-bridge --list-profiles` to see all
   built-in profiles.

## 5. Start the bridge

```bash
alphax-bridge
```

You should see:

```
2026-04-26 10:30:12 INFO   alphax-bridge   loaded config from /home/me/.alphax-bridge/config.yaml
2026-04-26 10:30:12 INFO   alphax-bridge.registry  device added: front-printer (printer, usb/escpos)
2026-04-26 10:30:12 INFO   alphax-bridge.registry  device added: drawer-1 (drawer, passthrough/escpos)
2026-04-26 10:30:12 INFO   alphax-bridge.registry  device added: pole-1 (display, serial/vfd-cd5220)
2026-04-26 10:30:12 INFO   alphax-bridge.server    alphax bridge listening on http://127.0.0.1:8420
```

Leave it running.

## 6. Test from another terminal

```bash
# What devices does the bridge see?
curl -H "Authorization: Bearer change-me-to-something-secret" \
     http://localhost:8420/devices

# Print a test receipt
curl -X POST http://localhost:8420/test \
     -H "Authorization: Bearer change-me-to-something-secret" \
     -H "Content-Type: application/json" \
     -d '{"device": "front-printer", "action": "print"}'

# Open the drawer
curl -X POST http://localhost:8420/test \
     -H "Authorization: Bearer change-me-to-something-secret" \
     -H "Content-Type: application/json" \
     -d '{"device": "drawer-1", "action": "kick"}'

# Show two lines on the pole display
curl -X POST http://localhost:8420/test \
     -H "Authorization: Bearer change-me-to-something-secret" \
     -H "Content-Type: application/json" \
     -d '{"device": "pole-1", "action": "display"}'
```

Every test that succeeds confirms one piece of the stack is working: USB
permissions, serial port access, profile match, protocol commands.

## 7. Tell the AlphaX POS UI about it

In the Vue cashier, open **Settings → Hardware** and enter:

- Bridge URL: `http://localhost:8420`
- Auth token: the same token you put in `config.yaml`

Click **Connect**. The UI will list your devices and let you map "Receipt
printer" → `front-printer`, "Cash drawer" → `drawer-1`, etc.

After that:
- Cash sales auto-print receipts and auto-open the drawer.
- The pole display mirrors the cart.
- Weighed items read live weight from the scale.

## 8. Auto-start on boot

So the bridge starts whenever the cashier turns the device on:

- **Linux** (systemd) — see
  [./troubleshooting.md#linux-autostart](./troubleshooting.md#linux-autostart)
- **macOS** (launchd) —
  [./troubleshooting.md#macos-autostart](./troubleshooting.md#macos-autostart)
- **Windows** (Task Scheduler / NSSM service) —
  [./troubleshooting.md#windows-autostart](./troubleshooting.md#windows-autostart)

## What's next

- **My device isn't in `--list-profiles`** —
  see [writing-a-profile.md](./writing-a-profile.md). Most "exotic"
  devices speak ESC/POS or a serial line protocol; you can usually wire
  one up in 20 lines of YAML.
- **Why does this exist? What's it doing?** —
  see [architecture.md](./architecture.md).
- **Stuck on permissions, COM ports, codepages?** —
  see [troubleshooting.md](./troubleshooting.md).
