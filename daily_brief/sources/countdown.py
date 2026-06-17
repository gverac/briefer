"""Countdown to a target date.

Shows the number of days remaining until `target_date`:
  - more than a day away -> "N days until <label>" (+ an optional progress bar),
  - on the day itself     -> a configurable arrival message,
  - in the past           -> nothing (the section is omitted).

Config options:
    target_date      the day to count down to, ISO "YYYY-MM-DD" (required)
    label            what you're counting down to, e.g. "Vacation"
    arrived_message  what to print on the target day (default: "<label> is here!")
    progress_bar     draw a progress bar (default false); needs `start_date`
    start_date       ISO date the countdown began; the bar fills from here to
                     `target_date`. Ignored (bar skipped) if missing/invalid.
"""

from __future__ import annotations

from datetime import date

from ..brief import Banner, KeyVal, ProgressBar, Section, Text


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "COUNTDOWN"
    target = _parse_date(section_cfg.get("target_date"))
    if target is None:
        return Section(title, [Text("(set a target date)")])

    label = (section_cfg.get("label") or "").strip()
    today = ctx.now.date()
    days = (target - today).days

    if days < 0:  # the target has passed — stop showing the countdown
        return None

    if days == 0:
        default = f"{label} is here!" if label else "The day is here!"
        message = (section_cfg.get("arrived_message") or default).strip()
        return Section(title, [Banner(message)])

    unit = "day" if days == 1 else "days"
    line = f"{days} {unit} until {label}" if label else f"{days} {unit} to go"
    items: list = [Banner(line)]

    if section_cfg.get("progress_bar"):
        start = _parse_date(section_cfg.get("start_date"))
        if start is not None:
            total = (target - start).days
            if total > 0:
                fraction = max(0.0, min(1.0, (today - start).days / total))
                items.append(ProgressBar(fraction))
                items.append(KeyVal("Progress", f"{round(fraction * 100)}%"))

    return Section(title, items)
