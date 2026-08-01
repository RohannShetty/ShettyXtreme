"""Lexicon tests (spec 4A §3.1, §6)."""
from __future__ import annotations

import pytest

from shettyxtreme.core.knowledge.lexicons import (
    NSE_SYMBOLS,
    REGIME_TERMS,
    RISK_THEMES,
    SYMBOL_STOPWORDS,
    normalize_symbol,
)


def test_normalize_symbol() -> None:
    assert normalize_symbol("nifty") == "NIFTY"
    assert normalize_symbol("NSE:NIFTY") == "NIFTY"
    assert normalize_symbol("NSE_FNO:BANKNIFTY") == "BANKNIFTY"
    assert normalize_symbol("it") is None  # stopword
    assert normalize_symbol("the") is None
    assert normalize_symbol("  ") is None


def test_lexicons_are_curated() -> None:
    assert "NIFTY" in NSE_SYMBOLS and "BANKNIFTY" in NSE_SYMBOLS
    assert REGIME_TERMS["trending"] == "trending_up"
    assert REGIME_TERMS["ranging"] == "range_bound"
    assert RISK_THEMES["elevated iv"] == "ELEVATED_IV"
    assert RISK_THEMES["crowding"] == "CROWDING"
    assert "IT" in SYMBOL_STOPWORDS


def test_lexicon_values_normalized() -> None:
    # every regime value matches the canonical enum (lowercase values)
    from shettyxtreme.intelligence.regime.regime_classifier import Regime

    for v in set(REGIME_TERMS.values()):
        assert v in {r.value for r in Regime}
