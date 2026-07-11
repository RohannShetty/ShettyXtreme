"""Standard market data models."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

@dataclass
class Bar:
    symbol: str; exchange: str; timeframe: str
    open: float; high: float; low: float; close: float; volume: int
    timestamp: datetime; oi: Optional[int] = None

@dataclass
class Tick:
    symbol: str; exchange: str; ltp: float; volume: int
    timestamp: datetime; bid: Optional[float] = None; ask: Optional[float] = None
    open: Optional[float] = None; high: Optional[float] = None; low: Optional[float] = None; close: Optional[float] = None

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
