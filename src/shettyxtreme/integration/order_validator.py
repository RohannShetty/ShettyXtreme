"""Order validation for Dhan orders.

Validates exchanges, actions, price types, product types, and validity
before submitting orders to Dhan. Raises ValueError with descriptive
messages on invalid combinations.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.core.interfaces.order_executor import (
    Order,
    OrderSide,
    OrderType,
    ProductType,
)

VALID_EXCHANGES: set[str] = {"NSE", "BSE", "NFO", "BFO", "MCX", "NSE_FNO", "BSE_FNO", "MCX_FNO", "IDX_I"}
VALID_ACTIONS: set[str] = {"BUY", "SELL"}
VALID_PRICE_TYPES: set[str] = {"MARKET", "LIMIT", "SL", "SL-M"}
VALID_PRODUCT_TYPES: set[str] = {"MIS", "NRML", "CNC", "MARGIN"}
VALID_VALIDITY: set[str] = {"DAY", "IOC"}


class OrderValidator:
    """Validates order parameters before submission.

    Validates exchange, action/side, price type, product type, and
    validity against known-good sets. Raises ValueError with a
    descriptive message on any invalid field.
    """

    @staticmethod
    def _normalize_price_type(pt: str) -> str:
        """Normalize SL-M variants to canonical form."""
        upper: str = pt.upper().strip()
        aliases: dict[str, str] = {
            "SL-M": "SL-M",
            "SLM": "SL-M",
            "SL_M": "SL-M",
            "STOP_LOSS_MARKET": "SL-M",
            "STOPLOSS_MARKET": "SL-M",
            "SL": "SL",
            "STOP_LOSS": "SL",
            "STOPLOSS": "SL",
        }
        return aliases.get(upper, upper)

    @staticmethod
    def validate(order: Order) -> bool:
        """Validate an Order instance. Returns True if valid.

        Args:
            order: The Order dataclass to validate.

        Returns:
            True if the order passes all validation checks.

        Raises:
            ValueError: If any field is invalid, with a descriptive
                message identifying the problematic field.
        """
        # Validate exchange
        exchange: str = order.exchange.upper()
        if exchange not in VALID_EXCHANGES:
            raise ValueError(
                f"Invalid exchange '{order.exchange}'. "
                f"Must be one of {sorted(VALID_EXCHANGES)}."
            )

        # Validate action/side
        side_str: str = order.side.value.upper() if isinstance(order.side, OrderSide) else str(order.side).upper()
        if side_str not in VALID_ACTIONS:
            raise ValueError(
                f"Invalid action/side '{side_str}'. "
                f"Must be one of {sorted(VALID_ACTIONS)}."
            )

        # Validate price type
        raw_pt: str = order.order_type.value if isinstance(order.order_type, OrderType) else str(order.order_type)
        price_type: str = OrderValidator._normalize_price_type(raw_pt)
        if price_type not in VALID_PRICE_TYPES:
            raise ValueError(
                f"Invalid price type '{raw_pt}'. "
                f"Must be one of {sorted(VALID_PRICE_TYPES)}."
            )

        # Validate product type
        raw_product: str = order.product.value if isinstance(order.product, ProductType) else str(order.product)
        product_type: str = raw_product.upper().strip()
        if product_type not in VALID_PRODUCT_TYPES:
            raise ValueError(
                f"Invalid product type '{raw_product}'. "
                f"Must be one of {sorted(VALID_PRODUCT_TYPES)}."
            )

        # Validate validity
        validity: str = order.validity.upper().strip()
        if validity not in VALID_VALIDITY:
            raise ValueError(
                f"Invalid validity '{order.validity}'. "
                f"Must be one of {sorted(VALID_VALIDITY)}."
            )

        # Validate quantity
        if order.quantity <= 0:
            raise ValueError(
                f"Invalid quantity {order.quantity}. Must be positive."
            )

        # Price must be provided for LIMIT and SL orders
        if price_type in ("LIMIT", "SL"):
            if order.price is None or order.price <= 0:
                raise ValueError(
                    f"Price type '{price_type}' requires a positive price, "
                    f"got {order.price}."
                )

        # Trigger price required for SL and SL-M
        if price_type in ("SL", "SL-M"):
            if order.trigger_price is None or order.trigger_price <= 0:
                raise ValueError(
                    f"Price type '{price_type}' requires a positive trigger_price, "
                    f"got {order.trigger_price}."
                )

        return True
