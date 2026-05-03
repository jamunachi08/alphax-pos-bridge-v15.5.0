"""
Local HTTP server for the bridge.

Exposes a tiny REST API on http://localhost:<port>. The Vue SPA uses fetch()
against this. Auth via a shared token from config (Bearer header).

Endpoints:

  GET  /                  — bridge status + version
  GET  /devices           — list configured devices + their status
  GET  /profiles          — list available profiles (built-in + user)
  GET  /discover          — auto-detect USB / serial / network candidates
  POST /print             — { "device": "front-printer", "receipt": {...} }
  POST /drawer            — { "device": "drawer-1" }
  POST /display           — { "device": "pole-1", "action": "due", "amount": 46 }
  GET  /scale?device=...  — read a single weight from a scale
  POST /test              — { "device": "...", "action": "print"|"kick"|"display"|"weight" }
  POST /raw               — { "device": "...", "data_hex": "1b40..." }   — raw passthrough
  POST /charge            — { "device": "card-1", "amount": 46.00, "currency": "SAR",
                              "invoice_ref": "SINV-...", "idempotency_key": "..." }
  POST /refund            — { "device": "card-1", "amount": 46.00,
                              "original_txn_id": "...", "idempotency_key": "..." }
  POST /cancel            — { "device": "card-1", "current_txn_id": "..." }

Stdlib-only — no flask/fastapi dependency. Install is just `pip install
pyusb pyserial` plus optional `pip install pyyaml arabic-reshaper python-bidi`.
"""
from __future__ import annotations

import json
import logging
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from . import __version__
from .registry import DeviceRegistry
from .renderer import render_display_text, render_to_bytes
from .transports import discover_all

log = logging.getLogger("alphax-bridge.server")


def make_app(registry: DeviceRegistry, auth_token: Optional[str] = None,
             cors_origin: str = "*"):
    """Returns a Handler class bound to this registry. Each thread gets its
    own handler instance; the registry is shared."""

    class Handler(BaseHTTPRequestHandler):
        # Quiet down access logs.
        def log_message(self, fmt, *args):
            log.debug("%s - %s", self.address_string(), fmt % args)

        # --- helpers -------------------------------------------------------

        def _set_cors(self):
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _check_auth(self) -> bool:
            if not auth_token:
                return True
            hdr = self.headers.get("Authorization", "")
            return hdr == f"Bearer {auth_token}"

        def _json(self, status: HTTPStatus, payload):
            body = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self._set_cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            raw = self.rfile.read(n)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        # --- routing -------------------------------------------------------

        def do_OPTIONS(self):
            self.send_response(HTTPStatus.NO_CONTENT)
            self._set_cors()
            self.end_headers()

        def do_GET(self):
            if not self._check_auth():
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "auth required"})
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            try:
                if url.path == "/":
                    return self._json(HTTPStatus.OK, {
                        "name": "alphax-pos-bridge",
                        "version": __version__,
                        "devices": len(registry.all()),
                        "profiles": len(registry.list_profiles()),
                    })
                if url.path == "/devices":
                    return self._json(HTTPStatus.OK, registry.info())
                if url.path == "/profiles":
                    return self._json(HTTPStatus.OK, {"profiles": registry.list_profiles()})
                if url.path == "/discover":
                    return self._json(HTTPStatus.OK, discover_all())
                if url.path == "/scale":
                    name = (qs.get("device") or [None])[0]
                    dev = registry.get(name)
                    if not dev:
                        return self._json(HTTPStatus.NOT_FOUND, {"error": f"device {name} not configured"})
                    weight = dev.read_weight(timeout=float((qs.get("timeout") or ["1.5"])[0]))
                    return self._json(HTTPStatus.OK, {"device": name, "weight": weight})
                return self._json(HTTPStatus.NOT_FOUND, {"error": "unknown path"})
            except Exception as e:
                log.exception("GET error")
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

        def do_POST(self):
            if not self._check_auth():
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "auth required"})
            url = urlparse(self.path)
            body = self._read_json()
            try:
                if url.path == "/print":
                    return self._handle_print(body)
                if url.path == "/drawer":
                    return self._handle_drawer(body)
                if url.path == "/display":
                    return self._handle_display(body)
                if url.path == "/test":
                    return self._handle_test(body)
                if url.path == "/raw":
                    return self._handle_raw(body)
                if url.path == "/charge":
                    return self._handle_charge(body)
                if url.path == "/refund":
                    return self._handle_refund(body)
                if url.path == "/cancel":
                    return self._handle_cancel(body)
                return self._json(HTTPStatus.NOT_FOUND, {"error": "unknown path"})
            except Exception as e:
                log.exception("POST error")
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

        # --- handlers ------------------------------------------------------

        def _handle_print(self, body):
            name = body.get("device")
            receipt = body.get("receipt") or {}
            dev = registry.get(name)
            if not dev:
                return self._json(HTTPStatus.NOT_FOUND, {"error": f"device {name} not configured"})
            payload = render_to_bytes(dev, receipt)
            dev.send_raw(payload)
            return self._json(HTTPStatus.OK, {"ok": True, "device": name, "bytes": len(payload)})

        def _handle_drawer(self, body):
            name = body.get("device")
            pin = int(body.get("pin", 0))
            dev = registry.get(name)
            if not dev:
                return self._json(HTTPStatus.NOT_FOUND, {"error": f"device {name} not configured"})
            dev.kick_drawer(pin=pin)
            return self._json(HTTPStatus.OK, {"ok": True, "device": name})

        def _handle_display(self, body):
            name = body.get("device")
            dev = registry.get(name)
            if not dev:
                return self._json(HTTPStatus.NOT_FOUND, {"error": f"device {name} not configured"})
            line_width = int(dev.profile.get("line_width", 20))
            top, bottom = render_display_text(body, line_width=line_width)
            dev.show_lines(top, bottom)
            return self._json(HTTPStatus.OK, {"ok": True, "device": name, "top": top, "bottom": bottom})

        def _handle_test(self, body):
            name = body.get("device")
            action = body.get("action", "print")
            dev = registry.get(name)
            if not dev:
                return self._json(HTTPStatus.NOT_FOUND, {"error": f"device {name} not configured"})
            if action == "print":
                test_receipt = {
                    "header": {"store_name": "AlphaX Bridge",
                               "branch": "Hardware test"},
                    "meta":   {"invoice_no": "TEST-0001",
                               "datetime": "2026-04-26 10:00:00",
                               "cashier": "test"},
                    "items":  [{"name": "Test item", "qty": 1, "rate": 10, "amount": 10}],
                    "totals": {"subtotal": 10, "tax": 0, "total": 10},
                    "footer": {"line1": "Hello from the bridge"},
                }
                dev.send_raw(render_to_bytes(dev, test_receipt))
                return self._json(HTTPStatus.OK, {"ok": True, "action": "print"})
            if action == "kick":
                dev.kick_drawer()
                return self._json(HTTPStatus.OK, {"ok": True, "action": "kick"})
            if action == "display":
                dev.show_lines("AlphaX Bridge", "Display test ok")
                return self._json(HTTPStatus.OK, {"ok": True, "action": "display"})
            if action == "weight":
                w = dev.read_weight(timeout=1.5)
                return self._json(HTTPStatus.OK, {"ok": True, "action": "weight", "weight": w})
            return self._json(HTTPStatus.BAD_REQUEST, {"error": f"unknown test action {action}"})

        def _handle_raw(self, body):
            name = body.get("device")
            hex_data = body.get("data_hex") or ""
            dev = registry.get(name)
            if not dev:
                return self._json(HTTPStatus.NOT_FOUND, {"error": f"device {name} not configured"})
            try:
                data = bytes.fromhex(hex_data.replace(" ", ""))
            except ValueError:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid hex"})
            n = dev.send_raw(data)
            return self._json(HTTPStatus.OK, {"ok": True, "device": name, "bytes": n})

        # ---- card-terminal handlers --------------------------------------

        def _handle_charge(self, body):
            name = body.get("device")
            terminal = registry.get_terminal(name)
            if not terminal:
                return self._json(HTTPStatus.NOT_FOUND,
                                  {"error": f"terminal {name} not configured"})
            try:
                amount = float(body.get("amount", 0))
                currency = body.get("currency", "")
                invoice_ref = body.get("invoice_ref", "")
                idem = body.get("idempotency_key", "")
                metadata = body.get("metadata") or None
                timeout = float(body.get("timeout", 90))
                result = terminal.charge(
                    amount, currency,
                    invoice_ref=invoice_ref,
                    idempotency_key=idem,
                    metadata=metadata,
                    timeout=timeout,
                )
                return self._json(HTTPStatus.OK,
                                  {"device": name, **result.to_dict()})
            except Exception as e:
                log.exception("charge error")
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  {"device": name, "status": "error", "ok": False,
                                   "decline_reason": str(e)})

        def _handle_refund(self, body):
            name = body.get("device")
            terminal = registry.get_terminal(name)
            if not terminal:
                return self._json(HTTPStatus.NOT_FOUND,
                                  {"error": f"terminal {name} not configured"})
            try:
                amount = float(body.get("amount", 0))
                original = body.get("original_txn_id", "")
                idem = body.get("idempotency_key", "")
                metadata = body.get("metadata") or None
                result = terminal.refund(amount, original,
                                         idempotency_key=idem, metadata=metadata)
                return self._json(HTTPStatus.OK,
                                  {"device": name, **result.to_dict()})
            except NotImplementedError as e:
                return self._json(HTTPStatus.NOT_IMPLEMENTED,
                                  {"device": name, "error": str(e)})
            except Exception as e:
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  {"device": name, "status": "error", "ok": False,
                                   "decline_reason": str(e)})

        def _handle_cancel(self, body):
            name = body.get("device")
            terminal = registry.get_terminal(name)
            if not terminal:
                return self._json(HTTPStatus.NOT_FOUND,
                                  {"error": f"terminal {name} not configured"})
            current = body.get("current_txn_id", "")
            result = terminal.cancel(current)
            return self._json(HTTPStatus.OK, {"device": name, **result.to_dict()})

    return Handler


def serve(registry: DeviceRegistry, *, host: str = "127.0.0.1", port: int = 8420,
          auth_token: Optional[str] = None, cors_origin: str = "*") -> ThreadingHTTPServer:
    handler = make_app(registry, auth_token=auth_token, cors_origin=cors_origin)
    httpd = ThreadingHTTPServer((host, port), handler)
    log.info("alphax bridge listening on http://%s:%d", host, port)
    return httpd
