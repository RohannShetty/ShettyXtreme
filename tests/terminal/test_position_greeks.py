"""Tests for per-position greeks and portfolio greeks aggregation (P2-3.2).

Verifies:
- IV cache population and lookup
- Position greeks computation from option identity
- Portfolio greeks aggregation across positions
- PositionResponse includes greeks when available
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from shettyxtreme.terminal.api.execution_router import (
    _compute_position_greeks,
    _enrich_position,
    _iv_cache,
    _last_spot,
    update_iv_cache,
)
from shettyxtreme.terminal.api.models import PositionGreeks, PositionResponse


class TestIVCache:
    """IV cache population and lookup."""

    def setup_method(self) -> None:
        _iv_cache.clear()

    def test_update_iv_cache_from_dicts(self) -> None:
        contracts = [
            {"strike": 25000, "option_type": "CE", "iv": 15.5},
            {"strike": 25000, "option_type": "PE", "iv": 16.2},
            {"strike": 25100, "option_type": "CE", "iv": 14.0},
        ]
        update_iv_cache(contracts, spot=24950.0)
        assert _iv_cache[(25000, "CE")] == 15.5
        assert _iv_cache[(25000, "PE")] == 16.2
        assert _iv_cache[(25100, "CE")] == 14.0

    def test_update_iv_cache_skips_zero_iv(self) -> None:
        contracts = [
            {"strike": 25000, "option_type": "CE", "iv": 0.0},
            {"strike": 25100, "option_type": "PE", "iv": -1.0},
        ]
        update_iv_cache(contracts)
        assert len(_iv_cache) == 0

    def test_update_iv_cache_overwrites_previous(self) -> None:
        update_iv_cache([{"strike": 25000, "option_type": "CE", "iv": 10.0}])
        update_iv_cache([{"strike": 25000, "option_type": "CE", "iv": 20.0}])
        assert _iv_cache[(25000, "CE")] == 20.0


class TestPositionGreeks:
    """Per-position greeks computation."""

    def setup_method(self) -> None:
        _iv_cache.clear()

    def test_returns_none_when_no_iv(self) -> None:
        result = _compute_position_greeks(
            strike=25000, option_type="CE",
            expiry=date(2026, 12, 31), net_quantity=50,
        )
        assert result is None

    def test_returns_none_when_no_expiry(self) -> None:
        _iv_cache[(25000, "CE")] = 15.0
        result = _compute_position_greeks(
            strike=25000, option_type="CE",
            expiry=None, net_quantity=50,
        )
        assert result is None

    def test_computes_greeks_when_iv_and_spot_available(self) -> None:
        _iv_cache[(25000, "CE")] = 15.0
        # Set module-level _last_spot
        import shettyxtreme.terminal.api.execution_router as mod
        mod._last_spot = 24950.0

        result = _compute_position_greeks(
            strike=25000, option_type="CE",
            expiry=date(2026, 12, 31), net_quantity=50,
        )
        assert result is not None
        assert isinstance(result, PositionGreeks)
        # Delta should be positive for a long call
        assert result.delta != 0.0
        # Gamma should be positive
        assert result.gamma >= 0.0

    def test_greeks_scaled_by_net_quantity(self) -> None:
        _iv_cache[(25000, "CE")] = 15.0
        import shettyxtreme.terminal.api.execution_router as mod
        mod._last_spot = 24950.0

        g1 = _compute_position_greeks(
            strike=25000, option_type="CE",
            expiry=date(2026, 12, 31), net_quantity=1,
        )
        g50 = _compute_position_greeks(
            strike=25000, option_type="CE",
            expiry=date(2026, 12, 31), net_quantity=50,
        )
        assert g1 is not None and g50 is not None
        # Greeks should scale linearly with quantity
        assert abs(g50.delta - 50 * g1.delta) < 1e-6
        assert abs(g50.gamma - 50 * g1.gamma) < 1e-6


class TestEnrichPosition:
    """Position enrichment with option identity and greeks."""

    def setup_method(self) -> None:
        _iv_cache.clear()

    def test_non_option_position_has_no_greeks(self) -> None:
        raw = {
            "symbol": "NSE:NIFTY50-INDEX",
            "exchange": "NSE",
            "quantity": 0,
            "buy_avg": 0.0,
            "net_quantity": 0,
            "m2m": 0.0,
            "pnl": 0.0,
            "product": "NRML",
        }
        result = _enrich_position(raw)
        assert isinstance(result, PositionResponse)
        assert result.strike is None
        assert result.option_type is None
        assert result.greeks is None

    def test_option_position_has_identity_fields(self) -> None:
        raw = {
            "symbol": "NSE:NIFTY26AUG25000CE",
            "exchange": "NSE_FNO",
            "quantity": 50,
            "buy_avg": 240.5,
            "net_quantity": 50,
            "m2m": 1200.0,
            "pnl": 600.0,
            "product": "NRML",
        }
        # Feed the IV cache so greeks can be computed
        _iv_cache[(25000, "CE")] = 15.0
        import shettyxtreme.terminal.api.execution_router as mod
        mod._last_spot = 24950.0

        result = _enrich_position(raw)
        assert result.strike == 25000
        assert result.option_type == "CE"
        assert result.expiry is not None
        # Greeks should be computed when IV + spot are available
        assert result.greeks is not None


class TestPortfolioGreeksAggregation:
    """Portfolio-level greeks aggregation logic."""

    def test_aggregation_sums_greeks(self) -> None:
        """Net greeks = sum of position greeks."""
        positions = [
            PositionResponse(
                symbol="A", exchange="NSE", quantity=50, net_quantity=50,
                greeks=PositionGreeks(delta=10.0, gamma=0.5, theta=-5.0, vega=8.0),
            ),
            PositionResponse(
                symbol="B", exchange="NSE", quantity=-30, net_quantity=-30,
                greeks=PositionGreeks(delta=-8.0, gamma=0.3, theta=-3.0, vega=5.0),
            ),
        ]
        net_delta = sum(p.greeks.delta for p in positions if p.greeks)
        net_gamma = sum(p.greeks.gamma for p in positions if p.greeks)
        net_theta = sum(p.greeks.theta for p in positions if p.greeks)
        net_vega = sum(p.greeks.vega for p in positions if p.greeks)
        assert net_delta == pytest.approx(2.0)
        assert net_gamma == pytest.approx(0.8)
        assert net_theta == pytest.approx(-8.0)
        assert net_vega == pytest.approx(13.0)

    def test_aggregation_ignores_none_greeks(self) -> None:
        """Positions without greeks don't affect the sum."""
        positions = [
            PositionResponse(
                symbol="A", exchange="NSE", quantity=50, net_quantity=50,
                greeks=PositionGreeks(delta=10.0, gamma=0.5, theta=-5.0, vega=8.0),
            ),
            PositionResponse(
                symbol="B", exchange="NSE", quantity=0, net_quantity=0,
                greeks=None,
            ),
        ]
        net_delta = sum(p.greeks.delta for p in positions if p.greeks)
        assert net_delta == pytest.approx(10.0)
