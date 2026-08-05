"""Fyers data adapter: MarketDataStream + DataProvider (F4).

Thin adapter layer implementing the broker-neutral Protocols on top of the
F2 transport, F1 symbol resolution, and the F3 sockets
(:class:`FyersOrderSocket` / :class:`FyersDataSocketWrapper`).

History (``/data/history``): minute resolutions are capped at 100 days per
request, so the date range is chunked; daily bars are capped at 366 days.
Live bars are aggregated client-side from ticks (Fyers has no server-side
bar subscription) using the same OHLCV accumulation pattern as the
``data/pipeline/bar_builder.py`` engine.

Entitlement (the Dhan 806 twin) surfaces as :class:`FyersDataEntitlementError`
from the transport; live-subscribe errors propagate so the caller can gate on
them, history reads degrade to empty lists.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import unquote

from shettyxtreme.core.data_models import Bar, Tick
from shettyxtreme.core.interfaces.market_data_stream import BarCallback, TickCallback
from shettyxtreme.integration.fyers._util import (
    DAILY_CHUNK_DAYS as _DAILY_CHUNK_DAYS,
    INTRADAY_CHUNK_DAYS as _INTRADAY_CHUNK_DAYS,
    IST as _IST,
    BarAggregator as _BarAggregator,
    chunk_date_range as _chunk_date_range,
    epoch_to_dt as _epoch_to_dt,
    expiry_epoch as _expiry_epoch,
    floor_ts as _floor_ts,
    infer_instrument_type as _infer_instrument_type,
    market_epoch as _market_epoch,
    resolution_for as _resolution_for,
    tf_minutes as _tf_minutes,
    to_float as _to_float,
    to_int as _to_int,
)
from shettyxtreme.integration.fyers.client import (
    FyersAPIError,
    FyersDataEntitlementError,
    FyersError,
    FyersHTTPClient,
    FyersTokenExpired,
)
from shettyxtreme.integration.fyers.data_socket import FyersDataSocketWrapper
from shettyxtreme.integration.fyers.session import FyersSession
from shettyxtreme.integration.fyers.symbols import FyersSymbolResolver
from shettyxtreme.integration.fyers.ws_client import FyersOrderSocket

logger = logging.getLogger(__name__)

#: Fyers caps ``/data/quotes`` at 50 comma-separated symbols per request.
_QUOTES_BATCH_SIZE = 50


class FyersDataAdapter:
    """Fyers market-data adapter (MarketDataStream + DataProvider).

    Args:
        session: Fyers access-token lifecycle.
        client: Fyers REST transport.
        symbol_resolver: Internal-symbol -> Fyers ticker resolution (F1).
        order_socket: F3 order WebSocket (lifecycle only).
        data_socket: F3 supervised HSM data-socket wrapper.
    """

    name: str = "fyers-data"
    description: str = "Fyers market data provider"

    def __init__(
        self,
        session: FyersSession,
        client: FyersHTTPClient,
        symbol_resolver: FyersSymbolResolver,
        order_socket: FyersOrderSocket,
        data_socket: FyersDataSocketWrapper,
    ) -> None:
        self._session = session
        self._client = client
        self._symbol_resolver = symbol_resolver
        self._order_socket = order_socket
        self._data_socket = data_socket

        self._tick_callbacks: list[TickCallback] = []
        self._bar_callbacks: dict[tuple[str, str], BarCallback] = {}
        self._bar_agg: dict[tuple[str, str], _BarAggregator] = {}
        # Route the socket's tick batches through the adapter's parser.
        self._data_socket.on_tick(self._on_ticks)

    # ------------------------------------------------------------------ lifecycle

    async def connect(self) -> bool:
        """Connect both sockets; True only when both succeed."""
        ok = True
        try:
            await self._order_socket.connect()
        except Exception as exc:  # noqa: BLE001 — connect failures collapse to False
            logger.warning("Fyers order socket connect failed: %s", exc)
            ok = False
        try:
            await self._data_socket.connect()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fyers data socket connect failed: %s", exc)
            ok = False
        return ok

    async def disconnect(self) -> bool:
        try:
            await self._order_socket.disconnect()
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._data_socket.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return True

    async def is_connected(self) -> bool:
        return await self._data_socket.is_connected()

    # ------------------------------------------------------------------ helpers

    def _resolve_symbol(self, symbol: str, exchange: str) -> str:
        """Resolve an internal symbol to a Fyers ticker.

        Prefers an exact instrument-master match (round-trip gate for the
        weekly-vs-monthly encoding gotcha); falls back to construction from
        the plain name when no master is bound. Already-resolved tickers
        (containing ``:``) pass through.
        """
        s = str(symbol).strip()
        if ":" in s:
            return s
        master = self._symbol_resolver.master
        if master is not None:
            rows = master.search(s)
            if rows:
                preferred = next(
                    (r for r in rows if r["instrument_type"] == "INDEX"), None
                )
                if preferred is None:
                    preferred = next(
                        (r for r in rows if r["instrument_type"] == "EQUITY"), rows[0]
                    )
                return str(preferred["fyers_symbol"])
        return self._symbol_resolver.to_fyers(s, exchange, _infer_instrument_type(s))

    def _parse_tick(self, raw: Any) -> Tick | None:
        """Parse an SDK symbol-update dict into a :class:`Tick`.

        Field names mirror the SDK's ``map.json`` ``data_val`` / ``index_val``
        lists (the HSM decoder emits exactly those keys): volume is
        ``vol_traded_today``, the timestamp is ``last_traded_time`` (epoch
        seconds), bid/ask are flat ``bid_price``/``ask_price`` floats (the SDK
        already applied the price precision), and the previous close is
        ``prev_close_price``. There is no ``close_price`` in the feed. Open
        interest rides the SDK's uppercase ``OI`` key, which only appears on
        ``data_val`` ticks (F&O / equities) — ``index_val`` ticks omit it, so
        it defaults to ``None`` when absent.
        """
        if not isinstance(raw, dict):
            return None
        ticker = str(raw.get("symbol", ""))
        if not ticker:
            return None
        ltp = _to_float(raw.get("ltp"))
        if ltp is None:
            return None
        parsed = None
        if ":" in ticker:
            try:
                parsed = self._symbol_resolver.from_fyers(ticker)
            except ValueError:
                parsed = None
        internal = str(parsed.get("internal_symbol", ticker)) if parsed else ticker
        exchange = str(parsed.get("exchange", "")) if parsed else ""
        raw_oi = raw.get("OI")
        return Tick(
            symbol=internal,
            exchange=exchange,
            ltp=ltp,
            volume=_to_int(raw.get("vol_traded_today")),
            timestamp=_epoch_to_dt(raw.get("last_traded_time")),
            bid=_to_float(raw.get("bid_price")),
            ask=_to_float(raw.get("ask_price")),
            open=_to_float(raw.get("open_price")),
            high=_to_float(raw.get("high_price")),
            low=_to_float(raw.get("low_price")),
            close=_to_float(raw.get("prev_close_price")),
            # F-INT-005: the SDK's OI key is uppercase and only present on
            # data_val (F&O/equity) ticks; index ticks omit it -> None.
            oi=_to_int(raw_oi) if raw_oi is not None else None,
        )

    async def _on_ticks(self, batch: list[Any]) -> None:
        """Socket tick-batch handler: fan out to callbacks and bar aggregation."""
        for raw in batch:
            tick = self._parse_tick(raw)
            if tick is None:
                continue
            for cb in list(self._tick_callbacks):
                result = cb(tick)
                if asyncio.iscoroutine(result):
                    await result
            await self._accumulate_bars(tick)

    async def _accumulate_bars(self, tick: Tick) -> None:
        """Advance client-side bar aggregation for every live bar on the symbol."""
        for key in [k for k in list(self._bar_agg) if k[0] == tick.symbol]:
            agg = self._bar_agg[key]
            if agg.is_complete(tick.timestamp):
                bar = agg.build(tick.symbol, tick.exchange, key[1])
                self._bar_agg[key] = _BarAggregator(
                    agg.minutes, _floor_ts(tick.timestamp, agg.minutes)
                )
                cb = self._bar_callbacks.get(key)
                if cb is not None:
                    result = cb(bar)
                    if asyncio.iscoroutine(result):
                        await result
            self._bar_agg[key].apply(tick)

    def _parse_history(
        self, resp: Any, symbol: str, exchange: str, tf_label: str
    ) -> list[Bar]:
        """Parse ``/data/history`` candles (``[epoch, o, h, l, c, v(, oi)]``)."""
        if not isinstance(resp, dict):
            return []
        candles = resp.get("candles")
        if not isinstance(candles, list):
            return []
        bars: list[Bar] = []
        for c in candles:
            if not isinstance(c, (list, tuple)) or len(c) < 6:
                continue
            try:
                ts = _epoch_to_dt(c[0])
                o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
                v = _to_int(c[5])
            except (TypeError, ValueError):
                continue
            oi = _to_int(c[6]) if len(c) > 6 and c[6] is not None else None
            bars.append(Bar(
                symbol=str(symbol),
                exchange=exchange,
                timeframe=tf_label,
                open=o, high=h, low=l, close=cl, volume=v,
                timestamp=ts, oi=oi,
            ))
        bars.sort(key=lambda b: b.timestamp)
        return bars

    # ------------------------------------------------------------------ MarketDataStream

    async def subscribe_ticks(self, symbols: list[str], callback: TickCallback) -> bool:
        """Resolve symbols and subscribe to live symbol updates on the data socket."""
        self._tick_callbacks.append(callback)
        resolved = [self._resolve_symbol(s, "NSE_FNO") for s in symbols]
        return await self._data_socket.subscribe(resolved, "SymbolUpdate")

    async def subscribe_bars(self, symbols: list[str], tf: str, callback: BarCallback) -> bool:
        """Subscribe to live ticks and aggregate bars client-side.

        Fyers has no server-side bar subscription, so the adapter builds bars
        from the symbol-update stream (same pattern as ``BarBuilder``).
        """
        minutes = _tf_minutes(tf)
        tf_label = f"{minutes}min"
        resolved: list[str] = []
        now = datetime.now(UTC)
        for s in symbols:
            ticker = self._resolve_symbol(s, "NSE_FNO")
            resolved.append(ticker)
            key = (str(s).strip(), tf_label)
            self._bar_callbacks[key] = callback
            self._bar_agg[key] = _BarAggregator(minutes, _floor_ts(now, minutes))
        return await self._data_socket.subscribe(resolved, "SymbolUpdate")

    async def unsubscribe(self, symbol: str) -> bool:
        """Unsubscribe one symbol (resolved to its Fyers ticker)."""
        ticker = self._resolve_symbol(symbol, "NSE_FNO")
        return await self._data_socket.unsubscribe([ticker])

    # ------------------------------------------------------------------ DataProvider

    async def is_available(self) -> bool:
        return self._session.is_valid() and await self._data_socket.is_connected()

    # ------------------------------------------------------------------ history (routers)

    async def get_intraday_bars(
        self, symbol: str, tf: str, days: int, exchange: str = "NSE_FNO"
    ) -> list[Bar]:
        """Fetch intraday OHLCV, chunking the range to <=100 days/request."""
        ticker = self._resolve_symbol(symbol, exchange)
        resolution = _resolution_for(tf)
        today = datetime.now(_IST).date()
        start = today - timedelta(days=max(int(days), 1) - 1)
        bars: list[Bar] = []
        for chunk_start, chunk_end in _chunk_date_range(
            start, today, _INTRADAY_CHUNK_DAYS
        ):
            url = (
                f"/data/history?symbol={ticker}&resolution={resolution}"
                f"&date_format=1&range_from={_market_epoch(chunk_start, 9, 15)}"
                f"&range_to={_market_epoch(chunk_end, 15, 30)}&cont_flag=1"
            )
            try:
                resp = await self._client.get(url)
            except (FyersTokenExpired, FyersDataEntitlementError, FyersAPIError) as exc:
                logger.warning("Fyers intraday history failed for %s: %s", ticker, exc)
                continue
            bars.extend(self._parse_history(resp, symbol, exchange, f"{resolution}min"))
        return bars

    async def get_daily_bars(
        self, symbol: str, days: int, exchange: str = "NSE_FNO"
    ) -> list[Bar]:
        """Fetch daily OHLCV, chunking the range to <=366 days/request."""
        ticker = self._resolve_symbol(symbol, exchange)
        today = datetime.now(_IST).date()
        start = today - timedelta(days=max(int(days), 1) - 1)
        bars: list[Bar] = []
        for chunk_start, chunk_end in _chunk_date_range(start, today, _DAILY_CHUNK_DAYS):
            url = (
                f"/data/history?symbol={ticker}&resolution=D"
                f"&date_format=1&range_from={_market_epoch(chunk_start, 9, 15)}"
                f"&range_to={_market_epoch(chunk_end, 15, 30)}&cont_flag=1"
            )
            try:
                resp = await self._client.get(url)
            except (FyersTokenExpired, FyersDataEntitlementError, FyersAPIError) as exc:
                logger.warning("Fyers daily history failed for %s: %s", ticker, exc)
                continue
            bars.extend(self._parse_history(resp, symbol, exchange, "D"))
        return bars

    async def get_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Batch-fetch OHLC + ltp for many internal symbols via ``/data/quotes``.

        Symbols are resolved to Fyers tickers and grouped into batches of at
        most :data:`_QUOTES_BATCH_SIZE` (Fyers' per-request cap) — one REST
        call per batch instead of one per symbol. The returned dict is keyed
        by the *internal* symbol (the query the caller passed in) so results
        can be looked up directly; each value carries
        ``{open, high, low, close, ltp}`` with ``ltp`` falling back from the
        quote's top-level ``ltp`` when ``fp.ltp`` is absent (the old
        ``get_ltp`` behaviour, folded in — callers never need a second call).

        Unresolvable symbols, non-dict responses, and failed batches are
        skipped without raising (the degrade-not-throw contract of
        ``get_ohlc``). Requests still flow through the client's 8/s token
        bucket — batching never bypasses it.
        """
        if not symbols:
            return {}
        # Resolve every symbol up front, mapping internal name -> Fyers ticker.
        resolved: dict[str, str] = {}
        for name in symbols:
            name = str(name).strip()
            if not name or name in resolved:
                continue
            try:
                resolved[name] = self._resolve_symbol(name, "NSE_FNO")
            except ValueError as exc:
                logger.warning("Fyers quote resolution failed for %s: %s", name, exc)
                continue
        if not resolved:
            return {}
        by_ticker: dict[str, str] = {ticker: name for name, ticker in resolved.items()}
        result: dict[str, dict[str, Any]] = {}
        tickers = list(by_ticker)
        for i in range(0, len(tickers), _QUOTES_BATCH_SIZE):
            batch = tickers[i : i + _QUOTES_BATCH_SIZE]
            try:
                resp = await self._client.get("/data/quotes?symbols=" + ",".join(batch))
            except FyersError as exc:
                logger.warning("Fyers batch quotes failed (%d symbols): %s", len(batch), exc)
                continue
            d = resp.get("d", {}) if isinstance(resp, dict) else {}
            if not isinstance(d, dict):
                continue
            for ticker, quote in d.items():
                name = by_ticker.get(ticker) or by_ticker.get(unquote(ticker))
                if name is None or not isinstance(quote, dict):
                    continue
                fp = quote.get("fp")
                fp = fp if isinstance(fp, dict) else {}
                ltp = _to_float(fp.get("ltp"))
                if ltp is None:
                    ltp = _to_float(quote.get("ltp"))
                result[name] = {
                    "open": _to_float(fp.get("open_price")),
                    "high": _to_float(fp.get("high_price")),
                    "low": _to_float(fp.get("low_price")),
                    "close": _to_float(fp.get("close_price")),
                    "ltp": ltp,
                }
        return result

    async def get_ohlc(self, symbol: str) -> dict[str, Any]:
        """Extract OHLC + ltp from ``/data/quotes`` (single-symbol wrapper)."""
        return (await self.get_quotes([symbol])).get(str(symbol).strip(), {})

    async def get_ltp(self, symbol: str) -> float:
        """Last traded price from ``/data/quotes`` (0.0 when absent)."""
        ohlc = (await self.get_quotes([symbol])).get(str(symbol).strip(), {})
        ltp = ohlc.get("ltp")
        return ltp if ltp is not None else 0.0

    async def get_option_chain(
        self, underlying: str, expiry: str, strike_count: int = 50
    ) -> dict[str, Any]:
        """Fetch the options chain (+ greeks) via ``/data/options-chain-v3``."""
        ticker = self._resolve_symbol(underlying, "NSE_FNO")
        try:
            return await self._client.get(
                f"/data/options-chain-v3?symbol={ticker}"
                f"&strikecount={int(strike_count)}"
                f"&timestamp={_expiry_epoch(expiry)}&greeks=1"
            )
        except FyersError as exc:
            logger.warning("Fyers options chain failed for %s: %s", ticker, exc)
            return {}
