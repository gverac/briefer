"""Scheduler: due-detection, day filtering, no double-fire, tick wiring."""

from __future__ import annotations

import datetime

from daily_brief import daemon
from daily_brief.config import Config, ScheduleConfig


def _cfg():
    return Config(schedules=[
        ScheduleConfig(name="morning", brief="m", time="07:30"),                 # daily
        ScheduleConfig(name="weekday", brief="w", time="12:00",
                       days=["mon", "tue", "wed", "thu", "fri"]),
        ScheduleConfig(name="off", brief="x", time="07:30", enabled=False),
    ])


def test_daily_fires_any_day():
    sat = datetime.datetime(2026, 6, 13, 7, 30)  # Saturday
    fired = daemon.due_schedules(_cfg(), sat, {})
    assert [s.name for s in fired] == ["morning"]  # weekday excluded, off disabled


def test_weekday_only():
    mon_noon = datetime.datetime(2026, 6, 15, 12, 0)  # Monday
    assert [s.name for s in daemon.due_schedules(_cfg(), mon_noon, {})] == ["weekday"]
    sun_noon = datetime.datetime(2026, 6, 14, 12, 0)  # Sunday
    assert daemon.due_schedules(_cfg(), sun_noon, {}) == []


def test_no_double_fire_same_day():
    cfg, last = _cfg(), {}
    t = datetime.datetime(2026, 6, 15, 7, 30)
    assert len(daemon.due_schedules(cfg, t, last)) == 1
    assert daemon.due_schedules(cfg, t, last) == []           # already fired
    assert len(daemon.due_schedules(cfg, t.replace(day=16), last)) == 1  # next day fires


def test_tick_prints_due_brief(monkeypatch, tmp_path):
    printed = []
    monkeypatch.setattr(daemon, "print_brief", lambda cfg, name: printed.append(name))
    sch = daemon.Scheduler(config_path=tmp_path / "none.toml")  # missing file -> empty
    sch.config = _cfg()
    sch.tick(datetime.datetime(2026, 6, 15, 7, 30))  # Monday 07:30
    assert printed == ["m"]


def _controller(tmp_path):
    return daemon.Controller(config_path=tmp_path / "none.toml")  # defaults, no button


def test_single_tap_reprints(tmp_path):
    ctrl = _controller(tmp_path)
    called = []
    ctrl._reprint = lambda: called.append("reprint")
    ctrl.start_ap = lambda: called.append("ap")
    ctrl._dispatch_taps(1)
    assert called == ["reprint"]


def test_double_tap_opens_ap_and_prints_notice(tmp_path):
    ctrl = _controller(tmp_path)
    called = []
    ctrl._reprint = lambda: called.append("reprint")
    ctrl.start_ap = lambda: called.append("ap")
    ctrl._print_ap_notice = lambda: called.append("notice")
    ctrl._dispatch_taps(2)
    assert called == ["ap", "notice"]  # AP up first, then tell the user how to join


def _notice_text(brief):
    return " ".join(
        f"{getattr(i, 'label', '')} {getattr(i, 'value', '')} {getattr(i, 'text', '')}"
        for s in brief.sections for i in s.items
    )


def test_ap_notice_includes_credentials_and_console_url():
    from daily_brief import network
    from daily_brief.config import Config, NetworkConfig, WebConfig

    cfg = Config(
        network=NetworkConfig(ap_ssid="my-ap", ap_password="secret123",
                              console_host="hello.local"),
        web=WebConfig(port=8080),
    )
    text = _notice_text(daemon.ap_notice_brief(cfg))
    assert "my-ap" in text
    assert "secret123" in text
    assert "http://hello.local:8080" in text             # the persistent name, primary
    assert f"{network.AP_GATEWAY}:8080" in text           # bare IP, fallback


def test_ap_notice_drops_default_port():
    from daily_brief.config import Config, NetworkConfig, WebConfig

    cfg = Config(network=NetworkConfig(console_host="briefer.local"), web=WebConfig(port=80))
    text = _notice_text(daemon.ap_notice_brief(cfg))
    assert "http://briefer.local" in text
    assert ":80" not in text          # default port is dropped from the URL


def test_console_host_defaults_to_hostname_dot_local(monkeypatch):
    import socket

    from daily_brief.config import NetworkConfig

    monkeypatch.setattr(socket, "gethostname", lambda: "cedar")
    assert NetworkConfig(console_host="").effective_console_host() == "cedar.local"
    # an explicit override wins over the derived default
    assert NetworkConfig(console_host="custom.lan").effective_console_host() == "custom.lan"


def test_console_url_formatting():
    assert daemon._console_url("briefer.local", 80) == "http://briefer.local"
    assert daemon._console_url("briefer.local", 8080) == "http://briefer.local:8080"


def test_shutdown_prints_goodbye_before_powering_off(tmp_path):
    ctrl = _controller(tmp_path)
    order = []
    ctrl._print_notice = lambda brief: order.append(("print", brief))
    import subprocess

    import daily_brief.daemon as d
    orig = subprocess.run
    subprocess.run = lambda *a, **k: order.append(("run", a[0]))
    try:
        ctrl._shutdown()
    finally:
        subprocess.run = orig

    assert [step for step, _ in order] == ["print", "run"]      # goodbye first
    assert isinstance(order[0][1], d.Brief)
    assert order[1][1] == ["shutdown", "-h", "now"]


def test_shutdown_notice_brief_says_goodbye():
    from daily_brief.config import Config

    brief = daemon.shutdown_notice_brief(Config())
    titles = [i.text for s in brief.sections for i in s.items if isinstance(i, daemon.Title)]
    assert "Goodbye" in titles


def test_hold_shuts_down_and_skips_tap(tmp_path):
    ctrl = _controller(tmp_path)
    shut = []
    ctrl._shutdown = lambda: shut.append(True)
    ctrl._on_hold()                 # held past the threshold -> shutdown
    assert shut == [True]
    assert ctrl._held is True
    ctrl._on_release()              # the release that ends the hold isn't a tap
    assert ctrl._held is False
    assert ctrl._taps == 0
    assert ctrl._tap_timer is None  # no tap timer was armed
