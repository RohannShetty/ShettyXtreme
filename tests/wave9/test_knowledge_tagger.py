"""Tagger tests (spec 4A §3.4)."""
from __future__ import annotations

from shettyxtreme.knowledge.tagger import tag_document


def test_symbols_extracted() -> None:
    tags = tag_document("NIFTY broke out while BANKNIFTY lagged")
    syms = {t["tag"] for t in tags if t["kind"] == "symbol"}
    assert syms == {"NIFTY", "BANKNIFTY"}


def test_stopwords_not_symbols() -> None:
    tags = tag_document("The IT sector was ON fire")
    syms = {t["tag"] for t in tags if t["kind"] == "symbol"}
    assert syms == set()


def test_regime_phrases() -> None:
    tags = tag_document("market is trending up with sideways pressure")
    regimes = {t["tag"] for t in tags if t["kind"] == "regime"}
    assert regimes == {"trending_up", "range_bound"}


def test_risk_themes() -> None:
    tags = tag_document("elevated IV and crowding near resistance")
    risks = {t["tag"] for t in tags if t["kind"] == "risk"}
    assert risks == {"ELEVATED_IV", "CROWDING", "RESISTANCE"}


def test_dedup_and_cap() -> None:
    tags = tag_document("NIFTY NIFTY NIFTY " + " ".join([f"X{i}" for i in range(100)]))
    syms = [t for t in tags if t["kind"] == "symbol"]
    assert len([t for t in syms if t["tag"] == "NIFTY"]) == 1
    assert len(tags) <= 50


def test_word_boundaries() -> None:
    # "flat" must not fire inside "deflation"; "event" not inside "preventive"
    tags = tag_document("deflation prevents event-driven moves")
    regimes = {t["tag"] for t in tags if t["kind"] == "regime"}
    risks = {t["tag"] for t in tags if t["kind"] == "risk"}
    assert regimes == set()
    assert "EVENT_RISK" not in risks
    tags2 = tag_document("market flat, event risk")
    assert "range_bound" in {t["tag"] for t in tags2 if t["kind"] == "regime"}
    assert "EVENT_RISK" in {t["tag"] for t in tags2 if t["kind"] == "risk"}
