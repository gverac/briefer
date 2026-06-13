"""Assemble the daily brief.

A brief is an ordered list of `Section`s, each built by a content source
(weather, calendar, …). Sections carry structured `Item`s rather than plain
strings so the renderer can draw checkboxes, weather pictograms, etc. Rendering
lives in `daily_brief.render`; this module is pure data + assembly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# --- Items -----------------------------------------------------------------
# Small dataclasses the renderer dispatches on. Sources stay data-only.


@dataclass
class Text:
    """A run of body text (word-wrapped at render time)."""

    text: str


@dataclass
class Checkbox:
    """A line preceded by a tick box, e.g. a birthday to congratulate."""

    label: str
    checked: bool = False


@dataclass
class Bullet:
    """A dashed list item; wrapped continuation lines hang-indent under the text."""

    text: str


@dataclass
class Banner:
    """A prominent line with an optional pictogram, e.g. on-call status."""

    text: str
    icon_key: str | None = None


@dataclass
class KeyVal:
    """A label/value pair rendered on one line, e.g. Daylight / 10h32m."""

    label: str
    value: str


@dataclass
class Weather:
    """Today's weather: a pictogram key plus high/low (Celsius) and a blurb."""

    icon_key: str
    hi: float | None
    lo: float | None
    desc: str


@dataclass
class Picture:
    """An arbitrary bitmap (PIL image), centered and scaled to fit the width."""

    image: object  # PIL.Image.Image (kept loose to avoid importing PIL here)


@dataclass
class Mono:
    """Pre-formatted monospace text (e.g. ASCII art); lines are not wrapped."""

    text: str


Item = Text | Checkbox | Bullet | Banner | KeyVal | Weather | Picture | Mono


# --- Sections / Brief ------------------------------------------------------


@dataclass
class Section:
    title: str
    items: list[Item] = field(default_factory=list)
    icon: str | None = None  # icon key (assets/icons/<icon>.png) for the header


@dataclass
class Brief:
    date: datetime
    sections: list[Section] = field(default_factory=list)
    greeting: str | None = None  # header greeting (Claude-written if enabled)


def build_brief(config, now: datetime | None = None, expand_rotations: bool = False) -> Brief:
    """Build the brief from the configured `[[sections]]`.

    Iterates enabled sections in config order and asks each source to build
    its `Section`. Every source call goes through `safe_build`, so a failing or
    offline source yields an "(unavailable)" section instead of crashing the
    whole print job. With `expand_rotations`, any `rotate` section renders all
    of its choices instead of the day's single pick (test mode).
    """
    # Imported here to avoid a circular import (sources import brief items).
    from .sources import SourceContext, expand_section

    now = now or datetime.now()
    ctx = SourceContext(config=config, now=now, expand_rotations=expand_rotations)

    sections: list[Section] = []
    for section_cfg in config.sections:
        if not section_cfg.enabled:
            continue
        sections.extend(expand_section(section_cfg, ctx))

    from .greetings import generate_greeting

    return Brief(date=now, sections=sections, greeting=generate_greeting(config, now))
