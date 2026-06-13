"""Today's weather from OpenWeatherMap (Celsius), with a pictogram key.

Uses the free 5-day/3-hour forecast endpoint and aggregates today's buckets
(in the city's own local day) into a high/low plus a representative condition
near local noon. Returns a `Weather` item the renderer turns into an icon +
"H 24  L 12" row.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..brief import Section, Text, Weather
from ._http import get_json

FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def _icon_key(owm_id: int, icon_code: str) -> str:
    """Map an OWM condition id + icon code to one of our bundled pictograms."""
    is_day = icon_code.endswith("d")
    if 200 <= owm_id < 300:
        return "thunder"
    if 300 <= owm_id < 400:
        return "drizzle"
    if 500 <= owm_id < 600:
        return "rain"
    if 600 <= owm_id < 700:
        return "snow"
    if 700 <= owm_id < 800:
        return "mist"
    if owm_id == 800:
        return "clear-day" if is_day else "clear-night"
    if owm_id in (801, 802):
        return "partly-day" if is_day else "partly-night"
    return "cloudy"


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "WEATHER"
    api_key = section_cfg.get("api_key")
    if not api_key or api_key == "YOUR_OPENWEATHERMAP_KEY":
        return Section(title, [Text("(set api_key)")])

    loc = ctx.location
    data = get_json(
        FORECAST_URL,
        params={
            "lat": loc.lat,
            "lon": loc.lon,
            "appid": api_key,
            "units": "metric",
        },
        ttl=1800,
    )
    buckets = (data or {}).get("list") or []
    if not buckets:
        return Section(title, [Text("(unavailable)")])

    tz_offset = ((data.get("city") or {}).get("timezone")) or 0
    tz = timezone(timedelta(seconds=tz_offset))
    today = datetime.now(tz).date()

    def local_dt(bucket):
        return datetime.fromtimestamp(bucket["dt"], tz)

    todays = [b for b in buckets if local_dt(b).date() == today]
    if not todays:
        todays = buckets[:8]  # fall back to the next ~24h if "today" is over

    hi = max(b["main"]["temp_max"] for b in todays)
    lo = min(b["main"]["temp_min"] for b in todays)

    # Representative condition: bucket nearest local noon.
    noon = min(todays, key=lambda b: abs(local_dt(b).hour - 12))
    weather0 = (noon.get("weather") or [{}])[0]
    icon_key = _icon_key(int(weather0.get("id", 800)), weather0.get("icon", "01d"))
    desc = (weather0.get("description") or "").strip().capitalize()

    return Section(title, [Weather(icon_key=icon_key, hi=hi, lo=lo, desc=desc)])
