"""Portfolio-level greeks aggregation.

Pure functions over position dicts — no I/O, no side effects.
Computes net Δ/Γ/Θ/V across all open option positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PortfolioGreeks:
    """Aggregate portfolio greeks across all positions."""
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0


def aggregate_greeks(positions: list[dict[str, Any]]) -> PortfolioGreeks:
    """Sum greeks across all positions that have a greeks block.

    Args:
        positions: List of position dicts, each optionally containing a
            ``greeks`` sub-dict with ``delta``, ``gamma``, ``theta``, ``vega``.

    Returns:
        PortfolioGreeks with the net sum.
    """
    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0
    for p in positions:
        g = p.get("greeks")
        if g is None:
            continue
        net_delta += float(g.get("delta", 0.0))
        net_gamma += float(g.get("gamma", 0.0))
        net_theta += float(g.get("theta", 0.0))
        net_vega += float(g.get("vega", 0.0))
    return PortfolioGreeks(
        net_delta=net_delta,
        net_gamma=net_gamma,
        net_theta=net_theta,
        net_vega=net_vega,
    )
