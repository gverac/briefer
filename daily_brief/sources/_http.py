"""HTTP helpers with a small on-disk TTL cache.

The Pi Zero W is often slow or briefly offline. Every network call here:
  - has a short timeout (never hang the print job),
  - caches successful responses on disk keyed by URL,
  - falls back to the last cached value when the network fails.

So a daily brief still prints yesterday's joke rather than no joke.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "daily_brief"
DEFAULT_TIMEOUT = 8  # seconds
USER_AGENT = "daily-brief/0.1 (https://github.com/; Raspberry Pi receipt printer)"


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.json"


def _read_cache(key: str, ttl: float | None) -> object | None:
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if ttl is not None and (time.time() - payload.get("ts", 0)) > ttl:
        return None  # too old to use as a fresh hit (still usable as fallback)
    return payload.get("value")


def _read_cache_stale(key: str) -> object | None:
    """Return cached value regardless of age (used as a network fallback)."""
    return _read_cache(key, ttl=None)


def _write_cache(key: str, value: object) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(
            json.dumps({"ts": time.time(), "value": value}), "utf-8"
        )
    except OSError as exc:
        log.debug("cache write failed for %s: %s", key, exc)


def cache_get(key: str, ttl: float | None = None):
    """Public TTL cache read, for non-HTTP callers (e.g. the Claude wrapper)."""
    return _read_cache(key, ttl)


def cache_set(key: str, value) -> None:
    """Public cache write, for non-HTTP callers."""
    _write_cache(key, value)


def _fetch(
    url: str,
    *,
    as_json: bool,
    params: dict | None,
    headers: dict | None,
    ttl: float,
    timeout: float,
) -> object | None:
    cache_key = url + "?" + json.dumps(params, sort_keys=True) if params else url

    fresh = _read_cache(cache_key, ttl)
    if fresh is not None:
        return fresh

    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)

    try:
        resp = requests.get(url, params=params, headers=merged_headers, timeout=timeout)
        resp.raise_for_status()
        value = resp.json() if as_json else resp.text
    except (requests.RequestException, ValueError) as exc:
        stale = _read_cache_stale(cache_key)
        if stale is not None:
            log.warning("%s failed (%s); using cached copy", url, exc)
            return stale
        log.warning("%s failed (%s); no cache available", url, exc)
        return None

    _write_cache(cache_key, value)
    return value


def get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    ttl: float = 3600,
    timeout: float = DEFAULT_TIMEOUT,
) -> object | None:
    """GET and parse JSON, with TTL cache + stale fallback. None on failure."""
    return _fetch(
        url, as_json=True, params=params, headers=headers, ttl=ttl, timeout=timeout
    )


def get_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    ttl: float = 3600,
    timeout: float = DEFAULT_TIMEOUT,
) -> str | None:
    """GET text, with TTL cache + stale fallback. None on failure."""
    return _fetch(
        url, as_json=False, params=params, headers=headers, ttl=ttl, timeout=timeout
    )
