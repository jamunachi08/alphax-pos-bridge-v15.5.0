"""
DeviceRegistry — owns all devices configured on this bridge.

Loads profiles from disk (built-in + user) and a config file mapping
"this device on this bridge" to "use this profile, with these connection
overrides."

Config file format (config.yaml or config.json) — the bridge reads either:

  bridge:
    bind_host: "127.0.0.1"
    bind_port: 8420
    auth_token: "secret"
  devices:
    - name: front-printer
      kind: printer
      profile: epson-tm-t20iii
      connection:
        transport: usb
        vendor_id: "0x04b8"
        product_id: "0x0e15"
    - name: drawer-1
      kind: drawer
      profile: drawer-via-printer
      connection:
        transport: passthrough
        via: front-printer
    - name: pole-1
      kind: display
      profile: cd5220
      connection:
        transport: serial
        port: "/dev/ttyUSB0"
        baud: 9600
    - name: scale-1
      kind: scale
      profile: toledo-9091
      connection:
        transport: serial
        port: "/dev/ttyUSB1"
        baud: 9600
        parity: E
        bytesize: 7
    - name: card-1
      kind: terminal
      profile: geidea
      provider_options:
        merchant_id: "MID-12345"
        terminal_id: "TID-67890"
        auth_value: "Bearer YOUR_API_KEY"

The user's `connection` block overrides the profile's defaults. They never
have to write a profile from scratch — only override what's different.

Card terminals use `provider_options:` instead of `connection:` since
they're cloud-mediated rather than byte-pushed. The shape is the same.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from .devices import Device
from .protocols import make_protocol
from .terminals import TerminalAdapter, make_terminal
from .transports import make_transport

log = logging.getLogger("alphax-bridge.registry")

# Built-in profiles ship next to this file in `../profiles/`.
DEFAULT_PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"


class DeviceRegistry:

    def __init__(self):
        self._devices: dict[str, Device] = {}
        self._terminals: dict[str, TerminalAdapter] = {}
        self._profiles: dict[str, dict] = {}

    # ---- profile loading -------------------------------------------------

    def load_profiles_from(self, dir_path: Path) -> int:
        n = 0
        if not dir_path.exists():
            return 0
        for p in sorted(dir_path.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                pid = data.get("profile_id") or p.stem
                data["profile_id"] = pid
                self._profiles[pid] = data
                n += 1
            except Exception as e:
                log.warning("skipping bad profile %s: %s", p.name, e)
        # YAML support — only if PyYAML is installed.
        try:
            import yaml  # type: ignore
            for p in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
                try:
                    data = yaml.safe_load(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        pid = data.get("profile_id") or p.stem
                        data["profile_id"] = pid
                        self._profiles[pid] = data
                        n += 1
                except Exception as e:
                    log.warning("skipping bad profile %s: %s", p.name, e)
        except ImportError:
            pass
        return n

    def load_default_profiles(self) -> int:
        return self.load_profiles_from(DEFAULT_PROFILE_DIR)

    def load_user_config(self, path: str | Path) -> int:
        """Load user device config (YAML or JSON). Returns # of devices
        added. Skips devices that fail to instantiate (the failure is
        logged but doesn't abort the whole load — one bad device shouldn't
        prevent the bridge from starting with the rest)."""
        import json as _json
        from pathlib import Path as _Path

        p = _Path(path)
        if not p.exists():
            return 0
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                raise RuntimeError(
                    "YAML config requires PyYAML. pip install pyyaml"
                )
            cfg = yaml.safe_load(text) or {}
        else:
            cfg = _json.loads(text)

        added = 0
        for entry in cfg.get("devices", []) or []:
            try:
                self.add_device_from_config(entry)
                added += 1
            except Exception as e:
                import logging as _log
                _log.getLogger("alphax.registry").warning(
                    "Skipping device %r: %s",
                    entry.get("name", "?"), e,
                )
        return added

    def list_profiles(self) -> list[dict]:
        return [
            {"profile_id": pid,
             "label":    p.get("label", pid),
             "kind":     p.get("kind"),
             "vendor":   p.get("vendor"),
             "model":    p.get("model"),
             "protocol": (p.get("protocol") or {}).get("name")}
            for pid, p in sorted(self._profiles.items())
        ]

    def get_profile(self, profile_id: str) -> Optional[dict]:
        return self._profiles.get(profile_id)

    # ---- device instantiation -------------------------------------------

    def add_device_from_config(self, conf: dict) -> Device | TerminalAdapter:
        """conf is one entry from the `devices` array in config.yaml."""
        name = conf["name"]
        kind = conf.get("kind") or "printer"

        # Card terminals are cloud-mediated; they have a different
        # instantiation path than byte-pushed devices.
        if kind == "terminal":
            return self._add_terminal_from_config(conf)

        profile_id = conf.get("profile")
        profile = self._profiles.get(profile_id) if profile_id else None
        if profile_id and not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        # Merge: user `connection:` overrides profile's defaults.
        merged_connection = {}
        merged_protocol_opts = {}
        if profile:
            merged_connection.update(profile.get("connection", {}))
            merged_protocol_opts.update((profile.get("protocol") or {}).get("options", {}))
        merged_connection.update(conf.get("connection", {}))
        merged_protocol_opts.update(conf.get("protocol_options", {}))

        protocol_name = (
            (conf.get("protocol") or
             (profile or {}).get("protocol", {}).get("name") or
             "raw")
        )
        transport_name = merged_connection.pop("transport", None) or "raw"

        proto = make_protocol(protocol_name, **merged_protocol_opts)
        trans = make_transport(transport_name, registry=self, **merged_connection)
        dev = Device(
            name=name, kind=kind, transport=trans, protocol=proto,
            profile=profile or {"profile_id": "<inline>", "label": name},
        )
        self._devices[name] = dev
        log.info("device added: %s (%s, %s/%s)", name, kind, transport_name, protocol_name)
        return dev

    def _add_terminal_from_config(self, conf: dict) -> TerminalAdapter:
        name = conf["name"]
        profile_id = conf.get("profile")
        profile = self._profiles.get(profile_id) if profile_id else None
        if profile_id and not profile:
            raise ValueError(f"Terminal profile not found: {profile_id}")

        # The provider key comes from the profile or directly in the config.
        provider = (
            conf.get("provider") or
            (profile or {}).get("provider") or "mock"
        )

        merged_opts = {}
        if profile:
            merged_opts.update(profile.get("provider_options", {}))
        merged_opts.update(conf.get("provider_options", {}))

        adapter = make_terminal(provider, **merged_opts)
        try:
            adapter.open()
        except Exception as e:
            log.warning("terminal %s open() failed: %s", name, e)

        self._terminals[name] = adapter
        log.info("terminal added: %s (provider=%s)", name, provider)
        return adapter

    def get_terminal(self, name: str) -> Optional[TerminalAdapter]:
        return self._terminals.get(name)

    def list_terminals(self) -> list[str]:
        return list(self._terminals.keys())

    # ---- access ----------------------------------------------------------

    def get(self, name: str) -> Optional[Device]:
        return self._devices.get(name)

    def by_kind(self, kind: str) -> list[Device]:
        return [d for d in self._devices.values() if d.kind == kind]

    def all(self) -> list[Device]:
        return list(self._devices.values())

    def remove(self, name: str) -> None:
        d = self._devices.pop(name, None)
        if d:
            try: d.close()
            except Exception: pass

    def close_all(self) -> None:
        for d in list(self._devices.values()):
            try: d.close()
            except Exception: pass
        self._devices.clear()
        for t in list(self._terminals.values()):
            try: t.close()
            except Exception: pass
        self._terminals.clear()

    # ---- serialization ---------------------------------------------------

    def info(self) -> dict:
        return {
            "devices":   [d.info() for d in self._devices.values()],
            "terminals": [
                {"name": name, **adapter.status()}
                for name, adapter in self._terminals.items()
            ],
            "profiles":  self.list_profiles(),
        }
