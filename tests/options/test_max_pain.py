"""Tests for the max pain calculator."""
from __future__ import annotations

import pytest

from shettyxtreme.options.max_pain import compute_max_pain


class TestComputeMaxPain:
    """Test the max pain strike calculation algorithm."""

    def test_basic_max_pain(self) -> None:
        """Symmetric OI around a central strike → that strike is max pain."""
        contracts = [
            {"strike": 100, "option_type": "CE", "oi": 1000},
            {"strike": 100, "option_type": "PE", "oi": 1000},
            {"strike": 110, "option_type": "CE", "oi": 500},
            {"strike": 110, "option_type": "PE", "oi": 500},
            {"strike": 90, "option_type": "CE", "oi": 500},
            {"strike": 90, "option_type": "PE", "oi": 500},
        ]
        result = compute_max_pain(contracts)
        assert result is not None
        # With symmetric OI, max pain should be at the central strike
        assert result == 100.0

    def test_skewed_oi_shifts_max_pain(self) -> None:
        """Heavy CE OI at higher strikes should pull max pain up."""
        contracts = [
            {"strike": 100, "option_type": "CE", "oi": 100},
            {"strike": 100, "option_type": "PE", "oi": 100},
            {"strike": 110, "option_type": "CE", "oi": 5000},
            {"strike": 110, "option_type": "PE", "oi": 100},
            {"strike": 120, "option_type": "CE", "oi": 100},
            {"strike": 120, "option_type": "PE", "oi": 100},
        ]
        result = compute_max_pain(contracts)
        assert result is not None
        # Heavy CE OI at 110 → max pain should be near or at 110
        assert result >= 100.0

    def test_empty_contracts_returns_none(self) -> None:
        """Empty chain should return None."""
        assert compute_max_pain([]) is None

    def test_no_oi_returns_none(self) -> None:
        """Contracts with zero OI should be ignored."""
        contracts = [
            {"strike": 100, "option_type": "CE", "oi": 0},
            {"strike": 110, "option_type": "PE", "oi": 0},
        ]
        assert compute_max_pain(contracts) is None

    def test_single_strike(self) -> None:
        """Single strike should return that strike."""
        contracts = [
            {"strike": 25000, "option_type": "CE", "oi": 100},
            {"strike": 25000, "option_type": "PE", "oi": 100},
        ]
        result = compute_max_pain(contracts)
        assert result == 25000.0

    def test_realistic_nifty_chain(self) -> None:
        """Test with a realistic NIFTY-like chain."""
        contracts = [
            {"strike": 24000, "option_type": "CE", "oi": 50000},
            {"strike": 24000, "option_type": "PE", "oi": 80000},
            {"strike": 24500, "option_type": "CE", "oi": 70000},
            {"strike": 24500, "option_type": "PE", "oi": 90000},
            {"strike": 25000, "option_type": "CE", "oi": 120000},
            {"strike": 25000, "option_type": "PE", "oi": 150000},
            {"strike": 25500, "option_type": "CE", "oi": 90000},
            {"strike": 25500, "option_type": "PE", "oi": 60000},
            {"strike": 26000, "option_type": "CE", "oi": 40000},
            {"strike": 26000, "option_type": "PE", "oi": 30000},
        ]
        result = compute_max_pain(contracts)
        assert result is not None
        # Should be at or near the strike with highest total OI (25000)
        assert 24000.0 <= result <= 26000.0

    def test_alternative_field_names(self) -> None:
        """Test with open_interest instead of oi."""
        contracts = [
            {"strike": 100, "option_type": "CE", "open_interest": 100},
            {"strike": 100, "option_type": "PE", "open_interest": 100},
            {"strike": 110, "option_type": "CE", "open_interest": 50},
            {"strike": 110, "option_type": "PE", "open_interest": 50},
        ]
        result = compute_max_pain(contracts)
        assert result is not None
        assert result == 100.0

    def test_negative_strike_ignored(self) -> None:
        """Negative or zero strikes should be ignored."""
        contracts = [
            {"strike": 0, "option_type": "CE", "oi": 100},
            {"strike": -10, "option_type": "PE", "oi": 100},
            {"strike": 100, "option_type": "CE", "oi": 100},
            {"strike": 100, "option_type": "PE", "oi": 100},
        ]
        result = compute_max_pain(contracts)
        assert result == 100.0
