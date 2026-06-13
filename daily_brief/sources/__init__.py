"""Brief content sources.

Each source is a builder ``build(section_cfg, ctx) -> Section | None`` registered
in `BUILDERS` under its `type`. `build_section` looks up the builder for a
configured `[[sections]]` entry and runs it through `safe_build`, which catches
*any* exception so a flaky network or bad credential degrades to a one-line
"(unavailable)" section rather than killing the whole print job.

Adding a source:
    1. write `daily_brief/sources/foo.py` exposing `build(section_cfg, ctx)`,
    2. register it in `BUILDERS` below,
    3. add a `[[sections]]` block (type = "foo") to config.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from ..brief import Section, Text
from ..config import Config, SectionConfig

log = logging.getLogger(__name__)


@dataclass
class SourceContext:
    """Shared state handed to every source builder."""

    config: Config
    now: datetime
    expand_rotations: bool = False  # test mode: render all rotate choices

    @property
    def location(self):
        return self.config.location

    @property
    def tz(self) -> str:
        return self.config.location.tz

    @property
    def width(self) -> int:
        return self.config.render.dot_width


def _title_for(section_cfg: SectionConfig) -> str:
    return section_cfg.title or section_cfg.type.upper()


def safe_build(builder, section_cfg: SectionConfig, ctx: SourceContext) -> Section | None:
    """Run a source builder, converting failures into a graceful fallback.

    Returns the builder's Section, or an "(unavailable)" Section if it raised.
    A builder may legitimately return None (nothing to show today) — that is
    passed through so the section is omitted entirely.
    """
    try:
        return builder(section_cfg, ctx)
    except Exception as exc:  # never let a source crash the print job
        log.warning("source %r failed: %s", section_cfg.type, exc)
        return Section(_title_for(section_cfg), [Text("(unavailable)")])


# Header icons are off by default — only birthdays gets one. Enable an icon on
# any section with `icon = "<key>"` in config (or disable with `icon = ""`).
# Available keys (assets/icons/): cake, calendar, sun, cloud, hourglass, book,
# lightbulb, smiley, moon, satellite, planet, art, oncall.
DEFAULT_SECTION_ICONS = {
    "birthdays": "cake",
}


def build_section(section_cfg: SectionConfig, ctx: SourceContext) -> Section | None:
    builder = BUILDERS.get(section_cfg.type)
    if builder is None:
        log.warning("unknown section type %r — skipping", section_cfg.type)
        return None
    section = safe_build(builder, section_cfg, ctx)
    if section is not None and section.icon is None:
        # Explicit config wins; "" disables; otherwise the per-type default
        # (only birthdays has one).
        override = section_cfg.get("icon")
        section.icon = (
            override if override is not None
            else DEFAULT_SECTION_ICONS.get(section_cfg.type)
        )
        section.icon = section.icon or None  # treat "" as no icon
    return section


def _rotate_choices(section_cfg: SectionConfig) -> list[SectionConfig]:
    """Parse a rotate section's child sections from its `choices` list."""
    choices = []
    for raw in section_cfg.get("choices", []):
        if not isinstance(raw, dict) or "type" not in raw:
            continue
        options = {k: v for k, v in raw.items() if k not in {"type", "title", "enabled"}}
        choices.append(
            SectionConfig(
                type=raw["type"],
                title=raw.get("title"),
                enabled=raw.get("enabled", True),
                options=options,
            )
        )
    return [c for c in choices if c.enabled]


def expand_section(section_cfg: SectionConfig, ctx: SourceContext) -> list[Section]:
    """Build a configured section into one or more rendered Sections.

    For a `rotate` section, this picks one child per day (or, in test mode,
    returns all of them). Everything else builds to a single section.
    """
    if section_cfg.type != "rotate":
        section = build_section(section_cfg, ctx)
        return [section] if section is not None else []

    choices = _rotate_choices(section_cfg)
    if not choices:
        return []
    if ctx.expand_rotations:
        picks = choices  # test mode: show them all
    else:
        picks = [choices[ctx.now.toordinal() % len(choices)]]
    return [s for s in (build_section(c, ctx) for c in picks) if s is not None]


# Builders are imported lazily inside _register to keep import cost low on the
# Pi and avoid pulling optional deps until a section actually uses them.
def _register() -> dict:
    from . import (
        ai,
        asciiart,
        calendar,
        daylight,
        joke,
        oncall,
        onthisday,
        space,
        trivia,
        weather,
        word,
    )

    return {
        "weather": weather.build,
        "birthdays": calendar.build_birthdays,
        "events": calendar.build_events,
        "onthisday": onthisday.build,
        "word": word.build,
        "trivia": trivia.build,
        "daylight": daylight.build,
        "joke": joke.build,
        "oncall": oncall.build,
        "iss": space.build_iss,
        "moon": space.build_moon,
        "planets": space.build_planets,
        "ascii": asciiart.build,
        "ai": ai.build,
    }


BUILDERS = _register()
