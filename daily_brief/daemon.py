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

from .brief import build_brief
from .config import DEFAULT_CONFIG_PATH, load_config
from .render import render_brief

log = logging.getLogger("daily_brief.daemon")

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


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
    from .printer import open_printer

    brief = config.brief(brief_name)
    if brief is None:
        log.warning("schedule points to unknown brief %r", brief_name)
        return
    with open_printer(config.printer) as printer:
        render_brief(printer, build_brief(config, brief), config.render)


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

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = config_path
        self.scheduler = Scheduler(config_path)
        self.ap_active = False
        self.web: _WebServer | None = None
        self._btn = None
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
            log.info("access point %r up", cfg.network.ap_ssid)

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

            self._btn = Button(pin, hold_time=1)
            self._btn.when_held = self.start_ap  # hold 1s to (re)open the AP
            log.info("setup button on GPIO %s", pin)
        except Exception as exc:  # gpiozero/lgpio missing, bad pin, etc.
            log.warning("button unavailable: %s", exc)

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
            online = network.is_online()
            if online and self.ap_active:
                self.stop_ap()
            elif not online and not self.ap_active:
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
