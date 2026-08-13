"""PortfolioManager — deterministic weighted aggregation of analyst signals.

Fills the missing SignalThesis/aggregation slot (ai-hedge-fund pattern).
Deterministic weighted aggregation of analyst signals into a final proposal.
LLM narration is optional but constrained to a deterministically pre-validated
action set (section 12 §9: "LLM never touches the trade").
D3-clean: zero LLM calls.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from shettyxtreme.research.agents import Agent, register_agent, make_brief
from shettyxtreme.research.briefs import ResearchBrief

logger = logging.getLogger(__name__)

# Default agent weights (configurable)
DEFAULT_WEIGHTS: dict[str, float] = {
    "technical": 1.0,
    "options": 1.0,
    "sentiment": 0.8,
    "fundamental": 0.8,
    "risk": 1.5,  # Risk gets higher weight — safety first
}


def compute_portfolio_proposal(
    signals: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> ResearchBrief:
    """Aggregate analyst signals into a final portfolio proposal.

    This is the constrained aggregation stage: deterministic weighted voting
    over analyst signals. The result is a single ResearchBrief that represents
    the portfolio manager's proposal. LLM narration (optional, future) would
    be constrained to this pre-validated action set.

    Args:
        signals: List of signal dicts with keys: agent (str), direction (int),
                 confidence (float), instruments (list[str]), thesis (str).
        weights: Optional agent-name-to-weight mapping. Defaults to DEFAULT_WEIGHTS.

    Returns:
        ResearchBrief with aggregated direction, confidence, and synthesis.
    """
    w = weights or DEFAULT_WEIGHTS

    if not signals:
        return make_brief(
            agent_name="portfolio",
            instruments=[],
            direction=0,
            confidence=0.0,
            thesis="No analyst signals to aggregate",
            rationale="The portfolio manager received no analyst signals. At least one analyst must produce a signal for aggregation.",
            evidence=[{"item": "signals=0", "source": "input", "unsourced": False}],
            risks=["No signals — portfolio proposal not possible"],
        )

    # --- Weighted voting ---
    weighted_sum = 0.0
    total_weight = 0.0
    agent_details: list[dict[str, Any]] = []

    for signal in signals:
        agent_name = signal.get("agent", "unknown")
        direction = signal.get("direction", 0)
        confidence = signal.get("confidence", 0.0)
        weight = w.get(agent_name, 1.0)

        # Effective weight = agent weight * confidence
        effective_weight = weight * confidence
        weighted_sum += direction * effective_weight
        total_weight += effective_weight

        agent_details.append({
            "agent": agent_name,
            "direction": direction,
            "confidence": confidence,
            "weight": weight,
            "effective_weight": effective_weight,
            "contribution": direction * effective_weight,
        })

    # Compute weighted direction
    if total_weight > 0:
        weighted_direction = weighted_sum / total_weight
    else:
        weighted_direction = 0.0

    # Determine final direction
    if weighted_direction > 0.15:
        final_direction: Literal[-1, 0, 1] = 1
    elif weighted_direction < -0.15:
        final_direction = -1
    else:
        final_direction = 0

    # Confidence: based on agreement + total weight
    agreeing = sum(
        1 for d in agent_details
        if (d["direction"] > 0 and final_direction > 0)
        or (d["direction"] < 0 and final_direction < 0)
        or (d["direction"] == 0 and final_direction == 0)
    )
    agreement_ratio = agreeing / len(agent_details) if agent_details else 0.0
    final_confidence = min(
        agreement_ratio * 0.7 + abs(weighted_direction) * 0.3,
        0.95,
    )

    # --- Collect instruments ---
    all_instruments: list[str] = []
    for signal in signals:
        for inst in signal.get("instruments", []):
            if inst not in all_instruments:
                all_instruments.append(inst)

    # --- Risk assessment ---
    # Check if risk agent blocked
    risk_signal = next((s for s in signals if s.get("agent") == "risk"), None)
    risk_blocked = False
    if risk_signal:
        risk_dir = risk_signal.get("direction", 0)
        if risk_dir < 0:
            risk_blocked = True
            final_confidence *= 0.5  # Halve confidence if risk says caution

    # --- Build evidence ---
    evidence: list[dict[str, Any]] = []
    for detail in agent_details:
        dir_label = "bullish" if detail["direction"] > 0 else ("bearish" if detail["direction"] < 0 else "neutral")
        evidence.append({
            "item": f"{detail['agent']}: {dir_label} (conf={detail['confidence']:.2f}, weight={detail['weight']:.1f}, contribution={detail['contribution']:+.3f})",
            "source": "signal_aggregation",
            "unsourced": False,
        })
    evidence.append({
        "item": f"weighted_direction={weighted_direction:.3f}, agreement={agreement_ratio:.0%}",
        "source": "portfolio_manager",
        "unsourced": False,
    })
    if risk_blocked:
        evidence.append({
            "item": "Risk gate would BLOCK — confidence halved",
            "source": "risk_annotation",
            "unsourced": False,
        })

    # --- Build thesis ---
    dir_label = "Bullish" if final_direction > 0 else ("Bearish" if final_direction < 0 else "Neutral")
    thesis_parts = [f"{dir_label} portfolio proposal"]
    if risk_blocked:
        thesis_parts.append("(risk caution)")
    thesis_parts.append(f"from {len(signals)} agents")
    thesis = " ".join(thesis_parts)

    # --- Build rationale ---
    rationale = (
        f"Portfolio aggregation of {len(signals)} analyst signals: "
        f"weighted_direction={weighted_direction:.3f}, "
        f"agreement={agreement_ratio:.0%}, "
        f"total_weight={total_weight:.2f}. "
    )
    for detail in agent_details:
        dir_label = "bullish" if detail["direction"] > 0 else ("bearish" if detail["direction"] < 0 else "neutral")
        rationale += f"{detail['agent']}={dir_label}(w={detail['weight']:.1f},c={detail['confidence']:.2f}) "
    if risk_blocked:
        rationale += "Risk agent flagged caution — proposal confidence reduced. "
    rationale += (
        "This is a deterministic aggregation — the final proposal is derived "
        "from weighted voting over analyst signals with no LLM involvement. "
        "The operator decides whether to act on this proposal."
    )

    # --- Risks ---
    risks: list[str] = []
    if agreement_ratio < 0.5:
        risks.append("Low agent agreement — proposal is contested")
    if risk_blocked:
        risks.append("Risk agent would block — proceed with caution")
    if total_weight < 1.0:
        risks.append("Low total weight — few signals contributing")
    if final_confidence < 0.3:
        risks.append("Low final confidence — weak signal")

    return make_brief(
        agent_name="portfolio",
        instruments=all_instruments[:10],
        direction=final_direction,
        confidence=round(final_confidence, 4),
        thesis=thesis,
        rationale=rationale,
        evidence=evidence,
        risks=risks,
    )


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------
_portfolio_agent = Agent(
    name="portfolio",
    agent_type="portfolio",
    description=(
        "Deterministic portfolio aggregation: weighted voting over analyst signals "
        "into a final proposal. LLM narration optional but constrained to pre-validated actions."
    ),
    deterministic=True,
)

def _portfolio_compute(data: dict[str, Any], existing_signals: list | None = None) -> ResearchBrief:
    signal_dicts: list[dict[str, Any]] = []
    for s in (existing_signals or []):
        if hasattr(s, "model_dump"):
            signal_dicts.append(s.model_dump())
        elif isinstance(s, dict):
            signal_dicts.append(s)
        else:
            signal_dicts.append({"agent": getattr(s, "lens", "unknown"), "direction": 0, "confidence": 0.0})
    return compute_portfolio_proposal(
        signal_dicts,
        weights=data.get("weights"),
    )


_portfolio_agent.compute = _portfolio_compute  # type: ignore[assignment]

register_agent(_portfolio_agent)
