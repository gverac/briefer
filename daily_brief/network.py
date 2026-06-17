"""NetworkManager (`nmcli`) wrapper for setup mode.

Bookworm ships NetworkManager, which can create a WiFi hotspot and join networks
with a few `nmcli` calls. Everything here degrades safely: if `nmcli` isn't
present (e.g. on a laptop) `available()` is False and the daemon skips setup
mode entirely, just running the scheduler.

The daemon must run as root for these to work (AP + connection changes).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time

log = logging.getLogger("daily_brief.network")

HOTSPOT_CON = "Hotspot"  # connection name nmcli uses for `wifi hotspot`

# NetworkManager's `wifi hotspot` (shared mode) always hands out this gateway, so
# the setup console is reachable at this IP while a device is joined to the AP.
AP_GATEWAY = "10.42.0.1"

# A WiFi join and the daemon's AP-reconcile loop both drive the single radio. To
# stop the loop from grabbing it mid-association (which interrupts the join),
# connect() suppresses AP reopening for a grace window; the loop honors it via
# ap_suppressed(). The window covers association + DHCP + the connectivity check.
_JOIN_GRACE = 75.0
_suppress_lock = threading.Lock()
_suppress_until = 0.0


def suppress_ap(seconds: float) -> None:
    """Ask the reconcile loop not to (re)open the AP for the next `seconds`."""
    global _suppress_until
    with _suppress_lock:
        _suppress_until = max(_suppress_until, time.monotonic() + seconds)


def resume_ap() -> None:
    """Clear any AP suppression (e.g. a join failed — let setup mode return)."""
    global _suppress_until
    with _suppress_lock:
        _suppress_until = 0.0


def ap_suppressed() -> bool:
    """True while a WiFi join is in progress and the AP should stay down."""
    with _suppress_lock:
        return time.monotonic() < _suppress_until


def available() -> bool:
    """True if nmcli exists — i.e. we're on a NetworkManager system (the Pi)."""
    return shutil.which("nmcli") is not None


def _run(args: list[str], timeout: float = 20.0, quiet: bool = False) -> tuple[int, str]:
    """Run `nmcli args...`; return (returncode, stdout). (-1, "") on error.

    `quiet` downgrades the failure log to debug — for best-effort calls whose
    failure is expected (e.g. deleting a profile that may not exist).
    """
    try:
        proc = subprocess.run(
            ["nmcli", *args], capture_output=True, text=True, timeout=timeout
        )
        if proc.returncode != 0:
            (log.debug if quiet else log.warning)(
                "nmcli %s failed: %s", " ".join(args), proc.stderr.strip())
        return proc.returncode, proc.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("nmcli %s errored: %s", " ".join(args), exc)
        return -1, ""


def is_online() -> bool:
    """True when NetworkManager reports full connectivity."""
    if not available():
        return False
    rc, out = _run(["-t", "-f", "CONNECTIVITY", "general", "status"], timeout=8)
    return rc == 0 and out.strip() == "full"


def current_ssid() -> str | None:
    """SSID of the active WiFi connection, or None."""
    rc, out = _run(["-t", "-f", "ACTIVE,SSID", "dev", "wifi"], timeout=8)
    if rc != 0:
        return None
    for line in out.splitlines():
        if line.startswith("yes:"):
            return line.split(":", 1)[1] or None
    return None


def scan() -> list[dict]:
    """Nearby networks as [{ssid, signal, secure}], strongest first, deduped."""
    _run(["dev", "wifi", "rescan"], timeout=15)  # best-effort refresh
    rc, out = _run(["-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi"], timeout=15)
    if rc != 0:
        return []
    best: dict[str, dict] = {}
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 3 or not parts[0]:
            continue
        ssid = parts[0]
        try:
            signal = int(parts[1])
        except ValueError:
            signal = 0
        secure = parts[2] not in ("", "--", "none")
        if ssid not in best or signal > best[ssid]["signal"]:
            best[ssid] = {"ssid": ssid, "signal": signal, "secure": secure}
    return sorted(best.values(), key=lambda d: d["signal"], reverse=True)


def connect(ssid: str, password: str | None) -> tuple[bool, str]:
    """Join a WiFi network. Returns (ok, message).

    Builds the profile with explicit WPA-PSK security rather than letting
    `nmcli dev wifi connect` infer it from a scan. In setup mode the single
    radio is busy running the AP, so the target network isn't in the scan cache
    and nmcli fails with "802-11-wireless-security.key-mgmt: property is
    missing". Bringing the profile up switches the radio from AP to client; if
    it fails we drop the half-made profile and the daemon's reconcile loop
    reopens the AP so the user can retry.
    """
    # Hold off the daemon's AP-reconcile loop: the join briefly leaves us
    # offline with the hotspot down, which would otherwise trip the loop into
    # reopening the AP and stealing the radio mid-association.
    suppress_ap(_JOIN_GRACE)
    _run(["connection", "delete", ssid], timeout=10, quiet=True)  # clear any stale profile
    add = ["connection", "add", "type", "wifi", "con-name", ssid,
           "ssid", ssid, "connection.autoconnect", "yes"]
    if password:
        add += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
    rc, _ = _run(add, timeout=20)
    if rc == 0:
        rc, _ = _run(["connection", "up", ssid], timeout=60)
    if rc == 0:
        return True, f"Connected to {ssid}."
    _run(["connection", "delete", ssid], timeout=10, quiet=True)  # don't leave a broken profile
    resume_ap()  # join failed — let the setup AP come back so the user can retry
    return False, f"Could not connect to {ssid} (check the password)."


def hotspot_active() -> bool:
    """True if our setup hotspot is the currently-active connection."""
    rc, out = _run(["-t", "-f", "NAME", "connection", "show", "--active"], timeout=8)
    return rc == 0 and any(line.strip() == HOTSPOT_CON for line in out.splitlines())


def start_ap(ssid: str, password: str) -> bool:
    """Bring up the setup access point. Takes the radio offline (single radio)."""
    rc, _ = _run(["dev", "wifi", "hotspot", "ssid", ssid, "password", password], timeout=30)
    return rc == 0


def stop_ap() -> None:
    """Tear the hotspot down (ignored if it isn't up)."""
    _run(["connection", "down", HOTSPOT_CON], timeout=15)
