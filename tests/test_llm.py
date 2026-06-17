"""The Claude wrapper's web-search path (fake client — no network, no key)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from daily_brief import llm
from daily_brief.config import ClaudeConfig


def _block(text):
    return SimpleNamespace(type="text", text=text)


class _FakeMessages:
    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._script.pop(0)


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    # Keep the on-disk cache out of it — exercise the live path every time.
    monkeypatch.setattr(llm, "_get_client", _get_client_for_test)
    monkeypatch.setattr("daily_brief.sources._http.cache_get", lambda *a, **k: None)
    monkeypatch.setattr("daily_brief.sources._http.cache_set", lambda *a, **k: None)


_FAKE = None


def _get_client_for_test(cfg):
    return _FAKE


def _set_client(script):
    global _FAKE
    _FAKE = SimpleNamespace(messages=_FakeMessages(script))
    return _FAKE.messages


def test_web_search_passes_tool_and_extracts_text():
    msgs = _set_client([SimpleNamespace(stop_reason="end_turn", content=[_block("live answer")])])
    out = llm.generate(ClaudeConfig(api_key="k", enabled=True),
                       system="s", prompt="p", web_search=True)
    assert out == "live answer"
    assert msgs.calls[0]["tools"] == [llm.WEB_SEARCH_TOOL]


def test_web_search_resumes_on_pause_turn():
    msgs = _set_client([
        SimpleNamespace(stop_reason="pause_turn", content=[_block("searching…")]),
        SimpleNamespace(stop_reason="end_turn", content=[_block("final answer")]),
    ])
    out = llm.generate(ClaudeConfig(api_key="k", enabled=True),
                       system="s", prompt="p", web_search=True)
    assert out == "final answer"
    assert len(msgs.calls) == 2                      # paused once, then resumed
    assert msgs.calls[1]["messages"][-1]["role"] == "assistant"  # prior turn re-sent


def test_no_tool_when_web_search_off():
    msgs = _set_client([SimpleNamespace(stop_reason="end_turn", content=[_block("plain")])])
    llm.generate(ClaudeConfig(api_key="k", enabled=True), system="s", prompt="p")
    assert "tools" not in msgs.calls[0]
