"""Options Intelligence — IV rank, PCR contrarian, expiry/strike selection.

All computations are pure feature-based. Strike selection uses signal-drift
expected value (EV), NOT risk-neutral GBM.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# IV Rank / Percentile
# ---------------------------------------------------------------------------
def compute_iv_rank(current_iv: float, iv_history: list[float]) -> float:
    """Compute IV rank: (current - min) / (max - min).

    Args:
        current_iv: Current implied volatility.
        iv_history: Historical IV values.

    Returns:
        Rank between 0.0 and 1.0. Returns 0.5 if max == min.
    """
    if not iv_history:
        return 0.5
    min_iv = min(iv_history)
    max_iv = max(iv_history)
    if max_iv > min_iv:
        return (current_iv - min_iv) / (max_iv - min_iv)
    return 0.5


def compute_iv_percentile(current_iv: float, iv_history: list[float]) -> float:
    """Compute IV percentile: % of historical values <= current.

    Args:
        current_iv: Current implied volatility.
        iv_history: Historical IV values.

    Returns:
        Percentile between 0.0 and 1.0.
    """
    if not iv_history:
        return 0.5
    count_below = sum(1 for v in iv_history if v <= current_iv)
    return count_below / len(iv_history)


# ---------------------------------------------------------------------------
# PCR Contrarian Signal
# ---------------------------------------------------------------------------
def pcr_signal(
    pcr: float,
    threshold: float = 1.3,
) -> tuple[float, float]:
    """Compute PCR contrarian signal.

    PCR > threshold → bullish (fear = contrarian buy)
    PCR < 1/threshold → bearish (greed = contrarian sell)

    Args:
        pcr: Put/Call ratio.
        threshold: Threshold for extreme PCR (default 1.3).

    Returns:
        Tuple of (direction, confidence).
        direction: 1.0 = bullish, -1.0 = bearish, 0.0 = neutral.
        confidence: 0.0 to 1.0.
    """
    bearish_threshold = 1.0 / threshold

    if pcr > threshold:
        direction = 1.0
        distance = (pcr - threshold) / threshold
    elif pcr < bearish_threshold:
        direction = -1.0
        distance = (bearish_threshold - pcr) / bearish_threshold
    else:
        return (0.0, 0.0)

    confidence = min(abs(distance) * 0.5, 0.9)
    return (direction, confidence)


# ---------------------------------------------------------------------------
# Expiry Selection
# ---------------------------------------------------------------------------
_NSE_WEEKLY_EXPIRY_DAYS: dict[str, int] = {
    "MONDAY": 3,    # Monday expiry = Thursday (3 days later)
    "TUESDAY": 2,   # Tuesday expiry = Thursday (2 days later)
    "WEDNESDAY": 1,  # Wednesday expiry = Thursday (1 day later)
    "THURSDAY": 0,   # Thursday expiry = same day
    "FRIDAY": 6,     # Friday → next Thursday (6 days)
    "SATURDAY": 5,   # Saturday → next Thursday (5 days)
    "SUNDAY": 4,     # Sunday → next Thursday (4 days)
}


def select_expiry(
    current_date: date,
    weekly_expiry: date,
    dte_threshold: int = 2,
) -> str:
    """Select the appropriate expiry based on DTE threshold.

    If days-to-expiry <= threshold, switch to next week's expiry.

    Args:
        current_date: Today's date.
        weekly_expiry: Current weekly expiry date.
        dte_threshold: Minimum DTE before rolling (default 2).

    Returns:
        Expiry date as ISO string (YYYY-MM-DD).
    """
    dte = (weekly_expiry - current_date).days
    if dte <= dte_threshold:
        # Roll to next week (add 7 days)
        next_expiry = weekly_expiry + timedelta(days=7)
        return next_expiry.isoformat()
    return weekly_expiry.isoformat()


# ---------------------------------------------------------------------------
# Signal-Drift Expected Value (strike selection)
# ---------------------------------------------------------------------------
def compute_signal_drift_ev(
    direction: float,
    conviction: float,
    current_price: float,
    strike: float,
    premium: float,
    slippage: float,
    brokerage: float,
    iv: float,
    days_to_expiry: int,
) -> float:
    """Compute expected value of a trade using signal drift.

    This is NOT risk-neutral GBM. It uses the signal's conviction to estimate
    directional drift.

    Expected premium change = signal_drift * delta * price_move_estimate
    where:
      - signal_drift = direction * conviction * 0.01  (1% per unit conviction)
      - delta = approximate delta from strike proximity
      - price_move_estimate = current_price * sqrt(dte/365) * signal_drift

    EV = (direction * conviction * expected_premium_change) - (slippage + brokerage)

    Args:
        direction: Signal direction (-1 to 1).
        conviction: Signal conviction (0 to 1).
        current_price: Underlying price.
        strike: Option strike price.
        premium: Option premium.
        slippage: Estimated slippage cost.
        brokerage: Brokerage cost.
        iv: Implied volatility.
        days_to_expiry: Days to expiry.

    Returns:
        Expected value (positive = attractive).
    """
    if days_to_expiry <= 0:
        days_to_expiry = 1

    # Signal drift: the directional signal's tendency
    signal_drift = direction * conviction * 0.01

    # Approximate delta from moneyness
    moneyness = (strike - current_price) / current_price
    # Simple approximation: ATM ~0.5, ITM ~0.8, OTM ~0.2
    if direction > 0:
        # For bullish (call): negative moneyness = ITM
        raw_delta = 0.5 - moneyness * 2.0
    else:
        # For bearish (put): positive moneyness = ITM
        raw_delta = 0.5 + moneyness * 2.0
    delta = max(0.05, min(0.95, raw_delta))

    # Price move estimate using IV + signal drift
    time_factor = math.sqrt(days_to_expiry / 365.0)
    price_move_estimate = current_price * time_factor * abs(signal_drift) * (iv / 100.0)

    # Expected premium change
    expected_premium_change = delta * price_move_estimate

    # Total cost
    total_cost = slippage + brokerage

    # Direction * conviction gives the sign and scales the EV
    ev = (direction * conviction * expected_premium_change) - total_cost

    return ev


def select_strike_by_ev(
    strikes: list[dict[str, Any]],
    direction: float,
    conviction: float,
    current_price: float,
    slippage_per_lot: float,
    brokerage_per_lot: float,
    iv: float,
    days_to_expiry: int,
) -> dict[str, Any] | None:
    """Select the strike with highest positive EV after cost.

    Args:
        strikes: List of strike dicts with 'strike', 'premium', 'lot_size' keys.
        direction: Signal direction (-1 to 1).
        conviction: Signal conviction (0 to 1).
        current_price: Underlying price.
        slippage_per_lot: Slippage per lot.
        brokerage_per_lot: Brokerage per lot.
        iv: Implied volatility.
        days_to_expiry: Days to expiry.

    Returns:
        Best strike dict, or None if no positive EV strikes.
    """
    best: dict[str, Any] | None = None
    best_ev: float = -float("inf")

    for s in strikes:
        ev = compute_signal_drift_ev(
            direction=direction,
            conviction=conviction,
            current_price=current_price,
            strike=s.get("strike", 0.0),
            premium=s.get("premium", 0.0),
            slippage=slippage_per_lot,
            brokerage=brokerage_per_lot,
            iv=iv,
            days_to_expiry=days_to_expiry,
        )
        if ev > best_ev:
            best_ev = ev
            best = s

    if best is not None and best_ev > 0:
        return best
    return None
