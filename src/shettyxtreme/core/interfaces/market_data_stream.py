from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

# F-CORE-001: Tick/Bar are canonical in core.data_models; this module
# re-exports the same classes so protocol consumers share one identity
# with the bus-facing side (isinstance works across both import paths).
from shettyxtreme.core.data_models import Bar, Tick

TickCallback = Callable[[Tick], Awaitable[None]|None]
BarCallback = Callable[[Bar], Awaitable[None]|None]

@runtime_checkable
class MarketDataStream(Protocol):
    async def subscribe_ticks(self, symbols: list[str], callback: TickCallback) -> bool: ...
    async def subscribe_bars(self, symbols: list[str], tf: str, callback: BarCallback) -> bool: ...
    async def unsubscribe(self, symbol: str) -> bool: ...
    async def is_connected(self) -> bool: ...
