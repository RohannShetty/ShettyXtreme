"""Standard order and trade models (canonical shapes, F-CORE-001).

Single source of truth for order-side data classes and enums.
``core.interfaces`` re-exports these same classes, so protocol consumers
(``from core.interfaces.order_executor import ...``) and bus consumers
(``from core.data_models import ...``) share one identity — ``isinstance``
works across both import paths.

Naming (F-CORE-001): a placement *request* is :class:`OrderRequest`; an
order *record* (broker/paper-engine state) is :class:`Order`. The two are
deliberately distinct dataclasses with different shapes.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL_M"


class ProductType(str, Enum):
    CNC = "CNC"
    NRML = "NRML"
    MIS = "MIS"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class OrderRequest:
    """A placement request — what the execution layer asks a broker to do.

    Distinct from :class:`Order` (the broker record of an order): a request
    has no ``order_id``/``status``/``created_at`` and carries the typed
    enums (``side``, ``order_type``, ``product``).
    """
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
class Order:
    """An order record — broker/paper-engine state, not a placement request."""
    order_id: str; symbol: str; exchange: str; side: str
    order_type: str; quantity: int; price: float; status: str
    filled_quantity: int = 0; average_price: float = 0.0
    trigger_price: float | None = None; tag: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OrderResult:
    """Outcome of an order placement/modify/status call.

    ``status`` is an :class:`OrderStatus` member in the execution layer and a
    plain status string in the paper engine; because ``OrderStatus`` subclasses
    ``str`` the two compare equal in either direction.
    """
    order_id: str
    status: OrderStatus
    message: str = ""
    filled_quantity: int = 0
    average_price: float = 0.0
    rejected_reason: str | None = None


@dataclass
class Fill:
    trade_id: str; order_id: str; symbol: str; exchange: str
    side: str; quantity: int; price: float; timestamp: datetime
    order_tag: str | None = None


@dataclass
class Position:
    """A broker position. ``day_buy_quantity``/``day_sell_quantity`` were
    unified from the old interfaces shape (F-CORE-001) and default to 0 so
    existing 9-arg positional constructions keep working."""
    symbol: str; exchange: str; quantity: int; buy_avg: float
    sell_avg: float; net_quantity: int; m2m: float; pnl: float; product: str
    day_buy_quantity: int = 0; day_sell_quantity: int = 0


@dataclass
class Holding:
    symbol: str; exchange: str; quantity: int
    avg_price: float; last_price: float; pnl: float; collateral: float


@dataclass
class OrderBook:
    order_id: str; symbol: str; exchange: str; side: str
    order_type: str; quantity: int; filled_quantity: int
    price: float; status: str; timestamp: datetime


@dataclass
class Trade:
    trade_id: str; symbol: str; side: str
    entry_price: float; quantity: int; entry_time: datetime
    exit_price: float | None = None
    exit_time: datetime | None = None
    pnl: float | None = None
    strategy: str | None = None
