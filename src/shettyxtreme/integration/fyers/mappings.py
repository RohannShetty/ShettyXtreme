"""Fyers <-> internal enum mappings for order execution (F2).

Fyers v3 REST order conventions (``POST /orders/sync``):

    type        int   1=LIMIT 2=MARKET 3=SL-M 4=SL-L
    productType str   CNC | INTRADAY | MARGIN | MTF
    side        int   1=BUY, -1=SELL
    validity    str   DAY | IOC
    status      int   1=Canceled 2=Trading 3=Complete 4=Transmitted
                      5=Pending 6=Unknown 7=Rejected 8=Partial
                      9=Replaced 10=Expired

Forward maps (``*_MAP``) encode internal orders for the wire; reverse maps
(``*_TO_INTERNAL``) decode Fyers responses back to internal enums.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.core.data_models import OrderSide, OrderStatus, OrderType, ProductType

# ---------------------------------------------------------------------------
# Forward: internal -> Fyers wire values
# ---------------------------------------------------------------------------

#: Internal order type -> Fyers ``type`` code. SL (stop-loss limit) uses
#: code 4; SL_M (stop-loss market) uses code 3.
ORDER_TYPE_MAP: dict[OrderType, int] = {
    OrderType.MARKET: 2,
    OrderType.LIMIT: 1,
    OrderType.SL: 4,
    OrderType.SL_M: 3,
}

#: Internal product -> Fyers ``productType``.
PRODUCT_TYPE_MAP: dict[ProductType, str] = {
    ProductType.CNC: "CNC",
    ProductType.MIS: "INTRADAY",
    ProductType.NRML: "MARGIN",
}

#: Internal side -> Fyers ``side`` code.
SIDE_MAP: dict[OrderSide, int] = {
    OrderSide.BUY: 1,
    OrderSide.SELL: -1,
}

#: Internal validity -> Fyers ``validity`` (identity; internal validity is a str).
VALIDITY_MAP: dict[str, str] = {
    "DAY": "DAY",
    "IOC": "IOC",
}

# ---------------------------------------------------------------------------
# Reverse: Fyers wire values -> internal enums (response parsing)
# ---------------------------------------------------------------------------

#: Fyers ``type`` -> internal order type. Code 3 is SL-M; code 4 is SL-L.
ORDER_TYPE_TO_INTERNAL: dict[int, OrderType] = {
    1: OrderType.LIMIT,
    2: OrderType.MARKET,
    3: OrderType.SL_M,
    4: OrderType.SL,
}

PRODUCT_TYPE_TO_INTERNAL: dict[str, ProductType] = {
    "CNC": ProductType.CNC,
    "INTRADAY": ProductType.MIS,
    "MARGIN": ProductType.NRML,
    # MTF (margin trading facility) has no exact internal twin; treat as NRML.
    "MTF": ProductType.NRML,
}

SIDE_TO_INTERNAL: dict[int, OrderSide] = {
    1: OrderSide.BUY,
    -1: OrderSide.SELL,
}

VALIDITY_TO_INTERNAL: dict[str, str] = {
    "DAY": "DAY",
    "IOC": "IOC",
}

#: Fyers order ``status`` -> internal :class:`OrderStatus`.
ORDER_STATUS_MAP: dict[int, OrderStatus] = {
    1: OrderStatus.CANCELLED,        # Canceled
    2: OrderStatus.OPEN,             # Trading / working at exchange
    3: OrderStatus.FILLED,           # Complete
    4: OrderStatus.PENDING,          # Transmitted to exchange, not yet working
    5: OrderStatus.PENDING,          # Pending (e.g. limit awaiting trigger)
    6: OrderStatus.PENDING,          # Unknown
    7: OrderStatus.REJECTED,         # Rejected
    8: OrderStatus.PARTIALLY_FILLED, # Partial
    9: OrderStatus.OPEN,             # Replaced (working with new params)
    10: OrderStatus.CANCELLED,       # Expired
}


# ---------------------------------------------------------------------------
# Lenient parsers (responses may carry these as int or str)
# ---------------------------------------------------------------------------


def fyers_order_status(status: Any) -> OrderStatus:
    """Map a Fyers status value (int or str) to :class:`OrderStatus`.

    Unknown codes fall back to :class:`OrderStatus.PENDING` so an unexpected
    broker value never crashes the parse path.
    """
    try:
        return ORDER_STATUS_MAP[int(status)]
    except (TypeError, ValueError, KeyError):
        return OrderStatus.PENDING


def parse_order_type(value: Any) -> OrderType:
    """Decode a Fyers ``type`` value (int or str) to :class:`OrderType`."""
    return ORDER_TYPE_TO_INTERNAL[int(value)]


def parse_side(value: Any) -> OrderSide:
    """Decode a Fyers ``side`` value (int or str) to :class:`OrderSide`."""
    return SIDE_TO_INTERNAL[int(value)]


def parse_product_type(value: Any) -> ProductType:
    """Decode a Fyers ``productType`` string to :class:`ProductType`."""
    return PRODUCT_TYPE_TO_INTERNAL[str(value)]


def parse_validity(value: Any) -> str:
    """Decode a Fyers ``validity`` string to the internal validity string."""
    return VALIDITY_TO_INTERNAL[str(value)]
