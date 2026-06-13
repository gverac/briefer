"""Daylight section: sunrise, sunset, and day length with a day-over-day delta.

Computed locally with `astral` from the configured lat/lon/tz, so it works with
no network at all.
"""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

from ..brief import KeyVal, Section


def _day_length(observer, date, tz) -> timedelta:
    s = sun(observer, date=date, tzinfo=tz)
    return s["sunset"] - s["sunrise"]


def _fmt_hm(td: timedelta) -> str:
    total_minutes = int(round(td.total_seconds() / 60))
    return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "DAYLIGHT"
    loc = ctx.location
    tz = ZoneInfo(loc.tz)

    info = LocationInfo(latitude=loc.lat, longitude=loc.lon, timezone=loc.tz)
    today = ctx.now.date()

    s = sun(info.observer, date=today, tzinfo=tz)
    length = s["sunset"] - s["sunrise"]
    prev_length = _day_length(info.observer, today - timedelta(days=1), tz)

    delta_min = int(round((length - prev_length).total_seconds() / 60))
    sign = "+" if delta_min >= 0 else "-"
    delta = f"({sign}{abs(delta_min)}m)"

    return Section(
        title,
        [
            KeyVal("Sunrise", s["sunrise"].strftime("%H:%M")),
            KeyVal("Sunset", s["sunset"].strftime("%H:%M")),
            KeyVal("Daylight", f"{_fmt_hm(length)} {delta}"),
        ],
    )
