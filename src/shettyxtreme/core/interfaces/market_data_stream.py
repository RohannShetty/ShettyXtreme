from typing import Protocol, runtime_checkable, Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Tick:
    symbol: str; exchange: str; ltp: float; volume: int
    timestamp: datetime; bid: float|None=None; ask: float|None=None
    open: float|None=None; high: float|None=None
    low: float|None=None; close: float|None=None; oi: int|None=None

@dataclass
class Bar:
    symbol: str; exchange: str; timeframe: str
    open: float; high: float; low: float; close: float; volume: int
    timestamp: datetime; oi: int|None=None

TickCallback = Callable[[Tick], Awaitable[None]|None]
BarCallback = Callable[[Bar], Awaitable[None]|None]

@runtime_checkable
class MarketDataStream(Protocol):
    async def subscribe_ticks(self, symbols: list[str], callback: TickCallback) -> bool: ...
    async def subscribe_bars(self, symbols: list[str], tf: str, callback: BarCallback) -> bool: ...
    async def unsubscribe(self, symbol: str) -> bool: ...
    async def is_connected(self) -> bool: ...
