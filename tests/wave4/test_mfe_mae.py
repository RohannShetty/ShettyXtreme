"""Tests for the MFE/MAE calculator."""
from __future__ import annotations

import pytest

from shettyxtreme.learning.mfe_mae import MfeMaeCalculator, MfeMaeRecord


def test_mfe_increases_on_favorable() -> None:
    c = MfeMaeCalculator()
    c.update("s1", 100.0, 100.0, 1.0)
    assert c.get_mfe("s1") == 0.0
    c.update("s1", 110.0, 100.0, 1.0)
    assert c.get_mfe("s1") == pytest.approx(10.0)
    c.update("s1", 105.0, 100.0, 1.0)
    # never decreases
    assert c.get_mfe("s1") == pytest.approx(10.0)


def test_mae_increases_on_adverse() -> None:
    c = MfeMaeCalculator()
    c.update("s1", 100.0, 100.0, 1.0)
    c.update("s1", 90.0, 100.0, 1.0)
    assert c.get_mae("s1") == pytest.approx(10.0)
    c.update("s1", 95.0, 100.0, 1.0)
    assert c.get_mae("s1") == pytest.approx(10.0)


def test_short_direction() -> None:
    c = MfeMaeCalculator()
    c.update("s2", 100.0, 100.0, -1.0)
    c.update("s2", 90.0, 100.0, -1.0)  # favorable for short
    assert c.get_mfe("s2") == pytest.approx(10.0)
    c.update("s2", 108.0, 100.0, -1.0)  # adverse for short
    assert c.get_mae("s2") == pytest.approx(8.0)


def test_close_returns_record_and_stops_tracking() -> None:
    c = MfeMaeCalculator()
    c.update("s1", 100.0, 100.0, 1.0)
    c.update("s1", 115.0, 100.0, 1.0)
    c.update("s1", 92.0, 100.0, 1.0)
    rec = c.close("s1")
    assert isinstance(rec, MfeMaeRecord)
    assert rec.mfe == pytest.approx(15.0)
    assert rec.mae == pytest.approx(8.0)
    assert c.get_mfe("s1") is None
    assert c.get_mae("s1") is None


def test_percentile_across_signals() -> None:
    c = MfeMaeCalculator()
    c.update("a", 100.0, 100.0, 1.0)
    c.update("a", 110.0, 100.0, 1.0)  # mfe 10
    c.update("b", 100.0, 100.0, 1.0)
    c.update("b", 120.0, 100.0, 1.0)  # mfe 20
    c.update("c", 100.0, 100.0, 1.0)
    c.update("c", 105.0, 100.0, 1.0)  # mfe 5
    all_sigs = ["a", "b", "c"]
    # c (lowest) -> low percentile; b (highest) -> high percentile
    assert c.get_mfe_percentile("a", all_sigs) > c.get_mfe_percentile("c", all_sigs)
    assert c.get_mfe_percentile("b", all_sigs) >= c.get_mfe_percentile("a", all_sigs)
    assert 0.0 <= c.get_mfe_percentile("b", all_sigs) <= 100.0
