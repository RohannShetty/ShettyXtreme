"""F4 — Fyers trading adapter tests (OrderExecutor + AccountInfo).

The adapter is a thin layer over the F2 transport, so the REST client is
swapped for an ``AsyncMock`` and the real F1 resolver (master-backed) is used
to exercise the exact-match symbol gate.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from shettyxtreme.core.interfaces.order_executor import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)
from shettyxtreme.integration.fyers.client import FyersTokenExpired
from shettyxtreme.integration.fyers.session import FyersSession
from shettyxtreme.integration.fyers.trading_adapter import FyersTradingAdapter

APP_ID = "APP123"
SECRET = "SECRET1"
TOKEN = "TOK9"


def _order(**overrides: Any) -> Order:
    base: dict[str, Any] = dict(
        symbol="SBIN",
        exchange="NSE",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=480.0,
        trigger_price=None,
        product=ProductType.MIS,
        validity="DAY",
    )
    base.update(overrides)
    return Order(**base)


@pytest.fixture
def session() -> FyersSession:
    return FyersSession(app_id=APP_ID, secret_id=SECRET, access_token=TOKEN)


@pytest.fixture
def client() -> AsyncMock:
    c = AsyncMock()
    c.get = AsyncMock(return_value={})
    c.post = AsyncMock(return_value={})
    c.patch = AsyncMock(return_value={})
    c.delete = AsyncMock(return_value={})
    return c


@pytest.fixture
def adapter(session: FyersSession, client: AsyncMock, resolver: Any) -> FyersTradingAdapter:
    return FyersTradingAdapter(session=session, client=client, symbol_resolver=resolver)


class TestPlaceOrder:
    @pytest.mark.asyncio
    async def test_payload_and_result_parsing(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.post.return_value = {"s": "ok", "orderId": "O100"}
        result = await adapter.place_order(_order())

        call = client.post.await_args
        assert call.args[0] == "/orders/sync"
        payload = call.kwargs["json"]
        assert payload["symbol"] == "NSE:SBIN-EQ"
        assert payload["qty"] == 10
        assert payload["type"] == 1  # LIMIT
        assert payload["side"] == 1  # BUY
        assert payload["productType"] == "INTRADAY"
        assert payload["limitPrice"] == 480.0
        assert payload["stopPrice"] == 0.0
        assert payload["validity"] == "DAY"

        assert result.order_id == "O100"
        assert result.status == OrderStatus.OPEN

    @pytest.mark.asyncio
    async def test_sl_market_uses_stop_price(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.post.return_value = {"s": "ok", "orderId": "O101"}
        await adapter.place_order(_order(order_type=OrderType.SL_M, trigger_price=475.0))
        payload = client.post.await_args.kwargs["json"]
        assert payload["type"] == 3  # SL-M
        assert payload["limitPrice"] == 0.0
        assert payload["stopPrice"] == 475.0

    @pytest.mark.asyncio
    async def test_sl_limit_keeps_limit_price(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        """SL must go out as SL-L (type 4) carrying both limit and stop prices.

        Regression for F-INT-001: previously SL mapped to code 3 (SL-M), so
        Fyers dropped the limit price and filled at market after trigger.
        """
        client.post.return_value = {"s": "ok", "orderId": "O102"}
        await adapter.place_order(
            _order(order_type=OrderType.SL, price=480.0, trigger_price=475.0)
        )
        payload = client.post.await_args.kwargs["json"]
        assert payload["type"] == 4  # SL-L (stop-loss limit)
        assert payload["limitPrice"] == 480.0
        assert payload["stopPrice"] == 475.0

    @pytest.mark.asyncio
    async def test_error_response_rejected(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.post.return_value = {"s": "error", "code": -99, "message": "bad qty"}
        result = await adapter.place_order(_order())
        assert result.status == OrderStatus.REJECTED
        assert result.rejected_reason == "bad qty"


class TestModifyOrder:
    @pytest.mark.asyncio
    async def test_modify_payload_has_id_no_side(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.patch.return_value = {"s": "ok", "orderId": "O100"}
        result = await adapter.modify_order(
            "O100", _order(quantity=20, price=485.0)
        )

        call = client.patch.await_args
        assert call.args[0] == "/orders/sync"
        payload = call.kwargs["json"]
        assert payload["id"] == "O100"
        assert payload["qty"] == 20
        assert payload["limitPrice"] == 485.0
        assert "side" not in payload

        assert result.order_id == "O100"
        assert result.status == OrderStatus.OPEN


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_payload(self, adapter: FyersTradingAdapter, client: AsyncMock) -> None:
        client.delete.return_value = {"s": "ok", "code": 200}
        assert await adapter.cancel_order("O100") is True
        call = client.delete.await_args
        assert call.args[0] == "/orders/sync"
        assert call.kwargs["json"] == {"id": "O100"}

    @pytest.mark.asyncio
    async def test_cancel_error_returns_false(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.delete.return_value = {"s": "error", "code": -99}
        assert await adapter.cancel_order("O100") is False


class TestGetOrderStatus:
    @pytest.mark.asyncio
    async def test_status_mapping(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "orderBook": [
                {
                    "id": "O100",
                    "symbol": "NSE:SBIN-EQ",
                    "status": 3,  # Complete -> FILLED
                    "qty": 10,
                    "filledQty": 10,
                    "type": 1,
                    "side": 1,
                    "limitPrice": 480.0,
                    "orderDateTime": 1609744577,
                }
            ],
        }
        result = await adapter.get_order_status("O100")
        assert client.get.await_args.args[0] == "/orders?id=O100"
        assert result.order_id == "O100"
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == 10

    @pytest.mark.asyncio
    async def test_missing_order_rejected(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {"s": "ok", "orderBook": []}
        result = await adapter.get_order_status("O404")
        assert result.order_id == "O404"
        assert result.status == OrderStatus.REJECTED
        assert result.rejected_reason is not None


class TestPositions:
    @pytest.mark.asyncio
    async def test_maps_fyers_fields(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "netPositions": [
                {
                    "symbol": "NSE:SBIN-EQ",
                    "qty": 100,
                    "buyAvg": 480.0,
                    "sellAvg": 0.0,
                    "netQty": 100,
                    "dayBuyQty": 100,
                    "daySellQty": 0,
                    "unrealized_profit": 500.0,
                    "realized_profit": 200.0,
                    "productType": "INTRADAY",
                }
            ],
        }
        positions = await adapter.get_positions()
        assert client.get.await_args.args[0] == "/positions"
        assert len(positions) == 1
        p = positions[0]
        assert p.symbol == "SBIN"
        assert p.exchange == "NSE"
        assert p.quantity == 100
        assert p.net_quantity == 100
        assert p.day_buy_quantity == 100
        assert p.buy_avg == 480.0
        assert p.m2m == 500.0
        assert p.pnl == 200.0
        assert p.product == "INTRADAY"


class TestHoldings:
    @pytest.mark.asyncio
    async def test_maps_fyers_fields(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "holdings": [
                {
                    "symbol": "NSE:SBIN-EQ",
                    "qty": 10,
                    "costPrice": 450.0,
                    "ltp": 480.0,
                    "unrealized_profit": 300.0,
                }
            ],
        }
        holdings = await adapter.get_holdings()
        assert client.get.await_args.args[0] == "/holdings"
        assert len(holdings) == 1
        h = holdings[0]
        assert h.symbol == "SBIN"
        assert h.quantity == 10
        assert h.avg_price == 450.0
        assert h.last_price == 480.0
        assert h.pnl == 300.0


class TestOrderBook:
    @pytest.mark.asyncio
    async def test_maps_fyers_fields(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "orderBook": [
                {
                    "id": "O1",
                    "symbol": "NSE:SBIN-EQ",
                    "side": 1,
                    "type": 1,
                    "qty": 10,
                    "filledQty": 5,
                    "limitPrice": 480.0,
                    "status": 8,  # Partial
                    "orderDateTime": 1609744577,
                }
            ],
        }
        orders = await adapter.get_order_book()
        assert client.get.await_args.args[0] == "/orders"
        assert len(orders) == 1
        o = orders[0]
        assert o.order_id == "O1"
        assert o.symbol == "SBIN"
        assert o.side == "BUY"
        assert o.order_type == "LIMIT"
        assert o.quantity == 10
        assert o.filled_quantity == 5
        assert o.price == 480.0
        assert o.status == "PARTIALLY_FILLED"
        assert o.timestamp == datetime.fromtimestamp(1609744577, tz=UTC)


class TestTradeBook:
    @pytest.mark.asyncio
    async def test_returns_raw_dicts(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "tradeBook": [{"id": "T1", "symbol": "NSE:SBIN-EQ"}, {"id": "T2"}],
        }
        trades = await adapter.get_trade_book()
        assert client.get.await_args.args[0] == "/tradebook"
        assert trades == [{"id": "T1", "symbol": "NSE:SBIN-EQ"}, {"id": "T2"}]


class TestMargin:
    @pytest.mark.asyncio
    async def test_extracts_fund_limit(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get.return_value = {
            "s": "ok",
            "fund_limit": [
                {"title": "Total", "type": 15, "amount": 1000000.0},
                {"title": "Available Balance", "type": 2, "amount": 800000.0},
                {"title": "Margin Used", "type": 8, "amount": 200000.0},
            ],
        }
        margin = await adapter.get_margin()
        assert client.get.await_args.args[0] == "/funds"
        assert margin == {
            "available": 800000.0,
            "utilized": 200000.0,
            "total": 1000000.0,
        }


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_connect_probes_liveness(
        self, adapter: FyersTradingAdapter, session: FyersSession
    ) -> None:
        session.probe_liveness = AsyncMock(return_value=True)
        assert await adapter.connect() is True
        session.probe_liveness.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_false_when_probe_fails(
        self, adapter: FyersTradingAdapter, session: FyersSession
    ) -> None:
        session.probe_liveness = AsyncMock(return_value=False)
        assert await adapter.connect() is False

    @pytest.mark.asyncio
    async def test_disconnect_is_stateless_noop(
        self, adapter: FyersTradingAdapter
    ) -> None:
        assert await adapter.disconnect() is True

    @pytest.mark.asyncio
    async def test_is_connected_delegates_to_session(
        self, adapter: FyersTradingAdapter, session: FyersSession
    ) -> None:
        session.token_expiry = datetime.now(UTC) - timedelta(seconds=1)
        assert await adapter.is_connected() is False
        session.token_expiry = None
        assert await adapter.is_connected() is True


class TestTokenExpiry:
    @pytest.mark.asyncio
    async def test_place_order_returns_rejected_result(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.post = AsyncMock(side_effect=FyersTokenExpired("token expired"))
        result = await adapter.place_order(_order())
        assert result.status == OrderStatus.REJECTED
        assert result.rejected_reason is not None

    @pytest.mark.asyncio
    async def test_get_positions_returns_empty(
        self, adapter: FyersTradingAdapter, client: AsyncMock
    ) -> None:
        client.get = AsyncMock(side_effect=FyersTokenExpired("token expired"))
        assert await adapter.get_positions() == []
        assert await adapter.get_margin() == {}
