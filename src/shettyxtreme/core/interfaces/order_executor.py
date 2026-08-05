"""Protocol for order execution - implemented by FyersTradingAdapter.

F-CORE-001: the data classes (``OrderRequest``/``OrderResult``/enums) are
canonical in ``core.data_models``; this module re-exports them so the
Protocol signature and consumers share one identity.
"""
from typing import Protocol, runtime_checkable

from shettyxtreme.core.data_models import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)

@runtime_checkable
class OrderExecutor(Protocol):
    async def place_order(self, order: OrderRequest) -> OrderResult: ...
    async def modify_order(self, order_id: str, order: OrderRequest) -> OrderResult: ...
    async def cancel_order(self, order_id: str) -> bool: ...
    async def get_order_status(self, order_id: str) -> OrderResult: ...
