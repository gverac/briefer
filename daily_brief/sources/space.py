"""Space sections: ISS position, moon phase, visible planets.

  iss      Live ISS lat/lon plotted on a bundled world map (no API key).
  moon     Tonight's moon phase, drawn (offline, no API key).
  planets  Planets above the horizon tonight, computed with ephem (no API key).
"""

from __future__ import annotations

import math
from datetime import datetime, time
from zoneinfo import ZoneInfo

import ephem
from PIL import Image, ImageDraw

from ..brief import Bullet, KeyVal, Picture, Section, Text
from ..config import ASSETS_DIR
from ._http import get_json

WORLD_MAP = ASSETS_DIR / "space" / "world.png"
ISS_URL = "https://api.wheretheiss.at/v1/satellites/25544"
ISS_FALLBACK_URL = "http://api.open-notify.org/iss-now.json"


# --- ISS -------------------------------------------------------------------


def _iss_position() -> tuple[float, float] | None:
    data = get_json(ISS_URL, ttl=0)
    if isinstance(data, dict) and "latitude" in data:
        return float(data["latitude"]), float(data["longitude"])
    data = get_json(ISS_FALLBACK_URL, ttl=0)  # http fallback
    if isinstance(data, dict) and data.get("iss_position"):
        pos = data["iss_position"]
        return float(pos["latitude"]), float(pos["longitude"])
    return None


def build_iss(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "ISS TRACKER"
    pos = _iss_position()
    if pos is None or not WORLD_MAP.is_file():
        return Section(title, [Text("(unavailable)")])
    lat, lon = pos

    world = Image.open(WORLD_MAP).convert("L")
    W, H = world.size
    x = int((lon + 180) / 360 * W)
    y = int((90 - lat) / 180 * H)

    d = ImageDraw.Draw(world)
    d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=255)            # white halo over land
    d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=0, width=2)  # black ring
    d.line([x - 12, y, x + 12, y], fill=0, width=1)              # crosshair
    d.line([x, y - 12, x, y + 12], fill=0, width=1)
    d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=0)              # center dot

    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    caption = f"{abs(lat):.1f}°{ns}, {abs(lon):.1f}°{ew}"
    return Section(title, [Picture(world), KeyVal("Now over", caption)])


# --- Moon phase ------------------------------------------------------------

_MOON_NAMES = [
    "New moon", "Waxing crescent", "First quarter", "Waxing gibbous",
    "Full moon", "Waning gibbous", "Last quarter", "Waning crescent",
]


def _draw_moon(phase01: float, size: int = 150) -> Image.Image:
    """Draw the moon at phase01 (0=new, 0.5=full, 1=new); <0.5 waxing."""
    img = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(img)
    r = size // 2 - 3
    cx = cy = size // 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=0, width=2)

    ct = math.cos(2 * math.pi * phase01)
    waxing = phase01 < 0.5
    for yy in range(-r, r + 1):
        half = math.sqrt(max(0.0, r * r - yy * yy))
        if waxing:
            x0, x1 = -half, ct * half          # dark on the left
        else:
            x0, x1 = -ct * half, half          # dark on the right
        if x1 > x0:
            d.line([cx + int(round(x0)), cy + yy, cx + int(round(x1)), cy + yy], fill=0)
    return img


def build_moon(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "MOON PHASE"
    # ephem phase: % illuminated; pair with lunation age for waxing/waning + name.
    obs_date = ephem.Date(ctx.now.date())
    moon = ephem.Moon(obs_date)
    illum = float(moon.phase)  # 0..100 % illuminated

    prev_new = ephem.previous_new_moon(obs_date)
    next_new = ephem.next_new_moon(obs_date)
    age = obs_date - prev_new
    lunation = next_new - prev_new
    phase01 = age / lunation  # 0..1 through the cycle

    name = _MOON_NAMES[int((phase01 * 8 + 0.5)) % 8]
    image = _draw_moon(phase01)
    return Section(title, [Picture(image), KeyVal(name, f"{illum:.0f}% lit")])


# --- Visible planets -------------------------------------------------------

_PLANETS = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn"]


def build_planets(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "TONIGHT'S PLANETS"
    loc = ctx.location

    # Compute for tonight ~22:00 local, converted to UTC (ephem uses UTC).
    tz = ZoneInfo(loc.tz)
    local_night = datetime.combine(ctx.now.date(), time(22, 0), tzinfo=tz)
    obs = ephem.Observer()
    obs.lat = str(loc.lat)
    obs.lon = str(loc.lon)
    obs.date = ephem.Date(local_night.astimezone(ZoneInfo("UTC")).replace(tzinfo=None))

    visible = []
    for name in _PLANETS:
        body = getattr(ephem, name)(obs)
        alt_deg = math.degrees(float(body.alt))
        if alt_deg > 0:
            visible.append((name, alt_deg, float(body.mag)))

    if not visible:
        return Section(title, [Text("None visible tonight")])

    visible.sort(key=lambda t: t[2])  # brightest (lowest magnitude) first
    items = [Bullet(f"{n}  alt {a:.0f}°, mag {m:+.1f}") for n, a, m in visible]
    return Section(title, items)
