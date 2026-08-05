"""Market router — intraday bars and LTP snapshots via the Fyers data adapter.

Exposes the FyersDataAdapter history/quote methods (``get_intraday_bars``,
``get_daily_bars``, ``get_ohlc``, ``get_ltp``) as REST endpoints for today's
market data, including after market close.

Fyers shapes: history returns a list of ``Bar`` dataclasses
(``core.interfaces.market_data_stream.Bar``); quotes return a dict with
open/high/low/close/ltp. The data-API entitlement failure (the Dhan 806
twin) is Fyers HTTP 403 / error ``-373`` — surfaced as
``FyersDataEntitlementError`` by the transport.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from shettyxtreme.integration.fyers.client import FyersDataEntitlementError
from shettyxtreme.terminal.api.models import (
    MarketBar,
    MarketBarsResponse,
    MarketLtpResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

#: Internal index names that resolve to the Fyers INDEX instrument type.
_INDEX_SYMBOLS: frozenset[str] = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY"})

# Bars per trading day at tf=1 (6.25h session) — safety cap for large ranges.
_MAX_BARS_PER_DAY = 375

#: User-facing entitlement message (Fyers 403 / -373 — data-API entitlement).
_ENTITLEMENT_MSG = (
    "Data API entitlement missing — subscribe to Data APIs (Fyers 403/-373)"
)


def _as_price(value: Any) -> float | None:
    """Coerce a price value to float; None for junk/halted (<=0)."""
    if not isinstance(value, (int, float, str)):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _ensure_data_entitlement(adapter: Any) -> None:
    """Surface a missing data entitlement as a 503 when the adapter flags it."""
    if getattr(adapter, "entitlement_error", False):
        raise HTTPException(status_code=503, detail=_ENTITLEMENT_MSG)


def _resolve_symbol(request: Request, symbol: str, exchange: str) -> str | None:
    """Validate an internal symbol resolves to Fyers format.

    Already-resolved Fyers tickers (containing ``:``) pass through. Without a
    symbol resolver wired, the symbol is passed through unchanged — the data
    adapter resolves internally.
    """
    s = str(symbol).strip()
    if not s:
        return None
    if ":" in s:
        return s
    resolver = getattr(request.app.state, "symbol_resolver", None)
    if resolver is None:
        return s
    try:
        instrument_type = "INDEX" if s.upper() in _INDEX_SYMBOLS else "EQUITY"
        resolver.to_fyers(s, exchange, instrument_type)
        return s
    except ValueError:
        return None


@router.get("/bars", response_model=MarketBarsResponse)
async def get_market_bars(
    request: Request,
    symbol: str,
    exchange: str = "NSE_FNO",
    tf: int = Query(1, ge=1, le=60),
    days: int = Query(1, ge=1, le=5),
) -> MarketBarsResponse:
    """Return intraday OHLCV bars for a symbol (works after market close)."""
    if tf not in (1, 5, 15, 25, 60):
        raise HTTPException(status_code=422, detail="tf must be one of 1, 5, 15, 25, 60")
    resolved = _resolve_symbol(request, symbol, exchange)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Symbol not found")
    adapter = request.app.state.data_adapter
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail="market data adapter not available — check credentials / Fyers feed",
        )
    _ensure_data_entitlement(adapter)
    try:
        bars = await adapter.get_intraday_bars(resolved, str(tf), days, exchange)
    except FyersDataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=_ENTITLEMENT_MSG) from exc
    cap = days * _MAX_BARS_PER_DAY
    result = [
        MarketBar(
            timestamp=b.timestamp.isoformat(),
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for b in bars
    ][-cap:]
    return MarketBarsResponse(symbol=symbol.upper(), exchange=exchange.upper(), bars=result)


@router.get("/ltp", response_model=MarketLtpResponse)
async def get_market_ltp(
    request: Request,
    symbol: str,
    exchange: str = "NSE_FNO",
) -> MarketLtpResponse:
    """Return the latest traded price snapshot for a symbol (OHLC + ltp)."""
    resolved = _resolve_symbol(request, symbol, exchange)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Symbol not found")
    adapter = request.app.state.data_adapter
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail="market data adapter not available — check credentials / Fyers feed",
        )
    _ensure_data_entitlement(adapter)
    try:
        ohlc = await adapter.get_ohlc(resolved)
        ltp = _as_price(ohlc.get("ltp")) if isinstance(ohlc, dict) else None
        if ltp is None:
            ltp = _as_price(await adapter.get_ltp(resolved))
    except FyersDataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=_ENTITLEMENT_MSG) from exc
    if ltp is None:
        raise HTTPException(status_code=502, detail="LTP not found in response")
    return MarketLtpResponse(
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        ltp=float(ltp),
        open=ohlc.get("open") if isinstance(ohlc, dict) else None,
        high=ohlc.get("high") if isinstance(ohlc, dict) else None,
        low=ohlc.get("low") if isinstance(ohlc, dict) else None,
        prev_close=ohlc.get("close") if isinstance(ohlc, dict) else None,
    )
