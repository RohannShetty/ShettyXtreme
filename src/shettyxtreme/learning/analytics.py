"""Analytics engine — turn recorded decisions into actionable statistics.

Groups decisions by regime, attributes voter contributions, summarizes costs,
and produces a top-level performance summary. All inputs are first-party
SignalDecision objects so the engine depends only on core/ and learning/.
"""
from __future__ import annotations

from dataclasses import dataclass

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision
from shettyxtreme.learning.voter_quality import VoterQualityTracker


@dataclass
class RegimeStats:
    """Signal quality aggregated by regime."""

    regime: Regime
    total_signals: int
    win_rate: float
    avg_conviction: float
    avg_ev: float


@dataclass
class VoterContribution:
    """A voter's contribution to the decision set."""

    voter_name: str
    signals_contributed: int
    hit_rate_when_voting: float
    marginal_value: float


@dataclass
class CostAnalysis:
    """Aggregate transaction cost statistics."""

    total_cost: float
    total_trades: int
    avg_cost_per_trade: float


@dataclass
class WinLossCount:
    """Win/loss counts per regime."""

    regime: Regime
    wins: int
    losses: int


@dataclass
class PerformanceSummary:
    """Top-level performance summary."""

    total_signals: int
    total_trades: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    sharpe: float
    max_drawdown: float
    cost_adjusted_pnl: float


def _regime_of(decision: SignalDecision) -> Regime:
    hint = decision.strategy_hint or {}
    reg = hint.get("regime")
    if reg is None:
        return Regime.RANGE_BOUND
    if isinstance(reg, Regime):
        return reg
    return Regime(str(reg))


def _is_win(decision: SignalDecision) -> bool:
    return decision.outcome == OutcomeLabel.WIN


class AnalyticsEngine:
    """Compute analytics over a set of signal decisions."""

    def signal_quality_by_regime(
        self, decisions: list[SignalDecision]
    ) -> dict[Regime, RegimeStats]:
        """Aggregate signal quality per regime."""
        groups: dict[Regime, list[SignalDecision]] = {}
        for d in decisions:
            reg = _regime_of(d)
            groups.setdefault(reg, []).append(d)
        result: dict[Regime, RegimeStats] = {}
        for reg, items in groups.items():
            total = len(items)
            wins = sum(1 for i in items if _is_win(i))
            convictions = [i.signal.conviction for i in items]
            avg_conv = sum(convictions) / total if total else 0.0
            avg_ev = sum(i.signal.conviction for i in items) / total if total else 0.0
            result[reg] = RegimeStats(
                regime=reg,
                total_signals=total,
                win_rate=wins / total if total else 0.0,
                avg_conviction=avg_conv,
                avg_ev=avg_ev,
            )
        return result

    def voter_contribution(
        self,
        decisions: list[SignalDecision],
        quality: VoterQualityTracker,
    ) -> dict[str, VoterContribution]:
        """Attribute contribution per voter that voted in these decisions."""
        contributions: dict[str, VoterContribution] = {}
        seen: dict[str, int] = {}
        for d in decisions:
            for vote in d.signal.voters:
                seen[vote.name] = seen.get(vote.name, 0) + 1
        for name, count in seen.items():
            report = None
            for r in quality.get_voter_report():
                if r.name == name:
                    report = r
                    break
            hit_rate = report.hit_rate if report is not None else 0.0
            marginal = hit_rate * count
            contributions[name] = VoterContribution(
                voter_name=name,
                signals_contributed=count,
                hit_rate_when_voting=hit_rate,
                marginal_value=marginal,
            )
        return contributions

    def cost_analysis(self, decisions: list[SignalDecision]) -> CostAnalysis:
        """Summarize transaction costs implied by the decisions."""
        total = 0.0
        trades = 0
        for d in decisions:
            if d.outcome is None or d.outcome == OutcomeLabel.UNREALIZED:
                continue
            trades += 1
            # Use embedded voter count as a rough proxy is not meaningful;
            # costs are charged per executed attempt.
            attempts = d.execution_attempts or []
            total += len(attempts)
        avg = total / trades if trades else 0.0
        return CostAnalysis(
            total_cost=total,
            total_trades=trades,
            avg_cost_per_trade=avg,
        )

    def win_loss_by_regime(
        self, decisions: list[SignalDecision]
    ) -> dict[Regime, WinLossCount]:
        """Count wins and losses per regime."""
        groups: dict[Regime, list[SignalDecision]] = {}
        for d in decisions:
            reg = _regime_of(d)
            groups.setdefault(reg, []).append(d)
        result: dict[Regime, WinLossCount] = {}
        for reg, items in groups.items():
            wins = sum(1 for i in items if i.outcome == OutcomeLabel.WIN)
            losses = sum(1 for i in items if i.outcome == OutcomeLabel.LOSS)
            result[reg] = WinLossCount(regime=reg, wins=wins, losses=losses)
        return result

    def performance_summary(
        self, decisions: list[SignalDecision]
    ) -> PerformanceSummary:
        """Produce a top-level performance summary across all decisions."""
        total_signals = len(decisions)
        resolved = [d for d in decisions if d.outcome is not None]
        trades = len(resolved)
        wins = sum(1 for d in resolved if d.outcome == OutcomeLabel.WIN)
        losses = sum(1 for d in resolved if d.outcome == OutcomeLabel.LOSS)
        win_rate = wins / trades if trades else 0.0

        pnls = self._pnls(decisions)
        total_pnl = sum(pnls)
        win_pnls = [p for p in pnls if p > 0]
        loss_pnls = [p for p in pnls if p < 0]
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
        avg_loss = sum(loss_pnls) / len(loss_pnls) if loss_pnls else 0.0
        sharpe = self._sharpe(pnls)
        max_dd = self._max_drawdown(pnls)

        return PerformanceSummary(
            total_signals=total_signals,
            total_trades=trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            avg_win=avg_win,
            avg_loss=avg_loss,
            sharpe=sharpe,
            max_drawdown=max_dd,
            cost_adjusted_pnl=total_pnl,
        )

    def _pnls(self, decisions: list[SignalDecision]) -> list[float]:
        pnls: list[float] = []
        for d in decisions:
            if d.outcome is None:
                continue
            hint = d.strategy_hint or {}
            entry = hint.get("entry_price", 0.0)
            exit_ = hint.get("exit_price", 0.0)
            qty = hint.get("quantity", 1)
            if entry and exit_:
                if d.signal.direction.value == "up":
                    pnls.append((exit_ - entry) * qty)
                elif d.signal.direction.value == "down":
                    pnls.append((entry - exit_) * qty)
                else:
                    pnls.append(0.0)
            elif d.outcome == OutcomeLabel.WIN:
                pnls.append(1.0)
            elif d.outcome == OutcomeLabel.LOSS:
                pnls.append(-1.0)
        return pnls

    def _sharpe(self, pnls: list[float]) -> float:
        if len(pnls) < 2:
            return 0.0
        mean = sum(pnls) / len(pnls)
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        std = var ** 0.5
        if std == 0:
            return 0.0
        return mean / std

    def _max_drawdown(self, pnls: list[float]) -> float:
        peak = 0.0
        cum = 0.0
        max_dd = 0.0
        for p in pnls:
            cum += p
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        return max_dd
