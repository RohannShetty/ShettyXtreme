"""Response models for the analytics API (Phase 4B)."""
from __future__ import annotations

from pydantic import BaseModel


class CalibrationPointResponse(BaseModel):
    conviction_bin: list[float]
    actual_win_rate: float
    sample_size: int
    confidence_interval: list[float]


class ScorecardMetricResponse(BaseModel):
    key: str
    label: str
    value: str | float | bool | None = None
    unit: str | None = None
    available: bool = False
    note: str | None = None


class RegimeRowResponse(BaseModel):
    regime: str
    decided: int = 0
    with_outcome: int = 0
    win_rate: float = 0.0


class ScorecardResponse(BaseModel):
    reliable_calibration: bool = False
    metrics: list[ScorecardMetricResponse] = []
    by_regime: list[RegimeRowResponse] = []
    calibration: list[CalibrationPointResponse] = []


class SessionsResponse(BaseModel):
    sessions: list[dict] = []
    counts: dict = {}


class LedgerFillResponse(BaseModel):
    fill_id: str
    order_id: str | None = None
    session_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    quantity: int | None = None
    price: float | None = None
    product: str | None = None
    source: str
    recorded_at: str


class LedgerSessionResponse(BaseModel):
    session_id: str
    fills: int = 0
    gross_notional: float = 0.0
    realized_pnl: float = 0.0


class LedgerResponse(BaseModel):
    fills: list[LedgerFillResponse] = []
    sessions: list[LedgerSessionResponse] = []
