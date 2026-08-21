"""Cost model — re-export from core.

The canonical CostBreakdown / compute_cost / adjust_ev / check_marginal
live in ``core.risk.cost_model``.  This module re-exports them so existing
callers (intelligence/, execution/) keep working without import changes.
"""
from __future__ import annotations

from shettyxtreme.core.risk.cost_model import (
    CostBreakdown,
    adjust_ev,
    check_marginal,
    compute_cost,
)

__all__ = ["CostBreakdown", "compute_cost", "adjust_ev", "check_marginal"]
