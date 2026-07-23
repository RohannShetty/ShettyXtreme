"""Dhan Data API adapter: live market feed WS, historical OHLC, OI/PCR.

Implements core.interfaces.data_provider.DataProvider and
core.interfaces.market_data_stream.MarketDataStream protocols.

Uses SEPARATE credentials from Trading adapter (Dhan error 806 if mixed).
Includes staleness detection for data feed.

Dhan WS binary protocol feed codes:
  2 = ticker, 4 = quote, 5 = order data,
  8 = full quote, 41 = OHLC, 51 = market depth
"""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from dhanhq import DhanContext
from dhanhq import dhanhq as DhanHQClient
from dhanhq import MarketFeed

from shettyxtreme.core.interfaces.data_provider import DataProvider
from shettyxtreme.core.interfaces.market_data_stream import (
    Bar,
    BarCallback,
    MarketDataStream,
    Tick,
    TickCallback,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

EXCHANGE_MAP: dict[str, str] = {
    "NSE": "NSE_EQ", "BSE": "BSE_EQ", "NFO": "NSE_FNO",
    "BFO": "BSE_FNO", "MCX": "MCX", "IDX": "IDX_I",
}

FEED_CODE_TICKER: int = 2
FEED_CODE_QUOTE: int = 4
FEED_CODE_ORDER: int = 5
FEED_CODE_FULL_QUOTE: int = 8
FEED_CODE_OHLC: int = 41
FEED_CODE_MARKET_DEPTH: int = 51
STALENESS_THRESHOLD_SEC: float = 30.0


class DhanDataAdapter:
    """Dhan Data API adapter for market data.

    Implements DataProvider and MarketDataStream protocols.
    Uses data-specific credentials (separate from trading to avoid error 806).
    """

    name: str = "dhan-data"
    description: str = "Dhan market data: live WS feed, historical OHLC, OI"

    def __init__(self, client_id: str, access_token: str) -> None:
        self._client_id: str = client_id
        self._access_token: str = access_token
        self._context: DhanContext | None = None
        self._dhan: DhanHQClient | None = None
        self._feed: MarketFeed | None = None
        self._connected: bool = False
        self._ws_connected: bool = False
        self._tick_callbacks: dict[str, TickCallback] = {}
        self._bar_callbacks: dict[str, tuple[str, BarCallback]] = {}
        self._last_tick_time: float = 0.0
        self._init_context()

    def _init_context(self) -> None:
        """Initialize DhanContext with DATA credentials (not trading)."""
        self._context = DhanContext(
            client_id=self._client_id, access_token=self._access_token,
        )
        self._dhan = DhanHQClient(self._context)
        self._connected = True

    # ---- DataProvider protocol ----

    async def is_available(self) -> bool:
        """Check if Dhan data API is available."""
        return self._connected and self._dhan is not None

    # ---- Connection ----

    async def connect(self) -> bool:
        """Connect to Dhan data API."""
        try:
            self._init_context()
            return self._connected
        except Exception as exc:
            logger.error("Dhan data connect failed: %s", exc)
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Dhan data API."""
        if self._feed is not None:
            try:
                self._feed.disconnect()
            except Exception as exc:
                logger.warning("Dhan WS disconnect error: %s", exc)
        self._ws_connected = False
        self._connected = False
        self._dhan = None
        self._feed = None
        return True

    async def is_connected(self) -> bool:
        """Return whether the data adapter is connected."""
        return self._connected

    # ---- MarketDataStream protocol ----

    async def subscribe_ticks(self, symbols: list[str], callback: TickCallback) -> bool:
        """Subscribe to live tick data via Dhan WebSocket."""
        for sym in symbols:
            self._tick_callbacks[sym] = callback
        instruments: list[tuple[str, str, int]] = [
            ("NSE_EQ", sym, FEED_CODE_TICKER) for sym in symbols
        ]
        return await self._start_ws_feed(instruments)

    async def subscribe_bars(self, symbols: list[str], tf: str, callback: BarCallback) -> bool:
        """Subscribe to live bar data via Dhan WebSocket."""
        for sym in symbols:
            self._bar_callbacks[sym] = (tf, callback)
        instruments: list[tuple[str, str, int]] = [
            ("NSE_EQ", sym, FEED_CODE_FULL_QUOTE) for sym in symbols
        ]
        return await self._start_ws_feed(instruments)

    async def unsubscribe(self, symbol: str) -> bool:
        """Unsubscribe from updates for a specific instrument."""
        self._tick_callbacks.pop(symbol, None)
        self._bar_callbacks.pop(symbol, None)
        if self._feed is not None:
            try:
                self._feed.unsubscribe_symbols([symbol])
                return True
            except Exception as exc:
                logger.error("Dhan WS unsubscribe failed: %s", exc)
                return False
        return True

    async def _start_ws_feed(self, instruments: list[tuple[str, str, int]]) -> bool:
        """Start the Dhan WebSocket feed in a background thread."""
        if self._context is None:
            self._init_context()

        def _on_ticks(tick_data: Any) -> None:
            self._process_ws_tick(tick_data)

        def _on_connect() -> None:
            self._ws_connected = True
            logger.info("Dhan WS feed connected.")

        def _on_close() -> None:
            self._ws_connected = False
            logger.warning("Dhan WS feed closed.")

        def _on_error(err: Any) -> None:
            logger.error("Dhan WS feed error: %s", err)

        try:
            self._feed = MarketFeed(
                dhan_context=self._context, instruments=instruments,
                version="v2", on_connect=_on_connect, on_message=_on_ticks,
                on_close=_on_close, on_error=_on_error, on_ticks=_on_ticks,
            )
            loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._feed.run_forever)
            return True
        except Exception as exc:
            logger.error("Dhan WS feed start failed: %s", exc)
            return False

    def _process_ws_tick(self, tick_data: Any) -> None:
        """Process incoming WebSocket tick data and dispatch callbacks."""
        self._last_tick_time = time.time()
        if isinstance(tick_data, (bytes, bytearray)):
            tick: Tick | None = self._parse_binary_tick(tick_data)
            if tick is not None:
                cb: TickCallback | None = self._tick_callbacks.get(tick.symbol)
                if cb is not None:
                    result = cb(tick)
                    if asyncio.iscoroutine(result):
                        asyncio.ensure_future(result)
        elif isinstance(tick_data, dict):
            symbol: str = str(tick_data.get("security_id", tick_data.get("symbol", "")))
            feed_code: int = int(tick_data.get("feed_code", 0))
            if feed_code == FEED_CODE_OHLC:
                bar: Bar | None = self._parse_dict_bar(symbol, tick_data)
                if bar is not None:
                    bc_entry: tuple[str, BarCallback] | None = self._bar_callbacks.get(symbol)
                    if bc_entry is not None:
                        result_b = bc_entry[1](bar)
                        if asyncio.iscoroutine(result_b):
                            asyncio.ensure_future(result_b)
            else:
                tick_obj: Tick = self._parse_dict_tick(symbol, tick_data)
                cb2: TickCallback | None = self._tick_callbacks.get(symbol)
                if cb2 is not None:
                    result_t = cb2(tick_obj)
                    if asyncio.iscoroutine(result_t):
                        asyncio.ensure_future(result_t)

    @staticmethod
    def _parse_binary_tick(data: bytes) -> Tick | None:
        """Parse Dhan WS binary tick data (feed code 2: ticker)."""
        if len(data) < 30:
            return None
        try:
            feed_code: int = struct.unpack_from("!B", data, 0)[0]
            exchange_idx: int = struct.unpack_from("!B", data, 1)[0]
            security_id: int = struct.unpack_from("!I", data, 2)[0]
            ltp: float = struct.unpack_from("!d", data, 6)[0]
            volume: int = struct.unpack_from("!q", data, 14)[0]
            ts_ms: int = struct.unpack_from("!q", data, 22)[0]
            exchanges: list[str] = ["NSE_EQ", "BSE_EQ", "NSE_FNO", "MCX", "IDX_I"]
            exchange: str = exchanges[exchange_idx] if exchange_idx < len(exchanges) else "NSE_EQ"
            return Tick(
                symbol=str(security_id), exchange=exchange, ltp=ltp,
                volume=volume, timestamp=datetime.fromtimestamp(ts_ms / 1000.0, tz=IST),
            )
        except (struct.error, IndexError, ValueError) as exc:
            logger.error("Dhan WS binary parse error: %s", exc)
            return None

    @staticmethod
    def _parse_dict_tick(symbol: str, data: dict[str, Any]) -> Tick:
        """Parse a dict-format tick from Dhan WS."""
        ts_val: Any = data.get("tt", data.get("trade_time"))
        ts: datetime = (
            datetime.fromtimestamp(int(ts_val) / 1000.0, tz=IST)
            if ts_val else datetime.now(IST)
        )
        return Tick(
            symbol=symbol, exchange=str(data.get("exchange_segment", "NSE_EQ")),
            ltp=float(data.get("ltp", data.get("last_price", 0.0))),
            volume=int(data.get("volume", data.get("total_volume", 0))),
            timestamp=ts,
            bid=float(data.get("bid", 0)) if data.get("bid") else None,
            ask=float(data.get("ask", 0)) if data.get("ask") else None,
            open=float(data.get("open", 0)) if data.get("open") else None,
            high=float(data.get("high", 0)) if data.get("high") else None,
            low=float(data.get("low", 0)) if data.get("low") else None,
            close=float(data.get("close", 0)) if data.get("close") else None,
            oi=int(data.get("oi", 0)) if data.get("oi") or data.get("open_interest") else None,
        )

    # ---- Staleness detection ----

    @property
    def last_data_time(self) -> float:
        """Return the timestamp of the last received data (epoch seconds)."""
        return self._last_tick_time

    def is_stale(self, threshold: float | None = None) -> bool:
        """Check if the data feed is stale.

        Args:
            threshold: Seconds without data before considering stale.
                Defaults to STALENESS_THRESHOLD_SEC.

        Returns:
            True if no data received within the threshold, or if no
            data has been received at all.
        """
        if self._last_tick_time == 0.0:
            return True
        effective_threshold: float = threshold if threshold is not None else STALENESS_THRESHOLD_SEC
        elapsed: float = time.time() - self._last_tick_time
        return elapsed > effective_threshold

    def reset_staleness(self) -> None:
        """Reset the staleness timer by marking now as last data time."""
        self._last_tick_time = time.time()

    # ---- Historical & REST data methods ----

    async def get_intraday_bars(
        self, security_id: str, exchange_segment: str,
        instrument_type: str, from_date: str, to_date: str,
        interval: int = 1, oi: bool = False,
    ) -> dict[str, Any]:
        """Fetch intraday minute candles via dhanhq.intraday_minute_data.

        Args:
            security_id: Dhan security ID for the instrument.
            exchange_segment: e.g. NSE_EQ, NSE_FNO.
            instrument_type: EQUITY, OPTIDX, OPTSTK, FUTIDX, FUTSTK.
            from_date: Start date as string.
            to_date: End date as string.
            interval: Candle interval in minutes (1, 5, 15, 25, 60).
            oi: Include open interest for derivatives.

        Returns:
            Raw Dhan API response dict.
        """
        if self._dhan is None:
            self._init_context()
        assert self._dhan is not None
        try:
            result: dict[str, Any] = self._dhan.intraday_minute_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
                from_date=from_date, to_date=to_date,
                interval=interval, oi=oi,
            )
            self._last_tick_time = time.time()
            return result
        except Exception as exc:
            logger.error("Dhan get_intraday_bars failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_daily_bars(
        self, security_id: str, exchange_segment: str,
        instrument_type: str, from_date: str, to_date: str,
        oi: bool = False,
    ) -> dict[str, Any]:
        """Fetch daily candles via dhanhq.historical_daily_data.

        Args:
            security_id: Dhan security ID for the instrument.
            exchange_segment: e.g. NSE_EQ, NSE_FNO.
            instrument_type: EQUITY, OPTIDX, OPTSTK, FUTIDX, FUTSTK.
            from_date: Start date as string.
            to_date: End date as string.
            oi: Include open interest for derivatives.

        Returns:
            Raw Dhan API response dict.
        """
        if self._dhan is None:
            self._init_context()
        assert self._dhan is not None
        try:
            result: dict[str, Any] = self._dhan.historical_daily_data(
                security_id=security_id,
                exchange_segment=exchange_segment,
                instrument_type=instrument_type,
                from_date=from_date, to_date=to_date, oi=oi,
            )
            self._last_tick_time = time.time()
            return result
        except Exception as exc:
            logger.error("Dhan get_daily_bars failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_ohlc(self, securities: dict[str, list[str]]) -> dict[str, Any]:
        """Get OHLC + LTP for instruments via dhanhq.ohlc_data.

        Args:
            securities: Mapping of exchange segment to list of security IDs.
                e.g. {"NSE_EQ": ["11536"], "NSE_FNO": ["49081"]}

        Returns:
            Raw Dhan API response dict.
        """
        if self._dhan is None:
            self._init_context()
        assert self._dhan is not None
        try:
            result: dict[str, Any] = self._dhan.ohlc_data(securities)
            self._last_tick_time = time.time()
            return result
        except Exception as exc:
            logger.error("Dhan get_ohlc failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_ltp(self, securities: dict[str, list[str]]) -> dict[str, Any]:
        """Get latest traded prices via dhanhq.ticker_data.

        Args:
            securities: Mapping of exchange segment to list of security IDs.
                e.g. {"NSE_EQ": ["11536"]}

        Returns:
            Raw Dhan API response dict.
        """
        if self._dhan is None:
            self._init_context()
        assert self._dhan is not None
        try:
            result: dict[str, Any] = self._dhan.ticker_data(securities)
            self._last_tick_time = time.time()
            return result
        except Exception as exc:
            logger.error("Dhan get_ltp failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_option_chain(
        self, underlying_scrip: str, exchange_segment: str = "NSE_FNO",
        expiry: str = "",
    ) -> dict[str, Any]:
        """Fetch option chain data via dhanhq.option_chain.

        Args:
            underlying_scrip: Security ID of the underlying index/stock.
            exchange_segment: e.g. NSE_FNO, BSE_FNO.
            expiry: Expiry date string (optional).

        Returns:
            Raw Dhan API response dict.
        """
        if self._dhan is None:
            self._init_context()
        assert self._dhan is not None
        try:
            result: dict[str, Any] = self._dhan.option_chain(
                under_security_id=underlying_scrip,
                under_exchange_segment=exchange_segment,
                expiry=expiry,
            )
            self._last_tick_time = time.time()
            return result
        except Exception as exc:
            logger.error("Dhan get_option_chain failed: %s", exc)
            return {"status": "error", "message": str(exc)}
