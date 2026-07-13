"""Tests for DhanTradingAdapter and SessionHealth."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from shettyxtreme.core.interfaces.order_executor import (
    Order, OrderSide, OrderStatus, OrderType, ProductType,
)
from shettyxtreme.integration.dhan.trading_adapter import (
    DhanTradingAdapter, SessionHealth,
)

MOCK_CLIENT_ID = "test_client_001"
MOCK_ACCESS_TOKEN = "test_token_abc123"


def _make_mock_dhanhq() -> None:
    dhan_mock = MagicMock()
    dhan_mock.place_order.return_value = {
        "status": "success", "orderId": "DHAN_ORD_123",
    }
    dhan_mock.get_positions.return_value = [
        {
            "securityId": "11536", "exchangeSegment": "NSE_EQ",
            "quantity": 100, "buyAvg": 1950.0, "sellAvg": 0,
            "netQty": 100, "dayBuyQty": 100, "daySellQty": 0,
            "mtm": 500.0, "realizedProfit": 200.0,
            "productType": "MIS",
        },
    ]
    dhan_mock.get_fund_limits.return_value = {
        "status": "success",
        "data": {"available": 500000.0, "used": 50000.0},
    }
    return dhan_mock


@pytest.fixture
def trading_adapter() -> None:
    with patch(
        "shettyxtreme.integration.dhan.trading_adapter.DhanContext"
    ) as mock_ctx_cls, patch(
        "shettyxtreme.integration.dhan.trading_adapter.DhanHQClient"
    ) as mock_client_cls:
        mock_ctx = MagicMock()
        mock_ctx_cls.return_value = mock_ctx
        mock_dhan = _make_mock_dhanhq()
        mock_client_cls.return_value = mock_dhan
        adapter = DhanTradingAdapter(
            client_id=MOCK_CLIENT_ID, access_token=MOCK_ACCESS_TOKEN,
        )
        adapter._dhan = mock_dhan
        return adapter

class TestSessionHealth:

    def test_init_creates_context(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.trading_adapter.DhanContext"
        ) as mock_ctx_cls:
            mock_ctx = MagicMock()
            mock_ctx_cls.return_value = mock_ctx
            health = SessionHealth(MOCK_CLIENT_ID, MOCK_ACCESS_TOKEN)
            mock_ctx_cls.assert_called_once_with(
                client_id=MOCK_CLIENT_ID, access_token=MOCK_ACCESS_TOKEN
            )
            assert health._context is mock_ctx

    def test_context_property_returns_context(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.trading_adapter.DhanContext"
        ) as mock_ctx_cls:
            mock_ctx = MagicMock()
            mock_ctx_cls.return_value = mock_ctx
            health = SessionHealth(MOCK_CLIENT_ID, MOCK_ACCESS_TOKEN)
            assert health.context is mock_ctx

    def test_mark_success_updates_time(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.trading_adapter.DhanContext"
        ) as mock_ctx_cls:
            mock_ctx_cls.return_value = MagicMock()
            health = SessionHealth(MOCK_CLIENT_ID, MOCK_ACCESS_TOKEN)
            health._last_success_time = 0.0
            health.mark_success()
            assert health._last_success_time > 0.0

    def test_check_and_refresh_no_refresh_needed(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.trading_adapter.DhanContext"
        ) as mock_ctx_cls:
            mock_ctx = MagicMock()
            mock_ctx_cls.return_value = mock_ctx
            health = SessionHealth(MOCK_CLIENT_ID, MOCK_ACCESS_TOKEN)
            result = health.check_and_refresh()
            assert result is False

    def test_check_and_refresh_triggers_refresh_when_stale(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.trading_adapter.DhanContext"
        ) as mock_ctx_cls:
            mock_ctx1 = MagicMock()
            mock_ctx2 = MagicMock()
            mock_ctx_cls.side_effect = [mock_ctx1, mock_ctx2]
            health = SessionHealth(MOCK_CLIENT_ID, MOCK_ACCESS_TOKEN)
            health._last_success_time = time.time() - (21 * 3600)
            result = health.check_and_refresh()
            assert result is True
            assert health._context is mock_ctx2
            assert mock_ctx_cls.call_count == 2

    def test_refresh_force_reinit(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.trading_adapter.DhanContext"
        ) as mock_ctx_cls:
            mock_ctx1 = MagicMock()
            mock_ctx2 = MagicMock()
            mock_ctx_cls.side_effect = [mock_ctx1, mock_ctx2]
            health = SessionHealth(MOCK_CLIENT_ID, MOCK_ACCESS_TOKEN)
            health.refresh()
            assert health._context is mock_ctx2
            assert mock_ctx_cls.call_count == 2


class TestTradingAdapterOrderPlacement:

    @pytest.mark.asyncio
    async def test_place_order_success(self, trading_adapter) -> None:
        order = Order(
            symbol="11536", exchange="NSE", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=100,
            product=ProductType.MIS, validity="DAY",
        )
        result = await trading_adapter.place_order(order)
        dhan = trading_adapter._dhan
        dhan.place_order.assert_called_once()
        assert result.order_id == "DHAN_ORD_123"
        assert result.status == OrderStatus.OPEN

    @pytest.mark.asyncio
    async def test_place_order_passes_correct_params(self, trading_adapter) -> None:
        order = Order(
            symbol="11536", exchange="NFO", side=OrderSide.SELL,
            order_type=OrderType.LIMIT, quantity=50,
            price=2000.0, trigger_price=0.0,
            product=ProductType.NRML, validity="IOC",
            tag="test_tag",
        )
        await trading_adapter.place_order(order)
        dhan = trading_adapter._dhan
        dhan.place_order.assert_called_once()
        call_kwargs = dhan.place_order.call_args.kwargs
        assert call_kwargs["security_id"] == "11536"
        assert call_kwargs["exchange_segment"] == "NSE_FNO"
        assert call_kwargs["transaction_type"] == "SELL"
        assert call_kwargs["quantity"] == 50
        assert call_kwargs["order_type"] == "LIMIT"
        assert call_kwargs["product_type"] == "NRML"
        assert call_kwargs["price"] == 2000.0
        assert call_kwargs["validity"] == "IOC"
        assert call_kwargs["tag"] == "test_tag"

    @pytest.mark.asyncio
    async def test_place_order_rejected_on_api_error(self, trading_adapter) -> None:
        dhan = trading_adapter._dhan
        dhan.place_order.return_value = {
            "status": "error", "message": "Insufficient margin",
        }
        order = Order(
            symbol="11536", exchange="NSE", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=100,
        )
        result = await trading_adapter.place_order(order)
        assert result.status == OrderStatus.REJECTED
        assert "Insufficient margin" in (result.rejected_reason or "")

    @pytest.mark.asyncio
    async def test_place_order_handles_exception(self, trading_adapter) -> None:
        dhan = trading_adapter._dhan
        dhan.place_order.side_effect = RuntimeError("Connection lost")
        order = Order(
            symbol="11536", exchange="NSE", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=100,
        )
        result = await trading_adapter.place_order(order)
        assert result.status == OrderStatus.REJECTED
        assert "Connection lost" in result.message


class TestTradingAdapterPositions:

    @pytest.mark.asyncio
    async def test_get_positions_returns_list(self, trading_adapter) -> None:
        positions = await trading_adapter.get_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "11536"
        assert pos.exchange == "NSE_EQ"
        assert pos.quantity == 100
        assert pos.buy_avg == 1950.0
        assert pos.net_quantity == 100
        assert pos.m2m == 500.0
        assert pos.product == "MIS"

    @pytest.mark.asyncio
    async def test_get_positions_handles_dict_response(self, trading_adapter) -> None:
        dhan = trading_adapter._dhan
        dhan.get_positions.return_value = {
            "data": [
                {
                    "securityId": "12345", "exchangeSegment": "BSE_EQ",
                    "quantity": 200, "buyAvg": 100.0, "sellAvg": 0,
                    "netQty": 200, "dayBuyQty": 200, "daySellQty": 0,
                    "mtm": -50.0, "realizedProfit": 0,
                    "productType": "NRML",
                },
            ]
        }
        positions = await trading_adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "12345"
        assert positions[0].exchange == "BSE_EQ"

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, trading_adapter) -> None:
        dhan = trading_adapter._dhan
        dhan.get_positions.return_value = []
        positions = await trading_adapter.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_exception_returns_empty(self, trading_adapter) -> None:
        dhan = trading_adapter._dhan
        dhan.get_positions.side_effect = RuntimeError("API error")
        positions = await trading_adapter.get_positions()
        assert positions == []


class TestTradingAdapterMargin:

    @pytest.mark.asyncio
    async def test_get_margin_returns_data(self, trading_adapter) -> None:
        result = await trading_adapter.get_margin()
        assert "available" in result
        assert result["available"] == 500000.0

    @pytest.mark.asyncio
    async def test_get_margin_handles_no_data_key(self, trading_adapter) -> None:
        dhan = trading_adapter._dhan
        dhan.get_fund_limits.return_value = {"available": 100000.0, "used": 0}
        result = await trading_adapter.get_margin()
        assert result["available"] == 100000.0

    @pytest.mark.asyncio
    async def test_get_margin_exception_returns_empty(self, trading_adapter) -> None:
        dhan = trading_adapter._dhan
        dhan.get_fund_limits.side_effect = RuntimeError("API error")
        result = await trading_adapter.get_margin()
        assert result == {}


class TestTradingAdapterConnection:

    @pytest.mark.asyncio
    async def test_is_connected(self, trading_adapter) -> None:
        assert await trading_adapter.is_connected() is True

    @pytest.mark.asyncio
    async def test_disconnect(self, trading_adapter) -> None:
        result = await trading_adapter.disconnect()
        assert result is True
        assert await trading_adapter.is_connected() is False
