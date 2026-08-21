"""Response models for the Terminal API.

All pydantic BaseModel response models live here. Fields use `str | None`
syntax (not Optional[str]).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ── Watchlist ──────────────────────────────────────────────────────────────
class WatchlistItem(BaseModel):
    symbol: str
    exchange: str
    ltp: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    timestamp: datetime | None = None
    security_id: str | None = None
    expiry: str | None = None
    lot_size: int | None = None


# ── Symbol Search ─────────────────────────────────────────────────────────
class SymbolSearchHit(BaseModel):
    internal_symbol: str
    fyers_symbol: str
    exchange: str
    instrument_type: str
    expiry: str | None = None
    strike: float | None = None
    option_type: str | None = None
    lot_size: int | None = None
    tick_size: float | None = None


class SymbolSearchResponse(BaseModel):
    query: str
    canonical: str
    hits: list[SymbolSearchHit] = []


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
    strategy: str | None = None
    strike: float | None = None
    premium: float | None = None
    ev_after_cost: float | None = None
    rationale: str = ""
    expiry: str | None = None
    option_type: str | None = None
    lot_size: int | None = None
    lots: int | None = None
    entry_premium: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    confidence: float | None = None


class ProposeFromHintRequest(BaseModel):
    """Payload for one-click proposal generation from a hint (3A.2).

    Mirrors the StrategyHintResponse fields the hints panel displays; the
    endpoint builds a SignalV2-shaped signal and queues a PENDING proposal.
    """
    symbol: str
    direction: str  # bullish / bearish (UP / DOWN accepted)
    strike: float | None = None
    premium: float | None = None
    expiry: str | None = None
    option_type: str | None = None  # CE / PE (derived from direction when absent)
    lot_size: int | None = None
    lots: int | None = None
    stop_loss: float | None = None
    target: float | None = None
    rationale: str | None = None
    confidence: float | None = None
    conviction: float | None = None
    quantity: int | None = None


class RegimeHintStats(BaseModel):
    """Per-regime hint accuracy breakdown (Phase 3C.1)."""
    win_rate: float | None = None
    avg_pnl: float | None = None
    sample_size: int = 0


class HintStatsResponse(BaseModel):
    """Hint accuracy statistics over the trailing window (3A.2 + 3C.1)."""
    win_rate: float | None = None
    avg_pnl: float | None = None
    sample_size: int = 0
    total_hints: int = 0
    days: int = 30
    regime_breakdown: dict[str, RegimeHintStats] = {}


# ── Market data ────────────────────────────────────────────────────────────
class MarketBar(BaseModel):
    timestamp: str  # ISO-8601 (normalized from epoch seconds)
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketBarsResponse(BaseModel):
    symbol: str
    exchange: str
    bars: list[MarketBar] = []


class MarketLtpResponse(BaseModel):
    symbol: str
    exchange: str
    ltp: float
    change_pct: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None


# ── Execution ──────────────────────────────────────────────────────────────
class PositionGreeks(BaseModel):
    """Per-position greeks block (net_quantity × contract_greek)."""
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0


class PositionResponse(BaseModel):
    symbol: str
    exchange: str
    quantity: int
    buy_avg: float = 0.0
    net_quantity: int = 0
    m2m: float = 0.0
    pnl: float = 0.0
    product: str = "NRML"
    # Option identity — populated when the symbol parses as a Fyers option.
    strike: float | None = None
    option_type: str | None = None  # CE / PE
    expiry: str | None = None
    # Instrument type — OPTION / FUTURES / EQUITY / INDEX. Populated from
    # the Fyers symbol parser so the frontend can render per-position context
    # without extra lookups.
    instrument_type: str | None = None
    # Per-position greeks (net_quantity × contract_greek). None when not an
    # option or when IV/spot are unavailable.
    greeks: PositionGreeks | None = None
    # Trade context — linked from the originating proposal (P3-4.3).
    # Populated when the fill event carries a signal_id that maps to a
    # PendingApproval with a strategy_hint.
    stop_loss: float | None = None
    target: float | None = None
    rationale: str | None = None
    confidence: float | None = None
    signal_id: str | None = None
    lot_size: int | None = None


class RiskResponse(BaseModel):
    daily_pnl: float = 0.0
    margin_used: float = 0.0
    # None = unknown (no broker report yet); clients must render this as
    # "no data", never as zero or a fabricated amount (fix #2).
    margin_available: float | None = None
    loss_limit: float = 0.0
    loss_limit_hit: bool = False
    max_positions: int = 0
    active_positions: int = 0


class PortfolioGreeksResponse(BaseModel):
    """Aggregate portfolio greeks across all open option positions."""
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    positions: list[PositionResponse] = []


# ── Risk Heat Map ─────────────────────────────────────────────────────────
class SectorExposureItem(BaseModel):
    """One sector's aggregated exposure."""
    sector: str
    notional: float = 0.0
    pnl: float = 0.0
    share_pct: float = 0.0


class GreeksBreakdownItem(BaseModel):
    """Long/short split for one greek."""
    long_val: float = 0.0
    short_val: float = 0.0
    net: float = 0.0


class GreeksConcentrationItem(BaseModel):
    """Portfolio-level greeks with long/short breakdown."""
    delta: GreeksBreakdownItem = GreeksBreakdownItem()
    gamma: GreeksBreakdownItem = GreeksBreakdownItem()
    theta: GreeksBreakdownItem = GreeksBreakdownItem()
    vega: GreeksBreakdownItem = GreeksBreakdownItem()
    lopsided_warning: str | None = None


class ScenarioPnlItem(BaseModel):
    """P&L for one spot shift scenario."""
    shift_pct: float
    total_pnl: float = 0.0


class StressItem(BaseModel):
    """Max-loss stress test result."""
    scenarios: list[ScenarioPnlItem] = []
    worst_case_pnl: float = 0.0
    worst_case_shift: float = 0.0


class MarginUtilizationItem(BaseModel):
    """Margin utilization metric."""
    margin_used: float | None = None
    margin_available: float | None = None
    total: float | None = None
    utilization_pct: float | None = None
    breach: bool = False


class RiskHeatmapResponse(BaseModel):
    """Full risk heat map — all 4 dimensions.

    Missing data degrades to empty/None — never faked (honesty rule).
    """
    sector_exposure: list[SectorExposureItem] = []
    greeks: GreeksConcentrationItem = GreeksConcentrationItem()
    stress: StressItem = StressItem()
    margin: MarginUtilizationItem = MarginUtilizationItem()
    position_count: int = 0
    enriched_count: int = 0


class ModeResponse(BaseModel):
    mode: str  # OBSERVER / LIVE / PAPER
    # Per-session CSRF token (minted on typed LIVE activation). None outside
    # a LIVE session. Returned on every mode read so the SPA can recover it
    # across reloads (F-EXEC-001).
    csrf_token: str | None = None


class KillSwitchResponse(BaseModel):
    active: bool
    activated_at: datetime | None = None
    # Placements already dispatched to the broker when the switch was armed
    # (Phase 6 Lane B arm-window reporting: "placed just before kill").
    placements_in_flight: int = 0


class ProposalResponse(BaseModel):
    """An OBSERVER proposal awaiting (or having received) human action."""
    id: str
    symbol: str
    exchange: str
    side: str  # BUY / SELL
    quantity: int = 0
    price: float | None = None
    order_type: str = "MARKET"
    product: str = "MIS"
    conviction: float = 0.0
    D: float = 0.0
    P: float = 1.0
    G: str = "contested"
    source: str = "signal_v2"
    hint_kind: str = "default"  # default / chain — chain-derived when a real builder is plugged
    signal_id: str = ""
    status: str = "PENDING"  # PENDING / APPROVED / REJECTED / EXPIRED
    reason: str = ""
    timestamp: datetime | None = None
    strike: float | None = None
    expiry: str | None = None
    option_type: str | None = None
    lot_size: int | None = None
    lots: int | None = None
    entry_premium: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    rationale: str | None = None
    # Enriched fields (P3-4.3): strategy context from chain hint builder.
    confidence: float | None = None
    ev_after_cost: float | None = None
    strategy: str | None = None
    underlying: str | None = None


class OrderResponse(BaseModel):
    """An order record for the order history endpoint (P3-4.3)."""
    order_id: str
    symbol: str
    exchange: str
    side: str
    order_type: str
    quantity: int
    price: float
    status: str  # FILLED / REJECTED / CANCELLED / OPEN / PARTIALLY_FILLED
    filled_quantity: int = 0
    average_price: float = 0.0
    tag: str | None = None
    created_at: datetime | None = None
    # Option identity (P3-4.3).
    strike: float | None = None
    expiry: str | None = None
    option_type: str | None = None
    lot_size: int | None = None
    # Trade context from the originating proposal (P3-4.3).
    stop_loss: float | None = None
    target: float | None = None
    rationale: str | None = None
    confidence: float | None = None


class CancelOrderResponse(BaseModel):
    """Outcome of an order cancellation request (Phase 4)."""
    order_id: str
    cancelled: bool
    status: str = ""  # CANCELLED on success; terminal state on failure
    message: str = ""


class PositionHistoryItem(BaseModel):
    """One closed position reconstructed from ledger fills (Phase 4).

    Produced by FIFO-pairing opposite-side fills per symbol (entry/exit).
    Only fully paired (closed) fills appear — open remainder stays hidden.
    """
    symbol: str
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 0
    realized_pnl: float = 0.0
    opened_at: datetime | None = None
    closed_at: datetime | None = None


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


class ScannerFindingResponse(BaseModel):
    scanner_type: str  # e.g. gamma_spike, gap_fill, etc.
    symbol: str
    severity: str  # LOW / MEDIUM / HIGH
    detail: dict = {}
    timestamp: datetime | None = None


# ── Health ─────────────────────────────────────────────────────────────────
class ComponentHealth(BaseModel):
    name: str
    status: str  # healthy / stale / disconnected / token_expired / down
    latency_ms: float | None = None
    last_check: datetime | None = None
    message: str = ""


class HealthResponse(BaseModel):
    components: list[ComponentHealth] = []
    overall: str = "healthy"  # healthy / degraded / down (aggregate severity)
    # P1-2.4: unified connection state from the state machine.
    state: str = "unknown"  # connected / connecting / stale / expired / disconnected / unknown
    detail: str = ""


class SessionResponse(BaseModel):
    status: str  # pre_open / open / post_close / closed
    current_time_ist: str = ""
    next_event: str = ""
    next_event_time: str = ""


# ── Postback ─────────────────────────────────────────────────────────────
class PostbackResponse(BaseModel):
    status: str


# ── Learning ──────────────────────────────────────────────────────────────
class CalibrationPointResponse(BaseModel):
    conviction_bin: list[float]  # [low, high]
    actual_win_rate: float
    sample_size: int
    confidence_interval: list[float]  # [low, high]


class CalibrationResponse(BaseModel):
    reliable: bool
    points: list[CalibrationPointResponse] = []


class ShadowStatusItem(BaseModel):
    name: str
    sessions: int
    evaluated: int
    hit_rate: float
    graduated: bool
    registered: bool


class ShadowStatusResponse(BaseModel):
    shadows: list[ShadowStatusItem] = []


# ── Research ───────────────────────────────────────────────────────────────
class ResearchBriefResponse(BaseModel):
    brief_id: str
    lens: str
    as_of: str
    instruments: list[str] = []
    direction: int
    confidence: float
    thesis: str
    rationale: str
    evidence: list[dict] = []
    risks: list[str] = []
    validity_window_minutes: int
    status: str
    outcome: str | None = None
    decided_at: str | None = None
    regime_at_decision: str | None = None
    expired: bool = False


class LensInfoResponse(BaseModel):
    name: str
    description: str


class LensListResponse(BaseModel):
    lenses: list[LensInfoResponse] = []


class ResearchRunRequest(BaseModel):
    lenses: list[str] | None = None
    context: dict[str, str] | None = None
    tools: list[str] | None = None


class ResearchRunItem(BaseModel):
    lens: str
    brief: ResearchBriefResponse | None = None
    error: str | None = None


class ResearchRunResponse(BaseModel):
    results: list[ResearchRunItem] = []


class ResearchBriefListResponse(BaseModel):
    briefs: list[ResearchBriefResponse] = []


class ResearchDecisionResponse(BaseModel):
    brief_id: str
    status: str


class ResearchToolResponse(BaseModel):
    name: str
    description: str
    params_schema: dict = {}


class ResearchToolsResponse(BaseModel):
    tools: list[ResearchToolResponse] = []


class ResearchSchedulerResponse(BaseModel):
    enabled: bool = False
    interval_minutes: float = 60.0
    lenses: list[str] | None = None
    tools: list[str] | None = None
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_result: str | None = None


class ResearchOutcomeRequest(BaseModel):
    # str, not Literal: the store validates and the router maps the
    # resulting ValueError to the spec'd 400 (FastAPI would 422 otherwise).
    outcome: str


class ResearchOutcomeResponse(BaseModel):
    brief_id: str
    outcome: str


class ResearchScoringItem(BaseModel):
    lens: str
    total: int
    decided: int
    with_outcome: int
    win_rate: float
    avg_confidence: float


class ResearchScoringResponse(BaseModel):
    lenses: list[ResearchScoringItem] = []


# ── Options summary ───────────────────────────────────────────────────────
class ExpiryCalendarItem(BaseModel):
    date: str            # ISO date YYYY-MM-DD
    kind: str            # "weekly" | "monthly"


class ExpiryCalendarResponse(BaseModel):
    symbol: str
    instrument_type: str   # OPTION / FUTURES
    expiries: list[ExpiryCalendarItem] = []
    default: str | None = None   # ISO date of the policy-selected default


class OptionsSummaryResponse(BaseModel):
    underlying: str
    max_pain: float | None = None
    pcr: float | None = None
    iv_rank_percent: float | None = None
    iv_classification: str | None = None  # LOW / NORMAL / HIGH
