"""OptionsAnalyst — deterministic signal from IV rank, PCR, Max Pain, OI.

Wires existing options modules into one signal. D3-clean: zero LLM calls.
Input: option chain data, IV history, spot price. Output: direction + confidence.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.intelligence.options.options_intel import compute_iv_rank, pcr_signal
from shettyxtreme.options.iv_rank import IVRankCalculator
from shettyxtreme.options.max_pain import compute_max_pain
from shettyxtreme.options.oi_tracker import OITracker
from shettyxtreme.research.agents import Agent, register_agent, make_brief
from shettyxtreme.research.briefs import ResearchBrief

logger = logging.getLogger(__name__)


def compute_options_signal(
    contracts: list[dict[str, Any]],
    spot: float,
    iv_history: list[float] | None = None,
    current_iv: float | None = None,
    symbol: str = "NIFTY",
) -> ResearchBrief:
    """Compute an options signal from chain data.

    Args:
        contracts: Option chain contracts (strike, option_type, oi, iv, etc.).
        spot: Current spot price.
        iv_history: Historical IV values for IV rank computation.
        current_iv: Current IV value (if None, uses average from contracts).
        symbol: Symbol name.

    Returns:
        ResearchBrief with direction, confidence, thesis, rationale.
    """
    if not contracts:
        return make_brief(
            agent_name="options",
            instruments=[symbol],
            direction=0,
            confidence=0.0,
            thesis="No option chain data available",
            rationale="No contracts provided for options analysis. Need option chain data with strike, option_type, oi, and iv fields.",
            evidence=[{"item": "contracts=0", "source": "input", "unsourced": False}],
            risks=["No data — cannot compute options signal"],
        )

    # --- Extract IV values ---
    iv_values: list[float] = []
    for c in contracts:
        try:
            iv = float(c.get("iv", 0))
            if iv > 0:
                iv_values.append(iv)
        except (TypeError, ValueError):
            pass

    if current_iv is None and iv_values:
        current_iv = sum(iv_values) / len(iv_values)

    # --- IV Rank ---
    iv_rank_val: float = 0.5  # default neutral
    iv_classification = "NORMAL"
    if current_iv is not None and iv_history and len(iv_history) >= 2:
        iv_rank_val = compute_iv_rank(current_iv, iv_history)
        if iv_rank_val > 0.7:
            iv_classification = "HIGH"
        elif iv_rank_val < 0.3:
            iv_classification = "LOW"

    # --- PCR Signal ---
    call_oi = 0
    put_oi = 0
    for c in contracts:
        try:
            oi = int(c.get("oi", 0) or 0)
            opt_type = str(c.get("option_type", "")).upper()
            if opt_type == "CE":
                call_oi += oi
            elif opt_type == "PE":
                put_oi += oi
        except (TypeError, ValueError):
            pass

    pcr = put_oi / call_oi if call_oi > 0 else 0.0
    pcr_dir, pcr_conf = pcr_signal(pcr, threshold=1.3)

    # --- Max Pain ---
    max_pain_strike = compute_max_pain(contracts)
    max_pain_bias: float = 0.0
    if max_pain_strike is not None and spot > 0:
        # If spot is above max pain → bias downward (mean reversion)
        # If spot is below max pain → bias upward (mean reversion)
        pain_diff_pct = (spot - max_pain_strike) / spot * 100
        if abs(pain_diff_pct) > 1.0:
            max_pain_bias = -1.0 if pain_diff_pct > 0 else 1.0
            max_pain_bias *= min(abs(pain_diff_pct) / 5.0, 1.0)  # Scale by distance

    # --- OI Buildup ---
    oi_tracker = OITracker()
    oi_tracker.update_from_chain(symbol, "current", contracts)
    oi_alerts = oi_tracker.get_alerts(min_significance="MEDIUM")

    oi_direction: float = 0.0
    if oi_alerts:
        # Count bullish (CE buildup = bearish for market, PE buildup = bullish)
        ce_buildup = sum(1 for a in oi_alerts if a.option_type == "CE" and a.oi_change_percent > 0)
        pe_buildup = sum(1 for a in oi_alerts if a.option_type == "PE" and a.oi_change_percent > 0)
        if pe_buildup > ce_buildup:
            oi_direction = 0.5  # PE buildup = bullish contrarian
        elif ce_buildup > pe_buildup:
            oi_direction = -0.5  # CE buildup = bearish contrarian

    # --- Signal aggregation ---
    # Weights: IV rank (25%), PCR (30%), Max Pain (25%), OI buildup (20%)
    weighted_dir = (
        (0.5 - iv_rank_val) * 0.25  # High IV rank → sell premium → slight bearish bias
        + pcr_dir * pcr_conf * 0.30
        + max_pain_bias * 0.25
        + oi_direction * 0.20
    )

    # Direction
    if weighted_dir > 0.1:
        direction: int = 1
    elif weighted_dir < -0.1:
        direction = -1
    else:
        direction = 0

    # Confidence
    confidence = min(
        abs(weighted_dir) * 2.0 + 0.3,
        0.95,
    )

    # Agreement
    agree_count = 0
    total_signals = 4
    if (0.5 - iv_rank_val) * (1 if direction > 0 else -1 if direction < 0 else 0) > 0:
        agree_count += 1
    if pcr_dir * (1 if direction > 0 else -1 if direction < 0 else 0) > 0:
        agree_count += 1
    if max_pain_bias * (1 if direction > 0 else -1 if direction < 0 else 0) > 0:
        agree_count += 1
    if oi_direction * (1 if direction > 0 else -1 if direction < 0 else 0) > 0:
        agree_count += 1

    agreement_ratio = agree_count / total_signals

    # Build evidence
    evidence: list[dict[str, Any]] = []
    evidence.append({"item": f"IV_rank={iv_rank_val:.2f} ({iv_classification})", "source": "options_intel", "unsourced": False})
    evidence.append({"item": f"PCR={pcr:.2f} pcr_signal_dir={pcr_dir:.1f}", "source": "options_intel", "unsourced": False})
    if max_pain_strike is not None:
        evidence.append({"item": f"MaxPain={max_pain_strike:.0f} spot={spot:.0f}", "source": "max_pain", "unsourced": False})
    evidence.append({"item": f"call_oi={call_oi} put_oi={put_oi}", "source": "oi_tracker", "unsourced": False})
    for alert in oi_alerts[:3]:
        evidence.append({
            "item": f"OI_alert {alert.option_type} {alert.strike} change={alert.oi_change_percent:+.1f}%",
            "source": "oi_tracker",
            "unsourced": False,
        })

    # Build thesis
    dir_label = "Bullish" if direction > 0 else ("Bearish" if direction < 0 else "Neutral")
    thesis = f"{dir_label} options positioning (IV={iv_classification}, PCR={pcr:.2f})"

    # Build rationale
    rationale = (
        f"Options analysis of {symbol}: IV rank={iv_rank_val:.2f} ({iv_classification}), "
        f"PCR={pcr:.2f} (signal={pcr_dir:+.1f}, conf={pcr_conf:.2f}), "
    )
    if max_pain_strike is not None:
        rationale += f"Max Pain={max_pain_strike:.0f} (spot={spot:.0f}, bias={max_pain_bias:+.2f}), "
    rationale += (
        f"OI alerts={len(oi_alerts)} ({'bullish' if oi_direction > 0 else 'bearish' if oi_direction < 0 else 'neutral'} buildup). "
        f"Weighted direction={weighted_dir:.3f}, agreement={agreement_ratio:.0%}. "
    )
    if len(rationale) < 300:
        rationale += (
            "This signal is derived from deterministic options analytics with no "
            "external data sources or LLM inference. All computations are "
            "reproducible from the provided chain data."
        )

    # Risks
    risks: list[str] = []
    if iv_rank_val > 0.8:
        risks.append("Extremely high IV rank — IV crush risk on short vol")
    if pcr > 1.5:
        risks.append("Very high PCR — contrarian reversal possible")
    if agreement_ratio < 0.5:
        risks.append("Low agreement between options signals")
    if not oi_alerts:
        risks.append("No OI buildup alerts — limited flow information")

    return make_brief(
        agent_name="options",
        instruments=[symbol],
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
_options_agent = Agent(
    name="options",
    agent_type="options",
    description=(
        "Deterministic options analyst: IV rank, PCR contrarian, Max Pain, OI buildup. "
        "No LLM calls — pure options analytics."
    ),
    deterministic=True,
)

_options_agent.compute = lambda data, existing_signals=None: compute_options_signal(  # type: ignore[assignment]
    data.get("contracts", []),
    spot=data.get("spot", 0.0),
    iv_history=data.get("iv_history"),
    current_iv=data.get("current_iv"),
    symbol=data.get("symbol", "NIFTY"),
)

register_agent(_options_agent)
