"""Countdown section: days-remaining, arrival message, past-date hiding, bar."""

from __future__ import annotations

from datetime import datetime

from daily_brief.brief import Banner, ProgressBar
from daily_brief.config import Config, SectionConfig
from daily_brief.sources import SourceContext, countdown


def _ctx(now: datetime) -> SourceContext:
    return SourceContext(config=Config(), now=now)


def _build(now: datetime, **options):
    cfg = SectionConfig(type="countdown", options=options)
    return countdown.build(cfg, _ctx(now))


def test_future_date_shows_day_count():
    sec = _build(datetime(2026, 6, 15), target_date="2026-06-25", label="Vacation")
    assert isinstance(sec.items[0], Banner)
    assert sec.items[0].text == "10 days until Vacation"


def test_singular_day():
    sec = _build(datetime(2026, 6, 24), target_date="2026-06-25", label="Vacation")
    assert sec.items[0].text == "1 day until Vacation"


def test_no_label_uses_generic_phrasing():
    sec = _build(datetime(2026, 6, 15), target_date="2026-06-18")
    assert sec.items[0].text == "3 days to go"


def test_arrival_message_on_the_day():
    sec = _build(datetime(2026, 12, 25), target_date="2026-12-25", label="Christmas")
    assert isinstance(sec.items[0], Banner)
    assert sec.items[0].text == "Christmas is here!"


def test_custom_arrival_message():
    sec = _build(datetime(2026, 12, 25), target_date="2026-12-25",
                 label="Christmas", arrived_message="Merry Christmas!")
    assert sec.items[0].text == "Merry Christmas!"


def test_past_date_is_hidden():
    assert _build(datetime(2026, 6, 26), target_date="2026-06-25") is None


def test_progress_bar_fraction():
    # 10-day window, 7 days elapsed -> 70%.
    sec = _build(datetime(2026, 6, 8), target_date="2026-06-11",
                 start_date="2026-06-01", progress_bar=True)
    bar = next(i for i in sec.items if isinstance(i, ProgressBar))
    assert abs(bar.fraction - 0.7) < 1e-9


def test_progress_bar_skipped_without_start_date():
    sec = _build(datetime(2026, 6, 8), target_date="2026-06-11", progress_bar=True)
    assert not any(isinstance(i, ProgressBar) for i in sec.items)


def test_invalid_target_date_degrades():
    sec = _build(datetime(2026, 6, 15), target_date="not-a-date")
    assert sec is not None  # graceful placeholder, not a crash
    assert "target" in sec.items[0].text.lower()
