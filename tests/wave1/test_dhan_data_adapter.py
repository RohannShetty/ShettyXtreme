"""Tests for DhanDataAdapter: staleness, error 806, OHLC, option chain.

Mocks the dhanhq DhanContext and dhanhq client module so no real API calls.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from shettyxtreme.integration.dhan.data_adapter import DhanDataAdapter

MOCK_CLIENT_ID = "data_client_001"
MOCK_API_KEY = "data_token_xyz"


def _make_mock_dhanhq() -> None:
    dhan_mock = MagicMock()
    dhan_mock.ohlc_data.return_value = {
        "status": "success",
        "data": {
            "NSE_EQ": {
                "11536": {
                    "open": 1900.0, "high": 1950.0,
                    "low": 1890.0, "close": 1945.0,
                    "last_price": 1945.5,
                },
            },
        },
    }
    dhan_mock.option_chain.return_value = {
        "status": "success",
        "data": {
            "option_chain": [
                {"strike": 19000, "option_type": "CE", "ltp": 150.0},
                {"strike": 19000, "option_type": "PE", "ltp": 120.0},
            ],
        },
    }
    dhan_mock.ticker_data.return_value = {
        "status": "success",
        "data": {"NSE_EQ": {"11536": {"last_price": 1945.5}}},
    }
    dhan_mock.intraday_minute_data.return_value = {
        "status": "success",
        "data": [{"time": "09:15", "open": 1900.0, "close": 1905.0}],
    }
    dhan_mock.historical_daily_data.return_value = {
        "status": "success",
        "data": [{"date": "2024-01-01", "close": 1900.0}],
    }
    return dhan_mock


@pytest.fixture
def data_adapter() -> None:
    with patch(
        "shettyxtreme.integration.dhan.data_adapter.DhanContext"
    ) as mock_ctx_cls, patch(
        "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
    ) as mock_client_cls, patch(
        "shettyxtreme.integration.dhan.data_adapter.MarketFeed"
    ) as mock_feed_cls:
        mock_ctx_cls.return_value = MagicMock()
        mock_dhan = _make_mock_dhanhq()
        mock_client_cls.return_value = mock_dhan
        adapter = DhanDataAdapter(
            client_id=MOCK_CLIENT_ID, access_token=MOCK_API_KEY,
        )
        adapter._dhan = mock_dhan
        return adapter


class TestStalenessDetection:
    """Tests for is_stale and reset_staleness."""

    def test_stale_when_no_data_received(self, data_adapter) -> None:
        """is_stale should return True when no tick has been received."""
        data_adapter._last_tick_time = 0.0
        assert data_adapter.is_stale() is True

    def test_stale_when_old_tick(self, data_adapter) -> None:
        """is_stale should return True when last tick is older than threshold."""
        data_adapter._last_tick_time = time.time() - 60.0
        assert data_adapter.is_stale() is True

    def test_not_stale_when_recent_tick(self, data_adapter) -> None:
        """is_stale should return False when last tick is recent."""
        data_adapter._last_tick_time = time.time() - 5.0
        assert data_adapter.is_stale() is False

    def test_custom_threshold(self, data_adapter) -> None:
        """is_stale should respect a custom threshold."""
        data_adapter._last_tick_time = time.time() - 45.0
        assert data_adapter.is_stale(threshold=30.0) is True
        assert data_adapter.is_stale(threshold=60.0) is False

    def test_reset_staleness(self, data_adapter) -> None:
        """reset_staleness should update last_tick_time to now."""
        data_adapter._last_tick_time = 0.0
        data_adapter.reset_staleness()
        assert data_adapter._last_tick_time > 0.0
        assert data_adapter.is_stale() is False

    def test_last_data_time_property(self, data_adapter) -> None:
        """last_data_time should return the last_tick_time."""
        expected = time.time() - 10.0
        data_adapter._last_tick_time = expected
        assert data_adapter.last_data_time == expected


class TestError806Detection:
    """Tests for error 806 treatment in data adapter methods."""

    @pytest.mark.asyncio
    async def test_ohlc_error_806_returns_error(self, data_adapter) -> None:
        """get_ohlc should return error dict when dhanhq raises (simulating 806)."""
        dhan = data_adapter._dhan
        error_response = Exception("HTTP 806: Token expired or session conflict")
        dhan.ohlc_data.side_effect = error_response
        result = await data_adapter.get_ohlc({"NSE_EQ": ["11536"]})
        assert "status" in result
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_option_chain_error_806_returns_error(self, data_adapter) -> None:
        """get_option_chain should return error dict when 806 error occurs."""
        dhan = data_adapter._dhan
        dhan.option_chain.side_effect = RuntimeError("806: access token expired")
        result = await data_adapter.get_option_chain(
            underlying_scrip="13", exchange_segment="NSE_FNO", expiry="",
        )
        assert result["status"] == "error"
        assert "806" in result["message"]

    @pytest.mark.asyncio
    async def test_ltp_error_806_returns_error(self, data_adapter) -> None:
        """get_ltp should return error dict when 806 error occurs."""
        dhan = data_adapter._dhan
        dhan.ticker_data.side_effect = RuntimeError("806 error")
        result = await data_adapter.get_ltp({"NSE_EQ": ["11536"]})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_intraday_bars_error_returns_error(self, data_adapter) -> None:
        """get_intraday_bars should return error dict on exception."""
        dhan = data_adapter._dhan
        dhan.intraday_minute_data.side_effect = RuntimeError("API error")
        result = await data_adapter.get_intraday_bars(
            security_id="11536", exchange_segment="NSE_EQ",
            instrument_type="EQUITY", from_date="2024-01-01",
            to_date="2024-01-02", interval=1,
        )
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_daily_bars_error_returns_error(self, data_adapter) -> None:
        """get_daily_bars should return error dict on exception."""
        dhan = data_adapter._dhan
        dhan.historical_daily_data.side_effect = RuntimeError("API error")
        result = await data_adapter.get_daily_bars(
            security_id="11536", exchange_segment="NSE_EQ",
            instrument_type="EQUITY", from_date="2024-01-01",
            to_date="2024-01-02",
        )
        assert result["status"] == "error"


class TestHistoricalOHLC:
    """Tests for get_ohlc mocking dhanhq.ohlc_data."""

    @pytest.mark.asyncio
    async def test_get_ohlc_success(self, data_adapter) -> None:
        """get_ohlc should return OHLC data from dhanhq."""
        result = await data_adapter.get_ohlc({"NSE_EQ": ["11536"]})
        assert "status" in result
        assert result["status"] == "success"
        nse_data = result["data"]["NSE_EQ"]
        assert "11536" in nse_data
        assert nse_data["11536"]["open"] == 1900.0
        assert nse_data["11536"]["high"] == 1950.0
        assert nse_data["11536"]["low"] == 1890.0
        assert nse_data["11536"]["close"] == 1945.0

    @pytest.mark.asyncio
    async def test_get_ohlc_calls_dhanhq(self, data_adapter) -> None:
        """get_ohlc should call dhanhq.ohlc_data with securities arg."""
        securities = {"NSE_EQ": ["11536"]}
        await data_adapter.get_ohlc(securities)
        dhan = data_adapter._dhan
        dhan.ohlc_data.assert_called_once_with(securities)

    @pytest.mark.asyncio
    async def test_get_ohlc_updates_timestamp(self, data_adapter) -> None:
        """get_ohlc should update last_tick_time after success."""
        data_adapter._last_tick_time = 0.0
        await data_adapter.get_ohlc({"NSE_EQ": ["11536"]})
        assert data_adapter._last_tick_time > 0.0


class TestOptionChain:
    """Tests for get_option_chain mocking dhanhq.option_chain."""

    @pytest.mark.asyncio
    async def test_get_option_chain_success(self, data_adapter) -> None:
        """get_option_chain should return chain data from dhanhq."""
        result = await data_adapter.get_option_chain(
            underlying_scrip="13", exchange_segment="NSE_FNO", expiry="",
        )
        assert result["status"] == "success"
        assert "option_chain" in result["data"]
        assert len(result["data"]["option_chain"]) == 2

    @pytest.mark.asyncio
    async def test_get_option_chain_calls_dhanhq(self, data_adapter) -> None:
        """get_option_chain should call dhanhq.option_chain with params."""
        await data_adapter.get_option_chain(
            underlying_scrip="13",
            exchange_segment="NSE_FNO",
            expiry="2024-01-25",
        )
        dhan = data_adapter._dhan
        dhan.option_chain.assert_called_once_with(
            under_security_id="13",
            under_exchange_segment="NSE_FNO",
            expiry="2024-01-25",
        )


class TestDataAdapterConnection:
    """Tests for connection methods."""

    @pytest.mark.asyncio
    async def test_is_available(self, data_adapter) -> None:
        """is_available should return True when connected."""
        assert await data_adapter.is_available() is True

    @pytest.mark.asyncio
    async def test_is_connected(self, data_adapter) -> None:
        """is_connected should return True after init."""
        assert await data_adapter.is_connected() is True

    @pytest.mark.asyncio
    async def test_disconnect(self, data_adapter) -> None:
        """disconnect should set connected to False."""
        result = await data_adapter.disconnect()
        assert result is True
        assert await data_adapter.is_connected() is False
        assert await data_adapter.is_available() is False


class TestLTP:
    """Tests for get_ltp mocking dhanhq.ticker_data."""

    @pytest.mark.asyncio
    async def test_get_ltp_success(self, data_adapter) -> None:
        """get_ltp should return LTP data from dhanhq."""
        result = await data_adapter.get_ltp({"NSE_EQ": ["11536"]})
        assert result["status"] == "success"
        assert "NSE_EQ" in result["data"]

    @pytest.mark.asyncio
    async def test_get_ltp_updates_timestamp(self, data_adapter) -> None:
        """get_ltp should update last_tick_time after success."""
        data_adapter._last_tick_time = 0.0
        await data_adapter.get_ltp({"NSE_EQ": ["11536"]})
        assert data_adapter._last_tick_time > 0.0


class TestFeedRequestCodes:
    """Dhan WS v2 accepts only request codes 15/17/21 (corrected fact 2)."""

    @pytest.mark.asyncio
    async def test_subscribe_ticks_uses_v2_request_code(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanContext"
        ) as mock_ctx_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
        ) as mock_client_cls:
            mock_ctx_cls.return_value = MagicMock()
            mock_client_cls.return_value = _make_mock_dhanhq()
            adapter = DhanDataAdapter(client_id=MOCK_CLIENT_ID, access_token=MOCK_API_KEY)
            adapter._dhan = mock_client_cls.return_value

            loop = asyncio.get_running_loop()
            with patch.object(loop, "run_in_executor") as mock_rie:
                ok = await adapter.subscribe_ticks(["11536"], lambda t: None)

            assert ok is True
            supervisor, instruments = mock_rie.call_args.args[1:]
            assert supervisor == adapter._feed_supervisor
            assert ("NSE_EQ", "11536", 15) in instruments

    @pytest.mark.asyncio
    async def test_subscribe_bars_uses_v2_request_code(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanContext"
        ) as mock_ctx_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
        ) as mock_client_cls:
            mock_ctx_cls.return_value = MagicMock()
            mock_client_cls.return_value = _make_mock_dhanhq()
            adapter = DhanDataAdapter(client_id=MOCK_CLIENT_ID, access_token=MOCK_API_KEY)
            adapter._dhan = mock_client_cls.return_value

            loop = asyncio.get_running_loop()
            with patch.object(loop, "run_in_executor") as mock_rie:
                ok = await adapter.subscribe_bars(["11536"], "1", lambda b: None)

            assert ok is True
            supervisor, instruments = mock_rie.call_args.args[1:]
            assert supervisor == adapter._feed_supervisor
            assert ("NSE_EQ", "11536", 21) in instruments

    @pytest.mark.asyncio
    async def test_start_ws_feed_blocked_by_entitlement_error(self) -> None:
        """806 entitlement must gate feed start — never loop."""
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanContext"
        ) as mock_ctx_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
        ) as mock_client_cls:
            mock_ctx_cls.return_value = MagicMock()
            mock_client_cls.return_value = _make_mock_dhanhq()
            adapter = DhanDataAdapter(client_id=MOCK_CLIENT_ID, access_token=MOCK_API_KEY)
            adapter.entitlement_error = True
            ok = await adapter.subscribe_ticks(["11536"], lambda t: None)
            assert ok is False


class TestDataAccessTokenFallback:
    """Data API token fallback slot and 806 entitlement surfacing."""

    @pytest.mark.asyncio
    async def test_data_token_preferred_over_primary(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanContext"
        ) as mock_ctx_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
        ) as mock_client_cls:
            mock_ctx_cls.return_value = MagicMock()
            mock_client_cls.return_value = _make_mock_dhanhq()
            DhanDataAdapter(
                client_id=MOCK_CLIENT_ID,
                access_token="primary_token",
                data_access_token="data_token",
            )
            _, kwargs = mock_ctx_cls.call_args
            assert kwargs["access_token"] == "data_token"

    @pytest.mark.asyncio
    async def test_806_returns_entitlement_error_dict(self, data_adapter) -> None:
        """The raising path still classifies 806 (transport exceptions)."""
        dhan = data_adapter._dhan
        dhan.option_chain.side_effect = RuntimeError("806: token rejected")
        result = await data_adapter.get_option_chain(
            underlying_scrip="13", exchange_segment="NSE_FNO", expiry="",
        )
        assert result["status"] == "error"
        assert result.get("entitlement") is True
        assert "subscribe to Data APIs" in result["message"]

    @pytest.mark.asyncio
    async def test_806_failure_dict_returns_entitlement_error(self, data_adapter) -> None:
        """dhanhq never raises on HTTP errors — model its failure-dict contract."""
        dhan = data_adapter._dhan
        dhan.option_chain.return_value = {
            "status": "failure",
            "remarks": {
                "error_code": 806,
                "error_type": "HTTP 806",
                "error_message": "Subscribe to Data APIs to continue",
            },
            "data": "",
        }
        result = await data_adapter.get_option_chain(
            underlying_scrip="13", exchange_segment="NSE_FNO", expiry="",
        )
        assert result["status"] == "error"
        assert result.get("entitlement") is True
        assert "subscribe to Data APIs" in result["message"]
        assert data_adapter.entitlement_error is True

    @pytest.mark.asyncio
    async def test_failure_dict_non_entitlement_returns_remarks_message(self, data_adapter) -> None:
        """Non-806 failures surface the remarks message as an error dict."""
        dhan = data_adapter._dhan
        dhan.option_chain.return_value = {
            "status": "failure",
            "remarks": {
                "error_code": 429,
                "error_type": "HTTP 429",
                "error_message": "Rate limit exceeded",
            },
            "data": "",
        }
        result = await data_adapter.get_option_chain(
            underlying_scrip="13", exchange_segment="NSE_FNO", expiry="",
        )
        assert result["status"] == "error"
        assert result.get("entitlement") is not True
        assert "Rate limit exceeded" in result["message"]

    @pytest.mark.asyncio
    async def test_failure_dict_string_remarks(self, data_adapter) -> None:
        """Transport-exception remarks arrive as a plain string, not a dict."""
        dhan = data_adapter._dhan
        dhan.ticker_data.return_value = {
            "status": "failure",
            "remarks": "Subscribe to Data APIs to continue",
            "data": "",
        }
        result = await data_adapter.get_ltp({"NSE_EQ": ["11536"]})
        assert result["status"] == "error"
        assert result.get("entitlement") is True

    def test_806_marks_entitlement_flag(self, data_adapter) -> None:
        data_adapter._mark_ws_error(
            RuntimeError("Disconnected: Subscribe to Data APIs to continue")
        )
        assert data_adapter.entitlement_error is True
        assert data_adapter.last_error == "subscribe to Data APIs"


class _ScriptedFeed:
    """Minimal MarketFeed stand-in that drives the adapter's SDK callbacks.

    `default_events` is a shared list of (kind, code) steps consumed by each
    constructed instance; instances after the first see whatever remains.
    """

    default_events: list = []
    instances: list = []

    def __init__(self, **kwargs: object) -> None:
        self.on_connect = kwargs["on_connect"]
        self.on_message = kwargs["on_message"]
        self.on_close = kwargs["on_close"]
        self.on_error = kwargs["on_error"]
        self.last_disconnect_code: int | None = None
        self._running: bool = True
        self.run_calls: int = 0
        self.events: list = _ScriptedFeed.default_events
        _ScriptedFeed.instances.append(self)

    def run(self) -> None:
        self.run_calls += 1
        if not self.events:
            return
        kind, code = self.events.pop(0)
        if kind == "close":
            self.last_disconnect_code = code
            self.on_close(self)
        elif kind == "error":
            self.last_disconnect_code = code
            self.on_error(self, RuntimeError("ws dropped"))


class TestDisconnectCodePolicy:
    """Task 2: disconnect-code-aware reconnect policy for the WS feed."""

    def test_classify_disconnect_codes(self) -> None:
        assert DhanDataAdapter._classify_disconnect(806) == "entitlement"
        assert DhanDataAdapter._classify_disconnect(807) == "renew"
        assert DhanDataAdapter._classify_disconnect(805) == "retry"
        assert DhanDataAdapter._classify_disconnect(808) == "retry"
        assert DhanDataAdapter._classify_disconnect(809) == "retry"
        assert DhanDataAdapter._classify_disconnect(None) == "retry"

    def test_reconnect_delay_backoff_caps(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.random.uniform",
            return_value=0.0,
        ):
            assert DhanDataAdapter._reconnect_delay(1) == 1.0
            assert DhanDataAdapter._reconnect_delay(2) == 2.0
            assert DhanDataAdapter._reconnect_delay(3) == 4.0
            assert DhanDataAdapter._reconnect_delay(4) == 8.0
            assert DhanDataAdapter._reconnect_delay(5) == 8.0
            assert DhanDataAdapter._reconnect_delay(10) == 8.0
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.random.uniform",
            return_value=0.5,
        ):
            assert DhanDataAdapter._reconnect_delay(4) == 8.5

    def test_supervisor_stops_on_806_entitlement(self, data_adapter) -> None:
        """806 must stop the reconnect loop — never re-create the feed."""
        _ScriptedFeed.default_events = [("close", 806)]
        _ScriptedFeed.instances = []
        with patch(
            "shettyxtreme.integration.dhan.data_adapter._DisconnectAwareFeed",
            _ScriptedFeed,
        ):
            data_adapter._feed_active = True
            data_adapter._feed_supervisor([("NSE_EQ", "11536", 15)])
        assert data_adapter.entitlement_error is True
        assert data_adapter.last_error == "subscribe to Data APIs"
        assert len(_ScriptedFeed.instances) == 1
        assert _ScriptedFeed.instances[0].run_calls == 1
        assert data_adapter._feed is None

    def test_supervisor_routes_807_to_token_renewal(self, data_adapter) -> None:
        """807 must trigger the renewal path instead of blind reconnect."""
        _ScriptedFeed.default_events = [("close", 807)]
        _ScriptedFeed.instances = []
        renewed = MagicMock(return_value=True)
        data_adapter._renew_token_sync = renewed
        data_adapter._reconnect_delay = lambda attempt: 1.0 * attempt
        waits: list[float] = []

        def _wait(delay: float) -> bool:
            waits.append(delay)
            return len(waits) >= 2

        data_adapter._feed_stop.wait = _wait
        with patch(
            "shettyxtreme.integration.dhan.data_adapter._DisconnectAwareFeed",
            _ScriptedFeed,
        ):
            data_adapter._feed_active = True
            data_adapter._feed_supervisor([("NSE_EQ", "11536", 15)])
        renewed.assert_called_once()
        assert data_adapter.entitlement_error is False
        # Reconnects happened with backoff waits (not a blind 1s loop).
        assert waits == [1.0, 2.0]
        assert data_adapter._feed is None

    def test_supervisor_backs_off_on_transient_drop(self, data_adapter) -> None:
        """805 + plain drops must reconnect with backoff, not flap on 806."""
        _ScriptedFeed.default_events = [("close", 805), ("error", None)]
        _ScriptedFeed.instances = []
        data_adapter._reconnect_delay = lambda attempt: 1.0 * attempt
        delays: list[float] = []

        def _wait(delay: float) -> bool:
            delays.append(delay)
            return len(delays) >= 2

        data_adapter._feed_stop.wait = _wait
        with patch(
            "shettyxtreme.integration.dhan.data_adapter._DisconnectAwareFeed",
            _ScriptedFeed,
        ):
            data_adapter._feed_active = True
            data_adapter._feed_supervisor([("NSE_EQ", "11536", 15)])
        assert delays == [1.0, 2.0]
        assert data_adapter.entitlement_error is False
        assert len(_ScriptedFeed.instances) == 2

    def test_local_close_is_not_treated_as_flapping(self, data_adapter) -> None:
        """Client-initiated close must not stop the loop or classify codes."""

        class _PlainFeed:
            def __init__(self) -> None:
                self._running = True

        feed = _PlainFeed()
        data_adapter._local_close = True
        data_adapter._on_close_cb(feed)
        assert feed._running is True
        assert data_adapter._ws_connected is False
        data_adapter._local_close = False
        data_adapter._on_close_cb(feed)
        assert feed._running is False


class TestDataTokenRenewal:
    """Task 3: data-side 807 renewal mints + persists a fresh token."""

    def test_renew_token_sync_persists_primary(self, data_adapter) -> None:
        store = MagicMock()
        data_adapter._credential_store = store
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanLogin"
        ) as mock_login_cls:
            mock_login_cls.return_value.renew_token.return_value = {
                "accessToken": "renewed_primary_1",
            }
            ok = data_adapter._renew_token_sync()
        assert ok is True
        assert data_adapter._access_token == "renewed_primary_1"
        store.update_token.assert_called_once_with(
            "renewed_primary_1", "", MOCK_CLIENT_ID
        )

    def test_renew_token_sync_persists_data_token(self, data_adapter) -> None:
        """The token IN USE (data fallback) is the one renewed."""
        store = MagicMock()
        data_adapter._data_access_token = "data_old_token"
        data_adapter._credential_store = store
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanLogin"
        ) as mock_login_cls:
            mock_login_cls.return_value.renew_token.return_value = {
                "accessToken": "renewed_data_2",
            }
            ok = data_adapter._renew_token_sync()
        assert ok is True
        assert data_adapter._data_access_token == "renewed_data_2"
        assert data_adapter._access_token == MOCK_API_KEY
        store.update_data_token.assert_called_once_with("renewed_data_2", "")
        store.update_token.assert_not_called()

    def test_renew_token_sync_failure_returns_false(self, data_adapter) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanLogin"
        ) as mock_login_cls:
            mock_login_cls.return_value.renew_token.side_effect = RuntimeError("boom")
            assert data_adapter._renew_token_sync() is False

    def test_renew_token_sync_no_token_in_response(self, data_adapter) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanLogin"
        ) as mock_login_cls:
            mock_login_cls.return_value.renew_token.return_value = {
                "status": "failure",
            }
            assert data_adapter._renew_token_sync() is False


class TestTickSymbolResolution:
    """Tests for _display_symbol and _process_ws_tick dispatch."""

    def test_display_symbol_resolves_known_id(self, data_adapter) -> None:
        data_adapter.set_symbol_map({"13": "NIFTY"})
        assert data_adapter._display_symbol("13") == "NIFTY"

    def test_display_symbol_falls_back_to_raw_id(self, data_adapter) -> None:
        data_adapter.set_symbol_map({"13": "NIFTY"})
        assert data_adapter._display_symbol("999") == "999"

    def test_process_ws_tick_raw_key_callback(self, data_adapter) -> None:
        """A callback registered under the raw ID must receive the resolved symbol."""
        data_adapter.set_symbol_map({"13": "NIFTY"})
        received: list = []
        display_fired: list = []
        data_adapter._tick_callbacks["13"] = lambda tick: received.append(tick)
        data_adapter._tick_callbacks["NIFTY"] = lambda tick: display_fired.append(tick)
        data_adapter._process_ws_tick(
            {
                "security_id": "13",
                "exchange_segment": "NSE_FNO",
                "ltp": 24500.5,
                "volume": 1000,
                "tt": 1700000000000,
            }
        )
        assert len(received) == 1
        assert received[0].symbol == "NIFTY"
        assert received[0].ltp == 24500.5
        assert len(display_fired) == 0

    def test_process_ws_tick_resolved_name_callback(self, data_adapter) -> None:
        """A callback under the display name must fire when the raw key misses."""
        data_adapter.set_symbol_map({"13": "NIFTY"})
        received: list = []
        data_adapter._tick_callbacks["NIFTY"] = lambda tick: received.append(tick)
        data_adapter._process_ws_tick(
            {
                "security_id": "13",
                "exchange_segment": "NSE_FNO",
                "ltp": 24500.5,
                "volume": 1000,
            }
        )
        assert len(received) == 1
        assert received[0].symbol == "NIFTY"

    def test_process_ws_tick_no_callback_no_crash(self, data_adapter) -> None:
        """Unknown security IDs with no registered callback are dropped safely."""
        data_adapter.set_symbol_map({"13": "NIFTY"})
        data_adapter._process_ws_tick(
            {"security_id": "777", "exchange_segment": "NSE_EQ", "ltp": 100.0}
        )

    def test_dhan_client_property(self, data_adapter) -> None:
        """dhan_client should expose the underlying DhanHQ client."""
        assert data_adapter.dhan_client is data_adapter._dhan
