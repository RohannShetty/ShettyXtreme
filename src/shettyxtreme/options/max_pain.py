"""Max pain calculator for option chains.

Computes the strike price at which option holders (combined CE + PE)
experience the minimum total pain — the max pain strike.
"""
from __future__ import annotations

from typing import Any


def compute_max_pain(contracts: list[dict[str, Any]]) -> float | None:
    """Compute max pain strike from option chain data.

    Each contract dict should have: strike, oi (or open_interest), option_type (CE/PE).
    Returns the strike price where total pain is minimized, or None if insufficient data.

    The algorithm iterates over every candidate strike and sums the total
    monetary pain option holders would suffer if the underlying settled there:

    - CE holders lose when spot < strike → pain += (strike - spot) * CE_OI
    - PE holders lose when spot > strike → pain += (spot - strike) * PE_OI

    The strike with the least total pain is the max-pain strike.

    Args:
        contracts: List of contract dicts from the option chain.
                   Keys: ``strike``, ``oi`` (or ``open_interest``),
                   ``option_type`` (``"CE"`` or ``"PE"``).

    Returns:
        The max-pain strike price as a float, or ``None`` when the
        contracts list is empty or lacks usable OI data.
    """
    strikes: set[float] = set()
    ce_oi: dict[float, int] = {}
    pe_oi: dict[float, int] = {}

    for c in contracts:
        s = float(c.get("strike", 0) or 0)
        oi_raw = c.get("oi") or c.get("open_interest") or 0
        try:
            oi = int(oi_raw)
        except (TypeError, ValueError):
            oi = 0
        opt_type = str(c.get("option_type", "")).upper()
        if s <= 0 or oi <= 0:
            continue
        strikes.add(s)
        if opt_type == "CE":
            ce_oi[s] = ce_oi.get(s, 0) + oi
        elif opt_type == "PE":
            pe_oi[s] = pe_oi.get(s, 0) + oi

    if not strikes:
        return None

    sorted_strikes = sorted(strikes)
    min_pain = float("inf")
    max_pain_strike: float | None = None

    for candidate in sorted_strikes:
        pain = 0.0
        for s in sorted_strikes:
            # CE holders lose when spot < strike (they paid premium but option expires worthless)
            if s > candidate and s in ce_oi:
                pain += (s - candidate) * ce_oi[s]
            # PE holders lose when spot > strike
            if s < candidate and s in pe_oi:
                pain += (candidate - s) * pe_oi[s]
        if pain < min_pain:
            min_pain = pain
            max_pain_strike = candidate

    return max_pain_strike
