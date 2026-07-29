"""Standard order and trade models."""
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Order:
    order_id: str; symbol: str; exchange: str; side: str
    order_type: str; quantity: int; price: float; status: str
    filled_quantity: int = 0; average_price: float = 0.0
    trigger_price: float | None = None; tag: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

@dataclass
class OrderResult:
    order_id: str; status: str; message: str = ""
    filled_quantity: int = 0; average_price: float = 0.0

@dataclass
class Fill:
    trade_id: str; order_id: str; symbol: str; exchange: str
    side: str; quantity: int; price: float; timestamp: datetime
    order_tag: str | None = None

@dataclass
class Position:
    symbol: str; exchange: str; quantity: int; buy_avg: float
    sell_avg: float; net_quantity: int; m2m: float; pnl: float; product: str

@dataclass
class Trade:
    trade_id: str; symbol: str; side: str
    entry_price: float; quantity: int; entry_time: datetime
    exit_price: float | None = None
    exit_time: datetime | None = None
    pnl: float | None = None
    strategy: str | None = None
