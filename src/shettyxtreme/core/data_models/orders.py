"""Standard order and trade models."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

@dataclass
class Order:
    order_id: str; symbol: str; exchange: str; side: str
    order_type: str; quantity: int; price: float; status: str
    filled_quantity: int = 0; average_price: float = 0.0
    trigger_price: Optional[float] = None; tag: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class OrderResult:
    order_id: str; status: str; message: str = ""
    filled_quantity: int = 0; average_price: float = 0.0

@dataclass
class Fill:
    trade_id: str; order_id: str; symbol: str; exchange: str
    side: str; quantity: int; price: float; timestamp: datetime
    order_tag: Optional[str] = None

@dataclass
class Position:
    symbol: str; exchange: str; quantity: int; buy_avg: float
    sell_avg: float; net_quantity: int; m2m: float; pnl: float; product: str

@dataclass
class Trade:
    trade_id: str; symbol: str; side: str
    entry_price: float; quantity: int; entry_time: datetime
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl: Optional[float] = None
    strategy: Optional[str] = None
