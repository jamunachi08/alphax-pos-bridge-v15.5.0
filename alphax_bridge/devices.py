"""
Device wrapper. Combines a transport with a protocol and exposes the logical
actions the bridge HTTP/WS API exposes.

Each Device has:
  - name           unique key inside this bridge ("front-printer", "drawer-1")
  - kind           "printer" / "drawer" / "display" / "scale"
  - transport      Transport instance (how to reach it)
  - protocol       Protocol instance (what bytes mean what)
  - profile        the raw profile dict (for diagnostics / UI)

A Device opens its transport lazily on first send and reuses it across calls.
That matches the way every commercial POS bridge works — open USB/serial once,
keep it warm.
"""
from __future__ import annotations

import logging
from typing import Optional

from .transports import Transport
from .protocols import Protocol, NotSupported

log = logging.getLogger("alphax-bridge.device")


class Device:
    def __init__(self, name: str, kind: str, transport: Transport,
                 protocol: Protocol, profile: dict):
        self.name = name
        self.kind = kind
        self.transport = transport
        self.protocol = protocol
        self.profile = profile
        self._open = False

    # ---- lifecycle -------------------------------------------------------

    def ensure_open(self) -> None:
        if self._open:
            return
        try:
            self.transport.open()
        except Exception:
            self._open = False
            raise
        # Send protocol init bytes if any.
        try:
            init_bytes = self.protocol.init()
            if init_bytes:
                self.transport.write(init_bytes)
        except (NotSupported, NotImplementedError):
            pass
        self._open = True

    def close(self) -> None:
        try:
            self.transport.close()
        finally:
            self._open = False

    # ---- low-level passthrough ------------------------------------------

    def send_raw(self, data: bytes) -> int:
        self.ensure_open()
        return self.transport.write(data)

    def read_raw(self, n: int = 1024, timeout: float = 0.5) -> bytes:
        self.ensure_open()
        return self.transport.read(n, timeout)

    # ---- printer actions -------------------------------------------------

    def print_text(self, text: str, **opts) -> None:
        self.ensure_open()
        self.transport.write(self.protocol.encode_text(text, **opts))

    def print_line(self, text: str = "", **opts) -> None:
        self.print_text((text or "") + "\n", **opts)

    def feed(self, lines: int = 1) -> None:
        self.ensure_open()
        self.transport.write(self.protocol.feed(lines))

    def cut(self, partial: bool = True) -> None:
        self.ensure_open()
        try:
            self.transport.write(self.protocol.cut(partial=partial))
        except NotSupported:
            self.feed(5)

    def beep(self) -> None:
        self.ensure_open()
        try:
            self.transport.write(self.protocol.beep())
        except NotSupported:
            pass

    # ---- drawer actions --------------------------------------------------

    def kick_drawer(self, pin: int = 0) -> None:
        self.ensure_open()
        self.transport.write(self.protocol.open_drawer(pin=pin))

    # ---- display actions -------------------------------------------------

    def show_lines(self, top: str, bottom: str) -> None:
        self.ensure_open()
        self.transport.write(self.protocol.show_two_lines(top, bottom))

    def clear_display(self) -> None:
        self.ensure_open()
        try:
            self.transport.write(self.protocol.clear_display())
        except NotSupported:
            self.transport.write(b"\x0c")

    # ---- scale actions ---------------------------------------------------

    def read_weight(self, timeout: float = 1.5) -> Optional[dict]:
        self.ensure_open()
        try:
            req = self.protocol.request_weight()
        except NotSupported:
            req = b""
        if req:
            self.transport.write(req)
        # Read up to 1 second of data.
        buf = self.transport.read(256, timeout=timeout)
        try:
            return self.protocol.parse_weight(buf)
        except NotSupported:
            return None

    # ---- diagnostics -----------------------------------------------------

    def info(self) -> dict:
        return {
            "name":      self.name,
            "kind":      self.kind,
            "transport": self.transport.name,
            "protocol":  self.protocol.name,
            "open":      self._open,
            "profile":   self.profile.get("profile_id") or self.profile.get("name"),
        }
