"""F4 — Fyers data adapter tests (MarketDataStream + DataProvider).

The REST client is swapped for an ``AsyncMock`` and the F3 data socket for a
fake wrapper that records subscriptions and lets the test drive the tick
handler directly (the same seam the F3 data-socket tests use).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from shettyxtreme.core.interfaces.market_data_stream import Tick
from shettyxtreme.integration.fyers.client import FyersTokenExpired
from shettyxtreme.integration.fyers.data_adapter import FyersDataAdapter
from shettyxtreme.integration.fyers.session import FyersSession

APP_ID = "APP123"
SECRET = "SECRET1"
TOKEN = "TOK9"

_SBIN_TICK: dict[str, Any] = {
    "symbol": "NSE:SBIN-EQ",
    "ltp": 480.5,
    "vol_traded_today": 1234,
    "last_traded_time": 1609744577,
    "bid_price": 480.0,
    "ask_price": 481.0,
    "open_price": 479.0,
    "high_price": 482.0,
    "low_price": 478.5,
    "prev_close_price": 480.5,
}


class _FakeDataSocket:
    """Stands in for FyersDataSocketWrapper (SDK not installed in tests)."""

    def __init__(self) -> None:
        self.tick_handler: Any = None
        self.subscribe = AsyncMock(return_value=True)
        self.unsubscribe = AsyncMock(return_value=True)
        self.is_connected = AsyncMock(return_value=True)
        self.connect = AsyncMock(return_value=True)
        self.disconnect = AsyncMock(return_value=True)

    def on_tick(self, cb: Any) -> "_FakeDataSocket":
        self.tick_handler = cb
        return self


@pytest.fixture
def session() -> FyersSession:
    return FyersSession(app_id=APP_ID, secret_id=SECRET, access_token=TOKEN)


@pytest.fixture
def client() -> AsyncMock:
    c = AsyncMock()
    c.get = AsyncMock(return_value={})
    return c


@pytest.fixture
def data_socket() -> _FakeDataSocket:
    return _FakeDataSocket()


@pytest.fixture
def order_socket() -> AsyncMock:
    return AsyncMock(connect=AsyncMock(return_value=True), disconnect=AsyncMock(return_value=True))


@pytest.fixture
def adapter(
    session: FyersSession,
    client: AsyncMock,
    resolver: Any,
    order_socket: AsyncMock,
    data_socket: _FakeDataSocket,
) -> FyersDataAdapter:
    return FyersDataAdapter(
        session=session,
        client=client,
        symbol_resolver=resolver,
        order_socket=order_socket,
        data_socket=data_socket,
    )


class TestSubscribeTicks:
    @pytest.mark.asyncio
    async def test_resolves_symbol_and_dispatches_tick(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        received: list[Tick] = []
        assert await adapter.subscribe_ticks(["SBIN"], lambda t: received.append(t)) is True

        data_socket.subscribe.assert_awaited_once_with(["NSE:SBIN-EQ"], "SymbolUpdate")
        assert data_socket.tick_handler is not None
        await data_socket.tick_handler([_SBIN_TICK])

        assert len(received) == 1
        tick = received[0]
        assert isinstance(tick, Tick)
        assert tick.symbol == "SBIN"
        assert tick.exchange == "NSE"
        assert tick.ltp == 480.5
        assert tick.volume == 1234
        assert tick.bid == 480.0
        assert tick.ask == 481.0
        assert tick.open == 479.0
        assert tick.high == 482.0
        assert tick.low == 478.5
        assert tick.close == 480.5
        assert tick.timestamp == datetime.fromtimestamp(1609744577, tz=UTC)

    @pytest.mark.asyncio
    async def test_index_symbol_resolves_to_index_ticker(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        await adapter.subscribe_ticks(["NIFTY"], lambda t: None)
        data_socket.subscribe.assert_awaited_once_with(
            ["NSE:NIFTY50-INDEX"], "SymbolUpdate"
        )

    @pytest.mark.asyncio
    async def test_token_expiry_propagates(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        data_socket.subscribe = AsyncMock(side_effect=FyersTokenExpired("expired"))
        with pytest.raises(FyersTokenExpired):
            await adapter.subscribe_ticks(["SBIN"], lambda t: None)


class TestSubscribeBars:
    @pytest.mark.asyncio
    async def test_client_side_aggregation_from_ticks(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        bars: list[Any] = []
        assert await adapter.subscribe_bars(["SBIN"], "1m", lambda b: bars.append(b)) is True
        data_socket.subscribe.assert_awaited_once_with(["NSE:SBIN-EQ"], "SymbolUpdate")

        base = datetime.now(UTC).replace(second=0, microsecond=0)
        # Fyers vol_traded_today is CUMULATIVE daily volume — must be
        # monotonically increasing; the closed bar's volume is the delta
        # within it (5), not a running sum (1000 + 1005 + 1010).
        t1 = dict(
            _SBIN_TICK, ltp=480.0, vol_traded_today=1000,
            last_traded_time=int(base.timestamp()),
        )
        t2 = dict(
            _SBIN_TICK, ltp=481.0, vol_traded_today=1005,
            last_traded_time=int((base + timedelta(seconds=30)).timestamp()),
        )
        t3 = dict(
            _SBIN_TICK, ltp=482.0, vol_traded_today=1010,
            last_traded_time=int((base + timedelta(seconds=61)).timestamp()),
        )
        await data_socket.tick_handler([t1, t2, t3])

        assert len(bars) == 1
        bar = bars[0]
        assert bar.symbol == "SBIN"
        assert bar.timeframe == "1min"
        assert bar.open == 480.0
        assert bar.high == 481.0
        assert bar.low == 480.0
        assert bar.close == 481.0
        assert bar.volume == 5


class TestUnsubscribe:
    @pytest.mark.asyncio
    async def test_resolves_symbol_and_forwards(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        assert await adapter.unsubscribe("SBIN") is True
        data_socket.unsubscribe.assert_awaited_once_with(["NSE:SBIN-EQ"])


class TestHistory:
    @pytest.mark.asyncio
    async def test_intraday_parses_candles(
        self, adapter: FyersDataAdapter, client: AsyncMock
    ) -> None:
        epoch = 1609744577
        client.get.return_value = {
            "s": "ok",
            "candles": [[epoch, 480.0, 481.0, 479.0, 480.5, 1000]],
        }
        bars = await adapter.get_intraday_bars("SBIN", "1", 1)

        url = client.get.await_args.args[0]
        assert url.startswith("/data/history?symbol=NSE:SBIN-EQ&resolution=1")
        assert "range_from=" in url and "range_to=" in url

        assert len(bars) == 1
        b = bars[0]
        assert b.symbol == "SBIN"
        assert b.timeframe == "1min"
        assert b.open == 480.0
        assert b.high == 481.0
        assert b.low == 479.0
        assert b.close == 480.5
        assert b.volume == 1000
        assert b.timestamp == datetime.fromtimestamp(epoch, tz=UTC)

    @pytest.mark.asyncio
    async def test_intraday_chunks_over_100_days(
        self, adapter: FyersDataAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {"s": "ok", "candles": []}
        bars = await adapter.get_intraday_bars("SBIN", "5", 250)
        assert client.get.await_count == 3  # 100 + 100 + 50 day windows
        assert bars == []

    @pytest.mark.asyncio
    async def test_daily_parses_candles(
        self, adapter: FyersDataAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "candles": [[1609744577, 470.0, 485.0, 468.0, 480.0, 5000]],
        }
        bars = await adapter.get_daily_bars("SBIN", 5)
        url = client.get.await_args.args[0]
        assert "symbol=NSE:SBIN-EQ" in url
        assert "resolution=D" in url
        assert len(bars) == 1
        assert bars[0].timeframe == "D"
        assert bars[0].close == 480.0


class TestQuotes:
    @pytest.mark.asyncio
    async def test_get_ohlc_extracts_prices(
        self, adapter: FyersDataAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "d": {
                "NSE:SBIN-EQ": {
                    "fp": {
                        "open_price": 479.0,
                        "high_price": 482.0,
                        "low_price": 478.5,
                        "close_price": 480.5,
                        "ltp": 480.5,
                    }
                }
            },
        }
        ohlc = await adapter.get_ohlc("SBIN")
        assert client.get.await_args.args[0].startswith(
            "/data/quotes?symbols=NSE:SBIN-EQ"
        )
        assert ohlc["open"] == 479.0
        assert ohlc["high"] == 482.0
        assert ohlc["low"] == 478.5
        assert ohlc["close"] == 480.5
        assert ohlc["ltp"] == 480.5

    @pytest.mark.asyncio
    async def test_get_ltp(self, adapter: FyersDataAdapter, client: AsyncMock) -> None:
        client.get.return_value = {
            "s": "ok",
            "d": {"NSE:SBIN-EQ": {"fp": {"ltp": 480.5}}},
        }
        assert await adapter.get_ltp("SBIN") == 480.5


class TestOptionChain:
    @pytest.mark.asyncio
    async def test_builds_url_and_returns_payload(
        self, adapter: FyersDataAdapter, client: AsyncMock
    ) -> None:
        payload = {"s": "ok", "option_chain": [{"strikePrice": 25000}]}
        client.get.return_value = payload
        result = await adapter.get_option_chain("NIFTY", "2024-10-31")
        url = client.get.await_args.args[0]
        assert url.startswith("/data/options-chain-v3?symbol=NSE:NIFTY50-INDEX")
        assert "strikecount=50" in url
        assert "timestamp=" in url
        assert "greeks=1" in url
        assert result == payload


class TestAvailabilityAndLifecycle:
    @pytest.mark.asyncio
    async def test_is_available_true_when_session_and_socket_ok(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        assert await adapter.is_available() is True
        data_socket.is_connected.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_available_false_when_socket_down(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        data_socket.is_connected.return_value = False
        assert await adapter.is_available() is False

    @pytest.mark.asyncio
    async def test_is_available_false_when_token_expired(
        self, adapter: FyersDataAdapter, session: FyersSession
    ) -> None:
        session.token_expiry = datetime.now(UTC) - timedelta(seconds=1)
        assert await adapter.is_available() is False

    @pytest.mark.asyncio
    async def test_connect_connects_both_sockets(
        self,
        adapter: FyersDataAdapter,
        order_socket: AsyncMock,
        data_socket: _FakeDataSocket,
    ) -> None:
        assert await adapter.connect() is True
        order_socket.connect.assert_awaited_once()
        data_socket.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_returns_true(
        self,
        adapter: FyersDataAdapter,
        order_socket: AsyncMock,
        data_socket: _FakeDataSocket,
    ) -> None:
        assert await adapter.disconnect() is True
        order_socket.disconnect.assert_awaited_once()
        data_socket.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_connected_delegates_to_data_socket(
        self, adapter: FyersDataAdapter, data_socket: _FakeDataSocket
    ) -> None:
        assert await adapter.is_connected() is True
        data_socket.is_connected.assert_awaited_once()
