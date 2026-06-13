"""Thin wrapper around the Claude API for the optional LLM-powered sources.

Uses the official `anthropic` SDK, imported lazily so the package isn't a hard
dependency — if it's not installed (or no API key is set, or the request fails),
`generate()` returns None and callers fall back to their non-Claude behavior.
Responses are cached (reusing the HTTP file cache) so re-runs on the same day
don't spend tokens again.

On a Pi Zero W (armv6) install with:  pip install anthropic
(see requirements.txt). It's optional; the brief prints fine without it.
"""

from __future__ import annotations

import logging

from .config import ClaudeConfig

log = logging.getLogger(__name__)

_client = None
_client_failed = False


def _get_client(cfg: ClaudeConfig):
    """Return a cached Anthropic client, or None if unavailable."""
    global _client, _client_failed
    if not cfg.enabled or _client_failed:
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
) -> str | None:
    """Run one Claude completion and return the text, or None on any failure.

    `cache_key` (when given) caches the result so repeated runs reuse it.
    """
    # Imported lazily to avoid a circular import (sources import this module).
    from .sources._http import cache_get, cache_set

    if cache_key:
        cached = cache_get(f"claude:{cfg.model}:{cache_key}", ttl)
        if isinstance(cached, str):
            return cached

    client = _get_client(cfg)
    if client is None:
        return None

    try:
        # No thinking / sampling params: these are tiny one-shot tasks, and on
        # Opus 4.x thinking is off by default when omitted.
        resp = client.messages.create(
            model=cfg.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as exc:
        log.warning("Claude request failed: %s", exc)
        return None

    if text and cache_key:
        cache_set(f"claude:{cfg.model}:{cache_key}", text)
    return text or None
