"""V2 API response models.

Backward-compatible with v1 but with room to evolve independently.
New fields are optional so v1 clients can migrate incrementally.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ── Watchlist v2 ──────────────────────────────────────────────────────────
class WatchlistItemV2(BaseModel):
    """V2 watchlist item — adds metadata fields for richer UI."""
    symbol: str
    exchange: str
    ltp: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    timestamp: datetime | None = None
    security_id: str | None = None
    expiry: str | None = None
    lot_size: int | None = None
    # V2 additions
    instrument_type: str | None = None  # INDEX / EQUITY / FUTURES / OPTION
    bid: float | None = None
    ask: float | None = None
    oi: int | None = None
    is_tradable: bool = True  # False for halted/suspended instruments


# ── Options Chain v2 ──────────────────────────────────────────────────────
class OptionsChainItemV2(BaseModel):
    """V2 options chain contract — normalized field names."""
    strike: float
    option_type: Literal["CE", "PE"]  # Normalized to CE/PE
    ltp: float
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    oi: int
    volume: int
    bid: float = 0.0
    ask: float = 0.0
    # V2 additions
    spot_distance_pct: float | None = None  # % from spot to strike
    open_interest_change: int | None = None  # OI change from prev session


class OptionsChainResponseV2(BaseModel):
    """V2 options chain response — adds analytics summary."""
    underlying: str
    expiry: str
    timestamp: datetime | None = None
    spot: float | None = None  # Underlying spot price
    contracts: list[OptionsChainItemV2] = []
    # V2 additions: aggregate analytics
    max_pain: float | None = None
    pcr: float | None = None  # Put-call ratio from OI
    iv_rank_percent: float | None = None


# ── API Info ──────────────────────────────────────────────────────────────
class APIVersionInfo(BaseModel):
    """Version metadata for the API."""
    version: str = "2.0.0"
    release_date: str = "2026-08-13"
    deprecated: list[str] = []  # List of deprecated v1 endpoints
    migration_guide: str = "/docs/api/v2/migration"
