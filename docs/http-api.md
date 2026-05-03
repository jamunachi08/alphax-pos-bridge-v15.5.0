# HTTP API Reference

Base URL: `http://localhost:8420` (or whatever you configured).
All endpoints accept and return JSON. If `auth_token` is set in
`config.yaml`, every request must include `Authorization: Bearer <token>`.

## `GET /`

Liveness check. Returns:

```json
{
  "name":     "alphax-pos-bridge",
  "version":  "1.0.0",
  "devices":  3,
  "profiles": 19
}
```

## `GET /devices`

List configured devices and their state.

```json
{
  "devices": [
    {
      "name":      "front-printer",
      "kind":      "printer",
      "transport": "usb",
      "protocol":  "escpos",
      "open":      true,
      "profile":   "epson-tm-t20iii"
    },
    ...
  ],
  "profiles": [...]
}
```

## `GET /profiles`

List built-in and user-supplied profiles available for use in
`config.yaml`. Returns:

```json
{
  "profiles": [
    {"profile_id": "epson-tm-t20iii", "label": "Epson TM-T20III (USB)",
     "kind": "printer", "vendor": "Epson", "model": "TM-T20III",
     "protocol": "escpos"},
    ...
  ]
}
```

## `GET /discover`

Auto-detect USB / serial / network candidates plugged into this device:

```json
{
  "usb":    [...],
  "serial": [...],
  "network": []
}
```

Useful for the "hardware setup wizard" UI.

## `POST /print`

Print a structured receipt. Body:

```json
{
  "device": "front-printer",
  "receipt": {
    "header": {
      "store_name": "Café Loyalty",
      "branch":     "Olaya",
      "vat_no":     "300-...",
      "phone":      "+966 ..."
    },
    "meta": {
      "invoice_no": "SINV-2026-0001",
      "datetime":   "2026-04-26T10:00:00+03:00",
      "cashier":    "ahmed",
      "terminal":   "TERM-01",
      "table":      "T5",
      "customer":   "Walk-in"
    },
    "items": [
      {"name": "Cappuccino", "qty": 2, "rate": 18.00, "amount": 36.00,
       "modifiers": [{"option": "Oat milk", "price_delta": 1}]}
    ],
    "totals": {
      "subtotal": 42.00, "discount": 2.00, "tax": 6.00, "total": 46.00,
      "tendered": 50.00, "change": 4.00,
      "tax_breakdown": [{"label": "VAT 15%", "amount": 6.00}]
    },
    "payments": [{"mode": "Cash", "amount": 50.00}],
    "loyalty":  {"earned": 4, "redeemed": 0, "balance": 542},
    "footer":   {"line1": "Thank you!", "qr": "ZATCA-base64-tlv"}
  }
}
```

The renderer adapts the receipt to whatever protocol the named device
speaks. ESC/POS prints styled output (bold TOTAL, ZATCA QR, invoice
barcode, configurable cut). Other protocols fall back to plain text.

Returns:

```json
{"ok": true, "device": "front-printer", "bytes": 412}
```

## `POST /drawer`

Kick a cash drawer.

```json
{"device": "drawer-1", "pin": 0}
```

`pin` is optional (0 or 1) — defaults to whatever the device's profile
specifies.

## `POST /display`

Update the customer pole display.

The bridge handles common cart-display patterns:

```json
{"device": "pole-1", "action": "line_total",
 "name": "Latte", "amount": 20.00, "currency": "SAR "}

{"device": "pole-1", "action": "subtotal", "amount": 42.00, "currency": "SAR "}
{"device": "pole-1", "action": "due",      "amount": 46.00, "currency": "SAR "}
{"device": "pole-1", "action": "change",   "amount":  4.00, "currency": "SAR "}
{"device": "pole-1", "action": "thanks"}

{"device": "pole-1", "action": "raw", "top": "Custom top line", "bottom": "Custom bot"}
```

## `GET /scale?device=<name>&timeout=<seconds>`

Read a single weight reading from a scale. Returns:

```json
{
  "device": "scale-1",
  "weight": {
    "weight": 1.234,
    "unit":   "kg",
    "stable": true
  }
}
```

If the scale didn't respond, `weight` is `null`. Re-call.

## `POST /test`

Run a built-in self-test for one device.

```json
{"device": "front-printer", "action": "print"}    // prints a test receipt
{"device": "drawer-1",      "action": "kick"}     // opens the drawer
{"device": "pole-1",        "action": "display"}  // shows "test ok" on the pole
{"device": "scale-1",       "action": "weight"}   // reads + returns one weight
```

## `POST /raw`

Truly opaque passthrough. The SPA sends hex bytes; the bridge writes
them verbatim to the device.

```json
{"device": "front-printer", "data_hex": "1b40 1b6101 4865 6c6c 6f0a"}
```

Useful as an escape hatch when you're debugging or have an exotic
device that the standard actions don't cover.
