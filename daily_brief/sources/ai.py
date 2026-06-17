"""An arbitrary Claude-powered section.

Configure a `title` and a `prompt`; Claude's answer is printed, capped to
`max_chars` (default 280). Needs a `[claude]` api_key — without one (or if the
`anthropic` package isn't installed) it shows a hint instead of failing. Set
`use_web_search = true` to let Claude search the web for current information
(news, today's events) — run server-side, slower, and costs more per print.

Example config:
    [[sections]]
    type = "ai"
    title = "TODAY'S HAIKU"
    prompt = "Write a haiku about the morning."
    max_chars = 200

    [[sections]]
    type = "ai"
    title = "TODAY'S NEWS"
    prompt = "Summarize one notable news story from today."
    use_web_search = true
"""

from __future__ import annotations

from ..brief import Section, Text
from ..llm import generate

DEFAULT_MAX_CHARS = 280


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip()
    return (cut or text[:limit]).rstrip(".,;:") + "…"


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "TODAY'S AI"
    prompt = section_cfg.get("prompt")
    if not prompt:
        return Section(title, [Text("(no prompt configured)")])
    claude = ctx.config.claude
    if not claude.active:
        msg = "(AI disabled)" if not claude.enabled else "(set [claude] api_key)"
        return Section(title, [Text(msg)])

    use_web_search = bool(section_cfg.get("use_web_search", False))
    max_chars = int(section_cfg.get("max_chars", DEFAULT_MAX_CHARS))
    # ~3 chars/token is conservative; add headroom so it isn't cut mid-thought
    # before our own character cap applies. Web search needs much more room for
    # the model's between-search reasoning before it writes the final answer.
    max_tokens = max(64, max_chars // 3 + 32)
    if use_web_search:
        max_tokens = max(max_tokens, 1024)

    system = (
        "You write one short section of a daily briefing printed on a narrow "
        f"paper receipt. Today is {ctx.now:%A, %B %d, %Y}. Answer in plain text — "
        f"no markdown, no preamble, no sign-off — and keep it under {max_chars} "
        "characters."
    )
    if use_web_search:
        system += " Use web search to ground the answer in current information."
    text = generate(
        claude,
        system=system,
        prompt=prompt,
        max_tokens=max_tokens,
        cache_key=f"ai:{ctx.now:%Y-%m-%d}:{title}:{prompt}",
        ttl=86_400,
        web_search=use_web_search,
    )
    if not text:
        return Section(title, [Text("(AI unavailable)")])

    text = _truncate(text, max_chars)
    # Keep line/paragraph breaks as separate items (each Text wraps on its own).
    items = [Text(line.strip()) for line in text.splitlines() if line.strip()]
    return Section(title, items or [Text(text)])
