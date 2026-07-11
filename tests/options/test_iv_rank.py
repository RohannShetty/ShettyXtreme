"""Tests for IVRankCalculator.

Verifies:
- IV rank computation
- IV classification (LOW / NORMAL / HIGH)
- Edge cases (insufficient data, constant IV)
"""

from __future__ import annotations

import pytest

from shettyxtreme.options.iv_rank import IVRankCalculator, IVClassification


class TestIVRankCalculator:
    """Suite for IVRankCalculator."""

    @pytest.fixture
    def calc(self) -> IVRankCalculator:
        return IVRankCalculator(max_history=5000)

    # ── Recording ──────────────────────────────────────────────────────

    def test_record_and_data_count(self, calc: IVRankCalculator) -> None:
        """Recording IV data points increases the count."""
        assert calc.data_count("NIFTY") == 0
        calc.record_iv("NIFTY", 0.15)
        assert calc.data_count("NIFTY") == 1
        calc.record_iv("NIFTY", 0.16)
        assert calc.data_count("NIFTY") == 2

    def test_record_batch(self, calc: IVRankCalculator) -> None:
        """record_iv_batch records multiple iv values."""
        calc.record_iv_batch("BANKNIFTY", [0.12, 0.13, 0.14, 0.15])
        assert calc.data_count("BANKNIFTY") == 4

    def test_symbols_property(self, calc: IVRankCalculator) -> None:
        """symbols returns all tracked symbols."""
        assert calc.symbols == []
        calc.record_iv("NIFTY", 0.15)
        calc.record_iv("BANKNIFTY", 0.12)
        assert set(calc.symbols) == {"NIFTY", "BANKNIFTY"}

    # ── IV Rank computation ────────────────────────────────────────────

    def test_iv_rank_within_bounds(self, calc: IVRankCalculator) -> None:
        """IV rank is always between 0 and 100."""
        calc.record_iv_batch("NIFTY", [0.10, 0.15, 0.20, 0.25, 0.30])
        result = calc.compute_iv_rank("NIFTY", current_iv=0.20)
        assert result is not None
        assert 0.0 <= result.iv_rank <= 100.0
        assert 0.0 <= result.iv_percentile <= 100.0

    def test_iv_rank_exact_value(self, calc: IVRankCalculator) -> None:
        """IV rank = (current - min) / (max - min) * 100."""
        calc.record_iv_batch("NIFTY", [10.0, 20.0, 30.0])
        result = calc.compute_iv_rank("NIFTY", current_iv=20.0)
        assert result is not None
        assert result.iv_rank == 50.0  # (20-10)/(30-10)*100 = 50
        assert result.min_iv == 10.0
        assert result.max_iv == 30.0
        assert result.mean_iv == 20.0

    def test_iv_rank_at_min(self, calc: IVRankCalculator) -> None:
        """IV rank is 0 when current IV equals min."""
        calc.record_iv_batch("NIFTY", [10.0, 20.0, 30.0])
        result = calc.compute_iv_rank("NIFTY", current_iv=10.0)
        assert result is not None
        assert result.iv_rank == 0.0
        assert result.iv_percentile == pytest.approx(33.33, rel=0.01)

    def test_iv_rank_at_max(self, calc: IVRankCalculator) -> None:
        """IV rank is 100 when current IV equals max."""
        calc.record_iv_batch("NIFTY", [10.0, 20.0, 30.0])
        result = calc.compute_iv_rank("NIFTY", current_iv=30.0)
        assert result is not None
        assert result.iv_rank == 100.0

    def test_iv_rank_no_current_iv(self, calc: IVRankCalculator) -> None:
        """When no current_iv supplied, uses latest recorded IV."""
        calc.record_iv_batch("NIFTY", [0.10, 0.20, 0.30])
        # Last recorded is 0.30
        result = calc.compute_iv_rank("NIFTY")
        assert result is not None
        assert result.current_iv == 0.30

    def test_iv_rank_insufficient_data(self, calc: IVRankCalculator) -> None:
        """Less than 2 data points returns None."""
        calc.record_iv("NIFTY", 0.15)
        assert calc.compute_iv_rank("NIFTY") is None

    def test_iv_rank_no_data(self, calc: IVRankCalculator) -> None:
        """No data for symbol returns None."""
        assert calc.compute_iv_rank("UNKNOWN") is None

    def test_iv_rank_constant_iv(self, calc: IVRankCalculator) -> None:
        """When all IV values are identical, rank defaults to 50."""
        calc.record_iv_batch("NIFTY", [0.15, 0.15, 0.15, 0.15])
        result = calc.compute_iv_rank("NIFTY")
        assert result is not None
        assert result.iv_rank == 50.0

    # ── Classification ─────────────────────────────────────────────────

    def test_classify_low(self, calc: IVRankCalculator) -> None:
        """IV in bottom 30th percentile is classified LOW."""
        calc.record_iv_batch("NIFTY", list(range(1, 101)))  # 1..100
        result = calc.compute_iv_rank("NIFTY", current_iv=10.0)
        assert result is not None
        assert result.classification == "LOW"
        assert calc.classify_iv("NIFTY", current_iv=10.0) == "LOW"

    def test_classify_normal(self, calc: IVRankCalculator) -> None:
        """IV between 30th and 70th percentile is NORMAL."""
        calc.record_iv_batch("NIFTY", list(range(1, 101)))  # 1..100
        result = calc.compute_iv_rank("NIFTY", current_iv=50.0)
        assert result is not None
        assert result.classification == "NORMAL"
        assert calc.classify_iv("NIFTY", current_iv=50.0) == "NORMAL"

    def test_classify_high(self, calc: IVRankCalculator) -> None:
        """IV above 70th percentile is HIGH."""
        calc.record_iv_batch("NIFTY", list(range(1, 101)))  # 1..100
        result = calc.compute_iv_rank("NIFTY", current_iv=90.0)
        assert result is not None
        assert result.classification == "HIGH"
        assert calc.classify_iv("NIFTY", current_iv=90.0) == "HIGH"

    def test_classify_insufficient_data_defaults_to_normal(
        self, calc: IVRankCalculator,
    ) -> None:
        """With no data, classify_iv returns NORMAL."""
        assert calc.classify_iv("UNKNOWN") == "NORMAL"

    # ── Clear history ──────────────────────────────────────────────────

    def test_clear_history_symbol(self, calc: IVRankCalculator) -> None:
        """Clearing a specific symbol removes only its data."""
        calc.record_iv("NIFTY", 0.15)
        calc.record_iv("BANKNIFTY", 0.12)
        calc.clear_history("NIFTY")
        assert "NIFTY" not in calc.symbols
        assert "BANKNIFTY" in calc.symbols

    def test_clear_history_all(self, calc: IVRankCalculator) -> None:
        """Clearing all symbols removes all data."""
        calc.record_iv("NIFTY", 0.15)
        calc.record_iv("BANKNIFTY", 0.12)
        calc.clear_history()
        assert calc.symbols == []
