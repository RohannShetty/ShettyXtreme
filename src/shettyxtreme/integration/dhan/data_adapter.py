"""Dhan Data API adapter: live market feed WS, historical OHLC, OI/PCR.

Implements core.interfaces.data_provider.DataProvider and
core.interfaces.market_data_stream.MarketDataStream protocols.

Uses the single primary access token (D8) for the WS feed; an optional
data-access token fallback exists for separate-entitlement cases (Dhan
error 806). Includes staleness detection for data feed.

Dhan WS binary protocol — two distinct code sets:
  Subscription REQUEST codes (v2 JSON, validated to 15/17/21):
    Ticker=15, Quote=17, Full=21; unsubscribe = request code + 1.
  Response feed codes (inbound first-byte dispatch, SDK marketfeed.process_data):
    2 = ticker, 3 = depth, 4 = quote, 5 = OI, 6 = prev close,
    7 = status, 8 = full quote, 50 = server disconnect (code at <BHBIH index 4:
    805 = connections exceeded, 806 = Data-API entitlement missing,
    807 = access token expired, 808 = invalid client id, 809 = auth failed).
"""
from __future__ import annotations

import asyncio
import logging
import random
import struct
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from dhanhq import DhanContext, DhanLogin, MarketFeed
from dhanhq import dhanhq as DhanHQClient

from shettyxtreme.core.interfaces.market_data_stream import (
    BarCallback,
    Tick,
    TickCallback,
)
from shettyxtreme.integration.dhan.trading_adapter import (
    _extract_access_token,
    _jwt_expiry,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

EXCHANGE_MAP: dict[str, str] = {
    "NSE": "NSE_EQ", "BSE": "BSE_EQ", "NFO": "NSE_FNO",
    "BFO": "BSE_FNO", "MCX": "MCX", "IDX": "IDX_I",
}

# Subscription REQUEST codes — v2 accepts only 15/17/21
REQUEST_CODE_TICKER: int = 15
REQUEST_CODE_QUOTE: int = 17
REQUEST_CODE_FULL: int = 21
# Inbound response feed codes (first byte; SDK marketfeed.process_data)
FEED_CODE_TICKER: int = 2
FEED_CODE_DEPTH: int = 3
FEED_CODE_QUOTE: int = 4
FEED_CODE_OI: int = 5
FEED_CODE_PREV_CLOSE: int = 6
FEED_CODE_STATUS: int = 7
FEED_CODE_FULL_QUOTE: int = 8
FEED_CODE_DISCONNECT: int = 50
# Server disconnect codes (50-packet <BHBIH index 4)
DISCONNECT_ENTITLEMENT: int = 806
DISCONNECT_TOKEN_EXPIRED: int = 807
# Reconnect policy for 805/transient drops: 1s->2s->4s->8s capped, +jitter
RECONNECT_BASE_DELAY: float = 1.0
RECONNECT_MAX_DELAY: float = 8.0
RECONNECT_JITTER_MAX: float = 0.5
STALENESS_THRESHOLD_SEC: float = 30.0


class _DisconnectAwareFeed(MarketFeed):
    """MarketFeed that records the server disconnect code (805-809).

    The upstream SDK prints the code from the 50-packet and drops it; the
    adapter needs it to classify 806 (entitlement) vs 807 (token expired)
    vs transient drops.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.last_disconnect_code: int | None = None

    def server_disconnection(self, data: bytes) -> None:
        try:
            self.last_disconnect_code = struct.unpack_from("<BHBIH", data, 0)[4]
        except (struct.error, IndexError, ValueError):
            self.last_disconnect_code = None
        return super().server_disconnection(data)


class DhanDataAdapter:
    """Dhan Data API adapter for market data.

    Implements DataProvider and MarketDataStream protocols.
    Uses the primary access token (D8); an optional data-access token
    fallback covers separate-entitlement cases (error 806).
    """

    name: str = "dhan-data"
    description: str = "Dhan market data: live WS feed, historical OHLC, OI"

    def __init__(
        self, client_id: str, access_token: str,
        data_access_token: str | None = None,
        credential_store: Any = None,
    ) -> None:
        self._client_id: str = client_id
        self._access_token: str = access_token
        self._data_access_token: str | None = data_access_token
        self._credential_store: Any = credential_store
        self._context: DhanContext | None = None
        self._dhan: DhanHQClient | None = None
        self._feed: MarketFeed | None = None
        self._connected: bool = False
        self._ws_connected: bool = False
        self._tick_callbacks: dict[str, TickCallback] = {}
        self._bar_callbacks: dict[str, tuple[str, BarCallback]] = {}
        self._last_tick_time: float = 0.0
        self.last_error: str | None = None
        self.entitlement_error: bool = False
        self._feed_active: bool = False
        self._feed_attempt: int = 0
        self._local_close: bool = False
        self._feed_stop: threading.Event = threading.Event()
        self._feed_future: Any = None
        self._init_context()

    def _init_context(self) -> None:
        """Initialize DhanContext with DATA credentials (not trading)."""
        self._context = DhanContext(
            client_id=self._client_id,
            access_token=self._data_access_token or self._access_token,
        )
        self._dhan = DhanHQClient(self._context)
        self._connected = True

    @staticmethod
    def _is_entitlement_text(text: str) -> bool:
        """True when an error text means the Data-API entitlement is missing (806)."""
        return "806" in text or "Subscribe to Data APIs" in text

    @staticmethod
    def _is_entitlement_error(exc: Exception) -> bool:
        """True when the error means the Data-API entitlement is missing (806)."""
        return DhanDataAdapter._is_entitlement_text(str(exc))

    def _mark_ws_error(self, exc: Exception) -> None:
        """Record a WS error; flag entitlement problems (806) for the reconnect cap."""
        if self._is_entitlement_error(exc):
            self.entitlement_error = True
            self.last_error = "subscribe to Data APIs"

    def _error_dict(self, exc: Exception) -> dict[str, Any]:
        """Build the REST error dict, surfacing 806 as a Data-API entitlement problem."""
        if self._is_entitlement_error(exc):
            return {
                "status": "error",
                "entitlement": True,
                "message": "subscribe to Data APIs — Dhan error 806",
            }
        return {"status": "error", "message": str(exc)}

    def _failure_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        """Convert a dhanhq-style failure dict to this adapter's error contract.

        dhanhq 2.2.0 never raises on HTTP errors: DhanHTTP._send_request
        returns {"status": "failure", "remarks": ..., "data": ""} instead
        (installed dhanhq/dhan_http.py:53-70). On HTTP errors ``remarks`` is
        a dict with error_code/error_type/error_message; on transport
        exceptions it is a plain string. Surface 806 as the Data-API
        entitlement problem; other failures carry the remarks message.
        """
        remarks: Any = result.get("remarks", "")
        if isinstance(remarks, dict):
            text = " ".join(
                str(remarks.get(k) or "")
                for k in ("error_message", "error_type", "error_code")
            )
        else:
            text = str(remarks)
        if self._is_entitlement_text(text):
            self.entitlement_error = True
            self.last_error = "subscribe to Data APIs"
            return {
                "status": "error",
                "entitlement": True,
                "message": "subscribe to Data APIs — Dhan error 806",
            }
        self.last_error = text or "Dhan API failure"
        return {"status": "error", "message": self.last_error}

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
        """Disconnect from Dhan data API (local close — no reconnect)."""
        self._local_close = True
        self._feed_active = False
        self._feed_stop.set()
        if self._feed is not None:
            try:
                self._feed.close_connection()
            except Exception as exc:
                logger.warning("Dhan WS disconnect error: %s", exc)
        if self._feed_future is not None:
            try:
                await asyncio.wait_for(self._feed_future, timeout=2.0)
            except Exception:
                pass
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
            ("NSE_EQ", sym, REQUEST_CODE_TICKER) for sym in symbols
        ]
        return await self._start_ws_feed(instruments)

    async def subscribe_bars(self, symbols: list[str], tf: str, callback: BarCallback) -> bool:
        """Subscribe to live bar data via Dhan WebSocket."""
        for sym in symbols:
            self._bar_callbacks[sym] = (tf, callback)
        instruments: list[tuple[str, str, int]] = [
            ("NSE_EQ", sym, REQUEST_CODE_FULL) for sym in symbols
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
        """Start the Dhan WS feed with a supervised, disconnect-code-aware loop."""
        if self.entitlement_error:
            logger.error(
                "Dhan WS feed not started: subscribe to Data APIs to continue"
            )
            return False
        if self._context is None:
            self._init_context()
        self._feed_active = True
        self._feed_stop.clear()
        loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._feed_future = loop.run_in_executor(
            None, self._feed_supervisor, instruments
        )
        return True

    def _feed_supervisor(self, instruments: list[tuple[str, str, int]]) -> None:
        """Blocking feed loop (executor thread): connect, supervise, reconnect.

        The SDK's own reconnect is a blind 1s retry; the close/error callbacks
        stop it (feed._running=False) and this supervisor owns the policy:
        806 = stop (entitlement), 807 = renew token, else backoff + jitter.
        """
        while self._feed_active:
            feed = _DisconnectAwareFeed(
                dhan_context=self._context, instruments=instruments,
                version="v2", on_connect=self._on_connect_cb,
                on_message=self._on_ticks_cb, on_close=self._on_close_cb,
                on_error=self._on_error_cb,
            )
            self._feed = feed
            try:
                feed.run()
            except Exception as exc:
                self._mark_ws_error(exc)
            self._ws_connected = False
            if not self._feed_active:
                break
            action: str = self._classify_disconnect(feed.last_disconnect_code)
            if action == "entitlement" or self.entitlement_error:
                self.entitlement_error = True
                self.last_error = "subscribe to Data APIs"
                logger.error("Dhan WS feed stopped: Data-API entitlement missing (806)")
                break
            if action == "renew":
                logger.warning("Dhan WS feed: access token expired (807) — renewing token")
                if self._renew_token_sync():
                    self._feed_attempt = 0
                    continue
                self.last_error = "Dhan WS token renewal failed"
                break
            self._feed_attempt = min(self._feed_attempt + 1, 5)
            delay: float = self._reconnect_delay(self._feed_attempt)
            logger.warning(
                "Dhan WS feed dropped (code=%s) — reconnect in %.2fs",
                feed.last_disconnect_code, delay,
            )
            if self._feed_stop.wait(delay):
                break
        self._feed = None

    @staticmethod
    def _classify_disconnect(code: int | None) -> str:
        """Classify a server disconnect code: entitlement / renew / retry."""
        if code == DISCONNECT_ENTITLEMENT:
            return "entitlement"
        if code == DISCONNECT_TOKEN_EXPIRED:
            return "renew"
        return "retry"

    @staticmethod
    def _reconnect_delay(attempt: int) -> float:
        """Exponential backoff with jitter, capped at RECONNECT_MAX_DELAY."""
        base: float = min(
            RECONNECT_BASE_DELAY * (2 ** max(attempt - 1, 0)),
            RECONNECT_MAX_DELAY,
        )
        return base + random.uniform(0.0, RECONNECT_JITTER_MAX)

    def _renew_token_sync(self) -> bool:
        """Renew the effective WS token (runs on the feed thread). Returns True on success."""
        old_token: str = self._data_access_token or self._access_token
        try:
            resp: Any = DhanLogin(self._client_id).renew_token(old_token)
        except Exception as exc:
            logger.warning("Dhan WS token renewal failed: %s", exc)
            return False
        new_token: str | None = _extract_access_token(resp)
        if not new_token:
            logger.warning("Dhan WS token renewal returned no accessToken")
            return False
        if self._data_access_token:
            self._data_access_token = new_token
            if self._credential_store is not None:
                self._credential_store.update_data_token(
                    new_token, _jwt_expiry(new_token)
                )
        else:
            self._access_token = new_token
            if self._credential_store is not None:
                self._credential_store.update_token(
                    new_token, _jwt_expiry(new_token), self._client_id
                )
        self._init_context()
        logger.info("Dhan WS token renewed (masked %s****)", new_token[:4])
        return True

    def _on_connect_cb(self, feed: MarketFeed) -> None:
        """SDK on_connect(feed): mark connected and reset the backoff counter."""
        self._ws_connected = True
        self._feed_attempt = 0
        logger.info("Dhan WS feed connected.")

    def _on_ticks_cb(self, feed: MarketFeed, tick_data: Any) -> None:
        """SDK on_message(feed, data): dispatch parsed ticks/bars."""
        self._process_ws_tick(tick_data)

    def _on_close_cb(self, feed: MarketFeed) -> None:
        """SDK on_close(feed): stop the blind 1s loop; the supervisor reconnects."""
        self._ws_connected = False
        if self._local_close:
            return
        feed._running = False

    def _on_error_cb(self, feed: MarketFeed, err: Any) -> None:
        """SDK on_error(feed, err): flag entitlement; stop blind loop on drops."""
        self._mark_ws_error(err)
        logger.error("Dhan WS feed error: %s", err)
        if not self._local_close:
            feed._running = False

    def _process_ws_tick(self, tick_data: Any) -> None:
        """Process incoming WebSocket tick data and dispatch callbacks."""
        if tick_data is None:
            # 50-packet disconnect: the SDK routes it via on_close, not here.
            return
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
            if result.get("status") == "failure":
                return self._failure_dict(result)
            return result
        except Exception as exc:
            logger.error("Dhan get_intraday_bars failed: %s", exc)
            return self._error_dict(exc)

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
            if result.get("status") == "failure":
                return self._failure_dict(result)
            return result
        except Exception as exc:
            logger.error("Dhan get_daily_bars failed: %s", exc)
            return self._error_dict(exc)

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
            if result.get("status") == "failure":
                return self._failure_dict(result)
            return result
        except Exception as exc:
            logger.error("Dhan get_ohlc failed: %s", exc)
            return self._error_dict(exc)

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
            if result.get("status") == "failure":
                return self._failure_dict(result)
            return result
        except Exception as exc:
            logger.error("Dhan get_ltp failed: %s", exc)
            return self._error_dict(exc)

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
            if result.get("status") == "failure":
                return self._failure_dict(result)
            return result
        except Exception as exc:
            logger.error("Dhan get_option_chain failed: %s", exc)
            return self._error_dict(exc)
