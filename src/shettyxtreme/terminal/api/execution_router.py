"""Execution router — positions, risk, mode, kill switch."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from shettyxtreme.terminal.api.models import (
    KillSwitchResponse,
    ModeResponse,
    PositionResponse,
    RiskResponse,
)

router = APIRouter(prefix="/api/execution", tags=["execution"])

# ── In-memory state ────────────────────────────────────────────────────────
_positions: list[dict[str, Any]] = []
_current_mode: str = "OBSERVER"
_kill_switch_path: str = ""

# ── Risk state ─────────────────────────────────────────────────────────────
_risk_state: dict[str, Any] = {
    "daily_pnl": 0.0,
    "margin_used": 0.0,
    "margin_available": 500000.0,
    "loss_limit": -5000.0,
    "max_positions": 5,
}


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions() -> list[PositionResponse]:
    """Return all active positions with MTM."""
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
        for p in _positions
    ]


@router.get("/risk", response_model=RiskResponse)
async def get_risk() -> RiskResponse:
    """Return risk summary."""
    active_positions = sum(1 for p in _positions if abs(p.get("net_quantity", 0)) > 0)
    return RiskResponse(
        daily_pnl=_risk_state.get("daily_pnl", 0.0),
        margin_used=_risk_state.get("margin_used", 0.0),
        margin_available=_risk_state.get("margin_available", 500000.0),
        loss_limit=_risk_state.get("loss_limit", -5000.0),
        loss_limit_hit=_risk_state.get("daily_pnl", 0.0) < _risk_state.get("loss_limit", -5000.0),
        max_positions=_risk_state.get("max_positions", 5),
        active_positions=active_positions,
    )


@router.get("/mode", response_model=ModeResponse)
async def get_mode() -> ModeResponse:
    """Return current execution mode."""
    return ModeResponse(mode=_current_mode)


@router.post("/mode", response_model=ModeResponse)
async def set_mode(mode: str) -> ModeResponse:
    """Switch execution mode.

    Valid modes: OBSERVER, LIVE, PAPER
    """
    global _current_mode
    valid = {"OBSERVER", "LIVE", "PAPER"}
    if mode.upper() in valid:
        _current_mode = mode.upper()
    return ModeResponse(mode=_current_mode)


@router.get("/kill-switch", response_model=KillSwitchResponse)
async def get_kill_switch() -> KillSwitchResponse:
    """Check kill switch status."""
    active = False
    if _kill_switch_path and os.path.exists(_kill_switch_path):
        active = True
    return KillSwitchResponse(active=active, activated_at=datetime.now(timezone.utc) if active else None)


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
        return KillSwitchResponse(active=True, activated_at=datetime.now(timezone.utc))
    else:
        Path(_kill_switch_path).unlink(missing_ok=True)
        return KillSwitchResponse(active=False)
