"""On-call status from an iCal feed.

Reports whether you're on call *today*, or when your next shift starts. Only
events whose title contains a configurable keyword (default "primary") count, so
a shared rota calendar with several roles still works.

Shifts are often multi-day, so "today" is tested by overlap (an event that
started yesterday and runs through tomorrow still counts), not by start date.

Config options:
    ical_url       the .ics feed (required)
    keyword        case-insensitive substring an event must contain ("primary")
    horizon_days   how far ahead to look for the next shift (default 14)
    hide_when_off  if true, omit the section entirely when not on call (default false)
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import recurring_ical_events

from ..brief import Banner, Section, Text
from .calendar import _day_label, _load_calendar

ONCALL_ICON = "oncall"


def _matches(component, keyword: str) -> bool:
    return keyword in str(component.get("SUMMARY", "")).lower()


def _start_date(component) -> date:
    dt = component.get("DTSTART").dt
    return dt.date() if isinstance(dt, datetime) else dt


def _last_day(component) -> date:
    """Inclusive last day a shift covers (handles iCal's exclusive DTEND)."""
    end = component.get("DTEND")
    if end is None:
        return _start_date(component)
    dt = end.dt
    if isinstance(dt, datetime):
        return (dt - timedelta(seconds=1)).date()
    return dt - timedelta(days=1)  # all-day DTEND is the day *after* the last day


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "ON CALL"

    # Testing override: render a given state without needing a matching event.
    #   force_state = "today" | "upcoming" | "off"
    force_state = section_cfg.get("force_state")
    if force_state == "today":
        return Section(title, [Banner("On call today", icon_key=ONCALL_ICON)])
    if force_state == "upcoming":
        return Section(title, [Text("Next shift Mon 01 Jan")])
    if force_state == "off":
        return Section(title, [Text("Not on call")])

    cal = _load_calendar(section_cfg.get("ical_url"))
    if cal is None:
        return Section(title, [Text("(unavailable)")])

    keyword = str(section_cfg.get("keyword", "primary")).lower()
    horizon = int(section_cfg.get("horizon_days", 14))
    hide_when_off = bool(section_cfg.get("hide_when_off", False))
    today = ctx.now.date()
    query = recurring_ical_events.of(cal)

    # On call today? (any matching shift overlapping today)
    todays = query.between(today, today + timedelta(days=1))
    on_today = [c for c in todays if _matches(c, keyword)]
    if on_today:
        last = max(_last_day(c) for c in on_today)
        if last > today:
            text = f"On call today, until {last:%a %d %b}"
        else:
            text = "On call today"
        return Section(title, [Banner(text, icon_key=ONCALL_ICON)])

    # Otherwise, find the next shift within the horizon.
    ahead = query.between(today + timedelta(days=1), today + timedelta(days=horizon + 1))
    upcoming = sorted(
        (c for c in ahead if _matches(c, keyword)), key=_start_date
    )
    if upcoming:
        start = _start_date(upcoming[0])
        return Section(title, [Text(f"Next shift {_day_label(start, today)} {start:%d %b}")])

    if hide_when_off:
        return None
    return Section(title, [Text(f"Not on call (next {horizon}d)")])
