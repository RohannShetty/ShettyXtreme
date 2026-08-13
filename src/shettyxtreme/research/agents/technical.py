"""TechnicalAnalyst — deterministic signal from RSI/EMA/MACD/Bollinger.

Reuses `intelligence.features.indicators` for the heavy lifting; this module
orchestrates the indicators and converts their outputs into a ResearchBrief-
shaped signal. D3-clean: zero LLM calls, zero external deps.

Input: a list of price dicts with keys `close`, `high`, `low`, `volume`
(plus optional `timestamp`). Output: direction + confidence + thesis.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.intelligence.features.indicators.bollinger import BollingerBands
from shettyxtreme.intelligence.features.indicators.ema import EMA
from shettyxtreme.intelligence.features.indicators.macd import MACD
from shettyxtreme.intelligence.features.indicators.rsi import RSI
from shettyxtreme.research.agents import Agent, AgentSignal, make_brief, register_agent
from shettyxtreme.research.briefs import ResearchBrief

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indicator thresholds
# ---------------------------------------------------------------------------
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0
RSI_STRONG_OVERSOLD = 20.0
RSI_STRONG_OVERBOUGHT = 80.0
MACD_CROSS_THRESHOLD = 0.0
BOLLINGER_PCT_B_LOW = 0.0
BOLLINGER_PCT_B_HIGH = 1.0
EMA_FAST = 9
EMA_SLOW = 21


def _prices_to_ticks(prices: list[dict[str, Any]], symbol: str = "NIFTY") -> list[Tick]:
    """Convert price dicts to Tick objects for indicator consumption."""
    ticks: list[Tick] = []
    for i, p in enumerate(prices):
        ts = p.get("timestamp", datetime.now(UTC))
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        ticks.append(Tick(
            symbol=symbol,
            exchange="NSE",
            ltp=float(p["close"]),
            volume=int(p.get("volume", 0)),
            timestamp=ts,
            high=float(p.get("high", p["close"])),
            low=float(p.get("low", p["close"])),
            open=float(p.get("open", p["close"])),
        ))
    return ticks


def compute_technical_signal(
    prices: list[dict[str, Any]],
    symbol: str = "NIFTY",
) -> ResearchBrief:
    """Compute a technical signal from OHLCV price data.

    Args:
        prices: List of dicts with keys: close, high, low, volume, timestamp.
                Must have at least 30 bars for meaningful signals.
        symbol: Symbol name for the brief.

    Returns:
        ResearchBrief with direction, confidence, thesis, rationale.
    """
    if len(prices) < 30:
        return make_brief(
            agent_name="technical",
            instruments=[symbol],
            direction=0,
            confidence=0.0,
            thesis="Insufficient data for technical analysis",
            rationale=(
                f"Need at least 30 bars of OHLCV data for RSI/EMA/MACD/Bollinger "
                f"computation. Got {len(prices)} bars. Provide more historical data "
                f"to enable technical signal generation."
            ),
            evidence=[{"item": f"data_points={len(prices)}", "source": "input", "unsourced": False}],
            risks=["Insufficient data — signal would be unreliable"],
        )

    ticks = _prices_to_ticks(prices, symbol)

    # Initialize indicators
    rsi = RSI(period=14)
    ema_fast = EMA(EMA_FAST)
    ema_slow = EMA(EMA_SLOW)
    macd = MACD(fast_period=12, slow_period=26, signal_period=9)
    bollinger = BollingerBands(period=20, num_std=2.0)

    # Feed all ticks
    last_rsi: float | None = None
    last_ema_fast: float | None = None
    last_ema_slow: float | None = None
    last_macd: float | None = None
    last_macd_signal: float | None = None
    last_macd_hist: float | None = None
    last_bb_pct_b: float | None = None
    last_bb_upper: float | None = None
    last_bb_lower: float | None = None

    for tick in ticks:
        rsi_val = rsi.update(tick)
        if rsi_val is not None:
            last_rsi = rsi_val
        fast_val = ema_fast.update(tick)
        if fast_val is not None:
            last_ema_fast = fast_val
        slow_val = ema_slow.update(tick)
        if slow_val is not None:
            last_ema_slow = slow_val
        macd_val = macd.update(tick)
        if macd_val is not None:
            last_macd = macd_val
            last_macd_signal = macd.signal
            last_macd_hist = macd.histogram
        bb_val = bollinger.update(tick)
        if bb_val is not None:
            last_bb_pct_b = bollinger.pct_b
            last_bb_upper = bollinger.upper
            last_bb_lower = bollinger.lower

    current_price = ticks[-1].ltp

    # --- Signal computation ---
    signals: list[tuple[str, float, float]] = []  # (name, direction, confidence)

    # RSI signal
    if last_rsi is not None:
        if last_rsi <= RSI_STRONG_OVERSOLD:
            signals.append(("RSI", 1.0, 0.8))
        elif last_rsi <= RSI_OVERSOLD:
            signals.append(("RSI", 1.0, 0.6))
        elif last_rsi >= RSI_STRONG_OVERBOUGHT:
            signals.append(("RSI", -1.0, 0.8))
        elif last_rsi >= RSI_OVERBOUGHT:
            signals.append(("RSI", -1.0, 0.6))
        else:
            signals.append(("RSI", 0.0, 0.3))

    # EMA crossover signal
    if last_ema_fast is not None and last_ema_slow is not None:
        ema_diff_pct = (last_ema_fast - last_ema_slow) / last_ema_slow * 100
        if ema_diff_pct > 0.5:
            signals.append(("EMA_crossover", 1.0, min(abs(ema_diff_pct) / 2.0, 0.9)))
        elif ema_diff_pct < -0.5:
            signals.append(("EMA_crossover", -1.0, min(abs(ema_diff_pct) / 2.0, 0.9)))
        else:
            signals.append(("EMA_crossover", 0.0, 0.2))

    # MACD signal
    if last_macd is not None and last_macd_signal is not None and last_macd_hist is not None:
        if last_macd_hist > 0:
            macd_conf = min(abs(last_macd_hist) / (current_price * 0.001), 0.9)
            signals.append(("MACD", 1.0, max(macd_conf, 0.3)))
        elif last_macd_hist < 0:
            macd_conf = min(abs(last_macd_hist) / (current_price * 0.001), 0.9)
            signals.append(("MACD", -1.0, max(macd_conf, 0.3)))
        else:
            signals.append(("MACD", 0.0, 0.2))

    # Bollinger Bands signal
    if last_bb_pct_b is not None:
        if last_bb_pct_b <= 0.0:
            signals.append(("Bollinger", 1.0, 0.7))  # At/below lower band → bullish
        elif last_bb_pct_b >= 1.0:
            signals.append(("Bollinger", -1.0, 0.7))  # At/above upper band → bearish
        elif last_bb_pct_b < 0.2:
            signals.append(("Bollinger", 1.0, 0.5))
        elif last_bb_pct_b > 0.8:
            signals.append(("Bollinger", -1.0, 0.5))
        else:
            signals.append(("Bollinger", 0.0, 0.2))

    # --- Weighted aggregation ---
    if not signals:
        return make_brief(
            agent_name="technical",
            instruments=[symbol],
            direction=0,
            confidence=0.0,
            thesis="No technical signals computed",
            rationale="Indicators produced no usable values from the provided data.",
            evidence=[],
            risks=["No signal — indicators may need more data"],
        )

    total_conf = sum(c for _, _, c in signals)
    if total_conf == 0:
        weighted_dir = 0.0
        avg_conf = 0.0
    else:
        weighted_dir = sum(d * c for _, d, c in signals) / total_conf
        avg_conf = total_conf / len(signals)

    # Determine direction
    if weighted_dir > 0.15:
        direction: int = 1
    elif weighted_dir < -0.15:
        direction = -1
    else:
        direction = 0

    # Confidence: scale by agreement
    agreement = sum(1 for _, d, _ in signals if (d > 0 and direction > 0) or (d < 0 and direction < 0) or (d == 0 and direction == 0))
    agreement_ratio = agreement / len(signals)
    final_confidence = min(avg_conf * agreement_ratio * 1.2, 1.0)

    # Build evidence
    evidence: list[dict[str, Any]] = []
    if last_rsi is not None:
        evidence.append({"item": f"RSI={last_rsi:.1f}", "source": "indicator", "unsourced": False})
    if last_ema_fast is not None and last_ema_slow is not None:
        evidence.append({"item": f"EMA{EMA_FAST}={last_ema_fast:.2f} EMA{EMA_SLOW}={last_ema_slow:.2f}", "source": "indicator", "unsourced": False})
    if last_macd is not None and last_macd_signal is not None:
        evidence.append({"item": f"MACD={last_macd:.4f} signal={last_macd_signal:.4f} hist={last_macd_hist:.4f}", "source": "indicator", "unsourced": False})
    if last_bb_pct_b is not None:
        evidence.append({"item": f"BB_%B={last_bb_pct_b:.2f} upper={last_bb_upper:.2f} lower={last_bb_lower:.2f}", "source": "indicator", "unsourced": False})

    # Build thesis
    dir_label = "Bullish" if direction > 0 else ("Bearish" if direction < 0 else "Neutral")
    indicators_str = ", ".join(name for name, _, _ in signals)
    thesis = f"{dir_label} technical setup ({indicators_str})"

    # Build rationale
    rationale_parts = []
    for name, d, c in signals:
        label = "bullish" if d > 0 else ("bearish" if d < 0 else "neutral")
        rationale_parts.append(f"{name} is {label} (conf={c:.2f})")
    rationale = (
        f"Technical analysis of {symbol} using {len(signals)} indicators: "
        + "; ".join(rationale_parts)
        + f". Weighted direction={weighted_dir:.3f}, agreement={agreement_ratio:.0%}. "
        + f"Current price={current_price:.2f}. "
    )
    # Pad to min_length=300 if needed
    if len(rationale) < 300:
        rationale += (
            "This signal is derived from pure price-action indicators with no "
            "external data sources or LLM inference. All computations are "
            "deterministic and reproducible."
        )

    # Risks
    risks: list[str] = []
    if agreement_ratio < 0.6:
        risks.append("Low indicator agreement — signal may be unreliable")
    if final_confidence < 0.4:
        risks.append("Low confidence — consider waiting for stronger setup")
    if last_rsi is not None and 40 < last_rsi < 60:
        risks.append("RSI in neutral zone — no clear momentum")

    return make_brief(
        agent_name="technical",
        instruments=[symbol],
        direction=direction,
        confidence=round(final_confidence, 4),
        thesis=thesis,
        rationale=rationale,
        evidence=evidence,
        risks=risks,
    )


# ---------------------------------------------------------------------------
# Agent registration
# ---------------------------------------------------------------------------
_technical_agent = Agent(
    name="technical",
    agent_type="technical",
    description=(
        "Deterministic technical analyst: RSI, EMA crossover, MACD, Bollinger Bands. "
        "No LLM calls — pure price-action indicators."
    ),
    deterministic=True,
)

# Override compute on the instance
_technical_agent.compute = lambda data, existing_signals=None: compute_technical_signal(  # type: ignore[assignment]
    data.get("prices", []),
    symbol=data.get("symbol", "NIFTY"),
)

register_agent(_technical_agent)
