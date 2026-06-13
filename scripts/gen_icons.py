#!/usr/bin/env python3
"""Generate general-purpose monochrome icons (assets/icons/<key>.png).

These are small black-on-white silhouettes used next to section headings (and
the on-call banner). They print crisply on a 1-bit thermal printer.

Run from the repo root:  python scripts/gen_icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 96
OUT = Path(__file__).resolve().parent.parent / "daily_brief" / "assets" / "icons"
BLACK, WHITE = 0, 255


def _new():
    img = Image.new("L", (SIZE, SIZE), WHITE)
    return img, ImageDraw.Draw(img)


def _bell():  # on-call / alert
    img, d = _new()
    cx, top = SIZE // 2, 22
    d.ellipse([cx - 6, top - 10, cx + 6, top + 2], fill=BLACK)
    d.pieslice([cx - 28, top, cx + 28, top + 56], 180, 360, fill=BLACK)
    d.rectangle([cx - 28, top + 28, cx + 28, top + 44], fill=BLACK)
    d.polygon([(cx - 40, top + 56), (cx + 40, top + 56), (cx + 28, top + 40), (cx - 28, top + 40)], fill=BLACK)
    d.rounded_rectangle([cx - 42, top + 54, cx + 42, top + 62], radius=4, fill=BLACK)
    d.ellipse([cx - 7, top + 62, cx + 7, top + 76], fill=BLACK)
    return img


def _sun():  # daylight
    img, d = _new()
    cx = cy = SIZE // 2
    r = 22
    for k in range(8):
        a = k * math.pi / 4
        d.line([cx + math.cos(a) * (r + 6), cy + math.sin(a) * (r + 6),
                cx + math.cos(a) * (r + 16), cy + math.sin(a) * (r + 16)], fill=BLACK, width=5)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLACK)
    return img


def _cloud():  # weather
    img, d = _new()
    cx, cy, w = SIZE // 2, 54, 72
    h = int(w * 0.62)
    left, top = cx - w // 2, cy - h // 2
    base_top = top + int(h * 0.45)
    d.rounded_rectangle([left, base_top, left + w, top + h], radius=h // 4, fill=BLACK)
    d.ellipse([left, base_top - h // 3, left + w * 0.5, top + h], fill=BLACK)
    d.ellipse([left + w * 0.28, top, left + w * 0.78, top + int(h * 0.9)], fill=BLACK)
    d.ellipse([left + w * 0.5, base_top - h // 4, left + w, top + h], fill=BLACK)
    return img


def _cake():  # birthdays
    img, d = _new()
    for x in (32, 48, 64):  # candles + flames
        d.rectangle([x - 1, 18, x + 1, 30], fill=BLACK)
        d.ellipse([x - 3, 8, x + 3, 18], fill=BLACK)
    d.rounded_rectangle([24, 30, 72, 50], radius=6, fill=BLACK)   # top tier
    d.rounded_rectangle([16, 50, 80, 74], radius=8, fill=BLACK)   # base tier
    d.rectangle([10, 74, 86, 80], fill=BLACK)                     # plate
    return img


def _calendar():  # upcoming events
    img, d = _new()
    d.rectangle([28, 12, 36, 26], fill=BLACK)   # binding rings
    d.rectangle([60, 12, 68, 26], fill=BLACK)
    d.rounded_rectangle([16, 20, 80, 82], radius=8, fill=BLACK)
    d.rectangle([20, 38, 76, 78], fill=WHITE)   # page area
    for gx in (34, 48, 62):                     # grid dots
        for gy in (46, 60, 74):
            d.rectangle([gx - 3, gy - 3, gx + 3, gy + 3], fill=BLACK)
    return img


def _hourglass():  # on this day
    img, d = _new()
    d.rectangle([22, 14, 74, 22], fill=BLACK)   # caps
    d.rectangle([22, 74, 74, 82], fill=BLACK)
    d.polygon([(26, 22), (70, 22), (48, 48)], fill=BLACK)   # top sand
    d.polygon([(48, 48), (26, 74), (70, 74)], fill=BLACK)   # bottom sand
    return img


def _book():  # word of the day
    img, d = _new()
    d.polygon([(14, 28), (48, 36), (48, 74), (14, 68)], fill=BLACK)  # left page
    d.polygon([(82, 28), (48, 36), (48, 74), (82, 68)], fill=BLACK)  # right page
    d.line([48, 36, 48, 74], fill=WHITE, width=3)                    # spine gap
    return img


def _lightbulb():  # trivia
    img, d = _new()
    d.ellipse([26, 16, 70, 60], fill=BLACK)       # bulb
    d.rectangle([40, 54, 56, 72], fill=BLACK)     # base
    for y in (60, 66):                            # screw threads
        d.line([40, y, 56, y], fill=WHITE, width=2)
    d.rounded_rectangle([42, 72, 54, 80], radius=2, fill=BLACK)
    return img


def _smiley():  # joke
    img, d = _new()
    cx = cy = SIZE // 2
    d.ellipse([cx - 36, cy - 36, cx + 36, cy + 36], fill=BLACK)
    d.ellipse([cx - 16, cy - 14, cx - 6, cy - 2], fill=WHITE)   # eyes
    d.ellipse([cx + 6, cy - 14, cx + 16, cy - 2], fill=WHITE)
    d.arc([cx - 20, cy - 12, cx + 20, cy + 22], 20, 160, fill=WHITE, width=5)  # smile
    return img


def _moon():  # moon phase section
    img, d = _new()
    cx = cy = SIZE // 2
    r = 32
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLACK)
    d.ellipse([cx - r + 18, cy - r - 6, cx + r + 18, cy + r - 6], fill=WHITE)  # carve crescent
    return img


def _satellite():  # ISS tracker
    img, d = _new()
    cx = cy = SIZE // 2
    d.rounded_rectangle([cx - 12, cy - 12, cx + 12, cy + 12], radius=4, fill=BLACK)  # body
    for panel in ([cx - 44, cx - 16], [cx + 16, cx + 44]):                           # solar panels
        d.rectangle([panel[0], cy - 9, panel[1], cy + 9], fill=BLACK)
        d.line([(panel[0] + panel[1]) // 2, cy - 9, (panel[0] + panel[1]) // 2, cy + 9], fill=WHITE, width=2)
    d.line([cx, cy - 12, cx, cy - 26], fill=BLACK, width=3)                           # antenna
    d.ellipse([cx - 5, cy - 32, cx + 5, cy - 22], fill=BLACK)
    return img


def _art():  # ASCII art (framed picture)
    img, d = _new()
    d.rounded_rectangle([14, 18, 82, 78], radius=6, outline=BLACK, width=6)  # frame
    d.polygon([(24, 68), (44, 44), (58, 60), (66, 50), (72, 68)], fill=BLACK)  # mountains
    d.ellipse([56, 28, 70, 42], fill=BLACK)                                   # sun
    return img


def _planet():  # visible planets (ringed planet)
    img, d = _new()
    cx = cy = SIZE // 2
    d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=BLACK)   # planet
    # ring: draw a wide ellipse outline, then erase the front/back overlap subtly
    d.ellipse([cx - 40, cy - 12, cx + 40, cy + 12], outline=BLACK, width=4)
    return img


def gen():
    OUT.mkdir(parents=True, exist_ok=True)
    icons = {
        "oncall": _bell(),
        "sun": _sun(),
        "cloud": _cloud(),
        "cake": _cake(),
        "calendar": _calendar(),
        "hourglass": _hourglass(),
        "book": _book(),
        "lightbulb": _lightbulb(),
        "smiley": _smiley(),
        "moon": _moon(),
        "satellite": _satellite(),
        "planet": _planet(),
        "art": _art(),
    }
    for key, image in icons.items():
        image.save(OUT / f"{key}.png")
    print(f"wrote {len(icons)} icons to {OUT}")


if __name__ == "__main__":
    gen()
