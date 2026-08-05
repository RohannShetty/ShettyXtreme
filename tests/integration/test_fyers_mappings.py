"""F2 — Fyers order mapping tests.

Pins the internal <-> Fyers wire-value maps: order type (SL -> 4 SL-L,
SL-M -> 3), product (MIS -> INTRADAY, NRML -> MARGIN), side (1/-1), validity,
and the Fyers order status -> internal OrderStatus decoding.
"""
from __future__ import annotations

import pytest

from shettyxtreme.core.data_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)
from shettyxtreme.integration.fyers.mappings import (
    ORDER_STATUS_MAP,
    ORDER_TYPE_MAP,
    ORDER_TYPE_TO_INTERNAL,
    PRODUCT_TYPE_MAP,
    PRODUCT_TYPE_TO_INTERNAL,
    SIDE_MAP,
    SIDE_TO_INTERNAL,
    VALIDITY_MAP,
    VALIDITY_TO_INTERNAL,
    fyers_order_status,
    parse_order_type,
    parse_product_type,
    parse_side,
    parse_validity,
)


class TestOrderType:
    def test_forward(self) -> None:
        assert ORDER_TYPE_MAP[OrderType.MARKET] == 2
        assert ORDER_TYPE_MAP[OrderType.LIMIT] == 1
        assert ORDER_TYPE_MAP[OrderType.SL] == 4  # SL-L (stop-loss limit)
        assert ORDER_TYPE_MAP[OrderType.SL_M] == 3

    def test_sl_market_still_maps_to_code_3(self) -> None:
        """SL_M (stop-loss market) keeps Fyers code 3 — only SL moved to 4."""
        assert ORDER_TYPE_MAP[OrderType.SL_M] == 3

    def test_reverse(self) -> None:
        assert ORDER_TYPE_TO_INTERNAL[1] is OrderType.LIMIT
        assert ORDER_TYPE_TO_INTERNAL[2] is OrderType.MARKET
        assert ORDER_TYPE_TO_INTERNAL[3] is OrderType.SL_M
        assert ORDER_TYPE_TO_INTERNAL[4] is OrderType.SL

    def test_parse_accepts_strings(self) -> None:
        assert parse_order_type("2") is OrderType.MARKET
        assert parse_order_type(3) is OrderType.SL_M


class TestProductType:
    def test_forward(self) -> None:
        assert PRODUCT_TYPE_MAP[ProductType.CNC] == "CNC"
        assert PRODUCT_TYPE_MAP[ProductType.MIS] == "INTRADAY"
        assert PRODUCT_TYPE_MAP[ProductType.NRML] == "MARGIN"

    def test_reverse(self) -> None:
        assert PRODUCT_TYPE_TO_INTERNAL["CNC"] is ProductType.CNC
        assert PRODUCT_TYPE_TO_INTERNAL["INTRADAY"] is ProductType.MIS
        assert PRODUCT_TYPE_TO_INTERNAL["MARGIN"] is ProductType.NRML

    def test_parse(self) -> None:
        assert parse_product_type("MARGIN") is ProductType.NRML


class TestSide:
    def test_forward(self) -> None:
        assert SIDE_MAP[OrderSide.BUY] == 1
        assert SIDE_MAP[OrderSide.SELL] == -1

    def test_reverse(self) -> None:
        assert SIDE_TO_INTERNAL[1] is OrderSide.BUY
        assert SIDE_TO_INTERNAL[-1] is OrderSide.SELL

    def test_parse_accepts_strings(self) -> None:
        assert parse_side("-1") is OrderSide.SELL


class TestValidity:
    def test_round_trip(self) -> None:
        assert VALIDITY_MAP["DAY"] == "DAY"
        assert VALIDITY_MAP["IOC"] == "IOC"
        assert VALIDITY_TO_INTERNAL["DAY"] == "DAY"
        assert VALIDITY_TO_INTERNAL["IOC"] == "IOC"
        assert parse_validity("IOC") == "IOC"


class TestOrderStatus:
    def test_status_codes(self) -> None:
        assert ORDER_STATUS_MAP[1] is OrderStatus.CANCELLED
        assert ORDER_STATUS_MAP[2] is OrderStatus.OPEN
        assert ORDER_STATUS_MAP[3] is OrderStatus.FILLED
        assert ORDER_STATUS_MAP[4] is OrderStatus.PENDING
        assert ORDER_STATUS_MAP[5] is OrderStatus.PENDING
        assert ORDER_STATUS_MAP[6] is OrderStatus.PENDING
        assert ORDER_STATUS_MAP[7] is OrderStatus.REJECTED
        assert ORDER_STATUS_MAP[8] is OrderStatus.PARTIALLY_FILLED
        assert ORDER_STATUS_MAP[9] is OrderStatus.OPEN
        assert ORDER_STATUS_MAP[10] is OrderStatus.CANCELLED

    def test_parser_accepts_int_and_str(self) -> None:
        assert fyers_order_status(3) is OrderStatus.FILLED
        assert fyers_order_status("3") is OrderStatus.FILLED

    def test_parser_unknown_code_falls_back_to_pending(self) -> None:
        assert fyers_order_status(999) is OrderStatus.PENDING
        assert fyers_order_status(None) is OrderStatus.PENDING


class TestCoverage:
    def test_every_internal_order_type_has_a_wire_value(self) -> None:
        for order_type in OrderType:
            assert ORDER_TYPE_MAP[order_type] is not None

    def test_every_internal_product_has_a_wire_value(self) -> None:
        for product in ProductType:
            assert PRODUCT_TYPE_MAP[product] is not None
