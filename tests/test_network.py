"""WiFi join + hotspot-state helpers (nmcli is faked, so these run anywhere)."""

from __future__ import annotations

import pytest

from daily_brief import network


@pytest.fixture(autouse=True)
def _clear_suppression():
    network.resume_ap()  # connect() sets a module-level window; isolate tests
    yield
    network.resume_ap()


def _fake_run(monkeypatch, returns):
    """Record nmcli calls; `returns` maps a verb (args[0]) to (rc, stdout)."""
    calls = []

    def fake(args, timeout=20.0, quiet=False):
        calls.append(args)
        return returns.get(args[0], (0, ""))

    monkeypatch.setattr(network, "_run", fake)
    return calls


def test_connect_sets_explicit_wpa_security(monkeypatch):
    calls = _fake_run(monkeypatch, {})
    ok, msg = network.connect("ZGN", "hunter2")
    assert ok and "ZGN" in msg

    add = next(c for c in calls if c[:2] == ["connection", "add"])
    assert "wifi-sec.key-mgmt" in add and add[add.index("wifi-sec.key-mgmt") + 1] == "wpa-psk"
    assert add[add.index("wifi-sec.psk") + 1] == "hunter2"
    assert ["connection", "up", "ZGN"] in calls


def test_connect_open_network_has_no_security(monkeypatch):
    calls = _fake_run(monkeypatch, {})
    ok, _ = network.connect("Cafe", None)
    assert ok
    add = next(c for c in calls if c[:2] == ["connection", "add"])
    assert "wifi-sec.key-mgmt" not in add and "wifi-sec.psk" not in add


def test_connect_suppresses_ap_during_attempt(monkeypatch):
    _fake_run(monkeypatch, {})
    assert not network.ap_suppressed()
    network.connect("ZGN", "hunter2")           # success path
    assert network.ap_suppressed()              # loop must back off while joined


def test_connect_failure_cleans_up_and_resumes_ap(monkeypatch):
    calls = []

    def fake(args, timeout=20.0, quiet=False):
        calls.append(args)
        return (1, "") if args[:2] == ["connection", "up"] else (0, "")

    monkeypatch.setattr(network, "_run", fake)
    ok, msg = network.connect("ZGN", "wrongpw")
    assert not ok and "check the password" in msg
    # The broken profile is deleted so it can't auto-activate later.
    assert calls.count(["connection", "delete", "ZGN"]) >= 2
    # A failed join must let the setup AP come back for a retry.
    assert not network.ap_suppressed()


def test_hotspot_active_parses_active_connections(monkeypatch):
    _fake_run(monkeypatch, {"-t": (0, f"some-wifi\n{network.HOTSPOT_CON}\n")})
    assert network.hotspot_active() is True
    _fake_run(monkeypatch, {"-t": (0, "some-wifi\n")})
    assert network.hotspot_active() is False
