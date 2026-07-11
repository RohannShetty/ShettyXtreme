import os
content = r'''
"""Integration tests for DhanAdapter with mocked dhanhq."""

import pytest


class TestDhanAdapterConnection:
    @pytest.mark.asyncio
    async def test_connect_returns_true(self, dhan_adapter):
        result = await dhan_adapter.connect()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_connected_after_init(self, dhan_adapter):
        assert await dhan_adapter.is_connected() is True

    @pytest.mark.asyncio
    async def test_disconnect(self, dhan_adapter):
        await dhan_adapter.disconnect()
        assert dhan_adapter._ws_connected is False


class TestDhanAdapterHistorical:
    @pytest.mark.asyncio
    async def test_get_intraday_bars(self, dhan_adapter):
        result = await dhan_adapter.get_intraday_bars(
            symbol="11536", exchange="NSE",
            inst_type="EQUITY",
            from_date="2024-01-01", to_date="2024-01-05",
            interval=1,
        )
        assert result["status"] == "success"
        assert len(result["data"]) > 0

    @pytest.mark.asyncio
    async def test_get_daily_bars(self, dhan_adapter):
        result = await dhan_adapter.get_daily_bars(
            symbol="11536", exchange="NSE",
            inst_type="EQUITY",
            from_date="2024-01-01", to_date="2024-12-31",
        )
        assert result["status"] == "success"
        assert result["data"][0]["close"] == 100

    @pytest.mark.asyncio
    async def test_get_expired_options(self, dhan_adapter):
        result = await dhan_adapter.get_expired_options(
            underlying="NIFTY", exchange="NFO",
            expiry_flag="NEAR", expiry_code=0,
            strike="50000", option_type="CE",
            fields=["open", "high", "low", "close"],
            from_date="2024-01-01", to_date="2024-01-31",
        )
        assert result["status"] == "success"


class TestDhanAdapterMarketData:
    @pytest.mark.asyncio
    async def test_get_ltp(self, dhan_adapter):
        result = await dhan_adapter.get_ltp({"NSE_EQ": [11536]})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_quotes(self, dhan_adapter):
        result = await dhan_adapter.get_quotes({"NSE_EQ": [11536]})
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_ohlc(self, dhan_adapter):
        result = await dhan_adapter.get_ohlc({"NSE_EQ": [11536]})
        assert result["status"] == "success"


class TestDhanAdapterOptionsChain:
    @pytest.mark.asyncio
    async def test_get_option_chain(self, dhan_adapter):
        result = await dhan_adapter.get_option_chain(
            symbol="NIFTY", exchange="NFO", expiry="28NOV2024",
        )
        assert result["status"] == "success"
        assert len(result["data"]) > 0
        assert result["data"][0]["option_type"] == "CE"


class TestDhanAdapterPortfolio:
    @pytest.mark.asyncio
    async def test_get_positions(self, dhan_adapter):
        positions = await dhan_adapter.get_positions()
        assert len(positions) > 0
        assert positions[0]["symbol"] == "NIFTY"

    @pytest.mark.asyncio
    async def test_get_holdings(self, dhan_adapter):
        holdings = await dhan_adapter.get_holdings()
        assert len(holdings) > 0
        assert holdings[0]["symbol"] == "RELIANCE"

    @pytest.mark.asyncio
    async def test_get_funds(self, dhan_adapter):
        funds = await dhan_adapter.get_funds()
        assert funds["available"] == 50000

    @pytest.mark.asyncio
    async def test_get_tradebook(self, dhan_adapter):
        book = await dhan_adapter.get_tradebook()
        assert book == []


class TestDhanAdapterOrders:
    @pytest.mark.asyncio
    async def test_place_dhan_order(self, dhan_adapter):
        from unittest.mock import MagicMock
        dhan_adapter._dhanhq.order.place_order = MagicMock(
            return_value={"status": "success", "order_id": "DH12345"}
        )
        result = await dhan_adapter.place_dhan_order(
            symbol="11536", exchange="NSE",
            side="BUY", order_type="LIMIT",
            quantity=10, price=2500.0,
        )
        assert result["order_id"] == "DH12345"
'''

with open("tests/integration/test_dhan_adapter.py", "w") as f:
    f.write(content)
print("test_dhan_adapter.py written")
