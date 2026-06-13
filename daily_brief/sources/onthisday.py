"""'On this day' historical events from Wikipedia's REST feed (no API key).

Endpoint: /api/rest_v1/feed/onthisday/events/MM/DD
Each event has a `year` and `text`. The feed is ordered newest-first, so by
default we skip recent years and surface genuinely historical events (oldest
first).

Config options:
    max_items        how many events to show (default 1)
    min_age_years    only consider events at least this old (default 50)
"""

from __future__ import annotations

from ..brief import Section, Text
from ._http import get_json

BASE = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events"


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "ON THIS DAY"
    max_items = int(section_cfg.get("max_items", 1))
    min_age_years = int(section_cfg.get("min_age_years", 50))

    url = f"{BASE}/{ctx.now:%m}/{ctx.now:%d}"
    # History doesn't change; cache for a day.
    data = get_json(url, ttl=86400)
    events = (data or {}).get("events") or []
    if not events:
        return Section(title, [Text("(unavailable)")])

    # Prefer events at least `min_age_years` old; fall back to all if none qualify.
    cutoff = ctx.now.year - min_age_years
    historical = [e for e in events if isinstance(e.get("year"), int) and e["year"] <= cutoff]
    pool = historical or events

    # Oldest first, so the brief leans into real history rather than recent news.
    pool = sorted(pool, key=lambda e: e.get("year", 0))

    items = []
    for event in pool[:max_items]:
        year = event.get("year")
        text = (event.get("text") or "").strip()
        items.append(Text(f"{year}: {text}" if year else text))
    return Section(title, items)
