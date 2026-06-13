"""Birthdays and upcoming events from a published iCal (.ics) feed.

Both builders share the same pipeline: fetch the ICS text (cached), parse it
with `icalendar`, and expand recurrences (yearly birthdays, weekly meetings, …)
over a date window with `recurring_ical_events`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import recurring_ical_events
from icalendar import Calendar

from ..brief import Bullet, Checkbox, Section, Text
from ._http import get_text


def _normalize_ical_url(url: str) -> str:
    """webcal:// is just an HTTP(S) URL by convention; requests can't fetch it."""
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://") :]
    if url.startswith("webcals://"):
        return "https://" + url[len("webcals://") :]
    return url


def _load_calendar(url: str | None) -> Calendar | None:
    if not url:
        return None
    text = get_text(_normalize_ical_url(url), ttl=3600)
    if not text:
        return None
    try:
        return Calendar.from_ical(text)
    except ValueError:
        return None


def _occ_start(component):
    """Return the occurrence's DTSTART as a (date, datetime-for-sorting) pair."""
    dt = component.get("DTSTART").dt
    if isinstance(dt, datetime):
        return dt.date(), dt
    return dt, datetime(dt.year, dt.month, dt.day)


def _occurrences(cal: Calendar, start: date, horizon_days: int):
    """Expanded occurrences whose start date falls in [start, start+horizon]."""
    end_exclusive = start + timedelta(days=horizon_days + 1)
    occs = recurring_ical_events.of(cal).between(start, end_exclusive)
    out = []
    for comp in occs:
        d, sort_dt = _occ_start(comp)
        if start <= d <= start + timedelta(days=horizon_days):
            out.append((d, sort_dt, comp))
    out.sort(key=lambda t: t[1])
    return out


def _day_label(d: date, today: date) -> str:
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return d.strftime("%a")


_BIRTHDAY_RE = re.compile(r"['’]s birthday$|\s*birthday$", re.IGNORECASE)


def _clean_birthday_name(summary: str) -> str:
    s = re.sub(r"^\s*[\U0001F382❤️]+\s*", "", summary).strip()  # strip cake/heart
    s = _BIRTHDAY_RE.sub("", s).strip()
    return s or summary.strip()


# --- builders --------------------------------------------------------------


def build_birthdays(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "BIRTHDAYS"
    cal = _load_calendar(section_cfg.get("ical_url"))
    if cal is None:
        return Section(title, [Text("(unavailable)")])

    horizon = int(section_cfg.get("horizon_days", 0))
    use_checkbox = bool(section_cfg.get("checkbox", True))
    today = ctx.now.date()

    items = []
    for d, _sort, comp in _occurrences(cal, today, horizon):
        name = _clean_birthday_name(str(comp.get("SUMMARY", "")))
        label = name if d == today else f"{name} - {_day_label(d, today)}"
        items.append(Checkbox(label) if use_checkbox else Text(label))

    if not items:
        return Section(title, [Text("None today")])
    return Section(title, items)


def build_events(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "UPCOMING"
    cal = _load_calendar(section_cfg.get("ical_url"))
    if cal is None:
        return Section(title, [Text("(unavailable)")])

    horizon = int(section_cfg.get("horizon_days", 3))
    max_items = int(section_cfg.get("max_items", 6))
    today = ctx.now.date()

    items = []
    for d, _sort, comp in _occurrences(cal, today, horizon)[:max_items]:
        summary = str(comp.get("SUMMARY", "")).strip()
        day = _day_label(d, today)
        dt = comp.get("DTSTART").dt
        if isinstance(dt, datetime):
            label = f"{day} {dt:%H:%M} {summary}"
        else:
            label = f"{day} {summary}"
        items.append(Bullet(label))

    if not items:
        return Section(title, [Text("Nothing scheduled")])
    return Section(title, items)
