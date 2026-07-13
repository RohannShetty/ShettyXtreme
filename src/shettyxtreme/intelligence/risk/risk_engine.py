"""Risk engine with composable filter chain.

Key design:
  - Loss limit BLOCKS ENTRIES only. Position management always allowed.
  - Composable RiskFilter protocol enables mix-and-match filters.
  - RiskDecision carries reason and filter name for audit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from shettyxtreme.core.data_models import Position
from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection


# ---------------------------------------------------------------------------
# Portfolio stub — in practice this comes from the execution layer
# ---------------------------------------------------------------------------
@dataclass
class Portfolio:
    """Minimal portfolio representation for risk checks."""
    positions: list[Position]
    daily_pnl: float  # Realised + unrealised PnL for the day
    total_margin_used: float
    available_margin: float


# ---------------------------------------------------------------------------
# RiskDecision
# ---------------------------------------------------------------------------
@dataclass
class RiskDecision:
    """Result of a risk check."""
    allowed: bool
    reason: str
    filter_name: str = ""

    ALLOW: "RiskDecision" = None  # type: ignore

    @staticmethod
    def allow(filter_name: str = "") -> "RiskDecision":
        return RiskDecision(allowed=True, reason="", filter_name=filter_name)

    @staticmethod
    def reject(reason: str, filter_name: str = "") -> "RiskDecision":
        return RiskDecision(allowed=False, reason=reason, filter_name=filter_name)


RiskDecision.ALLOW = RiskDecision.allow()


# ---------------------------------------------------------------------------
# RiskFilter protocol
# ---------------------------------------------------------------------------
class RiskFilter(Protocol):
    """Protocol for composable risk filters."""
    name: str

    def check(self, signal: Signal, portfolio: Portfolio) -> RiskDecision:
        """Evaluate risk conditions. Return ALLOW or REJECT."""
        ...


# ---------------------------------------------------------------------------
# Concrete filters
# ---------------------------------------------------------------------------
class LossLimitFilter:
    """Blocks entries when daily loss exceeds limit.

    CRITICAL: Position management always allowed regardless of loss limit.
    This is the fix from ShettyBot V1 where loss limit froze ALL trading.
    """

    def __init__(self, loss_limit: float = -5000.0) -> None:
        self.loss_limit = loss_limit

    name = "loss_limit"

    def check(self, signal: Signal, portfolio: Portfolio) -> RiskDecision:
        if portfolio.daily_pnl < self.loss_limit:
            return RiskDecision.reject(
                f"daily loss limit reached: {portfolio.daily_pnl:.2f} < {self.loss_limit:.2f}",
                filter_name=self.name,
            )
        return RiskDecision.allow(self.name)


class MarginFilter:
    """Blocks entry if not enough margin available."""

    def __init__(self, margin_threshold_ratio: float = 0.1) -> None:
        self.margin_threshold_ratio = margin_threshold_ratio

    name = "margin"

    def check(self, signal: Signal, portfolio: Portfolio) -> RiskDecision:
        required_margin = portfolio.total_margin_used * self.margin_threshold_ratio
        if required_margin <= 0:
            required_margin = 5000.0  # minimum margin for one lot
        if portfolio.available_margin < required_margin:
            return RiskDecision.reject(
                f"insufficient margin: available={portfolio.available_margin:.2f} < required={required_margin:.2f}",
                filter_name=self.name,
            )
        return RiskDecision.allow(self.name)


class MaxPositionFilter:
    """Blocks entry if max concurrent positions reached."""

    def __init__(self, max_positions: int = 5) -> None:
        self.max_positions = max_positions

    name = "max_positions"

    def check(self, signal: Signal, portfolio: Portfolio) -> RiskDecision:
        active = sum(1 for p in portfolio.positions if abs(p.net_quantity) > 0)
        if active >= self.max_positions:
            return RiskDecision.reject(
                f"max positions reached: {active} >= {self.max_positions}",
                filter_name=self.name,
            )
        return RiskDecision.allow(self.name)


class RegimeFilter:
    """Blocks entry if regime is incompatible with the signal direction."""

    def __init__(self, allowed_regimes: list[str] | None = None) -> None:
        if allowed_regimes is None:
            allowed_regimes = ["trending_up", "trending_down", "range_bound", "volatile"]
        self.allowed_regimes = allowed_regimes

    name = "regime"

    def check(self, signal: Signal, portfolio: Portfolio) -> RiskDecision:
        return RiskDecision.allow(self.name)


# ---------------------------------------------------------------------------
# RiskEngine
# ---------------------------------------------------------------------------
class RiskEngine:
    """Risk engine with composable filter chain.

    For entry checks: runs all filters.
    For position management: always allows (loss limit does not freeze Mgmt).
    """

    def __init__(self, filters: list[RiskFilter] | None = None) -> None:
        self._filters = filters or [
            LossLimitFilter(),
            MarginFilter(),
            MaxPositionFilter(),
            RegimeFilter(),
        ]

    def check_entry(self, signal: Signal, portfolio: Portfolio) -> RiskDecision:
        """Run all filters. Return ALLOW only if all pass."""
        for f in self._filters:
            result = f.check(signal, portfolio)
            if not result.allowed:
                return result
        return RiskDecision.allow("all_filters")

    def check_position_management(
        self,
        position: Position,
        portfolio: Portfolio,
    ) -> RiskDecision:
        """Always ALLOW. Positions must be managed regardless of loss limit."""
        return RiskDecision.allow("position_management")

    @property
    def filters(self) -> list[RiskFilter]:
        return list(self._filters)
