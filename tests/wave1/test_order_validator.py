"""Tests for OrderValidator.

Tests all valid order combinations pass and invalid combos raise ValueError.
"""
from __future__ import annotations

import pytest

from shettyxtreme.core.interfaces.order_executor import (
    Order,
    OrderSide,
    OrderType,
    ProductType,
)
from shettyxtreme.integration.order_validator import OrderValidator

# ---------------------------------------------------------------------------
# Valid order combinations
# ---------------------------------------------------------------------------

VALID_ORDERS = [
    # (label, symbol, exchange, side, order_type, quantity, price,
    #  trigger_price, product, validity)
    (
        "NSE+BUY+MARKET+MIS+DAY",
        "RELIANCE", "NSE", OrderSide.BUY, OrderType.MARKET, 100,
        None, None, ProductType.MIS, "DAY",
    ),
    (
        "BSE+SELL+LIMIT+NRML+IOC",
        "TATAMOTORS", "BSE", OrderSide.SELL, OrderType.LIMIT, 50,
        500.0, None, ProductType.NRML, "IOC",
    ),
    (
        "NSE+SELL+SL+CNC+DAY",
        "INFY", "NSE", OrderSide.SELL, OrderType.SL, 200,
        1500.0, 1450.0, ProductType.CNC, "DAY",
    ),
    (
        "BSE+BUY+SL_M+MIS+DAY",
        "SBIN", "BSE", OrderSide.BUY, OrderType.SL_M, 75,
        None, 600.0, ProductType.MIS, "DAY",
    ),
    (
        "NSE+BUY+LIMIT+MIS+DAY",
        "HDFCBANK", "NSE", OrderSide.BUY, OrderType.LIMIT, 10,
        1600.0, None, ProductType.MIS, "DAY",
    ),
    (
        "NSE+SELL+MARKET+CNC+DAY",
        "ITC", "NSE", OrderSide.SELL, OrderType.MARKET, 1000,
        None, None, ProductType.CNC, "DAY",
    ),
    (
        "BSE+BUY+MARKET+NRML+IOC",
        "WIPRO", "BSE", OrderSide.BUY, OrderType.MARKET, 25,
        None, None, ProductType.NRML, "IOC",
    ),
]


class TestValidOrders:
    """Test that all valid order combinations pass validation."""

    @pytest.mark.parametrize(
        "label,symbol,exchange,side,order_type,quantity,price,"
        "trigger_price,product,validity",
        VALID_ORDERS,
        ids=[c[0] for c in VALID_ORDERS],
    )
    def test_valid_order_passes(
        self, label, symbol, exchange, side, order_type,
        quantity, price, trigger_price, product, validity,
    ) -> None:
        """Valid order should pass validation returning True."""
        order = Order(
            symbol=symbol, exchange=exchange, side=side,
            order_type=order_type, quantity=quantity,
            price=price, trigger_price=trigger_price,
            product=product, validity=validity,
        )
        result = OrderValidator.validate(order)
        assert result is True


class TestInvalidOrders:
    """Test that invalid order combinations raise ValueError."""

    def test_invalid_exchange(self) -> None:
        """Invalid exchange should raise ValueError."""
        order = Order(
            symbol="X", exchange="NYSE", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=10,
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "exchange" in str(exc_info.value).lower()

    def test_invalid_action(self) -> None:
        """Invalid action/side should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side="INVALID",
            order_type=OrderType.MARKET, quantity=10,
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        msg = str(exc_info.value)
        assert "action" in msg.lower() or "side" in msg.lower()

    def test_invalid_price_type(self) -> None:
        """Invalid price type should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.BUY,
            order_type="BOGUS", quantity=10,
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "price type" in str(exc_info.value).lower()

    def test_invalid_product_type(self) -> None:
        """Invalid product type should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=10,
            product="BOGUS",
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "product type" in str(exc_info.value).lower()

    def test_invalid_validity(self) -> None:
        """Invalid validity should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=10,
            validity="GTC",
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "validity" in str(exc_info.value).lower()

    def test_zero_quantity_raises(self) -> None:
        """Zero or negative quantity should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0,
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "quantity" in str(exc_info.value).lower()

    def test_limit_order_without_price_raises(self) -> None:
        """LIMIT order without price should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.BUY,
            order_type=OrderType.LIMIT, quantity=10,
            price=None,
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "price" in str(exc_info.value).lower()

    def test_sl_without_trigger_raises(self) -> None:
        """SL order without trigger_price should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.SELL,
            order_type=OrderType.SL, quantity=10,
            price=1000.0, trigger_price=None,
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "trigger" in str(exc_info.value).lower()

    def test_sl_m_without_trigger_raises(self) -> None:
        """SL-M order without trigger_price should raise ValueError."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.SELL,
            order_type=OrderType.SL_M, quantity=10,
            trigger_price=None,
        )
        with pytest.raises(ValueError) as exc_info:
            OrderValidator.validate(order)
        assert "trigger" in str(exc_info.value).lower()


class TestPriceTypeNormalization:
    """Test SL-M alias normalization."""

    def test_sl_m_normalizes(self) -> None:
        """SL_M should normalize to SL-M and pass validation."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.SELL,
            order_type=OrderType.SL_M, quantity=10,
            trigger_price=500.0,
        )
        result = OrderValidator.validate(order)
        assert result is True

    def test_sl_m_string_alias(self) -> None:
        """String aliases for SL-M should be accepted."""
        order = Order(
            symbol="X", exchange="NSE", side=OrderSide.SELL,
            order_type="SLM", quantity=10,
            trigger_price=500.0,
        )
        result = OrderValidator.validate(order)
        assert result is True
