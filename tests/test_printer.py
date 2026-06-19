"""Tests that run without any printer hardware (dummy backend).

The brief is now rendered as a bitmap, so these check the render pipeline and
the printer factory rather than decoding ESC/POS text.
"""

from __future__ import annotations

from datetime import datetime

from daily_brief import lastbrief
from daily_brief.brief import Brief, Checkbox, KeyVal, Section, Text, Weather
from daily_brief.config import Config, PrinterConfig, RenderConfig
from daily_brief.printer import make_printer, open_printer
from daily_brief.render import render_brief


def _sample_brief() -> Brief:
    return Brief(
        date=datetime(2026, 6, 12, 8, 0),
        sections=[
            Section("WEATHER", [Weather("rain", hi=24.0, lo=12.0, desc="Light rain")]),
            Section("BIRTHDAYS", [Checkbox("Alice"), Checkbox("Bob")]),
            Section("DAYLIGHT", [KeyVal("Daylight", "15h 01m (+1m)")]),
            Section("JOKE", [Text("A short joke that wraps across a couple of lines.")]),
        ],
    )


def test_render_to_dummy_backend_produces_image():
    cfg = RenderConfig(dot_width=384)
    printer = make_printer(PrinterConfig(backend="dummy"))
    image = render_brief(printer, _sample_brief(), cfg)

    assert image.width == 384
    assert image.height > 100  # content was actually drawn
    assert len(printer.output) > 0  # bytes were sent to the device


def test_render_without_printer_returns_image():
    cfg = RenderConfig(dot_width=384)
    image = render_brief(None, _sample_brief(), cfg)
    assert image.size[0] == 384


def test_open_printer_context_manager():
    with open_printer(PrinterConfig(backend="dummy")) as printer:
        printer.text("hello\n")
        assert b"hello" in printer.output


def test_unknown_backend_raises():
    try:
        make_printer(PrinterConfig(backend="nope"))
    except ValueError as exc:
        assert "Unknown printer backend" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown backend")


def test_default_config_is_dummy():
    assert Config().printer.backend == "dummy"


def test_reprint_round_trips_saved_brief(monkeypatch, tmp_path):
    monkeypatch.setattr(lastbrief, "LAST_BRIEF_PATH", tmp_path / "last_brief.png")
    cfg = Config(printer=PrinterConfig(backend="dummy"))

    assert lastbrief.reprint(cfg) is False  # nothing saved yet

    image = render_brief(None, _sample_brief(), cfg.render)
    lastbrief.save(image)
    assert (tmp_path / "last_brief.png").is_file()

    sent = []
    monkeypatch.setattr(lastbrief, "send_image", lambda printer, img, cfg=None: sent.append(img.size))
    assert lastbrief.reprint(cfg) is True
    assert sent == [image.size]  # the saved bitmap was re-sent verbatim


def test_print_and_save_records_for_reprint(monkeypatch, tmp_path):
    # Printing through the shared helper must leave a brief the button can reprint.
    monkeypatch.setattr(lastbrief, "LAST_BRIEF_PATH", tmp_path / "last_brief.png")
    cfg = Config(printer=PrinterConfig(backend="dummy"))

    lastbrief.print_and_save(cfg, _sample_brief())
    assert (tmp_path / "last_brief.png").is_file()
    assert lastbrief.reprint(cfg) is True  # reprint now has something to print
