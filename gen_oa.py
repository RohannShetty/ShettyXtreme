import os
content = r'''
"""Integration tests for OpenAlgoAdapter with mocked HTTP."""

import pytest
from unittest.mock import MagicMock


class TestOpenAlgoConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self, openalgo_adapter):
        from tests.conftest import MockHttpResponse
        openalgo_adapter._client.set_response(
            "get", MockHttpResponse({"status": "ok"}, 200),
        )
        result = await openalgo_adapter.connect()
        assert result is True

    @pytest.mark.asyncio
    async def test_connect_failure(self, openalgo_adapter):
        from tests.conftest import MockHttpResponse
        openalgo_adapter._client.set_response(
            "get", MockHttpResponse({"error": "down"}, 503),
        )
        result = await openalgo_adapter.connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect(self, openalgo_adapter):
        await openalgo_adapter.disconnect()
        assert openalgo_adapter._client._closed is True

    @pytest.mark.asyncio
    async def test_is_connected(self, openalgo_adapter):
        openalgo_adapter._ws_connected = True
        assert await openalgo_adapter.is_connected() is True
        openalgo_adapter._ws_connected = False
        assert await openalgo_adapter.is_connected() is False


class TestOpenAlgoOrderPlacement:
    @pytest.mark.asyncio
    async def test_place_market_order(self, openalgo_adapter):
        from shettyxtreme.core.interfaces import Order, OrderSide, OrderType, ProductType
        from tests.conftest import MockHttpResponse

        openalgo_adapter._client.set_response(
            "post",
            MockHttpResponse({
                "status": "success", "orderid": "OA12345",
                "message": "Order placed successfully",
            }, 200),
        )
        order = Order(
            symbol="RELIANCE", exchange="NSE",
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            quantity=50, product=ProductType.MIS,
        )
        result = await openalgo_adapter.place_order(order)
        assert result.order_id == "OA12345"
        assert result.status.value == "FILLED"

    @pytest.mark.asyncio
    async def test_place_limit_order(self, openalgo_adapter):
        from shettyxtreme.core.interfaces import Order, OrderSide, OrderType, ProductType
        from tests.conftest import MockHttpResponse

        openalgo_adapter._client.set_response(
            "post",
            MockHttpResponse({
                "status": "success", "orderid": "OA_LIMIT_1",
                "message": "Limit order placed",
            }, 200),
        )
        order = Order(
            symbol="NIFTY", exchange="NFO",
            side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=25, price=18500.0, product=ProductType.NRML,
        )
        result = await openalgo_adapter.place_order(order)
        assert result.order_id == "OA_LIMIT_1"
        assert result.status.value == "FILLED"

    @pytest.mark.asyncio
    async def test_order_rejected(self, openalgo_adapter):
        from shettyxtreme.core.interfaces import Order, OrderSide, OrderType, ProductType
        from tests.conftest import MockHttpResponse

        openalgo_adapter._client.set_response(
            "post",
            MockHttpResponse({
                "status": "error", "orderid": "",
                "message": "Insufficient margin",
            }, 200),
        )
        order = Order(
            symbol="RELIANCE", exchange="NSE",
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            quantity=999999,
        )
        result = await openalgo_adapter.place_order(order)
        assert result.status.value == "REJECTED"


class TestOpenAlgoCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_order_success(self, openalgo_adapter):
        from tests.conftest import MockHttpResponse
        openalgo_adapter._client.set_response(
            "post", MockHttpResponse({"status": "success"}, 200),
        )
        result = await openalgo_adapter.cancel_order("OA12345")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, openalgo_adapter):
        from tests.conftest import MockHttpResponse
        openalgo_adapter._client.set_response(
            "post", MockHttpResponse({}, 404),
        )
        result = await openalgo_adapter.cancel_order("OA_NONEXISTENT")
        assert result is False


class TestOpenAlgoPositions:
    @pytest.mark.asyncio
    async def test_get_positions(self, openalgo_adapter):
        from tests.conftest import MockHttpResponse
        openalgo_adapter._client.set_response(
            "get",
            MockHttpResponse({
                "data": [
                    {
                        "symbol": "NIFTY", "exchange": "NFO",
                        "quantity": 50, "buyavg": 18500.0, "sellavg": 0.0,
                        "netqty": 50, "dayBuyQty": 50, "daySellQty": 0,
                        "m2m": 500.0, "pnl": 500.0, "product": "MIS",
                    }
                ]
            }, 200),
        )
        positions = await openalgo_adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "NIFTY"
        assert positions[0].net_quantity == 50

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, openalgo_adapter):
        from tests.conftest import MockHttpResponse
        openalgo_adapter._client.set_response(
            "get", MockHttpResponse({"data": []}, 200),
        )
        positions = await openalgo_adapter.get_positions()
        assert positions == []


class TestOpenAlgoOrderBook:
    @pytest.mark.asyncio
    async def test_get_order_book(self, openalgo_adapter):
        from tests.conftest import MockHttpResponse
        openalgo_adapter._client.set_response(
            "get",
            MockHttpResponse({
                "data": [
                    {
                        "orderid": "OA_001", "symbol": "RELIANCE",
                        "exchange": "NSE", "side": "BUY",
                        "ordertype": "MARKET", "quantity": 50,
                        "filledqty": 50, "price": 2500.0,
                        "status": "COMPLETE",
                    }
                ]
            }, 200),
        )
        orders = await openalgo_adapter.get_order_book()
        assert len(orders) == 1
        assert orders[0].order_id == "OA_001"
        assert orders[0].filled_quantity == 50


class TestOpenAlgoErrorHandling:
    @pytest.mark.asyncio
    async def test_http_500(self, openalgo_adapter):
        from shettyxtreme.core.interfaces import Order, OrderSide, OrderType
        from tests.conftest import MockHttpResponse
        import httpx

        openalgo_adapter._client.set_response(
            "post", MockHttpResponse({}, 500),
        )
        order = Order(
            symbol="RELIANCE", exchange="NSE",
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            quantity=10,
        )
        with pytest.raises((httpx.HTTPStatusError, Exception)):
            await openalgo_adapter.place_order(order)

    @pytest.mark.asyncio
    async def test_connect_timeout(self, openalgo_adapter):
        openalgo_adapter._client.responses.clear()
        result = await openalgo_adapter.connect()
        assert result is False
'''

with open("tests/integration/test_openalgo_adapter.py", "w") as f:
    f.write(content)
print("test_openalgo_adapter.py written")
