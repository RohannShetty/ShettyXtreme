"""Intelligence router — regime, signal, voters, options, strategy hints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from shettyxtreme.intelligence.hints.strategy_hints import StrategyHints
from shettyxtreme.options.greeks import GreeksCalculator
from shettyxtreme.terminal.api.models import (
    OptionsChainItem,
    OptionsChainResponse,
    RegimeResponse,
    SignalResponse,
    StrategyHintResponse,
    VoterBreakdown,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

_SYMBOL_SECURITY_ID: dict[str, str] = {"NIFTY": "13", "BANKNIFTY": "25"}


def _security_id(symbol: str) -> str:
    return _SYMBOL_SECURITY_ID.get(symbol.upper(), symbol)


async def _fetch_chain(request: Request, symbol: str, expiry: str | None) -> list[dict[str, Any]]:
    adapter = request.app.state.data_adapter
    if adapter is None:
        return []
    result = await adapter.get_option_chain(
        underlying_scrip=_security_id(symbol),
        exchange_segment="NSE_FNO",
        expiry=expiry or "",
    )
    if result.get("status") != "success":
        return []
    return result.get("data", {}).get("option_chain", [])


def _enrich_chain(chain: list[dict[str, Any]]) -> list[OptionsChainItem]:
    """Map raw chain rows to OptionsChainItem, enriching with pure-Python greeks."""
    calc = GreeksCalculator(use_quantlib=False)
    contracts: list[OptionsChainItem] = []
    for row in chain:
        spot = row.get("underlying_ltp") or row.get("spot")
        iv = float(row.get("iv", 0.0) or 0.0)
        greeks: dict[str, float] = {}
        if spot and iv > 0:
            try:
                raw_type = str(row.get("option_type", "CE")).upper()
                greeks = calc.calculate_all(
                    spot=float(spot),
                    strike=float(row.get("strike", 0.0)),
                    tte=0.25,
                    iv=iv,
                    option_type="CALL" if raw_type in ("CE", "CALL") else "PUT",
                )
            except Exception:
                greeks = {}
        contracts.append(OptionsChainItem(
            strike=float(row.get("strike", 0.0)),
            option_type=str(row.get("option_type", "CE")),
            ltp=float(row.get("ltp", 0.0) or 0.0),
            iv=iv,
            delta=float(greeks.get("delta", 0.0)),
            gamma=float(greeks.get("gamma", 0.0)),
            theta=float(greeks.get("theta", 0.0)),
            vega=float(greeks.get("vega", 0.0)),
            oi=int(row.get("oi", 0) or 0),
            volume=int(row.get("volume", 0) or 0),
            bid=float(row.get("bid", 0.0) or 0.0),
            ask=float(row.get("ask", 0.0) or 0.0),
        ))
    return contracts


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
    request: Request,
    symbol: str = Query("NIFTY"),
    expiry: str | None = None,
) -> OptionsChainResponse:
    """Return option chain for a given symbol and expiry."""
    chain = await _fetch_chain(request, symbol, expiry)
    contracts = _enrich_chain(chain)
    return OptionsChainResponse(underlying=symbol, expiry=expiry or "", contracts=contracts)


@router.get("/strategy-hint", response_model=StrategyHintResponse)
async def get_strategy_hint(request: Request) -> StrategyHintResponse:
    """Return a strategy hint with EV analysis."""
    signal = request.app.state.intelligence_projection.get_signal()
    chain = await _fetch_chain(request, "NIFTY", None)
    hint = StrategyHints(signal=signal, chain=chain).generate()
    return StrategyHintResponse(
        direction=hint.direction,
        strike=hint.strike,
        premium=hint.premium,
        ev_after_cost=hint.ev_after_cost,
        rationale=hint.rationale,
    )
