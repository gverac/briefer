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
class ProgressBar:
    """A horizontal progress bar filled to `fraction` (0..1), e.g. a countdown."""

    fraction: float


@dataclass
class Mono:
    """Pre-formatted monospace text (e.g. ASCII art); lines are not wrapped."""

    text: str


@dataclass
class Title:
    """A big centered greeting with a centered subtitle below (the brief header)."""

    text: str
    subtitle: str = ""


Item = (
    Text | Checkbox | Bullet | Banner | KeyVal | Weather | Picture | ProgressBar
    | Mono | Title
)


# --- Sections / Brief ------------------------------------------------------


@dataclass
class Section:
    title: str
    items: list[Item] = field(default_factory=list)
    icon: str | None = None  # icon key (assets/icons/<icon>.png) for the header
    bare: bool = False        # render items only, no separator rule or heading


@dataclass
class Brief:
    date: datetime
    sections: list[Section] = field(default_factory=list)


def build_brief(config, brief, now: datetime | None = None) -> Brief:
    """Build a `Brief` from a `BriefConfig` (its ordered sections).

    Iterates the brief's enabled sections and asks each source to build its
    `Section`. Every source call goes through `safe_build`, so a failing or
    offline source yields an "(unavailable)" section instead of crashing the
    whole print job. `config` carries the shared globals (location, render,
    claude). `brief` may be None.
    """
    # Imported here to avoid a circular import (sources import brief items).
    from .sources import SourceContext, build_section

    now = now or datetime.now()
    ctx = SourceContext(config=config, now=now)

    sections: list[Section] = []
    for section_cfg in (brief.sections if brief else []):
        if not section_cfg.enabled:
            continue
        section = build_section(section_cfg, ctx)
        if section is not None:
            sections.append(section)

    return Brief(date=now, sections=sections)
