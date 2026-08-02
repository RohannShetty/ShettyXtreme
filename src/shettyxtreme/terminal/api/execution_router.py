"""Execution router — positions, risk, mode, kill switch, proposals."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from shettyxtreme.terminal.api.models import (
    KillSwitchResponse,
    ModeResponse,
    PositionResponse,
    ProposalResponse,
    RiskResponse,
)

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
_kill_switch_path: str = ""


def get_mode_value() -> str:
    """Current execution mode (OBSERVER / PAPER / LIVE)."""
    return _current_mode


def is_kill_switch_armed() -> bool:
    """True when the file-based kill switch is armed (blocks placement)."""
    return bool(_kill_switch_path) and os.path.exists(_kill_switch_path)


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
    loss_limit = risk.get("loss_limit", -5000.0)
    return RiskResponse(
        daily_pnl=daily_pnl,
        margin_used=risk.get("margin_used", 0.0),
        margin_available=risk.get("margin_available", 500000.0),
        loss_limit=loss_limit,
        loss_limit_hit=daily_pnl < loss_limit,
        max_positions=risk.get("max_positions", 5),
        active_positions=active_positions,
    )


@router.get("/mode", response_model=ModeResponse)
async def get_mode() -> ModeResponse:
    """Return current execution mode."""
    return ModeResponse(mode=_current_mode)


@router.post("/mode", response_model=ModeResponse)
async def set_mode(request: Request, mode: str, confirm: bool = False) -> ModeResponse:
    """Switch execution mode. Valid modes: OBSERVER, LIVE, PAPER.

    LIVE requires explicit per-session confirmation (confirm=true, D10).
    """
    global _current_mode
    valid = {"OBSERVER", "LIVE", "PAPER"}
    requested = mode.upper()
    if requested not in valid:
        return ModeResponse(mode=_current_mode)
    if requested == "LIVE" and not confirm:
        return ModeResponse(mode=_current_mode)
    _current_mode = requested
    _save_mode(_current_mode)
    # Publish config changed event
    try:
        bus = request.app.state.event_bus
        if bus:
            from shettyxtreme.core.event_bus.event_bus import Event, Topic
            await bus.publish(Event(Topic.CONFIG_CHANGED, {"mode": _current_mode}, source="execution_router"))
    except Exception:
        pass
    return ModeResponse(mode=_current_mode)


@router.get("/kill-switch", response_model=KillSwitchResponse)
async def get_kill_switch() -> KillSwitchResponse:
    """Check kill switch status."""
    active = False
    if _kill_switch_path and os.path.exists(_kill_switch_path):
        active = True
    return KillSwitchResponse(active=active, activated_at=datetime.now(UTC) if active else None)


@router.post("/kill-switch", response_model=KillSwitchResponse)
async def activate_kill_switch(activate: bool = True) -> KillSwitchResponse:
    """Activate or deactivate the kill switch.

    Creates or removes a file-based kill switch indicator.
    """
    global _kill_switch_path
    if not _kill_switch_path:
        _kill_switch_path = str(Path.home() / ".shetty_kill_switch")

    if activate:
        Path(_kill_switch_path).touch()
        return KillSwitchResponse(active=True, activated_at=datetime.now(UTC))
    else:
        Path(_kill_switch_path).unlink(missing_ok=True)
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

    OBSERVER never places; LIVE requires an explicit confirm=true on top of
    the mode-switch gate; an armed kill switch blocks placement.
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
    if mode == "LIVE" and not confirm:
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
