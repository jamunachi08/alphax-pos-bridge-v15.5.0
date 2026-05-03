# AlphaX POS Bridge

Universal hardware adapter for the AlphaX POS Vue cashier UI.

Runs as a small local daemon on the cashier device. Lets the browser-based
POS drive **receipt printers, cash drawers, customer pole displays,
weighing scales, and card terminals** — without locking you into any
specific brand.

## ⚠️ This is NOT a Frappe app

Don't try `bench get-app` — bench will reject this with "Not a valid
Frappe App!" because there's no `hooks.py` here. **There shouldn't be.**

The bridge is a regular Python program. It runs on the cashier's
**physical computer** (where the printer is plugged into the USB port),
not on your ERPNext server.

If you don't have any hardware to drive yet, you don't need the bridge
at all. The cashier UI works without it.

## Installing — pick one of three paths

### A) Installer (easiest — for shopkeepers and installers, no Python knowledge needed)

Download the right installer for your OS from the
[Releases page](https://github.com/alphax/alphax-pos-suite/releases):

| OS                  | File                                              |
|---------------------|---------------------------------------------------|
| Windows 10/11       | `AlphaX-POS-Bridge-Setup-X.Y.Z.exe`               |
| macOS 10.15+        | `AlphaX-POS-Bridge-X.Y.Z.pkg`                     |
| Ubuntu/Debian/Mint  | `alphax-pos-bridge_X.Y.Z_amd64.deb`               |
| Any Linux distro    | `AlphaX-POS-Bridge-X.Y.Z-x86_64.AppImage`         |
| Raspberry Pi        | `alphax-pos-bridge_X.Y.Z_arm64.deb`               |

Double-click to install. The installer:

1. Copies the bridge to your Applications / Program Files folder.
2. Launches the **first-run setup wizard** that walks you through:
   - Picking a port (default 8420)
   - Generating an auth token (you paste this into the cashier UI)
   - Scanning your USB hardware so it can write your `config.yaml` for you
3. Configures autostart on login (Windows: Startup folder; macOS: launchd;
   Linux: systemd user service).
4. Adds a **system tray icon** so you can right-click → status, restart,
   edit config, view logs, quit.

That's it. No terminal, no Python, no pip.

### B) `pip install` (developers, advanced users, or air-gapped environments)

If you'd rather use pip:

```bash
pip install /path/to/alphax-pos-bridge[tray]   # NOT bench get-app!
alphax-bridge-wizard      # run the same setup wizard
alphax-bridge-tray        # start the tray app manually
```

Or for headless / server-side / SSH usage:

```bash
pip install alphax-pos-bridge[yaml]
alphax-bridge --discover
$EDITOR ~/.alphax-bridge/config.yaml
alphax-bridge
```

### C) Build the installer yourself (CI / customization)

```bash
git clone <repo>
cd alphax-pos-bridge
make windows    # on Windows
make mac        # on macOS
make linux      # on Linux
```

See `packaging/` for the build scripts. The
[GitHub Actions workflow](.github/workflows/build-installers.yml)
builds all three OS installers automatically on every release tag and
attaches them to the GitHub Release.

## Why this exists

Browsers can't reliably talk to USB or serial hardware. Web Serial /
Web USB exist but don't work in Safari or Firefox, expire on every
session, and don't survive page reloads. A small local daemon is what
every commercial POS does (Square, Toast, Foodics).

## What it supports

- **Printers** — Epson TM-T20III/T88V/m30, Star TSP143III, Bixolon SRP-275,
  Citizen CT-S310, generic ESC/POS (any thermal printer made in the last
  20 years), generic Star, networked ESC/POS over Ethernet.
- **Cash drawers** — kicked through the printer's RJ-11 socket (the
  industry-standard wiring) or directly over USB.
- **Customer pole displays** — Posiflex PD-2800, Logic Controls LD9000,
  any CD5220-compatible VFD, plain-text fallback for the cheapest hardware.
- **Scales** — Mettler-Toledo Prix 3 / 8217, CAS PD-II / AD series,
  Bizerba BS800, generic serial scales.
- **Card terminals** — Geidea, HyperPay, Network International, Payfort
  / Amazon Payment Services, mock (training / demo), and a generic-REST
  fallback for any provider with a JSON HTTP API. See
  [docs/card-terminals.md](docs/card-terminals.md). The skeletons need
  your sandbox credentials and provider-specific certification before
  going live; the architecture and wiring are done.
- **Anything else** — write a 20-line YAML profile and the bridge
  handles it. See [docs/writing-a-profile.md](docs/writing-a-profile.md).

## Quick start

```bash
# Install
pip install alphax-pos-bridge[yaml]

# See what hardware is plugged in
alphax-bridge --discover

# List built-in profiles
alphax-bridge --list-profiles

# Copy a starter config
mkdir -p ~/.alphax-bridge
cp docs/example-configs/cafe.yaml ~/.alphax-bridge/config.yaml
$EDITOR ~/.alphax-bridge/config.yaml

# Run it
alphax-bridge
```

Full walkthrough: [docs/getting-started.md](docs/getting-started.md).

## Documentation

- [Getting started](docs/getting-started.md) — install, first print,
  first drawer kick.
- [Configuring hardware](docs/configuring-hardware.md) — full reference
  for `config.yaml`.
- [Writing a profile](docs/writing-a-profile.md) — how to add support
  for a device that isn't in the built-ins.
- [Card terminals](docs/card-terminals.md) — Geidea, HyperPay, Network
  International, Payfort, generic REST: setup, certification, the
  universal pattern.
- [Troubleshooting](docs/troubleshooting.md) — every common
  permission, codepage, and hardware gotcha.
- [Architecture](docs/architecture.md) — why the bridge looks the way
  it does.
- [HTTP API reference](docs/http-api.md) — for client integrations.

## Example configs

- [Café](docs/example-configs/cafe.yaml) — printer + drawer + pole.
- [Restaurant](docs/example-configs/restaurant.yaml) — front + kitchen
  + bar printers + drawer + pole.
- [Grocery](docs/example-configs/grocery.yaml) — printer + drawer +
  Toledo scale + pole.
- [Dev / no hardware](docs/example-configs/dev-mock.yaml) — file +
  stdout transports for local development.

## Tests

```bash
python -m unittest discover -s tests
```

19 unit tests covering protocols, transports, renderer, registry, HTTP
endpoints, and drawer-through-printer passthrough. No real hardware
needed.

## License

MIT.
