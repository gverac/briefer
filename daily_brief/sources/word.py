"""Word of the day — a rare / SAT-level word with a definition.

We ship a bundled list of rare/SAT vocabulary and pick one by date. If Claude
is configured, it supplies the definition plus an example sentence (nicer, and
avoids the odd senses Free Dictionary sometimes returns first); otherwise we
look the definition up from the free Dictionary API (api.dictionaryapi.dev).
"""

from __future__ import annotations

import json
import random

from ..brief import Section, Text
from ..config import ASSETS_DIR
from ..llm import generate
from ._http import get_json

WORDS_PATH = ASSETS_DIR / "sat_words.json"
DICT_URL = "https://api.dictionaryapi.dev/api/v2/entries/en"
MAX_TRIES = 8

_CLAUDE_SYSTEM = "You are a precise lexicographer. Respond ONLY with a minified JSON object, no markdown."


def _claude_define(cfg, word: str):
    """Ask Claude for (pos, definition, example). None on failure."""
    prompt = (
        f'Define the word "{word}" for a word-of-the-day card. JSON keys: '
        '"pos" (abbreviated part of speech, e.g. "n.", "v.", "adj."), '
        '"definition" (one clear sentence under 15 words), '
        f'"example" (one natural sentence that uses "{word}"). Output only the JSON.'
    )
    text = generate(
        cfg, system=_CLAUDE_SYSTEM, prompt=prompt, max_tokens=200,
        cache_key=f"word:{word}", ttl=2_592_000,
    )
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    definition = (data.get("definition") or "").strip()
    if not definition:
        return None
    return (data.get("pos") or "").strip(), definition, (data.get("example") or "").strip()


def _load_words() -> list[str]:
    try:
        data = json.loads(WORDS_PATH.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [w for w in data if isinstance(w, str)] if isinstance(data, list) else []


def _define(word: str):
    """Return (part_of_speech, definition) from Free Dictionary, or None."""
    data = get_json(f"{DICT_URL}/{word}", ttl=2_592_000)  # definitions are stable
    if not isinstance(data, list) or not data:
        return None
    for entry in data:
        for meaning in entry.get("meanings", []):
            defs = meaning.get("definitions") or []
            if defs and defs[0].get("definition"):
                return meaning.get("partOfSpeech", ""), defs[0]["definition"].strip()
    return None


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "WORD OF THE DAY"
    words = _load_words()
    if not words:
        return Section(title, [Text("(unavailable)")])

    # Deterministic per-day order; try candidates until one resolves.
    rng = random.Random(ctx.now.strftime("%Y-%m-%d"))
    start = ctx.now.toordinal() % len(words)
    order = [words[(start + i) % len(words)] for i in range(len(words))]
    rng.shuffle(order)

    # Preferred path: Claude defines the day's word and gives an example.
    if ctx.config.claude.enabled:
        word = order[0]
        result = _claude_define(ctx.config.claude, word)
        if result:
            pos, definition, example = result
            items = [Text(f"{word} ({pos})" if pos else word), Text(definition)]
            if example:
                items.append(Text(f'"{example}"'))
            return Section(title, items)
        # else fall through to the dictionary lookup below

    for word in order[:MAX_TRIES]:
        result = _define(word)
        if result:
            pos, definition = result
            head = f"{word} ({pos})" if pos else word
            return Section(title, [Text(head), Text(definition)])

    return Section(title, [Text("(unavailable)")])
