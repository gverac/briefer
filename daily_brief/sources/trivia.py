"""A trivia fact from the Useless Facts API (uselessfacts.jsph.pl).

Replaces the old numbersapi number-fact source (numbersapi.com is defunct).
Modes:
  - "today"  -> the fact of the day (stable for the date; default)
  - "random" -> a random fact each run

Free, no API key. Responses are cached with a stale fallback.
"""

from __future__ import annotations

from ..brief import Section, Text

from ._http import get_json

BASE = "https://uselessfacts.jsph.pl/api/v2/facts"


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "TRIVIA"
    mode = section_cfg.get("mode", "today")

    if mode == "random":
        url, ttl = f"{BASE}/random", 600
    else:
        url, ttl = f"{BASE}/today", 43_200  # fact of the day; cache ~12h

    data = get_json(url, headers={"Accept": "application/json"}, ttl=ttl)
    text = (data or {}).get("text", "").strip()
    if not text:
        return Section(title, [Text("(unavailable)")])
    return Section(title, [Text(text)])
