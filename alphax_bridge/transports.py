"""
Transport layer.

A Transport is anything that takes a bytes payload and writes it to a device.
We don't care what the device is — that's the protocol layer's job.

Supported transports:

  usb         - libusb / pyusb. Vendor + product ID from profile.
  serial      - pyserial. Port path + baud + parity from profile.
  network     - raw TCP socket. host:port from profile.
  parallel    - LPT direct write (Linux/Windows). Path from profile.
  passthrough - send through another configured device (drawer through printer).
  file        - write to a path. Logging, virtual devices, tests.
  stdout      - hexdump to console. Development only.

Each transport is a class with open()/write()/read()/close() plus a
discover() classmethod returning auto-detected candidate devices of that type.
"""
from __future__ import annotations

import os
import socket
import sys
from typing import Optional


# ---- base ------------------------------------------------------------------


class Transport:
    name = "base"

    def __init__(self, **config):
        self.config = config
        self._opened = False

    def open(self) -> None:
        self._opened = True

    def write(self, data: bytes) -> int:
        raise NotImplementedError

    def read(self, n: int = 1024, timeout: float = 0.5) -> bytes:
        return b""

    def close(self) -> None:
        self._opened = False

    @classmethod
    def discover(cls) -> list[dict]:
        return []

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()


# ---- USB -------------------------------------------------------------------


class USBTransport(Transport):
    """libusb / pyusb USB transport.

    Profile fields:
      vendor_id     hex string, e.g. "0x04b8"
      product_id    hex string, e.g. "0x0202"
      interface     int, default 0
      in_endpoint   hex, optional (for read)
      out_endpoint  hex, optional (for write)
    """
    name = "usb"

    def open(self) -> None:
        try:
            import usb.core, usb.util  # noqa
        except ImportError:
            raise RuntimeError("USB transport needs `pyusb`. pip install pyusb")
        import usb.core, usb.util

        vid = int(str(self.config["vendor_id"]), 16)
        pid = int(str(self.config["product_id"]), 16)
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev is None:
            raise RuntimeError(f"USB device {vid:04x}:{pid:04x} not found")

        if hasattr(dev, "is_kernel_driver_active"):
            try:
                if dev.is_kernel_driver_active(0):
                    dev.detach_kernel_driver(0)
            except Exception:
                pass

        try:
            dev.set_configuration()
        except usb.core.USBError:
            pass

        cfg = dev.get_active_configuration()
        intf_num = int(self.config.get("interface", 0))
        intf = cfg[(intf_num, 0)]

        out_ep = self.config.get("out_endpoint")
        in_ep = self.config.get("in_endpoint")

        if out_ep is None:
            out = next((e for e in intf if usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT), None)
            if out is None:
                raise RuntimeError("No OUT endpoint")
            self._out_ep = out.bEndpointAddress
        else:
            self._out_ep = int(str(out_ep), 16)

        if in_ep is not None:
            self._in_ep = int(str(in_ep), 16)
        else:
            in_e = next((e for e in intf if usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN), None)
            self._in_ep = in_e.bEndpointAddress if in_e else None

        self._dev = dev
        self._opened = True

    def write(self, data: bytes) -> int:
        return int(self._dev.write(self._out_ep, data, timeout=2000))

    def read(self, n: int = 1024, timeout: float = 0.5) -> bytes:
        if self._in_ep is None:
            return b""
        try:
            arr = self._dev.read(self._in_ep, n, timeout=int(timeout * 1000))
            return bytes(arr)
        except Exception:
            return b""

    def close(self) -> None:
        try:
            import usb.util
            usb.util.dispose_resources(self._dev)
        except Exception:
            pass
        self._opened = False

    @classmethod
    def discover(cls) -> list[dict]:
        try:
            import usb.core, usb.util
            out = []
            for d in usb.core.find(find_all=True):
                row = {
                    "transport": "usb",
                    "vendor_id":  f"0x{d.idVendor:04x}",
                    "product_id": f"0x{d.idProduct:04x}",
                }
                try:
                    if d.iManufacturer:
                        row["manufacturer"] = (usb.util.get_string(d, d.iManufacturer) or "").strip()
                    if d.iProduct:
                        row["product"] = (usb.util.get_string(d, d.iProduct) or "").strip()
                    if d.iSerialNumber:
                        row["serial"] = (usb.util.get_string(d, d.iSerialNumber) or "").strip()
                except Exception:
                    pass
                out.append(row)
            return out
        except Exception:
            return []


# ---- Serial ----------------------------------------------------------------


class SerialTransport(Transport):
    """RS-232 / USB-to-serial transport.

    Profile fields:
      port      "COM3" / "/dev/ttyUSB0" / "/dev/cu.usbserial-1410"
      baud      int, default 9600
      bytesize  7 or 8, default 8
      parity    "N" / "E" / "O", default "N"
      stopbits  1 or 2, default 1
      timeout   seconds, default 1.0
    """
    name = "serial"

    def open(self) -> None:
        try:
            import serial  # noqa
        except ImportError:
            raise RuntimeError("Serial transport needs `pyserial`. pip install pyserial")
        import serial

        parity_map = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}
        self._ser = serial.Serial(
            port=self.config["port"],
            baudrate=int(self.config.get("baud", 9600)),
            bytesize=int(self.config.get("bytesize", 8)),
            parity=parity_map.get(str(self.config.get("parity", "N")).upper(), serial.PARITY_NONE),
            stopbits=int(self.config.get("stopbits", 1)),
            timeout=float(self.config.get("timeout", 1.0)),
        )
        self._opened = True

    def write(self, data: bytes) -> int:
        return self._ser.write(data)

    def read(self, n: int = 1024, timeout: float = 0.5) -> bytes:
        old = self._ser.timeout
        try:
            self._ser.timeout = timeout
            return self._ser.read(n)
        finally:
            self._ser.timeout = old

    def close(self) -> None:
        try: self._ser.close()
        except Exception: pass
        self._opened = False

    @classmethod
    def discover(cls) -> list[dict]:
        try:
            from serial.tools import list_ports
            return [
                {"transport": "serial", "port": p.device,
                 "description": p.description, "manufacturer": p.manufacturer or ""}
                for p in list_ports.comports()
            ]
        except Exception:
            return []


# ---- Network (TCP) ---------------------------------------------------------


class NetworkTransport(Transport):
    """Raw TCP socket. Used by Ethernet receipt printers (typically port 9100),
    network scales, networked customer displays.

    Profile fields:
      host      hostname or IP
      port      int, default 9100
      timeout   seconds, default 3.0
    """
    name = "network"

    def open(self) -> None:
        host = self.config["host"]
        port = int(self.config.get("port", 9100))
        timeout = float(self.config.get("timeout", 3.0))
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._opened = True

    def write(self, data: bytes) -> int:
        self._sock.sendall(data)
        return len(data)

    def read(self, n: int = 1024, timeout: float = 0.5) -> bytes:
        self._sock.settimeout(timeout)
        try:
            return self._sock.recv(n) or b""
        except socket.timeout:
            return b""

    def close(self) -> None:
        try: self._sock.close()
        except Exception: pass
        self._opened = False


# ---- Parallel (Linux /dev/lp0 or Windows LPT1) ----------------------------


class ParallelTransport(Transport):
    """Direct parallel-port write — file-style writes to /dev/lp0 or LPT1.

    Profile fields:
      path  e.g. "/dev/lp0" / "LPT1"
    """
    name = "parallel"

    def open(self) -> None:
        self._fd = open(self.config["path"], "wb")
        self._opened = True

    def write(self, data: bytes) -> int:
        self._fd.write(data)
        self._fd.flush()
        return len(data)

    def close(self) -> None:
        try: self._fd.close()
        except Exception: pass
        self._opened = False


# ---- File / stdout (test transports) --------------------------------------


class FileTransport(Transport):
    """Append-write payloads to a file. Useful for log-style printers and tests."""
    name = "file"

    def open(self) -> None:
        self._fd = open(self.config["path"], "ab")
        self._opened = True

    def write(self, data: bytes) -> int:
        self._fd.write(data)
        self._fd.write(b"\n----\n")
        self._fd.flush()
        return len(data)

    def close(self) -> None:
        try: self._fd.close()
        except Exception: pass
        self._opened = False


class StdoutTransport(Transport):
    """Hexdump payloads to stdout. Development only."""
    name = "stdout"

    def write(self, data: bytes) -> int:
        sys.stdout.write(f"[stdout-transport] {data.hex(' ')}\n")
        sys.stdout.flush()
        return len(data)


# ---- Passthrough (drawer through printer) ----------------------------------


class PassthroughTransport(Transport):
    """Routes payloads through another already-configured device.

    Used for: cash drawer connected to a receipt printer's RJ-11 socket.
    The drawer has no connection of its own; the printer kicks it.

    Profile fields:
      via   string — name of another configured device on this bridge.
    """
    name = "passthrough"

    def __init__(self, registry, **config):
        super().__init__(**config)
        self._registry = registry

    def open(self) -> None:
        target = self._registry.get(self.config["via"])
        if not target:
            raise RuntimeError(f"Passthrough target '{self.config['via']}' not configured")
        self._target = target
        self._opened = True

    def write(self, data: bytes) -> int:
        return self._target.send_raw(data)


# ---- factory ---------------------------------------------------------------


TRANSPORTS = {
    "usb":         USBTransport,
    "serial":      SerialTransport,
    "network":     NetworkTransport,
    "parallel":    ParallelTransport,
    "file":        FileTransport,
    "stdout":      StdoutTransport,
    "passthrough": PassthroughTransport,
}


def make_transport(transport_name: str, *, registry=None, **config) -> Transport:
    cls = TRANSPORTS.get(transport_name)
    if not cls:
        raise ValueError(f"Unknown transport: {transport_name}")
    if cls is PassthroughTransport:
        return cls(registry=registry, **config)
    return cls(**config)


def discover_all() -> dict[str, list[dict]]:
    """Run discover() on every transport that supports it."""
    return {
        "usb":     USBTransport.discover(),
        "serial":  SerialTransport.discover(),
        "network": [],
    }
