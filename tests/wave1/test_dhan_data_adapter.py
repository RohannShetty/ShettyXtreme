"""Tests for DhanDataAdapter: staleness, error 806, OHLC, option chain.

Mocks the dhanhq DhanContext and dhanhq client module so no real API calls.
"""
from __future__ import annotations

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
            client_id=MOCK_CLIENT_ID, api_key=MOCK_API_KEY,
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
            underlying_scrip="13",
            exchange_segment="NSE_FNO",
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
