"""
Machine identity for the bridge.

The cashier SPA needs a device fingerprint that survives a browser reset,
a cache clear and a reinstall. Only the local daemon can supply that —
the browser cannot see a hostname or a machine UUID.

Three values, in descending order of how much the server trusts them:

  machine_uuid  — the OS's own persistent install identifier.
                  Windows : HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
                  macOS   : IOPlatformUUID
                  Linux   : /etc/machine-id
                  Survives everything short of an OS reinstall.

  mac_address   — first non-randomised NIC. Survives a browser reset but
                  changes when someone swaps a USB ethernet dongle, and
                  is meaningless on tablets with MAC randomisation on.

  hostname      — human-readable, not unique. Used for the suggested
                  station name, never for identity.

Everything is best-effort and cached for the process lifetime. A failure
to read any of it returns an empty string rather than raising — a bridge
that cannot introspect itself must still print receipts.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import uuid as _uuid

_cache: dict | None = None


# ---------------------------------------------------------------------------
# machine uuid
# ---------------------------------------------------------------------------

def _machine_uuid_windows() -> str:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography", 0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
        try:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip()
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass
    # Fallback for locked-down registry policies.
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
            capture_output=True, text=True, timeout=6)
        v = (out.stdout or "").strip()
        if v and v.lower() not in ("ffffffff-ffff-ffff-ffff-ffffffffffff",):
            return v
    except Exception:
        pass
    return ""


def _machine_uuid_macos() -> str:
    try:
        out = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=6)
        for line in (out.stdout or "").splitlines():
            if "IOPlatformUUID" in line:
                return line.split('"')[-2].strip()
    except Exception:
        pass
    return ""


def _machine_uuid_linux() -> str:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                v = fh.read().strip()
                if v:
                    return v
        except Exception:
            continue
    # Containers sometimes have neither; fall back to the product UUID.
    try:
        with open("/sys/class/dmi/id/product_uuid", "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""


def machine_uuid() -> str:
    sysname = platform.system()
    if sysname == "Windows":
        return _machine_uuid_windows()
    if sysname == "Darwin":
        return _machine_uuid_macos()
    return _machine_uuid_linux()


# ---------------------------------------------------------------------------
# mac address
# ---------------------------------------------------------------------------

def mac_address() -> str:
    """Normalised AA:BB:CC:DD:EE:FF, or '' when the value is randomised
    or synthesised.

    `uuid.getnode()` sets bit 0x010000000000 when it had to invent a
    node id, and the locally-administered bit (0x02 in the first octet)
    marks a randomised MAC — common on tablets and on Windows with
    "random hardware addresses" enabled. Neither is identity.
    """
    try:
        node = _uuid.getnode()
    except Exception:
        return ""

    if node >> 40 & 0x01:          # multicast/synthesised marker
        return ""

    hexs = f"{node:012X}"
    try:
        if int(hexs[0:2], 16) & 0x02:   # locally administered => randomised
            return ""
    except ValueError:
        return ""
    if hexs == "000000000000":
        return ""
    return ":".join(hexs[i:i + 2] for i in range(0, 12, 2))


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------

def system_info(refresh: bool = False) -> dict:
    """Cached. Read once per process — none of this changes at runtime."""
    global _cache
    if _cache is not None and not refresh:
        return _cache

    try:
        host = socket.gethostname()
    except Exception:
        host = ""

    _cache = {
        "hostname": host,
        "machine_uuid": machine_uuid(),
        "mac_address": mac_address(),
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
    }
    return _cache
