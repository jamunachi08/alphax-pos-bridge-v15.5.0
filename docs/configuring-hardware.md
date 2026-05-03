# Configuring Hardware

This is the reference for the bridge's `config.yaml` (or `config.json`).

The shape is:

```yaml
bridge:               # how the bridge itself runs
  bind_host:  "127.0.0.1"
  bind_port:  8420
  auth_token: "secret-string"
  cors_origin: "*"

devices:              # one entry per physical device on this terminal
  - name:        "..."     # any unique name you pick
    kind:        "..."     # printer | drawer | display | scale
    profile:     "..."     # which built-in profile to start from
    connection:  { ... }   # OVERRIDES from the profile
    protocol_options: { ... }   # OVERRIDES from the profile's protocol
```

You almost never write a profile from scratch. Pick one with
`alphax-bridge --list-profiles`, then override only what's different
about your situation (port, vendor IDs, baud rate).

---

## The `bridge:` block

| Field         | Default       | Notes                                                        |
|---------------|---------------|--------------------------------------------------------------|
| `bind_host`   | `127.0.0.1`   | Use `0.0.0.0` only if you want other machines on the LAN to reach it. Almost always leave at localhost. |
| `bind_port`   | `8420`        | Pick any free port if 8420 collides.                         |
| `auth_token`  | _(empty)_     | Required in production. Leave empty only on a closed dev box.|
| `cors_origin` | `*`           | Restrict to your Frappe domain in production.                |

---

## Each `devices[]` entry

### `name`
Any unique string. Use what's meaningful: `receipt-printer`,
`kitchen-printer-1`, `bar-printer`, `drawer-front`, `pole-1`, `scale-1`.
The Vue SPA references devices by this name.

### `kind`
One of: `printer`, `drawer`, `display`, `scale`. Tells the server which
operations are valid for this device.

### `profile`
The `profile_id` of a built-in profile. Profiles ship in the bridge's
`profiles/` folder; user-supplied profiles can be loaded from extra
directories with `--profiles-dir /path/to/dir`.

| Hardware kind          | Pick this profile             |
|------------------------|-------------------------------|
| Epson TM-T20III        | `epson-tm-t20iii`             |
| Epson TM-T88V          | `epson-tm-t88v`               |
| Epson TM-m30           | `epson-tm-m30`                |
| Star TSP143III         | `star-tsp143iii`              |
| Bixolon SRP-275III     | `bixolon-srp-275`             |
| Citizen CT-S310II      | `citizen-ct-s310`             |
| Any other 80mm thermal | `generic-80mm-escpos`         |
| Any 58mm thermal       | `generic-58mm-escpos`         |
| Networked printer      | `generic-network-escpos`      |
| Cash drawer via printer| `drawer-via-printer`          |
| Posiflex pole          | `posiflex-pd-2800`            |
| Logic Controls pole    | `logic-controls-ld9000`       |
| Any CD5220 pole        | `generic-vfd-cd5220`          |
| Plain-text pole        | `generic-vfd-text`            |
| Mettler-Toledo Prix 3  | `toledo-prix-3`               |
| CAS PD-II / AD series  | `cas-pd-ii`                   |
| Bizerba BS800          | `bizerba-bs800`               |
| Any other serial scale | `generic-serial-scale`        |

If your hardware isn't here, see
[writing-a-profile.md](./writing-a-profile.md).

### `connection`

Overrides for the transport layer. Each transport has its own keys.

#### USB

```yaml
connection:
  transport:    usb
  vendor_id:    "0x04b8"   # required for USB
  product_id:   "0x0e15"   # required for USB
  interface:    0           # default 0
  out_endpoint: "0x01"      # optional, autodetected
  in_endpoint:  "0x82"      # optional, only needed for read
```

Run `alphax-bridge --discover` to find your IDs.

#### Serial / RS-232

```yaml
connection:
  transport: serial
  port:      "/dev/ttyUSB0"  # Windows: "COM3"; macOS: "/dev/cu.usbserial-XXXX"
  baud:      9600
  bytesize:  8               # 7 or 8
  parity:    "N"             # N | E | O
  stopbits:  1               # 1 or 2
  timeout:   1.0             # seconds
```

#### Network (Ethernet / Wi-Fi)

```yaml
connection:
  transport: network
  host:      "192.168.1.50"
  port:      9100              # ESC/POS Ethernet printers default to 9100
  timeout:   3.0
```

#### Parallel (LPT)

```yaml
connection:
  transport: parallel
  path:      "/dev/lp0"        # Linux; Windows: "LPT1"
```

#### Passthrough (drawer through printer)

```yaml
connection:
  transport: passthrough
  via:       "receipt-printer"  # name of the printer device
```

#### File / stdout (testing)

```yaml
connection:
  transport: file
  path:      "/tmp/test-receipts.txt"
```

```yaml
connection:
  transport: stdout
```

### `protocol_options`

Overrides for the protocol layer. Useful for codepage adjustments,
drawer pin selection, baud-tied timing, etc. Common ones:

```yaml
protocol_options:
  codepage:       22          # PC864 Arabic (or 0=PC437, 16=WPC1252, etc.)
  encoding:       cp864       # python codec matching your codepage
  cut_kind:       partial     # or "full"
  drawer_pin:     0           # most drawers; some need 1
  drawer_on_time: 50
  drawer_off_time: 250
  arabic_shape:   true        # if your printer can't render Arabic natively
  line_width:     20          # for VFD pole displays
```

---

## Worked example: an outlet with mixed brands

```yaml
bridge:
  bind_port: 8420
  auth_token: "yL9oQ2rT8sN..."

devices:
  # Front-of-house: cheap generic 80mm thermal
  - name: front-printer
    kind: printer
    profile: generic-80mm-escpos
    connection:
      transport: usb
      vendor_id:  "0x0fe6"
      product_id: "0x811e"

  # Kitchen: Bixolon impact printer over LAN
  - name: kitchen-printer
    kind: printer
    profile: bixolon-srp-275
    connection:
      transport: network
      host: "10.0.0.21"
      port: 9100

  # Drawer plugged into front printer
  - name: drawer-1
    kind: drawer
    profile: drawer-via-printer
    connection:
      via: front-printer

  # Customer pole on USB-to-serial dongle
  - name: pole-1
    kind: display
    profile: generic-vfd-cd5220
    connection:
      port: "/dev/ttyUSB0"

  # Toledo grocery scale
  - name: scale-1
    kind: scale
    profile: toledo-prix-3
    connection:
      port: "/dev/ttyUSB1"
```

That's it. Three brands, four protocols, four transport types, all
reachable from the same Vue UI through one bridge.

---

## Reloading config

The bridge reads `config.yaml` at startup. To pick up changes:

```bash
# foreground:
Ctrl-C, then re-run `alphax-bridge`

# systemd:
sudo systemctl restart alphax-bridge

# task-scheduler / NSSM:
restart the service from the GUI
```

There's no hot-reload by design — POS hardware shouldn't change behavior
mid-shift.
