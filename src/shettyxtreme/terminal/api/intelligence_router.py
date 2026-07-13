"""Intelligence router — regime, signal, voters, options, strategy hints."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Query

from shettyxtreme.intelligence.options import (
    compute_signal_drift_ev,
    pcr_signal,
    select_expiry,
)
from shettyxtreme.terminal.api.models import (
    OptionsChainItem,
    OptionsChainResponse,
    RegimeResponse,
    SignalResponse,
    StrategyHintResponse,
    VoterBreakdown,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

# In-memory state (connected to real engine in production)
_current_regime: dict[str, Any] = {
    "regime": "range_bound",
    "confidence": 0.5,
    "transition": False,
    "adx": 18.0,
    "di_plus": 12.0,
    "di_minus": 14.0,
}

_current_signal: dict[str, Any] = {
    "direction": "NEUTRAL",
    "conviction": 0.0,
    "D": 0.0,
    "P": 0.0,
    "G": 0.0,
    "voters": [],
    "timestamp": datetime.utcnow(),
}


@router.get("/regime", response_model=RegimeResponse)
async def get_regime() -> RegimeResponse:
    """Return current market regime classification."""
    return RegimeResponse(
        regime=_current_regime.get("regime", "range_bound"),
        confidence=_current_regime.get("confidence", 0.5),
        transition=_current_regime.get("transition", False),
        adx=_current_regime.get("adx"),
        di_plus=_current_regime.get("di_plus"),
        di_minus=_current_regime.get("di_minus"),
    )


@router.get("/signal", response_model=SignalResponse)
async def get_signal() -> SignalResponse:
    """Return current aggregate signal from all voters."""
    voters_raw = _current_signal.get("voters", [])
    voters = [
        VoterBreakdown(
            name=v.get("name", "unknown"),
            direction=v.get("direction", 0.0),
            confidence=v.get("confidence", 0.0),
            weight=v.get("weight", 1.0),
        )
        for v in voters_raw
    ]
    return SignalResponse(
        direction=_current_signal.get("direction", "NEUTRAL"),
        conviction=_current_signal.get("conviction", 0.0),
        D=_current_signal.get("D", 0.0),
        P=_current_signal.get("P", 0.0),
        G=_current_signal.get("G", 0.0),
        voters=voters,
        timestamp=_current_signal.get("timestamp"),
    )


@router.get("/voters", response_model=list[VoterBreakdown])
async def get_voters() -> list[VoterBreakdown]:
    """Return all active voters and their current votes."""
    voters_raw = _current_signal.get("voters", [])
    return [
        VoterBreakdown(
            name=v.get("name", "unknown"),
            direction=v.get("direction", 0.0),
            confidence=v.get("confidence", 0.0),
            weight=v.get("weight", 1.0),
        )
        for v in voters_raw
    ]


@router.get("/options", response_model=OptionsChainResponse)
async def get_options(
    symbol: str = Query("NIFTY"),
    expiry: str | None = None,
) -> OptionsChainResponse:
    """Return option chain for a given symbol and expiry."""
    return OptionsChainResponse(
        underlying=symbol,
        expiry=expiry or "next_weekly",
        timestamp=datetime.utcnow(),
        contracts=[],
    )


@router.get("/strategy-hint", response_model=StrategyHintResponse)
async def get_strategy_hint() -> StrategyHintResponse:
    """Return a strategy hint with EV analysis."""
    return StrategyHintResponse(
        direction="NEUTRAL",
        strike=None,
        premium=None,
        ev_after_cost=None,
        rationale="Insufficient signal conviction for a trade recommendation.",
    )
