"""Execution router — positions, risk, mode, kill switch, proposals."""
from __future__ import annotations

import logging
import secrets
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from shettyxtreme.core.settings import get_settings_store
from shettyxtreme.execution.kill_switch import KillSwitchGate
from shettyxtreme.terminal.api.models import (
    GreeksBreakdownItem,
    GreeksConcentrationItem,
    KillSwitchResponse,
    MarginUtilizationItem,
    ModeResponse,
    OrderResponse,
    PortfolioGreeksResponse,
    PositionGreeks,
    PositionResponse,
    ProposalResponse,
    RiskHeatmapResponse,
    RiskResponse,
    ScenarioPnlItem,
    SectorExposureItem,
    StressItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/execution", tags=["execution"])

# ── IV snapshot cache for per-position greeks ──────────────────────────────
# Populated by the intelligence router's chain enrichment on each
# GET /api/intelligence/options request.  Keyed by (strike, option_type).
# Only the freshest snapshot per key is kept (overwritten on every chain poll).
_iv_cache: dict[tuple[float, str], float] = {}
_last_spot: float | None = None

_SECONDS_PER_YEAR = 365.25 * 24 * 3600
_MIN_TTE = 1 / 365


def update_iv_cache(
    contracts: list[dict[str, Any]],
    spot: float | None = None,
) -> None:
    """Update the module-level IV cache from an enriched chain response.

    Called by the intelligence router after _enrich_chain fills
    OptionsChainItem rows so the execution router can compute per-position
    greeks even though the chain poll and position poll are independent.
    """
    global _last_spot
    if spot is not None:
        _last_spot = spot
    for c in contracts:
        strike = c.get("strike") if isinstance(c, dict) else getattr(c, "strike", None)
        option_type = c.get("option_type") if isinstance(c, dict) else getattr(c, "option_type", None)
        iv = c.get("iv") if isinstance(c, dict) else getattr(c, "iv", None)
        if strike is not None and option_type and iv is not None:
            try:
                iv_f = float(iv)
                if iv_f > 0:
                    _iv_cache[(float(strike), str(option_type).upper())] = iv_f
            except (TypeError, ValueError):
                pass

def _compute_position_greeks(
    strike: float,
    option_type: str,
    expiry: date | None,
    net_quantity: int,
) -> PositionGreeks | None:
    """Compute per-position greeks from option identity + IV cache.

    Returns None when IV or spot are unavailable (greeks unknown).
    """
    from shettyxtreme.options.greeks import GreeksCalculator

    iv = _iv_cache.get((strike, option_type.upper()))
    if iv is None or iv <= 0:
        return None
    if _last_spot is None or _last_spot <= 0:
        return None
    if expiry is None:
        return None

    # Compute TTE from expiry date
    try:
        expiry_dt = datetime(
            expiry.year, expiry.month, expiry.day,
            15, 30,  # 15:30 IST market close
        )
        now = datetime.now()
        tte = (expiry_dt - now).total_seconds() / _SECONDS_PER_YEAR
        tte = max(tte, _MIN_TTE)
    except (TypeError, ValueError):
        return None

    calc = GreeksCalculator(use_quantlib=False)
    opt = "CALL" if option_type.upper() == "CE" else "PUT"
    try:
        greeks = calc.calculate_all(
            spot=_last_spot,
            strike=strike,
            tte=tte,
            iv=iv,
            option_type=opt,
        )
    except Exception:
        return None

    qty = float(net_quantity)
    return PositionGreeks(
        delta=qty * greeks.get("delta", 0.0),
        gamma=qty * greeks.get("gamma", 0.0),
        theta=qty * greeks.get("theta", 0.0),
        vega=qty * greeks.get("vega", 0.0),
    )


def _enrich_position(raw: dict[str, Any]) -> PositionResponse:
    """Build a PositionResponse, deriving option identity and greeks."""
    symbol = raw.get("symbol", "")
    exchange = raw.get("exchange", "NSE")
    net_qty = raw.get("net_quantity", 0)

    # Try to parse option identity from the Fyers symbol
    strike: float | None = None
    option_type: str | None = None
    expiry: date | None = None
    instrument_type: str | None = None
    try:
        from shettyxtreme.integration.fyers.symbols import from_fyers
        parsed = from_fyers(symbol)
        instrument_type = parsed.get("instrument_type")
        if instrument_type == "OPTION":
            strike = parsed.get("strike")
            option_type = parsed.get("option_type")
            expiry = parsed.get("expiry")
    except (ValueError, ImportError):
        pass

    greeks: PositionGreeks | None = None
    if strike is not None and option_type and expiry:
        greeks = _compute_position_greeks(strike, option_type, expiry, net_qty)

    # P3-4.3: carry trade context from the fill event / position projection.
    # These fields are populated when the paper engine emits POSITION_CHANGED
    # with signal_id / stop_loss / target / rationale / confidence / lot_size.
    return PositionResponse(
        symbol=symbol,
        exchange=exchange,
        quantity=raw.get("quantity", 0),
        buy_avg=raw.get("buy_avg", 0.0),
        net_quantity=net_qty,
        m2m=raw.get("m2m", 0.0),
        pnl=raw.get("pnl", 0.0),
        product=raw.get("product", "NRML"),
        strike=strike,
        option_type=option_type,
        expiry=expiry.isoformat() if expiry else None,
        instrument_type=instrument_type,
        greeks=greeks,
        # Trade context from the originating proposal (P3-4.3).
        stop_loss=raw.get("stop_loss"),
        target=raw.get("target"),
        rationale=raw.get("rationale"),
        confidence=raw.get("confidence"),
        signal_id=raw.get("signal_id"),
        lot_size=raw.get("lot_size"),
    )


_MODE_FILE = Path.home() / ".shettyxtreme_mode"

def _load_mode() -> str:
    """Restore the persisted mode. LIVE never auto-restores: it is an
    explicit per-session action with confirmation (D10)."""
    try:
        if _MODE_FILE.exists():
            saved = _MODE_FILE.read_text().strip()
            if saved in ("OBSERVER", "PAPER"):
                return saved
    except Exception:
        pass
    return "OBSERVER"

def _save_mode(mode: str) -> None:
    try:
        _MODE_FILE.write_text(mode)
    except Exception:
        pass

_current_mode: str = _load_mode()
# Initialized at import time (not lazily in activate_kill_switch) so a kill
# switch armed by a previous process is honored across restarts.
_kill_switch_path: str = str(Path.home() / ".shetty_kill_switch")
# Per-session CSRF token, minted only when LIVE mode is activated with the
# typed confirmation. Required (X-CSRF-Token header) on LIVE placements so a
# bare form post / boolean query flag can never place a real order (F-EXEC-001).
_csrf_token: str | None = None

# Shared in-process kill gate (Phase 6 Lane B): an asyncio.Event that is set
# on arm and re-checked by the mode router immediately before the broker wire,
# closing the check-to-wire TOCTOU window of the file-only switch. The file
# remains the durable, cross-process layer (restart survival); the event is
# the fast in-process layer. Rebuilt lazily when the path changes (tests).
_kill_gate: KillSwitchGate | None = None


def _get_kill_gate() -> KillSwitchGate:
    """The shared gate for the current _kill_switch_path, rebuilt on change."""
    global _kill_gate
    if _kill_gate is None or _kill_gate.path != _kill_switch_path:
        _kill_gate = KillSwitchGate(_kill_switch_path)
    return _kill_gate


def get_kill_switch_gate() -> KillSwitchGate:
    """Shared in-process kill gate (asyncio.Event + atomic file persistence).

    Wired into ModeRoutingExecutor at app startup so placements double-check
    the gate immediately before reaching the broker.
    """
    return _get_kill_gate()


def get_mode_value() -> str:
    """Current execution mode (OBSERVER / PAPER / LIVE)."""
    return _current_mode


def is_kill_switch_armed() -> bool:
    """True when the kill switch is armed (blocks placement).

    Delegates to the shared gate: armed when EITHER the in-process event is
    set or the persisted file exists (honors a switch armed by another
    process, and an API arm that hasn't finished writing the file).
    """
    return _get_kill_gate().is_armed()


def _mint_csrf_token() -> str:
    """Mint a fresh per-session CSRF token (LIVE activation only)."""
    global _csrf_token
    _csrf_token = secrets.token_urlsafe(32)
    return _csrf_token


def _clear_csrf_token() -> None:
    """Invalidate the CSRF token when the LIVE session ends."""
    global _csrf_token
    _csrf_token = None


def get_csrf_token() -> str | None:
    """Current per-session CSRF token, or None outside a LIVE session."""
    return _csrf_token


def _require_csrf_token(request: Request) -> None:
    """LIVE placements must carry the per-session CSRF token (X-CSRF-Token).

    The token is minted when the operator types the LIVE confirmation, so a
    CSRF'd form post (which cannot set custom headers) can never place a real
    broker order (F-EXEC-001).
    """
    expected = _csrf_token
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="no CSRF token issued - activate LIVE mode with typed confirmation first",
        )
    supplied = request.headers.get("x-csrf-token")
    if not supplied or supplied != expected:
        raise HTTPException(
            status_code=403,
            detail="invalid or missing X-CSRF-Token header",
        )


def _engine(request: Request) -> Any | None:
    return getattr(request.app.state, "execution_engine", None)


def _enum_str(value: Any) -> str:
    """Coerce an enum-or-str value to its plain string form."""
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else str(value)


def _proposal_response(approval: Any) -> ProposalResponse:
    """Serialize a PendingApproval into the API response model."""
    hint: dict[str, Any] = approval.strategy_hint or {}
    direction = str(approval.signal.direction.name).upper()
    side = "BUY" if direction == "UP" else "SELL" if direction == "DOWN" else "NEUTRAL"
    lot_size = hint.get("lot_size")
    quantity = hint.get("quantity") or 0
    quantity = int(quantity)
    lots = hint.get("lots")
    if lots is None and lot_size and lot_size > 0 and quantity > 0:
        lots = quantity // lot_size
    return ProposalResponse(
        id=approval.id,
        symbol=str(hint.get("symbol", "")),
        exchange=str(hint.get("exchange", "NSE")),
        side=side,
        quantity=quantity,
        price=hint.get("price"),
        order_type=_enum_str(hint.get("order_type")) or "MARKET",
        product=_enum_str(hint.get("product")) or "MIS",
        conviction=approval.signal.conviction,
        D=approval.signal.D,
        P=approval.signal.P,
        G=str(approval.signal.G),
        source="signal_v2",
        hint_kind=str(hint.get("hint_kind", "default")),
        signal_id=approval.signal_id,
        status=approval.status,
        reason=approval.failure_reason or "",
        timestamp=approval.timestamp,
        strike=hint.get("strike"),
        expiry=hint.get("expiry"),
        option_type=hint.get("option_type"),
        lot_size=lot_size,
        lots=lots,
        entry_premium=hint.get("entry_premium"),
        stop_loss=hint.get("stop_loss"),
        target=hint.get("target"),
        rationale=hint.get("rationale"),
        # Enriched fields (P3-4.3): strategy context from chain hint builder.
        confidence=hint.get("confidence"),
        ev_after_cost=hint.get("ev_after_cost"),
        strategy=hint.get("strategy"),
        underlying=hint.get("underlying"),
    )


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions(request: Request) -> list[PositionResponse]:
    """Return all active positions with MTM and per-position greeks."""
    positions = request.app.state.position_projection.get()
    return [_enrich_position(p) for p in positions]


@router.get("/risk", response_model=RiskResponse)
async def get_risk(request: Request) -> RiskResponse:
    """Return risk summary."""
    risk = request.app.state.risk_projection.get()
    positions = request.app.state.position_projection.get()
    active_positions = sum(1 for p in positions if abs(p.get("net_quantity", 0)) > 0)
    daily_pnl = risk.get("daily_pnl", 0.0)
    # Risk caps default to the shared settings store (P7-W3); the projection
    # state carries the live values published by the risk bridge.
    loss_limit = risk.get("loss_limit", get_settings_store().loss_limit())
    return RiskResponse(
        daily_pnl=daily_pnl,
        margin_used=risk.get("margin_used", 0.0),
        # Honest no-data state: None (serialized as null), never a fabricated
        # default that implies margin the account may not have (fix #2).
        margin_available=risk.get("margin_available"),
        loss_limit=loss_limit,
        loss_limit_hit=daily_pnl < loss_limit,
        max_positions=risk.get("max_positions", get_settings_store().max_positions()),
        active_positions=active_positions,
    )


@router.get("/portfolio-greeks", response_model=PortfolioGreeksResponse)
async def get_portfolio_greeks(request: Request) -> PortfolioGreeksResponse:
    """Return aggregate portfolio greeks across all open option positions."""
    positions_raw = request.app.state.position_projection.get()
    enriched = [_enrich_position(p) for p in positions_raw]
    net_delta = sum(p.greeks.delta for p in enriched if p.greeks)
    net_gamma = sum(p.greeks.gamma for p in enriched if p.greeks)
    net_theta = sum(p.greeks.theta for p in enriched if p.greeks)
    net_vega = sum(p.greeks.vega for p in enriched if p.greeks)
    return PortfolioGreeksResponse(
        net_delta=net_delta,
        net_gamma=net_gamma,
        net_theta=net_theta,
        net_vega=net_vega,
        positions=enriched,
    )


@router.get("/greeks-history")
async def get_greeks_history(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    regime: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Return recorded portfolio greeks snapshots for charting (3A.4).

    Entries: ``{timestamp, net_delta, net_gamma, net_theta, net_vega,
    position_count}``, oldest first, covering the last ``days`` days.
    Returns an empty list when the greeks store is not initialized.

    Phase 3C.1: when ``regime`` is supplied, snapshots are filtered to
    periods where that regime was active (joined against analytics store
    regime history).
    """
    store = getattr(request.app.state, "greeks_store", None)
    if store is None:
        return []
    try:
        rows = store.get_history(days=days)
    except Exception:
        logger.exception("greeks-history read failed")
        return []

    if not regime:
        return rows

    analytics_store = getattr(request.app.state, "analytics_store", None)
    if analytics_store is None or not hasattr(analytics_store, "get_regime_history"):
        return []
    try:
        regime_history = analytics_store.get_regime_history(days=days)
    except Exception:
        logger.exception("regime history read failed for greeks filter")
        return []

    if not regime_history:
        return []

    # Map each greeks snapshot to the regime active at that timestamp.
    def active_at(ts: str) -> str | None:
        active: str | None = None
        for r in regime_history:
            if r["timestamp"] <= ts:
                active = r["regime"]
            else:
                break
        return active

    filtered = [row for row in rows if active_at(row["timestamp"]) == regime]
    return filtered


@router.get("/risk/heatmap", response_model=RiskHeatmapResponse)
async def get_risk_heatmap(request: Request) -> RiskHeatmapResponse:
    """Return risk heat map — all 4 dimensions.

    Missing data degrades to empty/None — never faked (honesty rule).
    """
    from shettyxtreme.intelligence.risk.portfolio_risk import (
        PortfolioRiskAggregator,
        GreeksBreakdown as _GB,
        GreeksConcentration as _GC,
        HeatMapResult,
        MarginUtilization as _MU,
        ScenarioPnl as _SP,
        StressResult as _SR,
    )

    positions_raw = request.app.state.position_projection.get()

    # Gather spot map from watchlist projection
    spot_map: dict[str, float] = {}
    watchlist = getattr(request.app.state, "watchlist_projection", None)
    if watchlist is not None:
        for sym, item in watchlist.get().items():
            ltp = item.get("ltp", 0.0)
            if ltp and ltp > 0:
                spot_map[sym] = ltp

    # Gather IV map from execution router's module-level cache
    iv_map = dict(_iv_cache)

    # Gather margin from risk projection
    risk_proj = getattr(request.app.state, "risk_projection", None)
    margin_data: dict[str, object] = {}
    if risk_proj is not None:
        risk_state = risk_proj.get()
        if risk_state.get("margin_used"):
            margin_data["utilized"] = risk_state["margin_used"]
        if risk_state.get("margin_available") is not None:
            margin_data["available"] = risk_state["margin_available"]

    # Get instrument master from app state (injected)
    instrument_master = getattr(request.app.state, "instrument_master", None)

    aggregator = PortfolioRiskAggregator(instrument_lookup=instrument_master)
    result = aggregator.compute(
        positions=positions_raw,
        spot_map=spot_map,
        iv_map=iv_map,
        margin=margin_data,
    )

    # Convert dataclass result to response models
    return RiskHeatmapResponse(
        sector_exposure=[
            SectorExposureItem(
                sector=s.sector,
                notional=s.notional,
                pnl=s.pnl,
                share_pct=s.share_pct,
            )
            for s in result.sector_exposure
        ],
        greeks=GreeksConcentrationItem(
            delta=GreeksBreakdownItem(
                long_val=result.greeks.delta.long,
                short_val=result.greeks.delta.short,
                net=result.greeks.delta.net,
            ),
            gamma=GreeksBreakdownItem(
                long_val=result.greeks.gamma.long,
                short_val=result.greeks.gamma.short,
                net=result.greeks.gamma.net,
            ),
            theta=GreeksBreakdownItem(
                long_val=result.greeks.theta.long,
                short_val=result.greeks.theta.short,
                net=result.greeks.theta.net,
            ),
            vega=GreeksBreakdownItem(
                long_val=result.greeks.vega.long,
                short_val=result.greeks.vega.short,
                net=result.greeks.vega.net,
            ),
            lopsided_warning=result.greeks.lopsided_warning,
        ),
        stress=StressItem(
            scenarios=[
                ScenarioPnlItem(shift_pct=s.shift_pct, total_pnl=s.total_pnl)
                for s in result.stress.scenarios
            ],
            worst_case_pnl=result.stress.worst_case_pnl,
            worst_case_shift=result.stress.worst_case_shift,
        ),
        margin=MarginUtilizationItem(
            margin_used=result.margin.margin_used,
            margin_available=result.margin.margin_available,
            total=result.margin.total,
            utilization_pct=result.margin.utilization_pct,
            breach=result.margin.breach,
        ),
        position_count=result.position_count,
        enriched_count=result.enriched_count,
    )


@router.get("/mode", response_model=ModeResponse)
async def get_mode() -> ModeResponse:
    """Return current execution mode (+ per-session CSRF token, if any)."""
    return ModeResponse(mode=_current_mode, csrf_token=get_csrf_token())


class ModeSwitchRequest(BaseModel):
    """Typed confirmation carried in the request body (never a query flag)."""

    confirm: str | None = None


@router.post("/mode", response_model=ModeResponse)
async def set_mode(
    request: Request,
    mode: str,
    confirm: bool = False,  # legacy query flag; kept for non-LIVE backward compat
    payload: ModeSwitchRequest | None = None,
) -> ModeResponse:
    """Switch execution mode. Valid modes: OBSERVER, LIVE, PAPER.

    LIVE requires typed per-session confirmation (D10): the string "LIVE"
    must be sent in the request body. A boolean query flag (confirm=true)
    never arms LIVE (F-EXEC-001). OBSERVER/PAPER keep the legacy query
    behavior and need no confirmation.
    """
    global _current_mode
    valid = {"OBSERVER", "LIVE", "PAPER"}
    requested = mode.upper()
    if requested not in valid:
        return ModeResponse(mode=_current_mode)
    if requested == "LIVE":
        typed = (payload.confirm if payload else None) or ""
        if typed != "LIVE":
            raise HTTPException(
                status_code=400,
                detail="LIVE mode requires typed confirmation: send {\"confirm\": \"LIVE\"} in the request body",
            )
    previous = _current_mode
    _current_mode = requested
    _save_mode(_current_mode)
    if requested == "LIVE":
        _mint_csrf_token()
    elif previous == "LIVE":
        # Leaving LIVE invalidates the per-session CSRF token (D10).
        _clear_csrf_token()
    # Publish config changed event
    try:
        bus = request.app.state.event_bus
        if bus:
            from shettyxtreme.core.event_bus.event_bus import Event, Topic
            await bus.publish(Event(Topic.CONFIG_CHANGED, {"mode": _current_mode}, source="execution_router"))
    except Exception:
        pass
    return ModeResponse(mode=_current_mode, csrf_token=get_csrf_token())


@router.get("/kill-switch", response_model=KillSwitchResponse)
async def get_kill_switch() -> KillSwitchResponse:
    """Check kill switch status."""
    active = is_kill_switch_armed()
    return KillSwitchResponse(active=active, activated_at=datetime.now(UTC) if active else None)


class KillSwitchRequest(BaseModel):
    """Typed confirmation for the kill-switch disarm (D10 parity)."""

    confirm: str | None = None


@router.post("/kill-switch", response_model=KillSwitchResponse)
async def activate_kill_switch(
    activate: bool = True,
    payload: KillSwitchRequest | None = None,
) -> KillSwitchResponse:
    """Activate or deactivate the kill switch.

    Arming stays a single click (activate=true). Disarming (activate=false)
    requires the typed confirmation string "DISARM" in the request body —
    same rule as LIVE mode (F-EXEC-001).

    Both layers of the shared gate are updated: the file atomically
    (tempfile + os.replace) for cross-process persistence/restart survival,
    and the in-process asyncio.Event so the mode router sees the arm the
    instant it happens. The arm response reports how many placements had
    already crossed the wire in the arm window ("placed just before kill").
    """
    global _kill_switch_path
    if not _kill_switch_path:
        _kill_switch_path = str(Path.home() / ".shetty_kill_switch")

    if activate:
        gate = _get_kill_gate()
        gate.arm()
        report = gate.arm_report
        in_flight = report["placements_in_flight"]
        if in_flight:
            logger.warning(
                "kill switch armed with %d placement(s) already in flight — "
                "crossed the wire during the arm window (placed just before kill)",
                in_flight,
            )
        else:
            logger.info("kill switch armed")
        return KillSwitchResponse(
            active=True,
            activated_at=datetime.now(UTC),
            placements_in_flight=in_flight,
        )
    typed = (payload.confirm if payload else None) or ""
    if typed != "DISARM":
        raise HTTPException(
            status_code=400,
            detail="disarming the kill switch requires typed confirmation: send {\"confirm\": \"DISARM\"} in the request body",
        )
    _get_kill_gate().disarm()
    return KillSwitchResponse(active=False)


# ── Proposals (OBSERVER propose→approve flow, D10) ─────────────────────────

@router.get("/proposals", response_model=list[ProposalResponse])
async def list_proposals(request: Request, status: str | None = None) -> list[ProposalResponse]:
    """List proposals; optional status filter (PENDING/APPROVED/REJECTED/EXPIRED)."""
    engine = _engine(request)
    if engine is None:
        return []
    engine.expire_stale()
    approvals = engine.get_all_approvals()
    if status:
        wanted = status.upper()
        approvals = [a for a in approvals if a.status == wanted]
    return [_proposal_response(a) for a in approvals]


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalResponse)
async def approve_proposal(
    request: Request,
    proposal_id: str,
    confirm: bool = False,
) -> ProposalResponse:
    """Approve a proposal: risk check → validate → route per mode (D10).

    OBSERVER never places; LIVE requires the per-session CSRF token (minted
    by typed LIVE activation) plus explicit confirm=true; an armed kill
    switch blocks placement.
    """
    engine = _engine(request)
    if engine is None:
        raise HTTPException(status_code=503, detail="execution engine not initialized")
    mode = get_mode_value()
    if mode == "OBSERVER":
        raise HTTPException(
            status_code=400,
            detail="OBSERVER mode never places orders - switch to PAPER or LIVE",
        )
    if mode == "LIVE":
        _require_csrf_token(request)
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="LIVE placement requires explicit confirmation (confirm=true)",
            )
    if is_kill_switch_armed():
        raise HTTPException(status_code=400, detail="kill switch armed - placement blocked")
    try:
        await engine.approve(proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    approval = engine.get_approval(proposal_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"unknown proposal: {proposal_id}")
    return _proposal_response(approval)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
async def reject_proposal(
    request: Request,
    proposal_id: str,
    reason: str = "",
) -> ProposalResponse:
    """Reject a proposal; no order is placed."""
    engine = _engine(request)
    if engine is None:
        raise HTTPException(status_code=503, detail="execution engine not initialized")
    try:
        engine.reject(proposal_id, reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    approval = engine.get_approval(proposal_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"unknown proposal: {proposal_id}")
    return _proposal_response(approval)


# ── Order History (P3-4.3) ─────────────────────────────────────────────────

def _order_response(order: Any) -> OrderResponse:
    """Serialize a paper-engine Order into the API response model."""
    return OrderResponse(
        order_id=order.order_id,
        symbol=order.symbol,
        exchange=order.exchange,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        price=order.price,
        status=order.status,
        filled_quantity=order.filled_quantity,
        average_price=order.average_price,
        tag=order.tag,
        created_at=order.created_at,
        # Option identity + trade context (P3-4.3).
        strike=getattr(order, "strike", None),
        expiry=getattr(order, "expiry", None),
        option_type=getattr(order, "option_type", None),
        lot_size=getattr(order, "lot_size", None),
        stop_loss=getattr(order, "stop_loss", None),
        target=getattr(order, "target", None),
        rationale=getattr(order, "rationale", None),
        confidence=getattr(order, "confidence", None),
    )


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    request: Request,
    status: str | None = None,
) -> list[OrderResponse]:
    """Return the order book from the paper trading engine.

    Optional ``status`` filter: FILLED, REJECTED, CANCELLED, OPEN,
    PARTIALLY_FILLED.  Returns all orders when omitted.
    """
    paper = getattr(request.app.state, "paper_engine", None)
    if paper is None:
        return []
    orders = paper.get_order_book()
    if status:
        wanted = status.upper()
        orders = [o for o in orders if o.status == wanted]
    # Newest first.
    orders = sorted(orders, key=lambda o: o.created_at, reverse=True)
    return [_order_response(o) for o in orders]
