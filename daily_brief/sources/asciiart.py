"""Daily ASCII art.

By default, a different piece from the bundled gallery each day (offline). If
`use_claude = true` and Claude is configured, Claude draws fresh art instead —
of a fixed `subject` if given, otherwise a fun subject it picks for the day.
Falls back to the bundled gallery if Claude is unavailable.
"""

from __future__ import annotations

from ..ascii_art import art_for
from ..brief import Mono, Section
from ..llm import generate

_CLAUDE_SYSTEM = "You are an expert ASCII artist. You output only ASCII art, nothing else."


def _strip_fences(text: str) -> str:
    """Drop surrounding ``` code fences if Claude added them; keep inner spacing."""
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].lstrip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip("\n")


def _claude_art(cfg, section_cfg, ctx) -> str | None:
    subject = section_cfg.get("subject")
    if subject:
        what, cache_key = f'of "{subject}"', f"ascii:{subject}"
    else:
        what = "of a fun, simple subject (an animal, object, or seasonal thing)"
        cache_key = f"ascii:{ctx.now:%Y-%m-%d}"

    prompt = (
        f"Draw small ASCII art {what}. Rules: at most 24 characters per line, "
        "at most 12 lines, plain ASCII only. Output ONLY the art — no code "
        "fences, no title, no commentary."
    )
    text = generate(
        cfg, system=_CLAUDE_SYSTEM, prompt=prompt, max_tokens=400,
        cache_key=cache_key, ttl=604_800,
    )
    if not text:
        return None
    art = _strip_fences(text)
    return art or None


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "ASCII ART"

    if section_cfg.get("use_claude") and ctx.config.claude.enabled:
        art = _claude_art(ctx.config.claude, section_cfg, ctx)
        if art:
            return Section(title, [Mono(art)])
        # else fall through to the bundled gallery

    _name, art = art_for(ctx.now.date())
    return Section(title, [Mono(art)])
