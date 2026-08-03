"""Market router — intraday bars and LTP snapshots via the data adapter.

Exposes DhanDataAdapter.get_intraday_bars / get_ltp (previously zero-caller)
as REST endpoints for today's market data, including after market close.

dhanhq response shapes (verified against the Dhan v2 API docs):
  /charts/intraday success body is COLUMNAR — parallel arrays under
  ``data`` keyed ``open``/``high``/``low``/``close``/``volume``/
  ``timestamp`` (epoch seconds)/``open_interest`` — not a list of
  per-candle dicts. Rows are zipped by index.
  /marketfeed/ltp success body: ``data[segment][security_id]["last_price"]``
  (only the LTP — no day OHLC or prev close).
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from shettyxtreme.integration.dhan.data_adapter import EXCHANGE_MAP
from shettyxtreme.terminal.api.models import (
    MarketBar,
    MarketBarsResponse,
    MarketLtpResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

_SYMBOL_SECURITY_ID: dict[str, str] = {"NIFTY": "13", "BANKNIFTY": "25"}
_ID_FOR_SYMBOL: dict[str, str] = {v: k for k, v in _SYMBOL_SECURITY_ID.items()}

# Same segment mapping the data pipeline uses (data_adapter.EXCHANGE_MAP).
_SEGMENT_FOR_EXCHANGE: dict[str, str] = {**EXCHANGE_MAP}

# Bars per trading day at tf=1 (6.25h session) — safety cap for large ranges.
_MAX_BARS_PER_DAY = 375


def _segment_for(exchange: str) -> str:
    """Map a friendly exchange name to its Dhan feed segment."""
    return _SEGMENT_FOR_EXCHANGE.get(exchange.upper(), exchange.upper())


def _instrument_type_for(exchange: str, symbol: str, security_id: str) -> str:
    """Pick the Dhan instrument enum for an intraday call.

    Index names on the F&O segment use ``INDEX``; everything else defaults
    to ``EQUITY`` (verified enum values: INDEX, FUTIDX, OPTIDX, EQUITY).
    """
    segment = _segment_for(exchange)
    if segment in ("NSE_FNO", "BSE_FNO", "IDX_I") and (
        symbol.upper() in _SYMBOL_SECURITY_ID or security_id in _ID_FOR_SYMBOL
    ):
        return "INDEX"
    return "EQUITY"


def _resolve_symbol(request: Request, symbol: str, exchange: str) -> tuple[str, str]:
    """Return (security_id, exchange_segment), raising 404 when unresolved."""
    symbol_upper = symbol.upper()
    security_id = _SYMBOL_SECURITY_ID.get(symbol_upper)
    if security_id is None:
        master = request.app.state.instrument_master
        if master is not None:
            security_id = master.resolve_symbol(symbol, exchange)
    if security_id is None and symbol.isdigit():
        security_id = symbol
    if security_id is None:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return security_id, _segment_for(exchange)


def _iso_timestamp(epoch_seconds: Any) -> str | None:
    """Normalize a dhanhq epoch-seconds value to ISO-8601 (UTC)."""
    try:
        return datetime.fromtimestamp(int(epoch_seconds), tz=UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_intraday(data: Any, cap: int) -> list[MarketBar]:
    """Zip the verified columnar /charts/intraday body into MarketBar rows."""
    if not isinstance(data, dict):
        return []
    opens = data.get("open")
    highs = data.get("high")
    lows = data.get("low")
    closes = data.get("close")
    volumes = data.get("volume")
    timestamps = data.get("timestamp")
    if not all(isinstance(x, list) for x in (opens, highs, lows, closes, volumes, timestamps)):
        logger.warning("market bars: unexpected columnar body shape")
        return []
    bars: list[MarketBar] = []
    for ts, open_v, high_v, low_v, close_v, volume_v in zip(
        timestamps, opens, highs, lows, closes, volumes,
    ):
        iso = _iso_timestamp(ts)
        if iso is None:
            continue
        try:
            bars.append(MarketBar(
                timestamp=iso,
                open=float(open_v),
                high=float(high_v),
                low=float(low_v),
                close=float(close_v),
                volume=int(volume_v or 0),
            ))
        except (TypeError, ValueError):
            continue
    bars.sort(key=lambda b: b.timestamp)
    return bars[-cap:]


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
    security_id, segment = _resolve_symbol(request, symbol, exchange)
    adapter = request.app.state.data_adapter
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail="market data adapter not available — check credentials / Dhan feed",
        )
    today = date.today()
    from_date = (today - timedelta(days=days - 1)).isoformat()
    to_date = today.isoformat()
    instrument_type = _instrument_type_for(exchange, symbol, security_id)
    result = await adapter.get_intraday_bars(
        security_id=security_id,
        exchange_segment=segment,
        instrument_type=instrument_type,
        from_date=from_date,
        to_date=to_date,
        interval=tf,
    )
    if result.get("entitlement") is True:
        raise HTTPException(
            status_code=503,
            detail="Data API entitlement missing — subscribe to Data APIs (Dhan 806)",
        )
    if result.get("status") != "success":
        message = result.get("message") or result.get("remarks") or "market data request failed"
        raise HTTPException(status_code=502, detail=str(message))
    bars = _parse_intraday(result.get("data"), cap=days * _MAX_BARS_PER_DAY)
    return MarketBarsResponse(symbol=symbol.upper(), exchange=exchange.upper(), bars=bars)


@router.get("/ltp", response_model=MarketLtpResponse)
async def get_market_ltp(
    request: Request,
    symbol: str,
    exchange: str = "NSE_FNO",
) -> MarketLtpResponse:
    """Return the latest traded price snapshot for a symbol."""
    security_id, segment = _resolve_symbol(request, symbol, exchange)
    adapter = request.app.state.data_adapter
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail="market data adapter not available — check credentials / Dhan feed",
        )
    result = await adapter.get_ltp({segment: [security_id]})
    if result.get("entitlement") is True:
        raise HTTPException(
            status_code=503,
            detail="Data API entitlement missing — subscribe to Data APIs (Dhan 806)",
        )
    if result.get("status") != "success":
        message = result.get("message") or result.get("remarks") or "market data request failed"
        raise HTTPException(status_code=502, detail=str(message))
    data = result.get("data", {})
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="unexpected LTP response shape")
    instrument = data.get(segment, {}).get(security_id)
    if not isinstance(instrument, dict):
        raise HTTPException(status_code=502, detail="LTP not found in response")
    last_price = instrument.get("last_price")
    if last_price is None:
        raise HTTPException(status_code=502, detail="LTP not found in response")
    return MarketLtpResponse(symbol=symbol.upper(), exchange=exchange.upper(), ltp=float(last_price))
