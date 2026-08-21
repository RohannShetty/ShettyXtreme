"""Option leg model — concrete option contract specification."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptionLeg:
    """A single option-leg specification used by proposals and hints.

    Carries everything needed to resolve an option contract: underlying,
    strike, expiry, CE/PE, and the lot-size / quantity relationship
    (``qty = lots * lot_size``).
    """

    underlying: str
    exchange: str
    strike: float
    expiry: str  # ISO date string (YYYY-MM-DD)
    option_type: str  # "CE" or "PE"
    lot_size: int
    qty: int  # total contracts = lots * lot_size
    lots: int
    entry_premium: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    dte: int | None = None
