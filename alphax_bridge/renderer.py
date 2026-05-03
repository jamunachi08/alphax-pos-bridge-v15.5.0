"""
Receipt renderer.

The SPA sends a structured receipt:

  {
    "header": {
      "store_name":  "Café Loyalty",
      "branch":      "Riyadh - Olaya",
      "address":     "Olaya St, Riyadh",
      "vat_no":      "300-...",
      "phone":       "+966 ...",
      "logo_qr":     null
    },
    "meta": {
      "invoice_no":   "SINV-2026-0001",
      "datetime":     "2026-04-26T10:00:00+03:00",
      "cashier":      "ahmed",
      "terminal":     "TERM-01",
      "table":        "T5",
      "customer":     "Walk-in"
    },
    "items": [
      {"name":"Cappuccino","qty":2,"rate":18.00,"amount":36.00,"modifiers":[{"option":"Oat milk","price_delta":1}]},
      ...
    ],
    "totals": {
      "subtotal":   42.00,
      "discount":   2.00,
      "service":    0,
      "tip":        0,
      "tax":        6.00,
      "total":     46.00,
      "tendered":  50.00,
      "change":     4.00,
      "tax_breakdown": [{"label":"VAT 15%","amount":6.00}]
    },
    "payments": [{"mode":"Cash","amount":50.00}],
    "loyalty":  {"earned": 4, "redeemed": 0, "balance": 542},
    "footer":   {"line1":"Thank you!", "qr": "ZATCA-base64-tlv"}
  }

The renderer takes that and the device's protocol, and produces a stream of
bytes the printer can chew. Works for ESC/POS today; for `generic-line` it
falls back to plain text.

Layout is paper-width aware (32 / 42 / 48 columns)."""
from __future__ import annotations

from typing import Optional

from .protocols import EscposProtocol, NotSupported, Protocol


# 80mm thermal printers usually print 42 chars wide at default font;
# 58mm thermals are 32. Configurable per profile.
DEFAULT_WIDTH = 42


def _hr(width: int) -> str:
    return "-" * width


def _fmt_money(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _two_col(left: str, right: str, width: int) -> str:
    space = max(1, width - len(left) - len(right))
    return left + (" " * space) + right


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in (text or "").split():
        if len(line) + len(word) + 1 > width:
            if line:
                out.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        out.append(line)
    return out or [""]


def render_text_lines(receipt: dict, width: int = DEFAULT_WIDTH) -> list[str]:
    """Render a receipt to plain text lines. The protocol-specific renderer
    can either send these as-is (generic-line) or use them as the data
    source for ESC/POS bytes."""
    lines: list[str] = []
    h = receipt.get("header", {})
    m = receipt.get("meta", {})
    items = receipt.get("items", [])
    t = receipt.get("totals", {})
    payments = receipt.get("payments", [])
    f = receipt.get("footer", {})
    loyalty = receipt.get("loyalty", {})

    # Header
    if h.get("store_name"):
        for ln in _wrap(h["store_name"], width):
            lines.append(ln.center(width))
    if h.get("branch"):
        for ln in _wrap(h["branch"], width):
            lines.append(ln.center(width))
    if h.get("address"):
        for ln in _wrap(h["address"], width):
            lines.append(ln.center(width))
    if h.get("vat_no"):
        lines.append(f"VAT: {h['vat_no']}".center(width))
    if h.get("phone"):
        lines.append(f"Tel: {h['phone']}".center(width))

    lines.append("")
    lines.append(_hr(width))

    # Meta
    if m.get("invoice_no"):
        lines.append(_two_col("Invoice", m["invoice_no"], width))
    if m.get("datetime"):
        lines.append(_two_col("Date", str(m["datetime"])[:19], width))
    if m.get("cashier"):
        lines.append(_two_col("Cashier", m["cashier"], width))
    if m.get("terminal"):
        lines.append(_two_col("Terminal", m["terminal"], width))
    if m.get("table"):
        lines.append(_two_col("Table", m["table"], width))
    if m.get("customer"):
        lines.append(_two_col("Customer", m["customer"], width))
    lines.append(_hr(width))

    # Items header
    lines.append(_two_col("Item", "Total", width))
    lines.append("")

    for it in items:
        name = it.get("name", "")
        qty = it.get("qty", 1)
        rate = it.get("rate", 0)
        amount = it.get("amount", qty * rate)

        # Item name (multi-line if long)
        wrapped = _wrap(name, width - 12)
        for i, ln in enumerate(wrapped):
            if i == 0:
                lines.append(_two_col(ln, _fmt_money(amount), width))
            else:
                lines.append(ln)
        # Qty x rate sub-line
        lines.append(f"  {qty} x {_fmt_money(rate)}")
        # Modifiers indented
        for mod in it.get("modifiers", []) or []:
            lab = mod.get("option") or mod.get("label") or ""
            delta = mod.get("price_delta", 0)
            if delta:
                lines.append(f"    + {lab}  ({_fmt_money(delta)})")
            else:
                lines.append(f"    + {lab}")

    lines.append(_hr(width))

    # Totals
    if t.get("subtotal") is not None:
        lines.append(_two_col("Subtotal", _fmt_money(t["subtotal"]), width))
    if t.get("discount"):
        lines.append(_two_col("Discount", "-" + _fmt_money(t["discount"]), width))
    if t.get("service"):
        lines.append(_two_col("Service", _fmt_money(t["service"]), width))
    if t.get("tip"):
        lines.append(_two_col("Tip", _fmt_money(t["tip"]), width))
    for tb in t.get("tax_breakdown") or []:
        lines.append(_two_col(tb.get("label", "Tax"), _fmt_money(tb.get("amount", 0)), width))
    if t.get("total") is not None:
        lines.append(_two_col("TOTAL", _fmt_money(t["total"]), width))
    lines.append("")

    # Payments
    for p in payments:
        lines.append(_two_col(p.get("mode", "Paid"), _fmt_money(p.get("amount", 0)), width))
    if t.get("tendered") is not None:
        lines.append(_two_col("Tendered", _fmt_money(t["tendered"]), width))
    if t.get("change"):
        lines.append(_two_col("Change", _fmt_money(t["change"]), width))

    # Loyalty
    if loyalty:
        lines.append(_hr(width))
        if loyalty.get("earned"):
            lines.append(_two_col("Loyalty earned", f"+{loyalty['earned']} pts", width))
        if loyalty.get("redeemed"):
            lines.append(_two_col("Loyalty redeemed", f"-{loyalty['redeemed']} pts", width))
        if loyalty.get("balance") is not None:
            lines.append(_two_col("Balance", f"{loyalty['balance']} pts", width))

    lines.append(_hr(width))
    if f.get("line1"):
        for ln in _wrap(f["line1"], width):
            lines.append(ln.center(width))
    if f.get("line2"):
        for ln in _wrap(f["line2"], width):
            lines.append(ln.center(width))

    return lines


def render_to_bytes(device, receipt: dict) -> bytes:
    """Produce the byte stream for `device` to print this receipt."""
    proto: Protocol = device.protocol
    width = int(receipt.get("width") or device.profile.get("paper_columns") or DEFAULT_WIDTH)
    lines = render_text_lines(receipt, width=width)

    # ESC/POS: layered, with center-align header, big TOTAL, optional QR/cut
    if isinstance(proto, EscposProtocol):
        out = b""
        out += proto.init()

        # Header — bold, centered, slightly larger
        h = receipt.get("header", {})
        if h.get("store_name"):
            out += proto.align("center")
            out += proto.text_size(2, 2)
            out += proto.bold(True)
            out += proto.encode_text(h["store_name"]) + b"\n"
            out += proto.bold(False)
            out += proto.text_size(1, 1)
        if h.get("branch"):
            out += proto.align("center")
            out += proto.encode_text(h["branch"]) + b"\n"
        if h.get("address"):
            out += proto.align("center")
            out += proto.encode_text(h["address"]) + b"\n"
        for k in ("vat_no", "phone"):
            if h.get(k):
                out += proto.align("center")
                out += proto.encode_text(("VAT" if k == "vat_no" else "Tel") + ": " + h[k]) + b"\n"
        out += proto.align("left") + b"\n"

        # Body
        for ln in lines[lines.index("-" * width):] if ("-" * width) in lines else lines:
            # bold the TOTAL line
            if ln.startswith("TOTAL"):
                out += proto.bold(True)
                out += proto.text_size(2, 2)
                out += proto.encode_text(ln) + b"\n"
                out += proto.text_size(1, 1)
                out += proto.bold(False)
            else:
                out += proto.encode_text(ln) + b"\n"

        # ZATCA-style QR if provided
        f = receipt.get("footer", {})
        if f.get("qr"):
            out += proto.align("center")
            try:
                out += proto.qrcode(f["qr"], size=int(receipt.get("qr_size", 6)))
                out += b"\n"
            except Exception:
                pass
            out += proto.align("left")

        # Barcode of invoice no
        m = receipt.get("meta", {})
        if m.get("invoice_no") and receipt.get("print_barcode", True):
            out += proto.align("center")
            try:
                out += proto.barcode(m["invoice_no"], kind="CODE128", height=60, width=2)
                out += b"\n"
            except Exception:
                pass
            out += proto.align("left")

        out += proto.feed(3)
        try:
            out += proto.cut(partial=True)
        except NotSupported:
            pass
        return out

    # Fallback — protocols that only support encode_text
    out = b""
    try: out += proto.init()
    except NotSupported: pass
    for ln in lines:
        try:
            out += proto.encode_text(ln + "\n")
        except NotSupported:
            out += (ln + "\n").encode("ascii", errors="replace")
    try: out += proto.feed(3)
    except NotSupported: pass
    try: out += proto.cut(partial=True)
    except NotSupported: pass
    return out


def render_display_text(payload: dict, line_width: int = 20) -> tuple[str, str]:
    """Render the customer pole-display payload to two lines.

    Payload conventions:
      {"action": "line_total", "name": "Latte", "amount": 20.00, "currency": "$"}
      {"action": "subtotal",   "amount": 42.00, "currency": "$"}
      {"action": "due",        "amount": 46.00, "currency": "$"}
      {"action": "change",     "amount":  4.00, "currency": "$"}
      {"action": "thanks"}
      {"action": "raw", "top":"line1", "bottom":"line2"}
    """
    a = payload.get("action", "raw")
    cur = payload.get("currency", "")
    if a == "raw":
        return (payload.get("top") or "")[:line_width], (payload.get("bottom") or "")[:line_width]
    if a == "thanks":
        return ("Thank you!".center(line_width), "Have a nice day".center(line_width))
    if a == "line_total":
        name = (payload.get("name") or "")[: line_width]
        amt = f"{cur}{_fmt_money(payload.get('amount', 0))}"
        return (name.ljust(line_width), amt.rjust(line_width))
    if a == "subtotal":
        return ("Subtotal".ljust(line_width), f"{cur}{_fmt_money(payload.get('amount', 0))}".rjust(line_width))
    if a == "due":
        return ("Total".ljust(line_width), f"{cur}{_fmt_money(payload.get('amount', 0))}".rjust(line_width))
    if a == "change":
        return ("Change".ljust(line_width), f"{cur}{_fmt_money(payload.get('amount', 0))}".rjust(line_width))
    return ("", "")
