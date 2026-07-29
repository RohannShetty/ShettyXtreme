"""Standard market data models."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    symbol: str; exchange: str; timeframe: str
    open: float; high: float; low: float; close: float; volume: int
    timestamp: datetime; oi: int | None = None

@dataclass
class Tick:
    symbol: str; exchange: str; ltp: float; volume: int
    timestamp: datetime; bid: float | None = None; ask: float | None = None
    open: float | None = None; high: float | None = None; low: float | None = None; close: float | None = None

@dataclass
class Quote:
    symbol: str; exchange: str; bid: float; ask: float
    bid_size: int; ask_size: int; timestamp: datetime

@dataclass
class OptionContract:
    symbol: str; exchange: str; expiry: str; strike: float; option_type: str
    ltp: float; iv: float; delta: float; gamma: float; theta: float; vega: float
    oi: int; volume: int; bid: float; ask: float

@dataclass
class OptionChain:
    underlying: str; expiry: str; timestamp: datetime
    contracts: list[OptionContract]
