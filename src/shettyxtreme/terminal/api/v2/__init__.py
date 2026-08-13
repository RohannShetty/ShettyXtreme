"""V2 API router — backward-compatible endpoints with incremental improvements.

Migration strategy:
  - v1 endpoints remain unchanged (backward compatibility)
  - v2 endpoints add richer metadata and normalized field names
  - Clients can migrate endpoint-by-endpoint at their own pace
  - v2 will eventually replace v1 once all clients are migrated

This router is mounted at /api/v2 in app.py.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from shettyxtreme.terminal.api.v2.models import (
    APIVersionInfo,
    OptionsChainItemV2,
    OptionsChainResponseV2,
    WatchlistItemV2,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["v2"])


# ── Health / Version ──────────────────────────────────────────────────────
@router.get("/version", response_model=APIVersionInfo)
async def get_version() -> APIVersionInfo:
    """Return API version and migration metadata.

    Use this endpoint to detect v2 availability and plan migration.
    """
    return APIVersionInfo()


# ── Watchlist v2 ──────────────────────────────────────────────────────────
@router.get("/watchlist", response_model=list[WatchlistItemV2])
async def get_watchlist_v2(request: Request) -> list[WatchlistItemV2]:
    """Return watchlist with enriched v2 metadata.

    **Migration notes:**
    - Same data as GET /api/watchlist but with additional fields
    - New fields: instrument_type, bid, ask, oi, is_tradable
    - All v1 fields are preserved (backward compatible)

    **Breaking changes:** None. v1 clients can ignore new fields.
    """
    proj = request.app.state.watchlist_projection
    data = proj.get()

    # Hydrate from REST (reuse v1 logic)
    from shettyxtreme.terminal.api.watchlist_router import _hydrate_from_rest
    await _hydrate_from_rest(data, request)

    return [
        WatchlistItemV2(
            symbol=symbol,
            exchange=d.get("exchange", "NSE"),
            ltp=d.get("ltp", 0.0),
            change_pct=d.get("change_pct", 0.0),
            volume=d.get("volume", 0),
            timestamp=d.get("timestamp"),
            security_id=d.get("security_id"),
            expiry=d.get("expiry"),
            lot_size=d.get("lot_size"),
            # V2 enrichments — pull from projection metadata
            instrument_type=d.get("instrument_type"),
            bid=d.get("bid"),
            ask=d.get("ask"),
            oi=d.get("oi"),
            is_tradable=d.get("is_tradable", True),
        )
        for symbol, d in data.items()
    ]


# ── Options Chain v2 ──────────────────────────────────────────────────────
@router.get("/options/chain", response_model=OptionsChainResponseV2)
async def get_options_chain_v2(
    request: Request,
    symbol: str = Query("NIFTY"),
    expiry: str | None = None,
) -> OptionsChainResponseV2:
    """Return enriched options chain with aggregate analytics.

    **Migration notes:**
    - Replaces GET /api/intelligence/options
    - Adds spot price, max_pain, pcr, iv_rank_percent in response
    - Contract fields normalized: option_type always CE/PE

    **Breaking changes:** None. Response is superset of v1.
    """
    from shettyxtreme.terminal.api.intelligence_router import (
        _enrich_chain,
        _expiry_to_tte,
        _fetch_chain_with_spot,
        _feed_options_calculators,
        DataAdapterUnavailable,
        DataEntitlementError,
    )
    from shettyxtreme.integration.fyers.symbols import resolve_default_expiry

    # Resolve expiry (reuse v1 logic)
    resolved_expiry = expiry
    if not resolved_expiry or not resolved_expiry.strip():
        master = getattr(request.app.state, "instrument_master", None)
        if master is not None:
            expiries = master.list_expiries(
                symbol.strip().upper(), exchange="NSE", instrument_type="OPTION",
            )
            if expiries:
                resolved_expiry = resolve_default_expiry(symbol.strip().upper(), expiries)

    # Fetch chain
    try:
        chain, spot = await _fetch_chain_with_spot(
            request.app.state.data_adapter, symbol, resolved_expiry
        )
    except DataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataAdapterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Enrich with greeks
    contracts = _enrich_chain(chain, spot, tte=_expiry_to_tte(resolved_expiry))

    # Cache the raw chain (same as v1)
    request.app.state.options_chain = {
        **getattr(request.app.state, "options_chain", {}),
        symbol: {"spot": spot, "contracts": chain},
    }
    _feed_options_calculators(request.app, chain, symbol, resolved_expiry or "")

    # V2 enrichments: aggregate analytics
    from shettyxtreme.options.max_pain import compute_max_pain
    max_pain_val = compute_max_pain(chain) if chain else None

    oi_track = getattr(request.app.state, "oi_tracker", None)
    pcr_val = oi_track.get_pcr(symbol) if oi_track else None
    if pcr_val == 0.0:
        pcr_val = None

    iv_calc = getattr(request.app.state, "iv_rank_calculator", None)
    iv_rank_val: float | None = None
    if iv_calc:
        result = iv_calc.compute_iv_rank_percent(symbol)
        if result is not None:
            iv_rank_val = result.iv_rank_percent

    # Convert to v2 models with spot distance
    v2_contracts: list[OptionsChainItemV2] = []
    for c in contracts:
        spot_dist = None
        if spot and spot > 0 and c.strike > 0:
            spot_dist = round(((c.strike - spot) / spot) * 100, 2)
        v2_contracts.append(OptionsChainItemV2(
            strike=c.strike,
            option_type="CE" if c.option_type == "CE" else "PE",
            ltp=c.ltp,
            iv=c.iv,
            delta=c.delta,
            gamma=c.gamma,
            theta=c.theta,
            vega=c.vega,
            oi=c.oi,
            volume=c.volume,
            bid=c.bid,
            ask=c.ask,
            spot_distance_pct=spot_dist,
        ))

    return OptionsChainResponseV2(
        underlying=symbol,
        expiry=resolved_expiry or "",
        contracts=v2_contracts,
        spot=spot,
        max_pain=max_pain_val,
        pcr=pcr_val,
        iv_rank_percent=iv_rank_val,
    )
