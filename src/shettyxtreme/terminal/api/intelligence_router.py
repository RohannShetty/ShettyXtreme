"""Intelligence router — regime, signal, voters, options, strategy hints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from shettyxtreme.terminal.api.models import (
    OptionsChainResponse,
    RegimeResponse,
    SignalResponse,
    StrategyHintResponse,
    VoterBreakdown,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/regime", response_model=RegimeResponse)
async def get_regime(request: Request) -> RegimeResponse:
    """Return current market regime classification."""
    r = request.app.state.intelligence_projection.get_regime()
    return RegimeResponse(
        regime=r.get("regime", "range_bound"),
        confidence=r.get("confidence", 0.5),
        transition=r.get("transition", False),
        adx=r.get("adx"),
        di_plus=r.get("di_plus"),
        di_minus=r.get("di_minus"),
    )


@router.get("/signal", response_model=SignalResponse)
async def get_signal(request: Request) -> SignalResponse:
    """Return current aggregate signal from all voters."""
    s = request.app.state.intelligence_projection.get_signal()
    voters_raw = s.get("voters", [])
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
        direction=s.get("direction", "NEUTRAL"),
        conviction=s.get("conviction", 0.0),
        D=s.get("D", 0.0),
        P=s.get("P", 0.0),
        G=s.get("G", 0.0),
        voters=voters,
        timestamp=s.get("timestamp"),
    )


@router.get("/voters", response_model=list[VoterBreakdown])
async def get_voters(request: Request) -> list[VoterBreakdown]:
    """Return all active voters and their current votes."""
    s = request.app.state.intelligence_projection.get_signal()
    voters_raw = s.get("voters", [])
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
        timestamp=datetime.now(timezone.utc),
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
