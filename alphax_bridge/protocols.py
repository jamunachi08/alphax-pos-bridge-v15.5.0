"""
Protocol layer.

A Protocol turns a logical action (print, kick drawer, show line, read weight)
into bytes for a particular device family. The action interface is the same
across protocols; not every protocol supports every action.

Built-in protocols:

  escpos       Epson-style ESC/POS receipt printers. The de-facto standard;
               works for Epson, Bixolon, Citizen, SNBC, most generic 80mm
               thermals, and most "Chinese ESC/POS" printers.
  star         Star line-mode printers (TSP100/650/700/800).
  vfd-text     Generic plain-text 2x20 pole display (fallback).
  vfd-cd5220   CD5220 / Aedex / Logic Controls / Posiflex pole display.
  toledo-9091  Toledo / Mettler-Toledo 8217 / 9091 weight protocol.
  cas-ad      CAS AD / PD-II series weight protocol.
  bizerba-bp   Bizerba BPlus weight protocol.
  generic-line Generic newline-terminated commands.
  raw          Pass through opaque bytes.

Adding a new protocol = one new class. New devices that speak any of these
just need a profile.
"""
from __future__ import annotations

import struct
from typing import Optional


class NotSupported(Exception):
    pass


class Protocol:
    name = "base"

    def init(self) -> bytes:
        return b""

    def encode_text(self, text: str, **opts) -> bytes:
        raise NotSupported(f"{self.name}.encode_text")

    # printer
    def feed(self, lines: int = 1) -> bytes:
        raise NotSupported(f"{self.name}.feed")

    def cut(self, partial: bool = False) -> bytes:
        raise NotSupported(f"{self.name}.cut")

    def open_drawer(self, pin: int = 0) -> bytes:
        raise NotSupported(f"{self.name}.open_drawer")

    def beep(self) -> bytes:
        raise NotSupported(f"{self.name}.beep")

    # display
    def show_two_lines(self, top: str, bottom: str) -> bytes:
        raise NotSupported(f"{self.name}.show_two_lines")

    def clear_display(self) -> bytes:
        raise NotSupported(f"{self.name}.clear_display")

    # scale
    def request_weight(self) -> bytes:
        raise NotSupported(f"{self.name}.request_weight")

    def parse_weight(self, payload: bytes) -> Optional[dict]:
        raise NotSupported(f"{self.name}.parse_weight")


# ===========================================================================
# ESC/POS (printers + drawer)
# ===========================================================================


class EscposProtocol(Protocol):
    """Epson-style ESC/POS. The only printer protocol most cashiers will
    ever need. Configurable codepage so it works for Arabic, Cyrillic,
    Thai, Latin1 etc. without code changes.

    Profile options:
      codepage          int (default 0 = PC437). 16 = WPC1252, 22 = PC864 Arabic.
      cut_kind          "full" or "partial" (default partial).
      drawer_pin        0 or 1 (which RJ-11 drive pin to pulse).
      drawer_on_time    0-255 (drive duration unit ~2ms).
      drawer_off_time   0-255 (off duration unit ~2ms).
      encoding          python codec (default "cp437"). Should match codepage.
      arabic_shape      bool (default False). Reshape Arabic for legacy printers.
    """
    name = "escpos"
    ESC = b"\x1b"
    GS = b"\x1d"

    def __init__(self, **opts):
        self.opts = opts
        self.codepage = int(opts.get("codepage", opts.get("char_table", 0)))
        self.encoding = opts.get("encoding", "cp437")
        self.arabic_shape = bool(opts.get("arabic_shape", False))

    def init(self) -> bytes:
        return self.ESC + b"@" + self.ESC + b"t" + bytes([self.codepage])

    def encode_text(self, text: str, **opts) -> bytes:
        if self.arabic_shape:
            text = _arabic_reshape(text)
        try:
            return text.encode(self.encoding, errors="replace")
        except LookupError:
            return text.encode("ascii", errors="replace")

    def feed(self, lines: int = 1) -> bytes:
        return self.ESC + b"d" + bytes([min(255, max(0, lines))])

    def cut(self, partial: bool = True) -> bytes:
        kind = self.opts.get("cut_kind", "partial" if partial else "full")
        m = 1 if kind == "partial" else 0
        return self.GS + b"V" + bytes([m])

    def open_drawer(self, pin: int = 0) -> bytes:
        m  = int(self.opts.get("drawer_pin", pin)) & 1
        t1 = int(self.opts.get("drawer_on_time", 50)) & 0xff
        t2 = int(self.opts.get("drawer_off_time", 250)) & 0xff
        return self.ESC + b"p" + bytes([m, t1, t2])

    def beep(self) -> bytes:
        return self.ESC + b"B" + bytes([3, 2])

    # high-level helpers used by the renderer
    def align(self, mode: str) -> bytes:
        return self.ESC + b"a" + bytes([{"left": 0, "center": 1, "right": 2}.get(mode, 0)])

    def text_size(self, w: int = 1, h: int = 1) -> bytes:
        w = max(1, min(8, w)); h = max(1, min(8, h))
        return self.GS + b"!" + bytes([((w - 1) << 4) | (h - 1)])

    def bold(self, on: bool) -> bytes:
        return self.ESC + b"E" + bytes([1 if on else 0])

    def underline(self, on: bool) -> bytes:
        return self.ESC + b"-" + bytes([1 if on else 0])

    def barcode(self, code: str, kind: str = "CODE128", height: int = 80, width: int = 2) -> bytes:
        kinds = {"UPC-A": 65, "UPC-E": 66, "EAN13": 67, "EAN8": 68, "CODE39": 69,
                 "ITF": 70, "CODABAR": 71, "CODE93": 72, "CODE128": 73}
        m = kinds.get(kind.upper(), 73)
        out  = self.GS + b"h" + bytes([min(255, max(1, height))])
        out += self.GS + b"w" + bytes([min(6, max(2, width))])
        out += self.GS + b"H" + bytes([2])
        out += self.GS + b"k" + bytes([m, len(code)]) + code.encode("ascii", errors="ignore")
        return out

    def qrcode(self, data: str, size: int = 6, ec: str = "L") -> bytes:
        store = lambda fn1, fn2, *params: (
            self.GS + b"(k" + struct.pack("<H", len(params) + 2) + bytes([fn1, fn2]) + bytes(params))
        out  = store(0x31, 0x41, 0x32, 0x00)
        out += store(0x31, 0x43, max(1, min(16, size)))
        ec_map = {"L": 0x30, "M": 0x31, "Q": 0x32, "H": 0x33}
        out += store(0x31, 0x45, ec_map.get(ec.upper(), 0x30))
        payload = data.encode("utf-8", errors="ignore")
        plen = len(payload) + 3
        out += self.GS + b"(k" + struct.pack("<H", plen) + b"\x31\x50\x30" + payload
        out += self.GS + b"(k\x03\x00\x31\x51\x30"
        return out


def _arabic_reshape(text: str) -> str:
    """Best-effort Arabic shaping for printers that lack a proper Arabic
    codepage. If `arabic-reshaper` and `python-bidi` are installed, use
    them; otherwise return text unchanged."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


# ===========================================================================
# Star line-mode (TSP100, TSP650, TSP800, …)
# ===========================================================================


class StarProtocol(Protocol):
    name = "star"
    ESC = b"\x1b"

    def __init__(self, **opts):
        self.opts = opts
        self.encoding = opts.get("encoding", "cp437")

    def init(self) -> bytes:
        return self.ESC + b"@"

    def encode_text(self, text: str, **opts) -> bytes:
        return text.encode(self.encoding, errors="replace")

    def feed(self, lines: int = 1) -> bytes:
        return b"\n" * max(0, min(50, lines))

    def cut(self, partial: bool = True) -> bytes:
        n = 3 if partial else 2  # 2 full+feed, 3 partial+feed
        return self.ESC + b"d" + bytes([n])

    def open_drawer(self, pin: int = 0) -> bytes:
        return b"\x07" if pin == 0 else b"\x1a"


# ===========================================================================
# VFD pole displays
# ===========================================================================


class VfdTextProtocol(Protocol):
    """Plain newline-terminated 2x20 display. Many cheap pole displays accept
    just `top\\r\\nbottom\\r\\n`."""
    name = "vfd-text"

    def __init__(self, **opts):
        self.opts = opts
        self.encoding = opts.get("encoding", "ascii")
        self.line_width = int(opts.get("line_width", 20))

    def show_two_lines(self, top: str, bottom: str) -> bytes:
        t = (top    or "").ljust(self.line_width)[: self.line_width]
        b = (bottom or "").ljust(self.line_width)[: self.line_width]
        return (t + "\r\n" + b + "\r\n").encode(self.encoding, errors="replace")

    def clear_display(self) -> bytes:
        return b"\x0c"


class VfdCD5220Protocol(VfdTextProtocol):
    """CD5220 / Aedex / Logic Controls / Posiflex protocol.
    Industry-standard for VFD pole displays."""
    name = "vfd-cd5220"
    ESC = b"\x1b"

    def init(self) -> bytes:
        return self.ESC + b"@"

    def clear_display(self) -> bytes:
        return self.ESC + b"@"

    def show_two_lines(self, top: str, bottom: str) -> bytes:
        out  = self.clear_display()
        out += self.ESC + b"QA" + (top    or "").encode(self.encoding, errors="replace")[:20] + b"\x0d"
        out += self.ESC + b"QB" + (bottom or "").encode(self.encoding, errors="replace")[:20] + b"\x0d"
        return out


# ===========================================================================
# Scales
# ===========================================================================


class ToledoProtocol(Protocol):
    """Toledo / Mettler-Toledo 8217 / 9091 protocol.
    ENQ → STX <status> <weight 6> <units 2> ETX [chk]."""
    name = "toledo-9091"

    def __init__(self, **opts):
        self.opts = opts
        self.continuous = bool(opts.get("continuous", False))

    def request_weight(self) -> bytes:
        return b"" if self.continuous else b"\x05"

    def parse_weight(self, payload: bytes) -> Optional[dict]:
        if not payload:
            return None
        try:
            stx = payload.index(b"\x02")
            etx = payload.index(b"\x03", stx)
        except ValueError:
            return None
        body = payload[stx + 1: etx].decode("ascii", errors="ignore")
        if len(body) < 9:
            return None
        try:
            weight = float(body[1:7].strip())
        except ValueError:
            return None
        units = body[7:9].strip().lower() or "kg"
        return {"weight": weight, "unit": units, "stable": (ord(body[0]) & 0x02) == 0}


class CasAdProtocol(Protocol):
    """CAS AD / PD-II series. Sends ENQ; expects an ASCII line."""
    name = "cas-ad"

    def request_weight(self) -> bytes:
        return b"\x05"

    def parse_weight(self, payload: bytes) -> Optional[dict]:
        if not payload:
            return None
        for s in payload.decode("ascii", errors="ignore").splitlines():
            parts = [p.strip() for p in s.strip().split(",")]
            if len(parts) >= 3:
                stable = parts[0].upper().startswith("ST")
                try:
                    nums = parts[2].split()
                    weight = float(nums[0])
                    unit = nums[1].lower() if len(nums) > 1 else "kg"
                    return {"weight": weight, "unit": unit, "stable": stable}
                except (ValueError, IndexError):
                    continue
        return None


class BizerbaProtocol(Protocol):
    name = "bizerba-bp"

    def request_weight(self) -> bytes:
        return b"S\r\n"

    def parse_weight(self, payload: bytes) -> Optional[dict]:
        if not payload:
            return None
        s = payload.decode("ascii", errors="ignore").strip()
        for tok in s.split():
            try:
                weight = float(tok)
                return {"weight": weight, "unit": "kg", "stable": "S" in (s.split()[:2] if s.split() else [])}
            except ValueError:
                continue
        return None


# ===========================================================================
# Generic & raw
# ===========================================================================


class GenericLineProtocol(Protocol):
    """Send opaque text with optional terminator. For exotic devices."""
    name = "generic-line"

    def __init__(self, **opts):
        self.terminator = opts.get("terminator", "\r\n").encode("latin-1")
        self.encoding = opts.get("encoding", "ascii")

    def encode_text(self, text: str, **opts) -> bytes:
        return text.encode(self.encoding, errors="replace") + self.terminator

    def show_two_lines(self, top: str, bottom: str) -> bytes:
        return (top + "\n" + bottom).encode(self.encoding, errors="replace") + self.terminator


class RawProtocol(Protocol):
    """Truly opaque. SPA sends bytes; we forward verbatim."""
    name = "raw"


# ---- factory ---------------------------------------------------------------


PROTOCOLS = {
    "escpos":       EscposProtocol,
    "star":         StarProtocol,
    "vfd-text":     VfdTextProtocol,
    "vfd-cd5220":   VfdCD5220Protocol,
    "toledo-9091":  ToledoProtocol,
    "cas-ad":       CasAdProtocol,
    "bizerba-bp":   BizerbaProtocol,
    "generic-line": GenericLineProtocol,
    "raw":          RawProtocol,
}


def make_protocol(name: str, **opts) -> Protocol:
    cls = PROTOCOLS.get(name)
    if not cls:
        raise ValueError(f"Unknown protocol: {name}")
    return cls(**opts)
