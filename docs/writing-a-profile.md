# Writing a Custom Hardware Profile

If your hardware isn't in `--list-profiles`, write a profile yourself.
Almost every commercial POS peripheral made in the last 25 years speaks
one of these protocols:

- **ESC/POS** — almost every receipt printer
- **Star line-mode** — Star printers
- **CD5220 / Aedex** — almost every VFD pole display
- **Toledo 8217 / 9091** — many grocery scales
- **CAS AD** — CAS scales
- **Bizerba BPlus** — Bizerba scales
- **Generic line** — anything that takes a CR-LF terminated string

A profile is just a JSON or YAML file in a folder you point the bridge at:

```bash
alphax-bridge --profiles-dir ~/my-profiles --config ~/.alphax-bridge/config.yaml
```

## Anatomy of a profile

```yaml
profile_id:   "my-weird-printer"      # unique id used in config.yaml
label:        "Weird Brand WB-300"    # human-readable
kind:         "printer"               # printer | drawer | display | scale
vendor:       "Weird Brand"
model:        "WB-300"
paper_columns: 42                     # printers only
notes: |
  Anything you want here. Helpful when you hand the profile off to
  someone else.

connection:
  transport:  "usb"
  vendor_id:  "0x1234"
  product_id: "0x5678"

protocol:
  name: "escpos"
  options:
    codepage:       0
    encoding:       "cp437"
    cut_kind:       "partial"
    drawer_pin:     0
```

Save as `~/my-profiles/my-weird-printer.yaml`, then in `config.yaml`:

```yaml
devices:
  - name:    front-printer
    kind:    printer
    profile: my-weird-printer
```

## Step-by-step: an unknown receipt printer

You bought a no-name 80mm thermal printer. The vendor has no SDK. The
manual says "ESC/POS compatible." Here's how to wire it up in five
minutes:

1. Plug it in. Run `alphax-bridge --discover`. Note the `vendor_id` and
   `product_id`.

2. Try the generic profile first — most ESC/POS printers work as-is:

   ```yaml
   devices:
     - name:    front-printer
       kind:    printer
       profile: generic-80mm-escpos
       connection:
         vendor_id:  "0x0fe6"     # from --discover
         product_id: "0x811e"
   ```

3. Restart the bridge, then:

   ```bash
   curl -X POST http://localhost:8420/test \
        -H "Authorization: Bearer your-token" \
        -d '{"device":"front-printer","action":"print"}'
   ```

4. If you see a test receipt come out, you're done.

5. If garbage comes out instead, it's a codepage mismatch. The most
   common: the printer expects WPC1252 for Latin Europe, or PC864 /
   ISO-8859-6 for Arabic, or GB18030 for Chinese, etc. Check your
   manual for "code page" or "character table." Then add:

   ```yaml
   protocol_options:
     codepage: 22       # PC864 Arabic
     encoding: cp864
   ```

6. If the cutter doesn't fire, your printer wants `full` cuts:

   ```yaml
   protocol_options:
     cut_kind: full
   ```

7. If your drawer doesn't kick, try the other pin:

   ```yaml
   protocol_options:
     drawer_pin: 1
   ```

That's the entire process. You don't write a single line of code. Save
your tweaks as a profile so the next outlet running the same hardware
inherits them.

## Step-by-step: an unknown serial scale

Your manual says it sends weight data over RS-232 at 9600 baud, with a
specific frame format. Pick the closest built-in protocol:

- If the manual says "Toledo," "8217," "9091," "continuous": use
  `toledo-9091`.
- If it says "CAS" or shows lines like `ST,GS,  1.234 kg`: use `cas-ad`.
- If it says "Bizerba BPlus": use `bizerba-bp`.
- Otherwise start with `toledo-9091`; the parser handles the most common
  STX-ETX framing.

Configure baud, parity, bytesize, stopbits from your manual. Default for
most scales is `9600 7-E-1` or `9600 8-N-1`. Try one, then the other.

```yaml
devices:
  - name:    scale-1
    kind:    scale
    profile: generic-serial-scale
    connection:
      port:     "/dev/ttyUSB1"
      baud:     9600
      bytesize: 7
      parity:   "E"
      stopbits: 1
```

Test:

```bash
curl -H "Authorization: Bearer your-token" \
     "http://localhost:8420/scale?device=scale-1"
```

If you get back `{"weight": null}`, the protocol or framing doesn't
match. Try the next one. If none of the built-ins work, your scale
needs a new protocol added — see "Adding a new protocol to the bridge"
below.

## Step-by-step: an unknown pole display

Most 2x20 pole displays speak **CD5220** (the Epson DM-D protocol that
became the de-facto standard). Try `generic-vfd-cd5220` first. If the
display does nothing or shows garbage, fall back to `generic-vfd-text`,
which sends plain CR-LF separated lines and works on the cheapest
displays.

If your display has a custom protocol from the vendor manual (ESC
sequences different from CD5220), see "Adding a new protocol" below.

## Adding a new protocol to the bridge

If your hardware speaks something exotic that none of the built-ins
support, add a new Protocol class. It's about 30 lines:

1. In `alphax_bridge/protocols.py`, add a class:

   ```python
   class MyExoticProtocol(Protocol):
       name = "my-exotic"

       def __init__(self, **opts):
           self.opts = opts

       def encode_text(self, text, **opts):
           return text.encode("ascii", errors="replace")

       def open_drawer(self, pin=0):
           # whatever bytes your device wants
           return b"\xee\x01" + bytes([pin])

       # ... only implement the actions your device does
   ```

2. Register it at the bottom of the file:

   ```python
   PROTOCOLS["my-exotic"] = MyExoticProtocol
   ```

3. Reference it in your profile:

   ```yaml
   protocol:
     name: "my-exotic"
     options:
       some_option: 42
   ```

That's it. Your new protocol now works with every transport
(USB / serial / network / parallel / passthrough).

## Submitting profiles back

If you write a profile for hardware others might use, please send it
back upstream so it ships with the next release. Include the vendor,
model, the exact protocol options that worked, and any quirks you
encountered.
