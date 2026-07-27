"""
Pairing — closes the loop on the "install the bridge" flow in the POS.

When the cashier clicks Download in the onboarding wizard, the site mints
a short-lived pair token and bakes it into the installer arguments. On
first start the bridge posts back to the site with that token, so the
wizard's spinner resolves without the cashier copying anything between
screens.

Deliberately fire-and-forget: pairing failing must never stop the daemon
from serving printers. The SPA also polls the local port independently,
so a failed call-home degrades to "detected a second later" rather than
to a broken install.

Config keys (written by the installer / wizard into config.yaml):

    pair_url:   https://pos.example.com
    pair_token: <opaque>

Both are cleared from the config after a successful pair — the token is
single-use and there is no reason to keep it on disk.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request

from . import __version__
from .identity import system_info

log = logging.getLogger("alphax-bridge.pairing")

ENDPOINT = ("/api/method/alphax_pos_suite.alphax_pos_suite.onboarding"
            ".bridge_registry.confirm_pairing")


def pair_async(pair_url: str, pair_token: str, port: int,
               on_done=None) -> None:
    """Fire the call-home on a daemon thread so startup is not delayed."""
    if not pair_url or not pair_token:
        return
    t = threading.Thread(
        target=_pair, args=(pair_url, pair_token, port, on_done),
        daemon=True, name="alphax-bridge-pairing")
    t.start()


def _pair(pair_url: str, pair_token: str, port: int, on_done) -> None:
    url = pair_url.rstrip("/") + ENDPOINT
    payload = json.dumps({
        "pair_token": pair_token,
        "bridge_info": {
            "version": __version__,
            "port": port,
            "system": system_info(),
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": f"alphax-pos-bridge/{__version__}"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
        ok = bool((body.get("message") or {}).get("ok"))
        log.info("pairing %s", "succeeded" if ok else "rejected by site")
        if on_done:
            on_done(ok)
    except urllib.error.HTTPError as e:
        log.warning("pairing failed: HTTP %s", e.code)
    except Exception as e:
        # Offline shop, wrong URL, TLS interception — all survivable.
        log.warning("pairing failed: %s", e)
