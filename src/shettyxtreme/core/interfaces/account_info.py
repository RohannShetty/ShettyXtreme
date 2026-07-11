from typing import Protocol, runtime_checkable
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Position:
    symbol: str; exchange: str; quantity: int
    buy_avg: float; sell_avg: float; net_quantity: int
    day_buy_quantity: int; day_sell_quantity: int
    m2m: float; pnl: float; product: str

@dataclass
class Holding:
    symbol: str; exchange: str; quantity: int
    avg_price: float; last_price: float; pnl: float; collateral: float

@dataclass
class OrderBook:
    order_id: str; symbol: str; exchange: str; side: str
    order_type: str; quantity: int; filled_quantity: int
    price: float; status: str; timestamp: datetime

@runtime_checkable
class AccountInfo(Protocol):
    async def get_positions(self) -> list[Position]: ...
    async def get_holdings(self) -> list[Holding]: ...
    async def get_order_book(self) -> list[OrderBook]: ...
    async def get_trade_book(self) -> list: ...
    async def get_margin(self) -> dict: ...
