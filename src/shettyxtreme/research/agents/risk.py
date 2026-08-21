"""RiskManager — read-only risk annotation of aggregated signals.

Reuses `intelligence.risk.risk_engine` limits and `voter_correlation` as a
research pass that annotates signals with risk rule outcomes + evidence.
This is NEVER a live order gate — it's a "what would the risk gate say"
annotation. D3-clean: zero LLM calls.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.research.agents import Agent, register_agent, make_brief
from shettyxtreme.research.briefs import ResearchBrief

logger = logging.getLogger(__name__)


def compute_risk_annotation(
    signals: list[dict[str, Any]],
    portfolio: dict[str, Any] | None = None,
    regime: str | None = None,
) -> ResearchBrief:
    """Analyze aggregated signals through the risk lens.

    This is a read-only research pass — it answers "what would the risk gate
    say?" without actually gating anything.

    Args:
        signals: List of signal dicts with keys: agent, direction, confidence, instruments.
        portfolio: Optional portfolio state (positions, daily_pnl, margin).
        regime: Current market regime string.

    Returns:
        ResearchBrief annotating the signals with risk assessments.
    """
    if not signals:
        return make_brief(
            agent_name="risk",
            instruments=[],
            direction=0,
            confidence=0.0,
            thesis="No signals to assess",
            rationale="No analyst signals were provided for risk assessment. The risk manager requires at least one signal to annotate.",
            evidence=[{"item": "signals=0", "source": "input", "unsourced": False}],
            risks=["No signals — risk assessment not possible"],
        )

    # --- Portfolio risk checks ---
    risk_findings: list[dict[str, Any]] = []
    risk_score = 0.0  # 0 = no risk, 1 = maximum risk

    # Check daily P&L
    daily_pnl = portfolio.get("daily_pnl", 0.0) if portfolio else 0.0
    loss_limit = portfolio.get("loss_limit", -50000.0) if portfolio else -50000.0
    if daily_pnl < loss_limit:
        risk_findings.append({
            "rule": "loss_limit",
            "outcome": "BLOCKED",
            "detail": f"Daily P&L {daily_pnl:.0f} below loss limit {loss_limit:.0f}",
            "source": "risk_engine",
            "unsourced": False,
        })
        risk_score = max(risk_score, 0.9)
    elif daily_pnl < loss_limit * 0.7:
        risk_findings.append({
            "rule": "loss_limit",
            "outcome": "WARNING",
            "detail": f"Daily P&L {daily_pnl:.0f} approaching loss limit {loss_limit:.0f}",
            "source": "risk_engine",
            "unsourced": False,
        })
        risk_score = max(risk_score, 0.5)

    # Check margin
    available_margin = portfolio.get("available_margin", 100000.0) if portfolio else 100000.0
    total_margin = portfolio.get("total_margin_used", 0.0) if portfolio else 0.0
    if available_margin < 5000:
        risk_findings.append({
            "rule": "margin",
            "outcome": "BLOCKED",
            "detail": f"Insufficient margin: available={available_margin:.0f}",
            "source": "risk_engine",
            "unsourced": False,
        })
        risk_score = max(risk_score, 0.8)

    # Check max positions
    positions = portfolio.get("positions", []) if portfolio else []
    active_positions = sum(1 for p in positions if abs(p.get("net_quantity", 0)) > 0)
    max_positions = portfolio.get("max_positions", 5) if portfolio else 5
    if active_positions >= max_positions:
        risk_findings.append({
            "rule": "max_positions",
            "outcome": "BLOCKED",
            "detail": f"Max positions reached: {active_positions} >= {max_positions}",
            "source": "risk_engine",
            "unsourced": False,
        })
        risk_score = max(risk_score, 0.7)

    # --- Correlation analysis ---
    # Check if multiple signals agree too much (potential crowding)
    directions = [s.get("direction", 0) for s in signals]
    bullish_count = sum(1 for d in directions if d > 0)
    bearish_count = sum(1 for d in directions if d < 0)
    total = len(directions)

    crowding_threshold = 0.8
    if total > 1:
        max_agreement = max(bullish_count, bearish_count) / total
        if max_agreement > crowding_threshold:
            risk_findings.append({
                "rule": "correlation",
                "outcome": "WARNING",
                "detail": f"High signal agreement: {max_agreement:.0%} of signals agree on direction",
                "source": "voter_correlation",
                "unsourced": False,
            })
            risk_score = max(risk_score, 0.4)

    # --- Regime risk ---
    if regime in ("volatile", "crisis"):
        risk_findings.append({
            "rule": "regime",
            "outcome": "WARNING",
            "detail": f"Market regime is {regime} — elevated tail risk",
            "source": "regime_classifier",
            "unsourced": False,
        })
        risk_score = max(risk_score, 0.6)

    # --- Aggregate signal risk ---
    # High-confidence directional signals from multiple agents = potential crowding
    high_conf_signals = [s for s in signals if s.get("confidence", 0) > 0.7 and s.get("direction", 0) != 0]
    if len(high_conf_signals) >= 3:
        risk_findings.append({
            "rule": "signal_heat",
            "outcome": "WARNING",
            "detail": f"{len(high_conf_signals)} high-confidence signals active — potential overexposure",
            "source": "signal_aggregation",
            "unsourced": False,
        })
        risk_score = max(risk_score, 0.5)

    # --- Build the annotation ---
    # Direction: overall risk assessment
    blocked = any(f["outcome"] == "BLOCKED" for f in risk_findings)
    if blocked:
        direction: int = -1  # Risk says bearish/caution
    elif risk_score > 0.5:
        direction = 0  # Risk says neutral/wary
    else:
        direction = 1  # Risk says clear

    confidence = min(risk_score + 0.3, 0.95) if risk_findings else 0.3

    # Build evidence
    evidence: list[dict[str, Any]] = []
    for finding in risk_findings:
        evidence.append({
            "item": f"{finding['rule']}: {finding['outcome']} — {finding['detail']}",
            "source": finding["source"],
            "unsourced": finding.get("unsourced", False),
        })

    if not evidence:
        evidence.append({"item": "No risk issues detected", "source": "risk_engine", "unsourced": False})

    # Thesis
    if blocked:
        thesis = f"Risk gate would BLOCK — {sum(1 for f in risk_findings if f['outcome'] == 'BLOCKED')} rule(s) triggered"
    elif risk_findings:
        thesis = f"Risk gate would ALLOW with warnings — {len(risk_findings)} finding(s)"
    else:
        thesis = "Risk gate would ALLOW — no issues detected"

    # Rationale
    rationale = (
        f"Risk assessment of {len(signals)} analyst signals: "
        f"risk_score={risk_score:.2f}, "
        f"blocked={blocked}, "
        f"warnings={sum(1 for f in risk_findings if f['outcome'] == 'WARNING')}. "
    )
    for f in risk_findings:
        rationale += f"[{f['rule']}] {f['outcome']}: {f['detail']}. "
    if not risk_findings:
        rationale += "No risk rules triggered. "
    rationale += (
        "This is a read-only research annotation — the risk engine does not "
        "gating live orders here. It answers 'what would the risk gate say?' "
        "to inform the operator's decision."
    )

    # Risks from the risk agent itself
    risks: list[str] = []
    if blocked:
        risks.append("Risk gate would block new entries — review position management")
    if risk_score > 0.7:
        risks.append("High cumulative risk score — consider reducing exposure")
    if not portfolio:
        risks.append("No portfolio data — risk assessment is partial")

    return make_brief(
        agent_name="risk",
        instruments=list(set(inst for s in signals for inst in s.get("instruments", []))),
        direction=direction,
        confidence=round(confidence, 4),
        thesis=thesis,
        rationale=rationale,
        evidence=evidence,
        risks=risks,
    )


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------
_risk_agent = Agent(
    name="risk",
    agent_type="risk",
    description=(
        "Read-only risk annotation: loss limit, margin, max positions, correlation, "
        "regime risk. Never gates live orders — research-only assessment."
    ),
    deterministic=True,
)

def _risk_compute(data: dict[str, Any], existing_signals: list | None = None) -> ResearchBrief:
    signal_dicts: list[dict[str, Any]] = []
    for s in (existing_signals or []):
        if hasattr(s, "model_dump"):
            signal_dicts.append(s.model_dump())
        elif isinstance(s, dict):
            signal_dicts.append(s)
        else:
            signal_dicts.append({"agent": getattr(s, "lens", "unknown"), "direction": 0, "confidence": 0.0})
    return compute_risk_annotation(
        signal_dicts,
        portfolio=data.get("portfolio"),
        regime=data.get("regime"),
    )


_risk_agent.compute = _risk_compute  # type: ignore[assignment]

register_agent(_risk_agent)
