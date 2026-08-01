"""Tests for participation-normalized conviction (D/P/G, blueprint §14)."""
from __future__ import annotations

import pytest

from shettyxtreme.intelligence.conviction.conviction_engine import ConvictionEngine

VOTES_UP = [{"name": "a", "direction": 1.0, "confidence": 0.8, "weight": 1.0}]


class TestConvictionEngine:
    def test_all_up_unanimous(self) -> None:
        r = ConvictionEngine().compute(VOTES_UP, eligible=1)
        assert r.direction == "UP"
        assert r.P == pytest.approx(1.0)
        assert r.G == "unanimous"

    def test_split_votes_contested(self) -> None:
        votes = [
            {"name": "a", "direction": 1.0, "confidence": 0.8, "weight": 1.0},
            {"name": "b", "direction": -1.0, "confidence": 0.8, "weight": 1.0},
        ]
        r = ConvictionEngine().compute(votes, eligible=2)
        assert r.direction == "NEUTRAL"
        assert r.G == "contested"

    def test_dead_voters_do_not_dilute(self) -> None:
        votes = [
            {"name": "a", "direction": 1.0, "confidence": 0.8, "weight": 1.0},
            {"name": "b", "direction": 0.0, "confidence": 0.0, "weight": 1.0},
        ]
        r = ConvictionEngine().compute(votes, eligible=2)
        assert r.P == pytest.approx(0.5)
        assert r.direction == "UP"
