"""Tests for portfolio greeks aggregation (P2-3.2)."""
from __future__ import annotations

import pytest

from shettyxtreme.options.portfolio_greeks import PortfolioGreeks, aggregate_greeks


class TestAggregateGreeks:
    """Aggregate greeks across positions."""

    def test_sums_all_greeks(self) -> None:
        positions = [
            {"greeks": {"delta": 10.0, "gamma": 0.5, "theta": -5.0, "vega": 8.0}},
            {"greeks": {"delta": -8.0, "gamma": 0.3, "theta": -3.0, "vega": 5.0}},
        ]
        result = aggregate_greeks(positions)
        assert result.net_delta == pytest.approx(2.0)
        assert result.net_gamma == pytest.approx(0.8)
        assert result.net_theta == pytest.approx(-8.0)
        assert result.net_vega == pytest.approx(13.0)

    def test_ignores_positions_without_greeks(self) -> None:
        positions = [
            {"greeks": {"delta": 10.0, "gamma": 0.5, "theta": -5.0, "vega": 8.0}},
            {"symbol": "NIFTY", "quantity": 0},  # no greeks key
        ]
        result = aggregate_greeks(positions)
        assert result.net_delta == pytest.approx(10.0)

    def test_empty_positions_returns_zero(self) -> None:
        result = aggregate_greeks([])
        assert result.net_delta == 0.0
        assert result.net_gamma == 0.0
        assert result.net_theta == 0.0
        assert result.net_vega == 0.0

    def test_frozen_dataclass(self) -> None:
        result = PortfolioGreeks(net_delta=1.0)
        with pytest.raises(AttributeError):
            result.net_delta = 2.0  # type: ignore

    def test_partial_greeks_keys(self) -> None:
        """Missing keys in the greeks sub-dict default to 0.0."""
        positions = [
            {"greeks": {"delta": 5.0}},  # gamma/theta/vega missing
        ]
        result = aggregate_greeks(positions)
        assert result.net_delta == pytest.approx(5.0)
        assert result.net_gamma == 0.0
        assert result.net_theta == 0.0
        assert result.net_vega == 0.0
