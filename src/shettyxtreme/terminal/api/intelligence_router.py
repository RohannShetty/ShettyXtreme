"""Intelligence router — regime, signal, voters, options, strategy hints.

OPEN QUESTION (blueprint §02 precedent): Dhan /optionchain response key
names are unverified against the live API — aliases handled defensively;
verify with a recorded fixture once live credentials available.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

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

# Spot-field aliases across the row and top-level /optionchain bodies.
_SPOT_ALIASES: tuple[str, ...] = ("underlying_ltp", "spot", "underlying_spot")


class DataEntitlementError(Exception):
    """Raised when the data adapter reports a missing Data-API entitlement (806)."""


class DataAdapterUnavailable(Exception):
    """Raised when no data adapter is wired — chain data cannot be fetched."""


def _security_id(symbol: str) -> str:
    return _SYMBOL_SECURITY_ID.get(symbol.upper(), symbol)


def _row_value(row: dict[str, Any], *aliases: str, default: Any = None) -> Any:
    """Return the first non-None alias value present in a row."""
    for key in aliases:
        if row.get(key) is not None:
            return row[key]
    return default


def _safe_float(value: Any) -> float:
    """Coerce a chain row value to float, defaulting to 0.0 on junk."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_float_opt(value: Any) -> float | None:
    """Coerce to float, returning None on junk (used for the spot scan)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_type(row: dict[str, Any]) -> str:
    """Normalize option_type/drv_option_type to CE or PE (uppercased)."""
    raw = str(_row_value(row, "option_type", "drv_option_type", default="CE")).upper()
    if raw == "CALL":
        return "CE"
    if raw == "PUT":
        return "PE"
    return raw if raw in ("CE", "PE") else "CE"


async def _fetch_chain_with_spot(
    request: Request, symbol: str, expiry: str | None,
) -> tuple[list[dict[str, Any]], float | None]:
    """Fetch the option chain, returning (rows, top-level spot).

    Accepts the adapter's success contract and dhanhq-style bodies where
    ``data`` is the chain list directly or a dict with an ``option_chain``
    key. Raises DataEntitlementError on 806 so callers surface the missing
    Data-API entitlement instead of silently returning an empty chain.
    Raises DataAdapterUnavailable when no adapter is wired — an empty chain
    must never be presented as data.
    """
    adapter = request.app.state.data_adapter
    if adapter is None:
        raise DataAdapterUnavailable(
            "market data adapter not available — check credentials / Dhan feed"
        )
    result = await adapter.get_option_chain(
        underlying_scrip=_security_id(symbol),
        exchange_segment="NSE_FNO",
        expiry=expiry or "",
    )
    if result.get("entitlement") is True:
        raise DataEntitlementError(
            "Data API entitlement missing — subscribe to Data APIs (Dhan 806)"
        )
    if result.get("status") != "success":
        return [], None
    data = result.get("data", {})
    if isinstance(data, list):
        return data, None
    if not isinstance(data, dict):
        return [], None
    spot = _safe_float_opt(_row_value(data, *_SPOT_ALIASES))
    chain = data.get("option_chain", [])
    return (chain if isinstance(chain, list) else []), spot


def _enrich_chain(
    chain: list[dict[str, Any]], spot: float | None = None,
) -> list[OptionsChainItem]:
    """Map raw chain rows to OptionsChainItem, enriching with pure-Python greeks."""
    calc = GreeksCalculator(use_quantlib=False)
    contracts: list[OptionsChainItem] = []
    for row in chain:
        if not isinstance(row, dict):
            continue
        try:
            strike = _safe_float(_row_value(row, "strike", "strike_price"))
            option_type = _normalized_type(row)
            ltp = _safe_float(_row_value(row, "ltp", "last_price"))
            iv = _safe_float(row.get("iv"))
            row_spot = _safe_float_opt(_row_value(row, *_SPOT_ALIASES))
            spot_val = row_spot if row_spot is not None else spot
            greeks: dict[str, float] = {}
            if spot_val and iv > 0 and strike > 0:
                greeks = calc.calculate_all(
                    spot=spot_val,
                    strike=strike,
                    tte=0.25,
                    iv=iv,
                    option_type="CALL" if option_type == "CE" else "PUT",
                )
            contracts.append(OptionsChainItem(
                strike=strike,
                option_type=option_type,
                ltp=ltp,
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
        except (TypeError, ValueError):
            contracts.append(OptionsChainItem(
                strike=_safe_float(_row_value(row, "strike", "strike_price")),
                option_type=_normalized_type(row),
                ltp=0.0, iv=0.0, delta=0.0, gamma=0.0, theta=0.0, vega=0.0,
                oi=0, volume=0, bid=0.0, ask=0.0,
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
    try:
        chain, spot = await _fetch_chain_with_spot(request, symbol, expiry)
    except DataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataAdapterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    contracts = _enrich_chain(chain, spot)
    # Cache the RAW rows (pre-enrichment) so the research layer's
    # options_posture tool can derive IV/PCR/OI posture from live data.
    request.app.state.options_chain = {
        **getattr(request.app.state, "options_chain", {}),
        symbol: {"spot": spot, "contracts": chain},
    }
    return OptionsChainResponse(underlying=symbol, expiry=expiry or "", contracts=contracts)


@router.get("/strategy-hint", response_model=StrategyHintResponse)
async def get_strategy_hint(request: Request) -> StrategyHintResponse:
    """Return a strategy hint with EV analysis."""
    signal = request.app.state.intelligence_projection.get_signal() or {}
    try:
        chain, chain_spot = await _fetch_chain_with_spot(request, "NIFTY", None)
    except DataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataAdapterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    current_price = chain_spot
    if current_price is None:
        for row in chain:
            if not isinstance(row, dict):
                continue
            spot = _row_value(row, *_SPOT_ALIASES)
            if spot is None:
                continue
            current_price = _safe_float_opt(spot)
            if current_price is not None:
                break
    hint = StrategyHints(signal=signal, chain=chain, current_price=current_price).generate()
    return StrategyHintResponse(
        direction=hint.direction,
        strike=hint.strike,
        premium=hint.premium,
        ev_after_cost=hint.ev_after_cost,
        rationale=hint.rationale,
    )
