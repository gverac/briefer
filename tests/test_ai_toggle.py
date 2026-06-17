"""The AI master toggle: local when off, surfaced failure when on but failing."""

from __future__ import annotations

from datetime import datetime

import pytest

from daily_brief import greetings
from daily_brief.config import ClaudeConfig, Config, SectionConfig
from daily_brief.sources import SourceContext
from daily_brief.sources import ai as ai_source


def _ctx(**claude):
    return SourceContext(config=Config(claude=ClaudeConfig(**claude)), now=datetime(2026, 6, 12, 8, 0))


def test_active_property():
    assert ClaudeConfig(api_key="k", enabled=True).active is True
    assert ClaudeConfig(api_key="k", enabled=False).active is False   # toggled off
    assert ClaudeConfig(api_key=None, enabled=True).active is False    # no key


def test_ai_section_messages(monkeypatch):
    cfg = SectionConfig(type="ai", title="AI", options={"prompt": "hi"})

    # disabled (key present, toggle off)
    s = ai_source.build(cfg, _ctx(api_key="k", enabled=False))
    assert s.items[0].text == "(AI disabled)"

    # enabled but no key
    s = ai_source.build(cfg, _ctx(api_key=None, enabled=True))
    assert s.items[0].text == "(set [claude] api_key)"

    # active but the call fails -> surfaced, not a fallback
    monkeypatch.setattr(ai_source, "generate", lambda *a, **k: None)
    s = ai_source.build(cfg, _ctx(api_key="k", enabled=True))
    assert s.items[0].text == "(AI unavailable)"

    # active and succeeds
    monkeypatch.setattr(ai_source, "generate", lambda *a, **k: "the answer")
    s = ai_source.build(cfg, _ctx(api_key="k", enabled=True))
    assert s.items[0].text == "the answer"


def test_ai_section_web_search_flag(monkeypatch):
    captured = {}

    def fake_generate(cfg, **kwargs):
        captured.update(kwargs)
        return "current news"

    monkeypatch.setattr(ai_source, "generate", fake_generate)

    # default: web search off, modest token budget
    cfg = SectionConfig(type="ai", title="AI", options={"prompt": "hi"})
    ai_source.build(cfg, _ctx(api_key="k", enabled=True))
    assert captured["web_search"] is False

    # opted in: web search on, with headroom for the tool loop
    cfg = SectionConfig(type="ai", title="NEWS",
                        options={"prompt": "today's news", "use_web_search": True})
    ai_source.build(cfg, _ctx(api_key="k", enabled=True))
    assert captured["web_search"] is True
    assert captured["max_tokens"] >= 1024


def test_word_per_section_use_claude(monkeypatch):
    from daily_brief.sources import word as word_source

    # use_claude unchecked + AI active -> dictionary path, Claude not called
    monkeypatch.setattr(word_source, "_claude_define",
                        lambda *a, **k: pytest.fail("should not call Claude"))
    monkeypatch.setattr(word_source, "_define", lambda w: ("n.", "a definition"))
    cfg = SectionConfig(type="word", title="WORD", options={"use_claude": False})
    s = word_source.build(cfg, _ctx(api_key="k", enabled=True))
    assert "a definition" in s.items[1].text

    # use_claude checked + AI active + Claude fails -> surfaced (no dictionary)
    monkeypatch.setattr(word_source, "_claude_define", lambda *a, **k: None)
    monkeypatch.setattr(word_source, "_define",
                        lambda w: pytest.fail("should not fall back to dictionary"))
    cfg = SectionConfig(type="word", title="WORD", options={"use_claude": True})
    s = word_source.build(cfg, _ctx(api_key="k", enabled=True))
    assert s.items[-1].text == "(AI unavailable)"


def test_greeting_section(monkeypatch):
    from daily_brief.sources import greeting as greeting_source

    now = datetime(2026, 6, 12, 8, 0)

    # AI off -> the rotating built-in greeting (a real one, not a failure)
    cfg = SectionConfig(type="greeting", options={"use_claude": False})
    s = greeting_source.build(cfg, _ctx(enabled=False))
    title = s.items[0]
    assert s.bare is True
    assert title.text == greetings.greeting_for(now.date())
    assert title.subtitle == "Friday, 12 June 2026"  # default date_format

    # configurable date/time format
    cfg = SectionConfig(type="greeting", options={"use_claude": False, "date_format": "%Y-%m-%d %H:%M"})
    assert greeting_source.build(cfg, _ctx(enabled=False)).items[0].subtitle == "2026-06-12 08:00"

    # AI on but the call fails -> surfaced as the greeting text
    monkeypatch.setattr(greeting_source, "generate", lambda *a, **k: None)
    cfg = SectionConfig(type="greeting", options={"use_claude": True})
    assert greeting_source.build(cfg, _ctx(api_key="k", enabled=True)).items[0].text == "(AI greeting failed)"
