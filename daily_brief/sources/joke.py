"""Dad joke from icanhazdadjoke.com.

Their API asks for a descriptive User-Agent and an Accept header; with
``Accept: application/json`` it returns ``{"joke": "..."}``.
"""

from __future__ import annotations

from ..brief import Section, Text
from ._http import get_json

API_URL = "https://icanhazdadjoke.com/"


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "DAD JOKE"
    # Cache only briefly so re-runs on the same day can still vary the joke,
    # but a flaky network falls back to the last one we saw.
    data = get_json(API_URL, headers={"Accept": "application/json"}, ttl=300)
    if not data or not data.get("joke"):
        return Section(title, [Text("(no joke today)")])
    return Section(title, [Text(data["joke"].strip())])
