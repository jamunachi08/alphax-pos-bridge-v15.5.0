"""
CLI entry point.

  python -m alphax_bridge --config config.yaml
  python -m alphax_bridge --config config.json --port 8420
  python -m alphax_bridge --discover         # just list detected hardware
  python -m alphax_bridge --list-profiles    # show all built-in profiles

Default config locations searched in order:
  ./config.yaml
  ./config.json
  ~/.alphax-bridge/config.yaml
  ~/.alphax-bridge/config.json
  /etc/alphax-bridge/config.yaml
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from pathlib import Path

from . import __version__
from .registry import DEFAULT_PROFILE_DIR, DeviceRegistry
from .server import serve
from .transports import discover_all


CONFIG_SEARCH = [
    Path.cwd() / "config.yaml",
    Path.cwd() / "config.json",
    Path.home() / ".alphax-bridge" / "config.yaml",
    Path.home() / ".alphax-bridge" / "config.json",
    Path("/etc/alphax-bridge/config.yaml"),
]


def find_config(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    for p in CONFIG_SEARCH:
        if p.exists():
            return p
    return None


def load_config(p: Path) -> dict:
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
            return yaml.safe_load(text) or {}
        except ImportError:
            print("YAML config requires PyYAML. pip install pyyaml", file=sys.stderr)
            sys.exit(2)
    return json.loads(text)


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_discover():
    print(json.dumps(discover_all(), indent=2, default=str))


def cmd_list_profiles():
    reg = DeviceRegistry()
    n = reg.load_default_profiles()
    print(f"# {n} profiles in {DEFAULT_PROFILE_DIR}\n")
    for p in reg.list_profiles():
        print(f"  {p['profile_id']:30s}  {p.get('label','')}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="alphax-bridge",
                                  description="AlphaX POS hardware bridge")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--config",  help="path to config.yaml or config.json")
    ap.add_argument("--port",    type=int, help="override config bind_port")
    ap.add_argument("--host",    help="override config bind_host")
    ap.add_argument("--token",   help="override config auth_token")
    ap.add_argument("--profiles-dir", action="append", default=[],
                    help="extra directory to load profiles from (repeatable)")
    ap.add_argument("--discover",      action="store_true",
                    help="list detected USB / serial / network hardware and exit")
    ap.add_argument("--list-profiles", action="store_true",
                    help="list built-in device profiles and exit")
    ap.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    args = ap.parse_args(argv)

    setup_logging(args.verbose)

    if args.discover:      return cmd_discover()
    if args.list_profiles: return cmd_list_profiles()

    cfg_path = find_config(args.config)
    if not cfg_path:
        print("No config found. See docs/getting-started.md for an example.", file=sys.stderr)
        sys.exit(1)
    cfg = load_config(cfg_path)
    logging.getLogger("alphax-bridge").info("loaded config from %s", cfg_path)

    bridge_cfg = cfg.get("bridge", {})
    host = args.host  or bridge_cfg.get("bind_host", "127.0.0.1")
    port = args.port  or int(bridge_cfg.get("bind_port", 8420))
    token = args.token or bridge_cfg.get("auth_token") or None

    registry = DeviceRegistry()
    registry.load_default_profiles()
    for d in args.profiles_dir:
        registry.load_profiles_from(Path(d))

    for entry in cfg.get("devices", []) or []:
        try:
            registry.add_device_from_config(entry)
        except Exception as e:
            print(f"WARN: could not register device {entry.get('name')!r}: {e}",
                  file=sys.stderr)

    httpd = serve(registry, host=host, port=port, auth_token=token,
                  cors_origin=bridge_cfg.get("cors_origin", "*"))

    def _shutdown(sig, frame):
        logging.getLogger("alphax-bridge").info("shutting down...")
        registry.close_all()
        httpd.shutdown()
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        httpd.serve_forever()
    finally:
        registry.close_all()


if __name__ == "__main__":
    main()
