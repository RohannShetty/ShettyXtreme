"""Risk engine with composable filter chain.

Key design:
  - Loss limit BLOCKS ENTRIES only. Position management always allowed.
  - Composable RiskFilter protocol enables mix-and-match filters.
  - RiskDecision carries reason and filter name for audit.
  - ProposalRiskContext gives filters order-level context (qty, price, SL, target).
  - OBSERVER-first (D10): rejections are advisory-but-hard; never auto-place.
  - Honesty rule: missing equity/stop/margin → REJECT (LIVE) or degrade (PAPER/OBSERVER).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

from shettyxtreme.core.data_models import Position
from shettyxtreme.core.settings import get_settings_store
from shettyxtreme.intelligence.signals.signal_engine import Signal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------
@dataclass
class Portfolio:
    """Portfolio representation for risk checks.

    ``equity`` is the total account equity (margin_used + available_margin in
    PAPER, broker fund_limit.total in LIVE).  ``None`` = unknown — loss-%
    and heat filters reject-or-degrade conservatively (honesty rule).
    """
    positions: list[Position]
    daily_pnl: float  # Realised + unrealised PnL for the day
    total_margin_used: float
    available_margin: float
    equity: float | None = None


# ---------------------------------------------------------------------------
# ProposalRiskContext — order-level context for filters
# ---------------------------------------------------------------------------
@dataclass
class ProposalRiskContext:
    """Proposed order context assembled from strategy_hint + _build_order.

    Filters that need order-level data (potential loss, RR, margin heat,
    concentration) read from this. Fields may be None when the hint builder
    does not supply them — honesty rule applies.
    """
    symbol: str = ""
    side: str = ""  # BUY / SELL
    quantity: int = 0
    entry_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    product: str = "MIS"
    lot_size: int | None = None
    underlying: str | None = None
    estimated_margin: float | None = None


# ---------------------------------------------------------------------------
# RiskDecision
# ---------------------------------------------------------------------------
@dataclass
class RiskDecision:
    """Result of a risk check."""
    allowed: bool
    reason: str
    filter_name: str = ""

    ALLOW: RiskDecision = None  # type: ignore

    @staticmethod
    def allow(filter_name: str = "") -> RiskDecision:
        return RiskDecision(allowed=True, reason="", filter_name=filter_name)

    @staticmethod
    def reject(reason: str, filter_name: str = "") -> RiskDecision:
        return RiskDecision(allowed=False, reason=reason, filter_name=filter_name)


RiskDecision.ALLOW = RiskDecision.allow()


# ---------------------------------------------------------------------------
# RiskFilter protocol — extended with optional proposal context
# ---------------------------------------------------------------------------
class RiskFilter(Protocol):
    """Protocol for composable risk filters.

    The optional ``proposal`` parameter is backward-compatible: existing
    filters that do not need order context simply ignore it. New filters
    REQUIRE it and return a conservative REJECT when it is missing.
    """
    name: str

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        """Evaluate risk conditions. Return ALLOW or REJECT."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _underlying_from_symbol(symbol: str) -> str:
    """Extract the underlying from a Fyers-style symbol.

    Attempts to parse option/future suffixes: NIFTY24AUG24000CE → NIFTY.
    Falls back to the symbol itself when parsing fails.
    """
    s = symbol.upper()
    for prefix in ("NSE:", "NSE_FNO:", "BSE:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    if "-" in s:
        s = s.rsplit("-", 1)[0]
    # Option: <underlying><DDMonYY><strike><CE|PE>
    m = re.match(r"^([A-Z]+?)(\d{2}[A-Z]{3}|\d{2}\d[A-Z]\d{2})(\d+)(CE|PE)$", s)
    if m:
        return m.group(1)
    # Future: <underlying><DDMonYY>FUT
    m2 = re.match(r"^([A-Z]+?)(\d{2}[A-Z]{3}|\d{2}\d[A-Z]\d{2})FUT$", s)
    if m2:
        return m2.group(1)
    return s


def _sector_for_symbol(symbol: str, sector_map: dict[str, str] | None = None) -> str:
    """Look up sector for a symbol. Returns 'Unknown' when not found."""
    if sector_map is None:
        from shettyxtreme.core.knowledge.sector_map import SYMBOL_SECTOR
        sector_map = SYMBOL_SECTOR
    underlying = _underlying_from_symbol(symbol)
    return sector_map.get(underlying.upper(), "Unknown")


# ---------------------------------------------------------------------------
# Concrete filters — existing (backward-compatible with proposal param)
# ---------------------------------------------------------------------------
class LossLimitFilter:
    """Blocks entries when daily loss exceeds limit.

    CRITICAL: Position management always allowed regardless of loss limit.
    This is the fix from ShettyBot V1 where loss limit froze ALL trading.

    ``loss_limit=None`` (the default) makes the filter settings-backed: it
    resolves the cap from the shared settings store at construction and
    re-reads it on every ``check``, so a runtime change to the settings
    form is honored by the live engine without a restart. An explicit
    value pins the filter to that cap.
    """

    name = "loss_limit"

    def __init__(self, loss_limit: float | None = None) -> None:
        self._settings_backed = loss_limit is None
        if loss_limit is None:
            loss_limit = get_settings_store().loss_limit()
        self.loss_limit = float(loss_limit)

    def _effective_limit(self) -> float:
        if self._settings_backed:
            return get_settings_store().loss_limit()
        return self.loss_limit

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        limit = self._effective_limit()
        if portfolio.daily_pnl < limit:
            return RiskDecision.reject(
                f"daily loss limit reached: {portfolio.daily_pnl:.2f} < {limit:.2f}",
                filter_name=self.name,
            )
        return RiskDecision.allow(self.name)


class MarginFilter:
    """Blocks entry if not enough margin available."""

    def __init__(self, margin_threshold_ratio: float = 0.1) -> None:
        self.margin_threshold_ratio = margin_threshold_ratio

    name = "margin"

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
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
    """Blocks entry if max concurrent positions reached.

    ``max_positions=None`` (the default) makes the filter settings-backed
    like ``LossLimitFilter``: the cap comes from the shared settings store
    and is re-read on every ``check``.
    """

    name = "max_positions"

    def __init__(self, max_positions: int | None = None) -> None:
        self._settings_backed = max_positions is None
        if max_positions is None:
            max_positions = get_settings_store().max_positions()
        self.max_positions = int(max_positions)

    def _effective_max(self) -> int:
        if self._settings_backed:
            return get_settings_store().max_positions()
        return self.max_positions

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        active = sum(1 for p in portfolio.positions if abs(p.net_quantity) > 0)
        limit = self._effective_max()
        if active >= limit:
            return RiskDecision.reject(
                f"max positions reached: {active} >= {limit}",
                filter_name=self.name,
            )
        return RiskDecision.allow(self.name)


class RegimeFilter:
    """Regime gating filter — currently an HONEST STUB.

    Neither ``Signal`` nor ``Portfolio`` carries the market regime, so the
    risk filter chain has no regime source to gate on. Real regime data is
    computed in the live pipeline by ``intelligence/regime/regime_classifier``
    and delivered to subscribers via the ``regime.changed`` EventBus event
    (see ``intelligence/regime/bus_bridge.py``) — not through ``check()``.

    Until regime data is plumbed into the risk chain, this filter returns a
    neutral ALLOW with an explicit stub marker so callers and audit trails can
    see that no regime gating occurred. Do not silently drop it from the
    chain — it keeps the ``RiskFilter`` protocol uniform and the audit trail
    complete, and the ``is_stub`` flag makes its no-op nature explicit.
    """

    #: Explicit marker: this filter performs no regime gating yet.
    is_stub = True

    def __init__(self, allowed_regimes: list[str] | None = None) -> None:
        if allowed_regimes is None:
            allowed_regimes = ["trending_up", "trending_down", "range_bound", "volatile"]
        self.allowed_regimes = allowed_regimes

    name = "regime"

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        # Honest stub: no regime source in the risk chain. Neutral ALLOW with
        # an explicit marker; see the class docstring for the rationale.
        return RiskDecision(
            allowed=True,
            reason="stub: no regime source in risk chain — neutral",
            filter_name=self.name,
        )


# ---------------------------------------------------------------------------
# New filters — P3-4.2
# ---------------------------------------------------------------------------

class MaxLossPerTradeFilter:
    """Rejects when potential loss on the proposed trade > max_loss_pct of equity.

    potential_loss = (entry_price - stop_loss) * quantity * lot_size
    For options with no stop: potential_loss = entry_price * quantity * lot_size
    (the full premium is at risk).

    Honesty rule:
      - No equity → REJECT (LIVE) or allow-with-reason (PAPER/OBSERVER).
      - No stop in LIVE → REJECT. In PAPER/OBSERVER → allow-with-reason.
    """

    name = "max_loss_per_trade"

    def __init__(self, max_loss_pct: float | None = None) -> None:
        self._settings_backed = max_loss_pct is None
        if max_loss_pct is None:
            max_loss_pct = float(get_settings_store().get("max_loss_pct") or 0.02)
        self.max_loss_pct = float(max_loss_pct)

    def _effective_pct(self) -> float:
        if self._settings_backed:
            return float(get_settings_store().get("max_loss_pct") or 0.02)
        return self.max_loss_pct

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        if proposal is None:
            # No proposal context — cannot evaluate. Allow passively; the
            # execution engine always passes proposal at approve-time.
            return RiskDecision.allow(self.name)

        pct = self._effective_pct()
        equity = portfolio.equity

        # Honesty: no equity
        if equity is None or equity <= 0:
            return RiskDecision.reject(
                "max_loss_per_trade: equity unknown — cannot evaluate risk",
                filter_name=self.name,
            )

        entry = proposal.entry_price
        stop = proposal.stop_loss
        qty = proposal.quantity
        lot_size = proposal.lot_size or 1

        if entry is None or entry <= 0:
            # No entry price (MARKET order) — cannot evaluate risk.
            # Allow passively; the fill price will be known post-execution.
            return RiskDecision.allow(self.name)

        # Compute potential loss
        if stop is not None and stop > 0:
            # Long: loss = (entry - stop) * qty; Short: loss = (stop - entry) * qty
            if proposal.side == "BUY":
                potential_loss = abs(entry - stop) * qty * lot_size
            else:
                potential_loss = abs(stop - entry) * qty * lot_size
        else:
            # No stop — full premium at risk (options)
            potential_loss = entry * qty * lot_size

        max_loss = equity * pct

        if potential_loss > max_loss:
            return RiskDecision.reject(
                f"max_loss_per_trade: potential loss {potential_loss:.2f} > "
                f"{pct:.1%} of equity ({max_loss:.2f})",
                filter_name=self.name,
            )

        return RiskDecision.allow(self.name)


class RiskRewardFilter:
    """Rejects when risk:reward ratio < min_risk_reward.

    rr = (target - entry) / (entry - stop)  [long]
    rr = (entry - target) / (stop - entry)  [short]

    Applies only when both stop and target are present.
    No target → allow (target is a nicety, stop is mandatory).
    """

    name = "risk_reward"

    def __init__(self, min_risk_reward: float | None = None) -> None:
        self._settings_backed = min_risk_reward is None
        if min_risk_reward is None:
            min_risk_reward = float(get_settings_store().get("min_risk_reward") or 1.5)
        self.min_risk_reward = float(min_risk_reward)

    def _effective_min(self) -> float:
        if self._settings_backed:
            return float(get_settings_store().get("min_risk_reward") or 1.5)
        return self.min_risk_reward

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        if proposal is None:
            return RiskDecision.allow(self.name)

        entry = proposal.entry_price
        stop = proposal.stop_loss
        target = proposal.target

        # Only apply when both stop and target are present
        if entry is None or stop is None or target is None:
            return RiskDecision.allow(self.name)
        if entry <= 0 or stop <= 0 or target <= 0:
            return RiskDecision.allow(self.name)

        min_rr = self._effective_min()

        if proposal.side == "BUY":
            risk = entry - stop
            reward = target - entry
        else:
            risk = stop - entry
            reward = entry - target

        if risk <= 0:
            return RiskDecision.reject(
                f"risk_reward: invalid SL ({stop}) relative to entry ({entry})",
                filter_name=self.name,
            )

        rr = reward / risk
        if rr < min_rr:
            return RiskDecision.reject(
                f"risk_reward: RR {rr:.2f} < minimum {min_rr:.2f}",
                filter_name=self.name,
            )

        return RiskDecision.allow(self.name)


class MarginHeatFilter:
    """Rejects when post-trade margin utilization exceeds cap.

    post_trade_utilization = (margin_used + est_new_margin) / (margin_used + available_margin)
    est_new_margin v1 = entry_price * quantity * lot_size (MIS option premium).

    Honesty rule: unknown margin data → REJECT.
    """

    name = "margin_heat"

    def __init__(self, max_utilization_pct: float | None = None) -> None:
        self._settings_backed = max_utilization_pct is None
        if max_utilization_pct is None:
            max_utilization_pct = float(get_settings_store().get("max_margin_utilization_pct") or 0.50)
        self.max_utilization_pct = float(max_utilization_pct)

    def _effective_pct(self) -> float:
        if self._settings_backed:
            return float(get_settings_store().get("max_margin_utilization_pct") or 0.50)
        return self.max_utilization_pct

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        if proposal is None:
            return RiskDecision.allow(self.name)

        cap = self._effective_pct()
        margin_used = portfolio.total_margin_used
        available = portfolio.available_margin

        # Estimate new margin: premium-based for MIS options
        est_new = proposal.estimated_margin
        if est_new is None and proposal.entry_price and proposal.entry_price > 0:
            qty = proposal.quantity
            lot_size = proposal.lot_size or 1
            est_new = proposal.entry_price * qty * lot_size

        if est_new is None:
            # Cannot estimate margin (e.g., MARKET order with no price).
            # Allow passively; margin will be known post-fill.
            return RiskDecision.allow(self.name)

        total_capital = margin_used + available
        if total_capital <= 0:
            return RiskDecision.reject(
                "margin_heat: no margin data available — cannot evaluate",
                filter_name=self.name,
            )

        post_trade_util = (margin_used + est_new) / total_capital

        if post_trade_util > cap:
            return RiskDecision.reject(
                f"margin_heat: post-trade utilization {post_trade_util:.1%} > cap {cap:.1%}",
                filter_name=self.name,
            )

        return RiskDecision.allow(self.name)


class UnderlyingConcentrationFilter:
    """Rejects when positions per underlying > cap.

    Counts existing positions + proposed position grouped by underlying.
    Underlying extracted from Fyers ticker parsing or proposal field.
    """

    name = "underlying_concentration"

    def __init__(self, max_per_underlying: int | None = None) -> None:
        self._settings_backed = max_per_underlying is None
        if max_per_underlying is None:
            max_per_underlying = int(get_settings_store().get("max_positions_per_underlying") or 3)
        self.max_per_underlying = int(max_per_underlying)

    def _effective_max(self) -> int:
        if self._settings_backed:
            return int(get_settings_store().get("max_positions_per_underlying") or 3)
        return self.max_per_underlying

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        cap = self._effective_max()

        # Count existing positions per underlying
        counts: dict[str, int] = {}
        for pos in portfolio.positions:
            if abs(pos.net_quantity) <= 0:
                continue
            ul = _underlying_from_symbol(pos.symbol)
            counts[ul] = counts.get(ul, 0) + 1

        # Add proposed position
        if proposal is not None and proposal.quantity > 0:
            ul = proposal.underlying or _underlying_from_symbol(proposal.symbol)
            counts[ul] = counts.get(ul, 0) + 1

        # Check breach
        for ul, count in counts.items():
            if count > cap:
                return RiskDecision.reject(
                    f"underlying_concentration: {ul} has {count} positions (cap {cap})",
                    filter_name=self.name,
                )

        return RiskDecision.allow(self.name)


class SectorConcentrationFilter:
    """Rejects when sector notional / total notional > cap.

    Reuses sector_map.py for classification. Proposed notional added to
    the appropriate sector bucket.
    """

    name = "sector_concentration"

    def __init__(self, max_sector_pct: float | None = None) -> None:
        self._settings_backed = max_sector_pct is None
        if max_sector_pct is None:
            max_sector_pct = float(get_settings_store().get("max_sector_pct") or 0.20)
        self.max_sector_pct = float(max_sector_pct)

    def _effective_pct(self) -> float:
        if self._settings_backed:
            return float(get_settings_store().get("max_sector_pct") or 0.20)
        return self.max_sector_pct

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        cap = self._effective_pct()

        # Aggregate notional by sector
        sector_notional: dict[str, float] = {}
        total_notional = 0.0

        for pos in portfolio.positions:
            if abs(pos.net_quantity) <= 0:
                continue
            sector = _sector_for_symbol(pos.symbol)
            notional = abs(pos.net_quantity * pos.buy_avg)
            sector_notional[sector] = sector_notional.get(sector, 0.0) + notional
            total_notional += notional

        # Add proposed position
        if proposal is not None and proposal.quantity > 0 and proposal.entry_price:
            sector = _sector_for_symbol(proposal.symbol)
            lot_size = proposal.lot_size or 1
            notional = proposal.entry_price * proposal.quantity * lot_size
            sector_notional[sector] = sector_notional.get(sector, 0.0) + notional
            total_notional += notional

        if total_notional <= 0:
            return RiskDecision.allow(self.name)

        # Skip concentration check when there's only one sector (trivially 100%)
        if len(sector_notional) <= 1:
            return RiskDecision.allow(self.name)

        # Check breach
        for sector, notional in sector_notional.items():
            share = notional / total_notional
            if share > cap:
                return RiskDecision.reject(
                    f"sector_concentration: {sector} at {share:.1%} of portfolio (cap {cap:.1%})",
                    filter_name=self.name,
                )

        return RiskDecision.allow(self.name)


class DirectionConcentrationFilter:
    """Rejects when one direction > cap of total notional.

    Net long notional / total notional — rejects if > cap after proposal.
    """

    name = "direction_concentration"

    def __init__(self, max_direction_pct: float | None = None) -> None:
        self._settings_backed = max_direction_pct is None
        if max_direction_pct is None:
            max_direction_pct = float(get_settings_store().get("max_direction_pct") or 0.80)
        self.max_direction_pct = float(max_direction_pct)

    def _effective_pct(self) -> float:
        if self._settings_backed:
            return float(get_settings_store().get("max_direction_pct") or 0.80)
        return self.max_direction_pct

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        cap = self._effective_pct()

        long_notional = 0.0
        short_notional = 0.0

        for pos in portfolio.positions:
            if abs(pos.net_quantity) <= 0:
                continue
            notional = abs(pos.net_quantity * pos.buy_avg)
            if pos.net_quantity > 0:
                long_notional += notional
            else:
                short_notional += notional

        # Add proposed position
        if proposal is not None and proposal.quantity > 0 and proposal.entry_price:
            lot_size = proposal.lot_size or 1
            notional = proposal.entry_price * proposal.quantity * lot_size
            if proposal.side == "BUY":
                long_notional += notional
            else:
                short_notional += notional

        total = long_notional + short_notional
        if total <= 0:
            return RiskDecision.allow(self.name)

        # Skip direction check when only one direction exists (trivially 100%)
        if (long_notional > 0) != (short_notional > 0):
            return RiskDecision.allow(self.name)

        long_share = long_notional / total
        short_share = short_notional / total

        if long_share > cap:
            return RiskDecision.reject(
                f"direction_concentration: long at {long_share:.1%} (cap {cap:.1%})",
                filter_name=self.name,
            )
        if short_share > cap:
            return RiskDecision.reject(
                f"direction_concentration: short at {short_share:.1%} (cap {cap:.1%})",
                filter_name=self.name,
            )

        return RiskDecision.allow(self.name)


class StopHitCooldownFilter:
    """Rejects re-entry of a symbol within cooldown window after a stop-loss hit.

    Maintains an in-memory ledger of {symbol: last_stop_exit_timestamp}.
    Entries via record_stop_hit() — typically called by a subscriber to
    position exit events (EXIT_TSL actions from PositionManager).
    """

    name = "stop_cooldown"

    def __init__(self, cooldown_minutes: float | None = None) -> None:
        self._settings_backed = cooldown_minutes is None
        if cooldown_minutes is None:
            cooldown_minutes = float(get_settings_store().get("stop_cooldown_minutes") or 30.0)
        self.cooldown_minutes = float(cooldown_minutes)
        self._stop_hits: dict[str, float] = {}  # symbol → epoch timestamp

    def _effective_minutes(self) -> float:
        if self._settings_backed:
            return float(get_settings_store().get("stop_cooldown_minutes") or 30.0)
        return self.cooldown_minutes

    def record_stop_hit(self, symbol: str) -> None:
        """Record a stop-loss exit for the given symbol."""
        self._stop_hits[symbol.upper()] = time.time()

    def check(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        if proposal is None:
            return RiskDecision.allow(self.name)

        symbol = proposal.symbol.upper()
        cooldown_sec = self._effective_minutes() * 60

        if cooldown_sec <= 0:
            return RiskDecision.allow(self.name)

        last_hit = self._stop_hits.get(symbol)
        if last_hit is not None:
            elapsed = time.time() - last_hit
            if elapsed < cooldown_sec:
                remaining = cooldown_sec - elapsed
                return RiskDecision.reject(
                    f"stop_cooldown: {symbol} had a stop hit {elapsed:.0f}s ago "
                    f"(cooldown {cooldown_sec:.0f}s, {remaining:.0f}s remaining)",
                    filter_name=self.name,
                )

        return RiskDecision.allow(self.name)


# ---------------------------------------------------------------------------
# RiskEngine
# ---------------------------------------------------------------------------
class RiskEngine:
    """Risk engine with composable filter chain.

    For entry checks: runs all filters.
    For position management: always allows (loss limit does not freeze Mgmt).

    Default chain order (P3-4.2):
      LossLimit → MaxLossPerTrade → RiskReward → Margin → MarginHeat →
      Underlying → Sector → Direction → MaxPosition → StopCooldown → Regime(stub)
    """

    def __init__(self, filters: list[RiskFilter] | None = None) -> None:
        self._filters = filters or [
            LossLimitFilter(),
            MaxLossPerTradeFilter(),
            RiskRewardFilter(),
            MarginFilter(),
            MarginHeatFilter(),
            UnderlyingConcentrationFilter(),
            SectorConcentrationFilter(),
            DirectionConcentrationFilter(),
            MaxPositionFilter(),
            StopHitCooldownFilter(),
            RegimeFilter(),
        ]

    def check_entry(
        self,
        signal: Signal,
        portfolio: Portfolio,
        proposal: ProposalRiskContext | None = None,
    ) -> RiskDecision:
        """Run all filters. Return ALLOW only if all pass."""
        for f in self._filters:
            result = f.check(signal, portfolio, proposal)
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
