"""Scheduler daemon: print briefs at their scheduled times.

A minute-resolution loop checks each schedule; when one is due it builds and
prints its brief. The config is reloaded automatically when `config.toml`
changes, so edits from the setup web UI take effect without a restart.

    python -m daily_brief.daemon [--config config.toml]

On the Pi this is the long-running systemd service. Phase 4 extends it with the
setup-mode AP/web/button state machine.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import threading
import time
from pathlib import Path

from .brief import Brief, KeyVal, Section, Text, Title, build_brief
from .config import DEFAULT_CONFIG_PATH, load_config
from .render import render_brief

log = logging.getLogger("daily_brief.daemon")

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _console_url(host: str, port: int) -> str:
    """`http://host` (dropping the default :80) — used in the AP setup notice."""
    return f"http://{host}" if port == 80 else f"http://{host}:{port}"


def ap_notice_brief(config, now: datetime.datetime | None = None) -> Brief:
    """A short receipt telling the user how to join the setup access point."""
    from . import network

    port = config.web.port
    friendly = _console_url(config.network.effective_console_host(), port)
    ip_url = _console_url(network.AP_GATEWAY, port)
    items = [
        KeyVal("Network", config.network.ap_ssid),
        KeyVal("Password", config.network.ap_password),
        KeyVal("Then open", friendly),
        Text("Join this WiFi network from a phone or laptop, then open the "
             "address above in a browser to choose your home network."),
    ]
    if ip_url != friendly:
        items.append(Text(f"If that doesn't load, try {ip_url} — and {friendly} "
                          "keeps working once the Pi is on your home WiFi."))
    return Brief(date=now or datetime.datetime.now(), sections=[
        Section("", [Title("Setup Mode")], bare=True),
        Section("WIFI SETUP", items),
    ])


def shutdown_notice_brief(config, now: datetime.datetime | None = None) -> Brief:
    """A short receipt confirming a button-triggered shutdown is underway."""
    return Brief(date=now or datetime.datetime.now(), sections=[
        Section("", [
            Title("Goodbye", "Powering off…"),
            Text("Wait ~30 seconds before unplugging — the Pi keeps shutting "
                 "down after this prints. Pulling power too early can corrupt "
                 "the SD card."),
        ], bare=True),
    ])


def _is_due(schedule, now: datetime.datetime) -> bool:
    if not schedule.enabled or not schedule.brief:
        return False
    if schedule.time != now.strftime("%H:%M"):
        return False
    if schedule.days and DAY_KEYS[now.weekday()] not in schedule.days:
        return False
    return True


def due_schedules(config, now: datetime.datetime, last_fired: dict) -> list:
    """Schedules due at `now` that haven't fired today; records the firing."""
    out = []
    for s in config.schedules:
        key = (s.name, s.brief, s.time)
        if _is_due(s, now) and last_fired.get(key) != now.date():
            last_fired[key] = now.date()
            out.append(s)
    return out


def print_brief(config, brief_name: str) -> None:
    """Build and print a brief by name (no-op-safe with the dummy backend)."""
    from . import lastbrief

    brief = config.brief(brief_name)
    if brief is None:
        log.warning("schedule points to unknown brief %r", brief_name)
        return
    # print_and_save records it so the button can reprint without rebuilding.
    lastbrief.print_and_save(config, build_brief(config, brief))


class Scheduler:
    """Reloadable scheduler. `tick()` is pure-ish for testing; `run()` loops."""

    def __init__(self, config_path: str | Path | None = None):
        self.path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config = load_config(self.path)
        self._mtime = self._stat()
        self.last_fired: dict = {}
        self._last_mail_poll: float | None = None  # monotonic; None = never polled
        self._stop = threading.Event()

    def _stat(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def reload_if_changed(self) -> None:
        mtime = self._stat()
        if mtime != self._mtime:
            self._mtime = mtime
            self.config = load_config(self.path)
            log.info("config reloaded (%d schedules)", len(self.config.schedules))

    def tick(self, now: datetime.datetime | None = None) -> None:
        now = now or datetime.datetime.now()
        self.reload_if_changed()
        for s in due_schedules(self.config, now, self.last_fired):
            log.info("firing %r -> brief %r", s.name, s.brief)
            try:
                print_brief(self.config, s.brief)
            except Exception as exc:
                log.error("print failed for %r: %s", s.brief, exc)
        self._poll_mail()

    def _poll_mail(self) -> None:
        """Print any newly-arrived approved email, throttled to poll_seconds."""
        ec = self.config.email
        if not ec.active:
            return
        mono = time.monotonic()
        if self._last_mail_poll is not None and (mono - self._last_mail_poll) < ec.poll_seconds:
            return
        self._last_mail_poll = mono
        from .mailbox import poll_and_print

        try:
            poll_and_print(self.config)
        except Exception as exc:
            log.error("mailbox poll failed: %s", exc)

    def run(self, interval: float = 20.0) -> None:
        from . import printqueue

        printqueue.QUEUE.start()  # serialize all printing through one worker
        log.info("scheduler started (%d schedules)", len(self.config.schedules))
        while not self._stop.wait(interval):
            try:
                self.tick()
            except Exception as exc:
                log.error("tick error: %s", exc)

    def stop(self) -> None:
        self._stop.set()


class _WebServer:
    """Run the Flask setup app in a background thread; start/stop on demand."""

    def __init__(self, app, host: str, port: int):
        from werkzeug.serving import make_server

        self._srv = make_server(host, port, app, threaded=True)
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._srv.shutdown()


class Controller:
    """Always-on console + scheduler, plus the WiFi access-point state machine.

    The password-protected web console and the scheduler run at all times. The
    setup access point is brought up only while the device is offline (and by the
    physical button, to change WiFi); it drops automatically once we're online
    again. Without `nmcli` (e.g. a laptop) there's no AP control — just the
    console + scheduler.
    """

    # Button gestures. A single tap reprints; a quick double-tap opens the AP;
    # a long hold shuts the Pi down. TAP_WINDOW is how long we wait for a second
    # tap before acting on a single one; HOLD_SECONDS is the shutdown threshold;
    # BOUNCE_SECONDS debounces contact chatter so one press isn't seen as two.
    TAP_WINDOW = 0.4
    HOLD_SECONDS = 5
    BOUNCE_SECONDS = 0.1

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = config_path
        self.scheduler = Scheduler(config_path)
        self.ap_active = False
        self.web: _WebServer | None = None
        self._btn = None
        self._held = False           # set while a hold (shutdown) is in progress
        self._taps = 0               # taps seen in the current TAP_WINDOW
        self._tap_timer: threading.Timer | None = None
        self._stop = threading.Event()

    def _start_web(self):
        """Start the always-on control console (password-protected)."""
        cfg = self.scheduler.config
        from .web import create_app

        try:
            self.web = _WebServer(create_app(self.config_path), "0.0.0.0", cfg.web.port)
            self.web.start()
            log.info("console on :%d", cfg.web.port)
        except Exception as exc:  # e.g. port 80 needs root, or already bound
            log.error("web console failed to start: %s", exc)

    def start_ap(self):
        """Bring up the setup access point (for entering/changing WiFi)."""
        if self.ap_active:
            return
        cfg = self.scheduler.config
        from . import network

        if network.start_ap(cfg.network.ap_ssid, cfg.network.ap_password):
            self.ap_active = True
            log.info("access point %r up (console at http://%s)",
                     cfg.network.ap_ssid, cfg.network.effective_console_host())

    def stop_ap(self):
        if not self.ap_active:
            return
        from . import network

        network.stop_ap()
        self.ap_active = False
        log.info("access point down (online)")

    def _install_button(self):
        pin = self.scheduler.config.network.button_gpio
        if pin is None:
            return
        try:
            from gpiozero import Button

            # `when_held` fires once after HOLD_SECONDS; taps are counted on
            # release (see _on_release) so one button serves all three actions.
            # `bounce_time` ignores contact chatter so one press isn't counted
            # twice (which a tap would misread as the double-tap = open-AP).
            self._btn = Button(pin, hold_time=self.HOLD_SECONDS,
                               bounce_time=self.BOUNCE_SECONDS)
            self._btn.when_held = self._on_hold
            self._btn.when_released = self._on_release
            log.info("setup button on GPIO %s", pin)
        except Exception as exc:  # gpiozero/lgpio missing, bad pin, etc.
            log.warning("button unavailable: %s", exc)

    # --- button gesture handling ------------------------------------------

    def _on_hold(self):
        """Held past HOLD_SECONDS: shut down (and don't treat release as a tap)."""
        self._held = True
        self._shutdown()

    def _on_release(self):
        """Count a tap and (re)arm the timer that fires once the taps settle."""
        if self._held:  # this release ends a hold, not a tap
            self._held = False
            return
        self._taps += 1
        if self._tap_timer is not None:
            self._tap_timer.cancel()
        self._tap_timer = threading.Timer(self.TAP_WINDOW, self._flush_taps)
        self._tap_timer.daemon = True
        self._tap_timer.start()

    def _flush_taps(self):
        count, self._taps = self._taps, 0
        self._dispatch_taps(count)

    def _dispatch_taps(self, count: int):
        """Map a settled tap count to an action: 1 = reprint, 2+ = open AP."""
        if count >= 2:
            log.info("button: double tap -> WiFi setup")
            self.start_ap()
            self._print_ap_notice()  # tell the user how to connect
        elif count == 1:
            log.info("button: tap -> reprint last brief")
            self._reprint()

    # --- button actions ----------------------------------------------------

    def _reprint(self):
        from . import lastbrief

        lastbrief.reprint(self.scheduler.config)

    def _print_notice(self, brief):
        """Print a one-off notice receipt (no daily-brief footer); never raises.

        Goes through the shared print queue (so it can't collide with a brief or
        email) and waits, so a goodbye notice is on paper before we power off.
        """
        cfg = self.scheduler.config
        from .printer import open_printer
        from . import printqueue

        def _do():
            with open_printer(cfg.printer) as printer:
                render_brief(printer, brief, cfg.render, footer=False, printer_cfg=cfg.printer)

        printqueue.submit("notice", _do).wait()

    def _print_ap_notice(self):
        """Print the AP's SSID/password/URL so a screenless device is usable."""
        self._print_notice(ap_notice_brief(self.scheduler.config))

    def _shutdown(self):
        log.info("button: long hold -> shutting down")
        # Print the goodbye first so it's confirmed before the OS goes down.
        self._print_notice(shutdown_notice_brief(self.scheduler.config))
        import subprocess

        from .privilege import sudo_wrap

        try:
            subprocess.run(sudo_wrap(["shutdown", "-h", "now"]), check=False)
        except OSError as exc:
            log.error("shutdown failed: %s", exc)

    def run(self, interval: float = 5.0):
        from . import network

        # The console and scheduler run at all times.
        self._start_web()
        threading.Thread(target=self.scheduler.run, daemon=True).start()

        if not network.available():
            log.info("nmcli not found — console + scheduler only (no AP control)")
            self._stop.wait()  # block forever; the threads do the work
            return

        self._install_button()
        # AP serves the console while offline; it drops once we're back online.
        while not self._stop.wait(interval):
            # Sync to the real hotspot state first: a WiFi-join attempt from the
            # console switches the single radio to client mode (dropping the AP)
            # without going through stop_ap(), so the cached flag can be stale.
            self.ap_active = network.hotspot_active()
            online = network.is_online()
            if online and self.ap_active:
                self.stop_ap()
            elif not online and not self.ap_active and not network.ap_suppressed():
                # Skip while a console-initiated WiFi join holds the radio, so we
                # don't reopen the AP and interrupt the association in progress.
                self.start_ap()

    def stop(self):
        self._stop.set()
        self.scheduler.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily_brief.daemon")
    parser.add_argument("--config", help="Path to config.toml.")
    parser.add_argument(
        "--no-setup", action="store_true",
        help="Run only the scheduler (skip AP/web/button setup mode).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.no_setup:
        Scheduler(args.config).run()
    else:
        Controller(args.config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
