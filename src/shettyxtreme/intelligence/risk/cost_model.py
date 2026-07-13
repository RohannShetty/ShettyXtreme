"""Cost model — compute transaction costs and adjust expected value.

Provides:
  - compute_cost: breakdown of slippage, brokerage, STT, exchange charges.
  - adjust_ev: net EV after cost.
  - Marginal trade detection.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Cost breakdown
# ---------------------------------------------------------------------------
@dataclass
class CostBreakdown:
    """Detailed cost breakdown for a trade."""
    slippage: float
    brokerage: float
    stt: float
    exchange_charges: float
    total: float = 0.0
    marginal_flag: bool = False

    def __post_init__(self) -> None:
        self.total = self.slippage + self.brokerage + self.stt + self.exchange_charges


# ---------------------------------------------------------------------------
# Compute costs
# ---------------------------------------------------------------------------
_STT_RATE = 0.0001  # 0.01% STT on options premium
_EXCHANGE_RATE = 0.0005  # 0.05% exchange charges


def compute_cost(
    quantity: int,
    price: float,
    slippage_bps: float = 2.0,
    brokerage_per_lot: float = 20.0,
    lot_size: int = 75,
) -> CostBreakdown:
    """Compute transaction cost breakdown.

    Args:
        quantity: Total quantity (contracts * lot_size).
        price: Price per unit.
        slippage_bps: Slippage in basis points (default 2.0 bps = 0.02%).
        brokerage_per_lot: Brokerage per lot in INR (default 20.0).
        lot_size: Contracts per lot (default 75 for NIFTY).

    Returns:
        CostBreakdown with all cost components.
    """
    notional = quantity * price

    slippage = notional * (slippage_bps / 10000.0)
    num_lots = quantity / lot_size if lot_size > 0 else 1
    brokerage = brokerage_per_lot * num_lots
    stt = notional * _STT_RATE
    exchange_charges = notional * _EXCHANGE_RATE

    breakdown = CostBreakdown(
        slippage=round(slippage, 2),
        brokerage=round(brokerage, 2),
        stt=round(stt, 2),
        exchange_charges=round(exchange_charges, 2),
    )

    # Marginal trade detection: if net EV < 2 * total cost
    breakdown.marginal_flag = False
    return breakdown


def adjust_ev(gross_ev: float, cost: CostBreakdown) -> float:
    """Adjust gross expected value by subtracting total cost.

    Args:
        gross_ev: Expected value before costs.
        cost: CostBreakdown from compute_cost.

    Returns:
        Net expected value after costs.
    """
    return gross_ev - cost.total


def check_marginal(net_ev: float, cost: CostBreakdown) -> tuple[float, bool]:
    """Check if a trade is marginal (net EV < 2 * total cost).

    Args:
        net_ev: Net expected value after costs (from adjust_ev).
        cost: CostBreakdown from compute_cost.

    Returns:
        Tuple of (net_ev, marginal_flag).
    """
    marginal = net_ev < 2.0 * cost.total
    return (net_ev, marginal)
