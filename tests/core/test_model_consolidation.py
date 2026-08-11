"""F-CORE-001 regression tests: model consolidation (interfaces == data_models).

Verifies the consolidation contract:
  - every divergent model pair is now ONE class across both import paths
    (``core.interfaces`` re-exports the canonical ``core.data_models`` class,
    so ``isinstance`` dispatch works on either side of the bus);
  - ``oi`` rides the canonical Tick through the bus bridge (no silent drop);
  - the placement request (``OrderRequest``) and the order record (``Order``)
    stay distinct names with distinct shapes;
  - ``OrderStatus`` is str-compatible so enum and plain-string statuses
    compare equal in either direction;
  - ``Position`` keeps both the interfaces fields (day buy/sell qty) and the
    data_models 9-arg positional construction.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shettyxtreme.core import data_models
from shettyxtreme.core import interfaces
from shettyxtreme.core.data_models import (
    Bar,
    Holding,
    Order,
    OrderBook,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Tick,
)
from shettyxtreme.core.interfaces import order_executor as interfaces_order_executor
from shettyxtreme.core.interfaces import market_data_stream as interfaces_mds


# ---------------------------------------------------------------------------
# Pair unification: one class per model, both import paths
# ---------------------------------------------------------------------------

class TestPairUnification:
    def test_tick_is_one_class(self) -> None:
        assert interfaces.Tick is data_models.Tick
        assert interfaces_mds.Tick is Tick

    def test_bar_is_one_class(self) -> None:
        assert interfaces.Bar is data_models.Bar
        assert interfaces_mds.Bar is Bar

    def test_position_is_one_class(self) -> None:
        assert interfaces.Position is data_models.Position
        assert interfaces.account_info.Position is Position

    def test_order_result_is_one_class(self) -> None:
        assert interfaces.OrderResult is data_models.OrderResult
        assert interfaces_order_executor.OrderResult is OrderResult

    def test_holding_and_order_book_are_canonical_in_data_models(self) -> None:
        assert interfaces.Holding is data_models.Holding
        assert interfaces.OrderBook is data_models.OrderBook
        assert Holding is data_models.Holding
        assert OrderBook is data_models.OrderBook

    def test_interfaces_reexports_full_data_model_surface(self) -> None:
        for name in ("Tick", "Bar", "Position", "Order", "OrderRequest",
                     "OrderResult", "OrderSide", "OrderType", "ProductType",
                     "OrderStatus", "Holding", "OrderBook", "Fill", "Trade"):
            assert getattr(interfaces, name) is getattr(data_models, name)

    def test_isinstance_dispatch_works_across_import_paths(self) -> None:
        # An instance built from the data_models class must satisfy an
        # isinstance check against the interfaces name, and vice versa.
        tick = Tick(
            symbol="NIFTY", exchange="NFO", ltp=18000.0, volume=100,
            timestamp=datetime.now(UTC),
        )
        assert isinstance(tick, interfaces.Tick)
        assert isinstance(tick, interfaces_mds.Tick)


# ---------------------------------------------------------------------------
# oi flows through the canonical Tick and the bus bridge
# ---------------------------------------------------------------------------

class TestOiFlow:
    def test_canonical_tick_has_oi(self) -> None:
        tick = Tick(
            symbol="NIFTY", exchange="NFO", ltp=18000.0, volume=100,
            timestamp=datetime.now(UTC), oi=123456,
        )
        assert tick.oi == 123456

    def test_interfaces_tick_defaults_oi_none(self) -> None:
        tick = interfaces.Tick(
            symbol="NIFTY", exchange="NFO", ltp=18000.0, volume=100,
            timestamp=datetime.now(UTC),
        )
        assert tick.oi is None

    def test_to_bus_tick_preserves_oi(self) -> None:
        """The bus bridge must no longer drop oi (the F-CORE-001 bug)."""
        from shettyxtreme.terminal.api.terminal_init import _to_bus_tick

        tick = interfaces.Tick(
            symbol="NIFTY", exchange="NFO", ltp=18000.0, volume=100,
            timestamp=datetime.now(UTC), oi=98765,
        )
        bus_tick = _to_bus_tick(tick)
        assert isinstance(bus_tick, Tick)
        assert bus_tick.oi == 98765
        # Pass-through: the very same instance (isinstance dispatch no-op).
        assert bus_tick is tick


# ---------------------------------------------------------------------------
# OrderRequest (placement) vs Order (record)
# ---------------------------------------------------------------------------

class TestOrderRequestVsOrder:
    def test_order_request_is_the_placement_shape(self) -> None:
        req = OrderRequest(
            symbol="NIFTY", exchange="NFO", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=75,
        )
        assert req.side == OrderSide.BUY
        assert req.order_type == OrderType.MARKET
        assert req.product == ProductType.MIS
        # A request has no broker lifecycle fields.
        assert not hasattr(req, "order_id")
        assert not hasattr(req, "status")

    def test_order_is_the_record_shape(self) -> None:
        rec = Order(
            order_id="PAPER1", symbol="NIFTY", exchange="NFO", side="BUY",
            order_type="MARKET", quantity=75, price=18000.0, status="FILLED",
        )
        assert rec.order_id == "PAPER1"
        assert rec.status == "FILLED"
        assert rec.created_at is not None

    def test_order_request_and_order_are_distinct_classes(self) -> None:
        assert OrderRequest is not Order
        assert not hasattr(OrderRequest, "order_id")
        assert not hasattr(Order, "client_id")

    def test_protocol_signature_uses_order_request(self) -> None:
        sig = interfaces_order_executor.OrderExecutor.place_order.__annotations__
        assert sig["order"] is OrderRequest
        assert sig["return"] is OrderResult


# ---------------------------------------------------------------------------
# OrderResult unification (enum vs str status)
# ---------------------------------------------------------------------------

class TestOrderResultUnification:
    def test_rejected_reason_field_exists(self) -> None:
        result = OrderResult(
            order_id="O1", status=OrderStatus.REJECTED, message="bad qty",
            rejected_reason="bad qty",
        )
        assert result.rejected_reason == "bad qty"

    def test_order_status_is_str_compatible(self) -> None:
        # enum == str in both directions (the paper engine passes plain
        # strings; the execution layer passes enum members).
        assert OrderStatus.REJECTED == "REJECTED"
        assert "REJECTED" == OrderStatus.REJECTED
        assert OrderStatus.OPEN == "OPEN"

    def test_str_status_result_compares_to_enum(self) -> None:
        result = OrderResult(order_id="", status="REJECTED")
        assert result.status == OrderStatus.REJECTED

    def test_enum_status_result_compares_to_str(self) -> None:
        result = OrderResult(order_id="", status=OrderStatus.REJECTED)
        assert result.status == "REJECTED"


# ---------------------------------------------------------------------------
# Position unification (field-merge, both construction styles)
# ---------------------------------------------------------------------------

class TestPositionUnification:
    def test_position_has_day_quantities(self) -> None:
        pos = Position(
            symbol="SBIN", exchange="NSE", quantity=100, buy_avg=480.0,
            sell_avg=0.0, net_quantity=100, m2m=500.0, pnl=200.0,
            product="INTRADAY", day_buy_quantity=100, day_sell_quantity=0,
        )
        assert pos.day_buy_quantity == 100
        assert pos.day_sell_quantity == 0

    def test_position_9_arg_positional_construction_still_works(self) -> None:
        # The data_models construction style used by tests/wave2 must not
        # break now that the interfaces fields were merged in (appended).
        pos = Position("A", "NSE", 75, 100, 0, 75, 0, 0, "NRML")
        assert pos.symbol == "A"
        assert pos.net_quantity == 75
        assert pos.product == "NRML"
        assert pos.day_buy_quantity == 0
        assert pos.day_sell_quantity == 0

    def test_interfaces_position_construction_works(self) -> None:
        pos = interfaces.Position(
            symbol="SBIN", exchange="NSE", quantity=100, buy_avg=480.0,
            sell_avg=0.0, net_quantity=100, day_buy_quantity=100,
            day_sell_quantity=0, m2m=500.0, pnl=200.0, product="INTRADAY",
        )
        assert isinstance(pos, data_models.Position)
        assert pos.day_buy_quantity == 100


# ---------------------------------------------------------------------------
# Enum identity across import paths
# ---------------------------------------------------------------------------

class TestEnumIdentity:
    def test_enums_are_one_class(self) -> None:
        assert interfaces.OrderSide is data_models.OrderSide
        assert interfaces.OrderType is data_models.OrderType
        assert interfaces.ProductType is data_models.ProductType
        assert interfaces.OrderStatus is data_models.OrderStatus

    def test_enum_member_lookup_by_name_and_value(self) -> None:
        assert OrderStatus["FILLED"] is OrderStatus.FILLED
        assert OrderStatus("FILLED") is OrderStatus.FILLED
        assert OrderType["SL_M"] is OrderType.SL_M

    def test_bar_fields_unchanged(self) -> None:
        bar = Bar(
            symbol="NIFTY", exchange="NFO", timeframe="1m", open=1.0,
            high=2.0, low=0.5, close=1.5, volume=100,
            timestamp=datetime.now(UTC), oi=10,
        )
        assert bar.timeframe == "1m"
        assert bar.oi == 10


@pytest.mark.parametrize("model_name", [
    "Tick", "Bar", "Position", "Order", "OrderResult", "Holding", "OrderBook",
])
def test_no_duplicate_class_identity(model_name: str) -> None:
    """Guard against a regression that re-introduces divergent pairs."""
    interfaces_cls = getattr(interfaces, model_name)
    data_models_cls = getattr(data_models, model_name)
    assert interfaces_cls is data_models_cls
