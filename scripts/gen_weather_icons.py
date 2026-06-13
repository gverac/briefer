#!/usr/bin/env python3
"""Generate monochrome weather pictograms for the brief.

Draws simple black-on-white silhouettes (which print crisply on a 1-bit thermal
printer) and saves them to daily_brief/assets/weather/<key>.png. Combined icons
(sun+cloud, cloud+rain, …) carve a thin white gap so the front element reads
cleanly over the back one.

Run from the repo root:  python scripts/gen_weather_icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 96
OUT = Path(__file__).resolve().parent.parent / "daily_brief" / "assets" / "weather"

BLACK, WHITE = 0, 255


def _new():
    img = Image.new("L", (SIZE, SIZE), WHITE)
    return img, ImageDraw.Draw(img)


def _sun(draw, cx, cy, r, ink=BLACK, rays=True):
    if rays:
        for k in range(8):
            a = k * math.pi / 4
            x1, y1 = cx + math.cos(a) * (r + 6), cy + math.sin(a) * (r + 6)
            x2, y2 = cx + math.cos(a) * (r + 16), cy + math.sin(a) * (r + 16)
            draw.line([x1, y1, x2, y2], fill=ink, width=5)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ink)


def _moon(draw, cx, cy, r, ink=BLACK):
    # Crescent = big disc minus an offset disc.
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ink)
    off = int(r * 0.55)
    draw.ellipse(
        [cx - r + off, cy - r - 4, cx + r + off, cy + r - 4], fill=WHITE
    )


def _cloud(draw, cx, cy, w, ink=BLACK, halo=False):
    """A puffy cloud centered roughly at (cx, cy). If halo, draw white first."""
    if halo:
        _cloud(draw, cx, cy, w + 7, ink=WHITE, halo=False)
    h = int(w * 0.62)
    left = cx - w // 2
    top = cy - h // 2
    base_top = top + int(h * 0.45)
    # base slab
    draw.rounded_rectangle(
        [left, base_top, left + w, top + h], radius=h // 4, fill=ink
    )
    # puffs
    draw.ellipse([left, base_top - h // 3, left + w * 0.5, top + h], fill=ink)
    draw.ellipse(
        [left + w * 0.28, top, left + w * 0.78, top + int(h * 0.9)], fill=ink
    )
    draw.ellipse([left + w * 0.5, base_top - h // 4, left + w, top + h], fill=ink)


def _drops(draw, cx, top, n, length, ink=BLACK):
    spacing = 22
    start = cx - (n - 1) * spacing // 2
    for i in range(n):
        x = start + i * spacing
        draw.line([x, top, x - 6, top + length], fill=ink, width=5)


def _snowflakes(draw, cx, top, n, ink=BLACK):
    spacing = 24
    start = cx - (n - 1) * spacing // 2
    for i in range(n):
        x = start + i * spacing
        y = top + (6 if i % 2 else 0)
        for a in (0, math.pi / 3, 2 * math.pi / 3):
            dx, dy = math.cos(a) * 7, math.sin(a) * 7
            draw.line([x - dx, y - dy, x + dx, y + dy], fill=ink, width=3)


def _bolt(draw, cx, top, ink=BLACK):
    draw.polygon(
        [
            (cx + 4, top),
            (cx - 12, top + 26),
            (cx + 0, top + 26),
            (cx - 6, top + 48),
            (cx + 16, top + 18),
            (cx + 4, top + 18),
        ],
        fill=ink,
    )


def gen():
    OUT.mkdir(parents=True, exist_ok=True)
    icons = {}

    img, d = _new(); _sun(d, SIZE // 2, SIZE // 2, 24); icons["clear-day"] = img
    img, d = _new(); _moon(d, SIZE // 2, SIZE // 2, 30); icons["clear-night"] = img

    img, d = _new()
    _sun(d, 34, 34, 16)
    _cloud(d, 58, 60, 60, halo=True)
    icons["partly-day"] = img

    img, d = _new()
    _moon(d, 34, 32, 18)
    _cloud(d, 58, 60, 60, halo=True)
    icons["partly-night"] = img

    img, d = _new(); _cloud(d, SIZE // 2, SIZE // 2, 72); icons["cloudy"] = img

    img, d = _new()
    _cloud(d, SIZE // 2, 40, 66)
    _drops(d, SIZE // 2, 62, 3, 20)
    icons["rain"] = img

    img, d = _new()
    _cloud(d, SIZE // 2, 40, 66)
    _drops(d, SIZE // 2, 64, 4, 12)
    icons["drizzle"] = img

    img, d = _new()
    _cloud(d, SIZE // 2, 38, 66)
    _bolt(d, SIZE // 2, 58)
    icons["thunder"] = img

    img, d = _new()
    _cloud(d, SIZE // 2, 38, 66)
    _snowflakes(d, SIZE // 2, 70, 3)
    icons["snow"] = img

    img, d = _new()
    for i, y in enumerate((36, 50, 64)):
        w = 64 - (i % 2) * 12
        draw_x = (SIZE - w) // 2
        d.rounded_rectangle([draw_x, y, draw_x + w, y + 6], radius=3, fill=BLACK)
    icons["mist"] = img

    for key, image in icons.items():
        image.save(OUT / f"{key}.png")
    print(f"wrote {len(icons)} icons to {OUT}")


if __name__ == "__main__":
    gen()
