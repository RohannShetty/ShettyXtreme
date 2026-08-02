"""Core knowledge lexicons (D12: pure data, no external imports).

Curated symbol, regime, and risk vocabularies used by the heuristic
tagger in `knowledge/tagger.py`. Hardcoded on purpose: core/ never reads
configs, and the tagger must behave identically on every machine.
"""
from __future__ import annotations

# Curated NSE instrument symbols. Seeded from configs/default_watchlist.yaml
# indices (NIFTY, BANKNIFTY, FINNIFTY) plus the common F&O bench names.
NSE_SYMBOLS: set[str] = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
}

# Common colloquial tokens -> canonical symbols (disambiguation at tag time).
SYMBOL_ALIASES: dict[str, str] = {
    "BANK": "BANKNIFTY",
    "BNF": "BANKNIFTY",
    "FIN": "FINNIFTY",
    "MIDCAP": "MIDCPNIFTY",
    "NIFTYNEXT50": "NIFTYNXT50",
}

# Regime keyword -> normalized tag. Values are the lowercase
# `intelligence.regime.regime_classifier.Regime` enum values (spec 4A §3.1).
REGIME_TERMS: dict[str, str] = {
    "trending": "trending_up",
    "trending up": "trending_up",
    "uptrend": "trending_up",
    "bullish": "trending_up",
    "bull": "trending_up",
    "falling": "trending_down",
    "downtrend": "trending_down",
    "bearish": "trending_down",
    "bear": "trending_down",
    "ranging": "range_bound",
    "range bound": "range_bound",
    "sideways": "range_bound",
    "flat": "range_bound",
}

# Risk keyword -> normalized risk tag.
RISK_THEMES: dict[str, str] = {
    "crowding": "CROWDING",
    "crowded": "CROWDING",
    "elevated iv": "ELEVATED_IV",
    "high iv": "ELEVATED_IV",
    "iv rank": "ELEVATED_IV",
    "tail risk": "TAIL_RISK",
    "tail-risk": "TAIL_RISK",
    "overbought": "OVERBOUGHT",
    "oversold": "OVERSOLD",
    "gap risk": "GAP_RISK",
    "gap up": "GAP_RISK",
    "gap down": "GAP_RISK",
    "event risk": "EVENT_RISK",
    "binary event": "EVENT_RISK",
    "resistance": "RESISTANCE",
    "support": "SUPPORT",
    "expiry": "EXPIRY",
}

# Common words that must never be tagged as symbols (disambiguation).
SYMBOL_STOPWORDS: set[str] = {
    "IT",
    "ON",
    "IN",
    "AT",
    "TO",
    "OF",
    "THE",
    "A",
    "AN",
    "AND",
    "OR",
    "FOR",
    "WITH",
    "AS",
    "BY",
    "IS",
    "BE",
    "ARE",
    "WAS",
    "WERE",
}

_EXCHANGE_PREFIXES = ("NSE:", "NSE_FNO:", "BSE:")


def normalize_symbol(token: str) -> str | None:
    """Normalize a candidate symbol token, or None when it isn't one.

    Strips exchange prefixes (NSE:, NSE_FNO:, BSE:), uppercases, and returns
    the token only when it names a known NSE symbol and isn't a stopword.
    """
    candidate = token.strip().upper()
    if not candidate:
        return None
    for prefix in _EXCHANGE_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):]
            break
    candidate = SYMBOL_ALIASES.get(candidate, candidate)
    if candidate in SYMBOL_STOPWORDS:
        return None
    return candidate if candidate in NSE_SYMBOLS else None
