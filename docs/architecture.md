# Architecture

The bridge is intentionally small and boring. It exists to do one thing:
let a browser-based POS UI talk to physical hardware that the browser
itself can't reach.

## Why a bridge instead of Web Serial / Web USB?

Modern browsers expose Web Serial API and Web USB API, but:

- Safari supports neither. iPad-based POS is dead-on-arrival there.
- Firefox supports neither.
- Chrome / Edge support both — but require HTTPS, require a user
  gesture to grant device permission *every session*, and don't survive
  page reloads.

For a real POS that runs all day, you want hardware to "just work"
across reboots, browser updates, and OS restarts. A small local daemon
is the right answer — it's what every commercial POS (Square's
hardware kit, Toast TPS, Foodics bridge, Lightspeed printer hub) does.

## The three-layer model

```
┌─────────────────────────────────────────────────┐
│  Vue cashier UI (in any browser)                │
│  http://your-frappe-server/app/alphax-pos-v2    │
└──────────────────┬──────────────────────────────┘
                   │  fetch() to localhost:8420
                   │  Authorization: Bearer <token>
                   ▼
┌─────────────────────────────────────────────────┐
│  Bridge daemon (this Python package)            │
│  • Routes /print, /drawer, /display, /scale     │
│  • Loads YAML/JSON profiles                     │
│  • Per device: transport + protocol             │
└──────────────────┬──────────────────────────────┘
                   │  bytes
                   ▼
┌─────────────────────────────────────────────────┐
│  Hardware                                       │
│  USB / Serial / Network / Parallel              │
└─────────────────────────────────────────────────┘
```

## Two abstractions: transport and protocol

Inside the bridge, every device is **a Transport plus a Protocol.**

**Transport** is "how do bytes get to the device" — USB, RS-232,
TCP, parallel-port, drawer-through-printer passthrough. The transport
doesn't know what the bytes mean.

**Protocol** is "what bytes mean what action" — print this string,
cut the paper, kick pin 0, show two lines on the display, request a
weight reading. The protocol doesn't know how to deliver bytes.

A Device wraps the two. Every logical action (`print_text`,
`kick_drawer`, `show_lines`, `read_weight`) becomes:

```python
device.transport.write(device.protocol.<action>(...))
```

This pairing means new hardware almost never requires new code:

| Want to support…                                    | What you do                            |
|-----------------------------------------------------|----------------------------------------|
| A new printer brand that speaks ESC/POS             | Add a profile (data only).             |
| A new printer brand that speaks ESC/POS over LAN    | Add a profile, transport: `network`.   |
| A new VFD pole display that speaks CD5220           | Add a profile, transport: `serial`.    |
| A scale that speaks Toledo over Bluetooth-as-COM    | Add a profile, transport: `serial`.    |
| Hardware speaking a totally novel protocol          | Add a Protocol class (~30 lines).      |
| A weird new connection medium (Bluetooth-LE direct) | Add a Transport class (~50 lines).     |

90% of new hardware needs zero code changes — just a profile.

## Why JSON / YAML profiles instead of code?

Three reasons:

1. **End users edit profiles.** A POS reseller deploying your software
   to a hundred outlets shouldn't need to hand-code Python for a quirky
   drawer at one of them.
2. **Profiles ship as data.** A community can submit hardware support
   without touching the bridge codebase.
3. **Configuration drift between outlets stays small.** Each outlet's
   `config.yaml` is mostly "use this profile, plus our specific port
   number" — the deltas are tiny and reviewable.

## Why no async / aiohttp?

The bridge serves at most a few requests per second per terminal. Stdlib
`ThreadingHTTPServer` is more than fast enough, and removes a dependency.
Python 3.10's `BaseHTTPRequestHandler` is 3000 lines of well-tested code
in stdlib. We use it.

If we ever need to serve a fleet of terminals from one bridge — we
won't, but if — switching to FastAPI is mechanical: each endpoint
already follows the same JSON-in / JSON-out shape.

## Why Python and not Node / Go / Rust?

- The serial-port + USB ecosystem in Python (`pyusb`, `pyserial`) is
  battle-tested across decades of POS deployments.
- Frappe / ERPNext shops already have Python on the cashier device.
- One Python install handles every transport and every protocol.
- Rewrites in Go or Rust are tempting for "ship a single binary," and
  PyInstaller is a perfectly fine alternative if that matters.

## What the bridge intentionally doesn't do

- **It doesn't queue.** If the printer is offline, the request fails
  immediately. The Vue SPA's IndexedDB queue is the right place for
  retry logic — it already has the cart state.
- **It doesn't cache.** Each request fully renders and writes. Printer
  buffers + transport latency are well below the human-perception
  threshold.
- **It doesn't authenticate users.** It authenticates that *this Vue UI
  has the shared token*. Per-user cashier identity is the SPA's job;
  the bridge just kicks the drawer when asked.
- **It doesn't talk to card terminals.** Card terminals (Geidea,
  HyperPay, Network International, Payfort) need their own SDK
  integrations — that's a separate concern from the "open / close /
  read" interface this bridge models. Tracked separately in the AlphaX
  POS roadmap.

## Source layout

```
alphax_pos_suite/bridge/
├─ alphax_bridge/
│  ├─ __init__.py        # version
│  ├─ __main__.py        # CLI entry point (python -m alphax_bridge)
│  ├─ transports.py      # USB / Serial / Network / Parallel / Passthrough / File / Stdout
│  ├─ protocols.py       # ESC/POS / Star / VFD / Toledo / CAS / Bizerba / generic / raw
│  ├─ devices.py         # Device class wrapping (transport, protocol)
│  ├─ registry.py        # DeviceRegistry — profiles + config loading
│  ├─ renderer.py        # SPA receipt JSON → ESC/POS bytes
│  └─ server.py          # ThreadingHTTPServer + JSON API
├─ profiles/             # 19 built-in device profiles
├─ docs/
│  ├─ getting-started.md
│  ├─ configuring-hardware.md
│  ├─ writing-a-profile.md
│  ├─ troubleshooting.md
│  ├─ architecture.md          (this file)
│  └─ example-configs/
└─ tests/                # offline tests with FileTransport / StdoutTransport
```
