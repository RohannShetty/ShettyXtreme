"""Tests for Cost Model."""
from __future__ import annotations

import pytest

from shettyxtreme.intelligence.risk.cost_model import (
    compute_cost, adjust_ev, check_marginal, CostBreakdown,
)


class TestComputeCost:
    def test_slippage_calculation(self) -> None:
        """quantity=75, price=100, slippage_bps=2 → slippage = 75*100*0.0002 = 1.5."""
        cost = compute_cost(
            quantity=75,
            price=100.0,
            slippage_bps=2.0,
            brokerage_per_lot=20.0,
            lot_size=75,
        )
        assert cost.slippage == 1.5  # 75 * 100 * 0.0002

    def test_brokerage_calculation(self) -> None:
        """1 lot (75 qty) at 20/lot → brokerage = 20."""
        cost = compute_cost(
            quantity=75,
            price=100.0,
            brokerage_per_lot=20.0,
            lot_size=75,
        )
        assert cost.brokerage == 20.0

    def test_brokerage_multiple_lots(self) -> None:
        """2 lots (150 qty) at 20/lot → brokerage = 40."""
        cost = compute_cost(
            quantity=150,
            price=100.0,
            brokerage_per_lot=20.0,
            lot_size=75,
        )
        assert cost.brokerage == 40.0

    def test_total_components(self) -> None:
        """Verify total = slippage + brokerage + stt + exchange."""
        cost = compute_cost(
            quantity=75,
            price=100.0,
            slippage_bps=2.0,
            brokerage_per_lot=20.0,
            lot_size=75,
        )
        expected_total = cost.slippage + cost.brokerage + cost.stt + cost.exchange_charges
        assert cost.total == expected_total

    def test_stt_calculation(self) -> None:
        """STT = notional * 0.0001 (0.01%)."""
        cost = compute_cost(
            quantity=75,
            price=100.0,
            lot_size=75,
        )
        notional = 75 * 100.0
        assert cost.stt == round(notional * 0.0001, 2)

    def test_exchange_charges(self) -> None:
        """Exchange = notional * 0.0005 (0.05%)."""
        cost = compute_cost(
            quantity=75,
            price=100.0,
            lot_size=75,
        )
        notional = 75 * 100.0
        assert cost.exchange_charges == round(notional * 0.0005, 2)


class TestAdjustEV:
    def test_adjust_ev_reduces_gross(self) -> None:
        """gross_ev=100, cost.total=10 → net_ev=90."""
        cost = CostBreakdown(slippage=5.0, brokerage=3.0, stt=1.0, exchange_charges=1.0)
        net = adjust_ev(100.0, cost)
        assert net == 90.0

    def test_adjust_ev_negative_cost(self) -> None:
        """gross_ev=50, cost=100 → net_ev=-50."""
        cost = CostBreakdown(slippage=50.0, brokerage=30.0, stt=10.0, exchange_charges=10.0)
        net = adjust_ev(50.0, cost)
        assert net == -50.0

    def test_adjust_ev_zero_cost(self) -> None:
        """gross_ev=100, cost=0 → net_ev=100."""
        cost = CostBreakdown(slippage=0.0, brokerage=0.0, stt=0.0, exchange_charges=0.0)
        net = adjust_ev(100.0, cost)
        assert net == 100.0


class TestMarginalCheck:
    def test_not_marginal(self) -> None:
        """net_ev=50, cost=10 → 50 >= 2*10 → not marginal."""
        cost = CostBreakdown(slippage=5.0, brokerage=3.0, stt=1.0, exchange_charges=1.0)
        net_ev, marginal = check_marginal(50.0, cost)
        assert net_ev == 50.0
        assert marginal is False

    def test_marginal(self) -> None:
        """net_ev=15, cost=10 → 15 < 2*10 → marginal."""
        cost = CostBreakdown(slippage=5.0, brokerage=3.0, stt=1.0, exchange_charges=1.0)
        net_ev, marginal = check_marginal(15.0, cost)
        assert net_ev == 15.0
        assert marginal is True
