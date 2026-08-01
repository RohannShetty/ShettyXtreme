"""Heuristic document tagger (spec 4A §3.4).

Extracts normalized tags from free text: NSE symbols (lexicon + stopword
disambiguation), regime keywords (multi-word phrases first), and risk-theme
keywords. Pure deterministic lookup — no ML, no LLM (D3).
"""
from __future__ import annotations

import re

from shettyxtreme.core.knowledge.lexicons import (
    REGIME_TERMS,
    RISK_THEMES,
    normalize_symbol,
)

_SYMBOL_TOKEN_RE = re.compile(r"[A-Za-z:]{2,}")
_MAX_TAGS = 50


def _phrase_keys(lexicon: dict[str, str]) -> list[str]:
    """Lexicon keys, longest (most words) first so phrases win over words."""
    return sorted(lexicon, key=lambda key: (key.count(" ") + 1, len(key)), reverse=True)


def tag_document(text: str) -> list[dict]:
    """Tag a document body, returning `{"tag", "kind"}` entries.

    Symbols are tokenized and normalized against the NSE lexicon; regime and
    risk keywords match on a lowercased copy (phrases first). Output is
    deduped per (tag, kind) and capped at 50 entries.
    """
    low = text.lower()
    tags: dict[tuple[str, str], None] = {}
    for phrase in _phrase_keys(REGIME_TERMS):
        if phrase in low:
            tags[(REGIME_TERMS[phrase], "regime")] = None
    for phrase in _phrase_keys(RISK_THEMES):
        if phrase in low:
            tags[(RISK_THEMES[phrase], "risk")] = None
    for token in _SYMBOL_TOKEN_RE.findall(text):
        symbol = normalize_symbol(token)
        if symbol is not None:
            tags[(symbol, "symbol")] = None
    return [{"tag": tag, "kind": kind} for (tag, kind) in tags][:_MAX_TAGS]
