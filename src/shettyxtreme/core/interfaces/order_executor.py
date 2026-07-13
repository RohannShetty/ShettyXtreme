"""Protocol for order execution - implemented by DhanTradingAdapter."""
from typing import Protocol, runtime_checkable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL_M"

class ProductType(Enum):
    CNC = "CNC"
    NRML = "NRML"
    MIS = "MIS"

class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

@dataclass
class Order:
    symbol: str
    exchange: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float | None = None
    trigger_price: float | None = None
    product: ProductType = ProductType.MIS
    validity: str = "DAY"
    tag: str | None = None
    client_id: str | None = None

@dataclass
class OrderResult:
    order_id: str
    status: OrderStatus
    message: str = ""
    filled_quantity: int = 0
    average_price: float = 0.0
    rejected_reason: str | None = None

@runtime_checkable
class OrderExecutor(Protocol):
    async def place_order(self, order: Order) -> OrderResult: ...
    async def modify_order(self, order_id: str, order: Order) -> OrderResult: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def get_order_status(self, order_id: str) -> OrderResult: ...
