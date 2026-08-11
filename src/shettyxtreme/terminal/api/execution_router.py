"""Execution router — positions, risk, mode, kill switch, proposals."""
from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from shettyxtreme.core.settings import get_settings_store
from shettyxtreme.execution.kill_switch import KillSwitchGate
from shettyxtreme.terminal.api.models import (
    KillSwitchResponse,
    ModeResponse,
    PositionResponse,
    ProposalResponse,
    RiskResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/execution", tags=["execution"])

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
    return ProposalResponse(
        id=approval.id,
        symbol=str(hint.get("symbol", "")),
        exchange=str(hint.get("exchange", "NSE")),
        side=side,
        quantity=int(hint.get("quantity", 0)),
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
    )


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions(request: Request) -> list[PositionResponse]:
    """Return all active positions with MTM."""
    positions = request.app.state.position_projection.get()
    return [
        PositionResponse(
            symbol=p.get("symbol", ""),
            exchange=p.get("exchange", "NSE"),
            quantity=p.get("quantity", 0),
            buy_avg=p.get("buy_avg", 0.0),
            net_quantity=p.get("net_quantity", 0),
            m2m=p.get("m2m", 0.0),
            pnl=p.get("pnl", 0.0),
            product=p.get("product", "NRML"),
        )
        for p in positions
    ]


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
