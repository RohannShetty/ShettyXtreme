"""Response models for the Terminal API.

All pydantic BaseModel response models live here. Fields use `str | None`
syntax (not Optional[str]).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ── Watchlist ──────────────────────────────────────────────────────────────
class WatchlistItem(BaseModel):
    symbol: str
    exchange: str
    ltp: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    timestamp: datetime | None = None


# ── Intelligence ───────────────────────────────────────────────────────────
class VoterBreakdown(BaseModel):
    name: str
    direction: float
    confidence: float
    weight: float


class RegimeResponse(BaseModel):
    regime: str
    confidence: float
    transition: bool
    adx: float | None = None
    di_plus: float | None = None
    di_minus: float | None = None


class SignalResponse(BaseModel):
    direction: str  # UP / DOWN / NEUTRAL
    conviction: float
    D: float
    P: float
    G: float
    voters: list[VoterBreakdown] = []
    timestamp: datetime | None = None


class OptionsChainItem(BaseModel):
    strike: float
    option_type: str  # CE / PE
    ltp: float
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
    oi: int
    volume: int
    bid: float
    ask: float


class OptionsChainResponse(BaseModel):
    underlying: str
    expiry: str
    timestamp: datetime | None = None
    contracts: list[OptionsChainItem] = []


class StrategyHintResponse(BaseModel):
    direction: str
    strike: float | None = None
    premium: float | None = None
    ev_after_cost: float | None = None
    rationale: str = ""


# ── Execution ──────────────────────────────────────────────────────────────
class PositionResponse(BaseModel):
    symbol: str
    exchange: str
    quantity: int
    buy_avg: float = 0.0
    net_quantity: int = 0
    m2m: float = 0.0
    pnl: float = 0.0
    product: str = "NRML"


class RiskResponse(BaseModel):
    daily_pnl: float = 0.0
    margin_used: float = 0.0
    margin_available: float = 0.0
    loss_limit: float = 0.0
    loss_limit_hit: bool = False
    max_positions: int = 0
    active_positions: int = 0


class ModeResponse(BaseModel):
    mode: str  # OBSERVER / LIVE / PAPER


class KillSwitchResponse(BaseModel):
    active: bool
    activated_at: datetime | None = None


# ── Scanner ────────────────────────────────────────────────────────────────
class GapResponse(BaseModel):
    symbol: str
    gap_type: str  # breakaway / exhaustion / common
    gap_percent: float
    direction: str  # gap_up / gap_down
    timestamp: datetime | None = None


class ClusterResponse(BaseModel):
    symbol: str
    cluster_type: str  # e.g. "multi_scanner"
    strength: float  # 0-10
    source_count: int
    sources: list[str] = []


class AlertResponse(BaseModel):
    alert_type: str  # staleness / threshold_breach / regime_change
    severity: str  # LOW / MEDIUM / HIGH
    message: str
    timestamp: datetime | None = None


class LogResponse(BaseModel):
    log_type: str  # signal / execution / system
    message: str
    level: str  # INFO / WARN / ERROR
    timestamp: datetime | None = None


# ── Health ─────────────────────────────────────────────────────────────────
class ComponentHealth(BaseModel):
    name: str
    status: str  # healthy / degraded / down
    latency_ms: float | None = None
    last_check: datetime | None = None
    message: str = ""


class HealthResponse(BaseModel):
    components: list[ComponentHealth] = []
    overall: str = "healthy"  # healthy / degraded / down


class SessionResponse(BaseModel):
    status: str  # pre_open / open / post_close / closed
    current_time_ist: str = ""
    next_event: str = ""
    next_event_time: str = ""
