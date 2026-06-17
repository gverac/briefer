"""Thin wrapper around the Claude API for the LLM-powered sources.

Uses the official `anthropic` SDK (imported lazily). If no API key is set, or the
request fails, `generate()` returns None and callers fall back to their
non-Claude behavior — so the brief still prints. Responses are cached (reusing
the HTTP file cache) so re-runs on the same day don't spend tokens again.
"""

from __future__ import annotations

import logging

from .config import ClaudeConfig

log = logging.getLogger(__name__)

_client = None
_client_failed = False

# Anthropic-hosted web search tool: declared in `tools`, run server-side, no
# local execution or dependencies. Bumped versions only need a string change.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
# Cap on server-side tool-loop resumes (`stop_reason == "pause_turn"`) so a
# misbehaving search can't loop forever.
_MAX_PAUSE_RESUMES = 4


def _get_client(cfg: ClaudeConfig):
    """Return a cached Anthropic client, or None if unavailable."""
    global _client, _client_failed
    if not cfg.active or _client_failed:
        return None
    if _client is None:
        try:
            import anthropic

            _client = anthropic.Anthropic(api_key=cfg.api_key)
        except Exception as exc:  # not installed, bad key, etc.
            log.warning("Claude unavailable (%s); install `anthropic` to enable", exc)
            _client_failed = True
            return None
    return _client


def generate(
    cfg: ClaudeConfig,
    *,
    system: str,
    prompt: str,
    max_tokens: int = 256,
    cache_key: str | None = None,
    ttl: float = 86_400,
    web_search: bool = False,
) -> str | None:
    """Run one Claude completion and return the text, or None on any failure.

    `cache_key` (when given) caches the result so repeated runs reuse it.
    `web_search=True` grants Claude the Anthropic-hosted web search tool so it
    can ground the answer in current information (run server-side — no local
    fetching). The cache key includes the search flag so toggling it doesn't
    serve a stale non-search answer.
    """
    # Imported lazily to avoid a circular import (sources import this module).
    from .sources._http import cache_get, cache_set

    full_key = f"claude:{cfg.model}:{'web:' if web_search else ''}{cache_key}" if cache_key else None
    if full_key:
        cached = cache_get(full_key, ttl)
        if isinstance(cached, str):
            return cached

    client = _get_client(cfg)
    if client is None:
        return None

    try:
        # No thinking / sampling params: these are tiny one-shot tasks, and on
        # Opus 4.x thinking is off by default when omitted.
        kwargs = {"tools": [WEB_SEARCH_TOOL]} if web_search else {}
        messages = [{"role": "user", "content": prompt}]
        for _ in range(_MAX_PAUSE_RESUMES + 1):
            resp = client.messages.create(
                model=cfg.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                **kwargs,
            )
            # The server-side tool loop can pause if it hits its step limit;
            # re-send with the assistant turn appended to let it resume.
            if resp.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as exc:
        log.warning("Claude request failed: %s", exc)
        return None

    if text and full_key:
        cache_set(full_key, text)
    return text or None
