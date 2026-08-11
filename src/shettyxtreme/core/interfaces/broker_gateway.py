from typing import Protocol, runtime_checkable

from .account_info import AccountInfo
from .market_data_stream import MarketDataStream
from .order_executor import OrderExecutor


@runtime_checkable
class BrokerGateway(OrderExecutor, MarketDataStream, AccountInfo, Protocol):
    broker_name: str
    async def connect(self) -> bool: ...
    async def disconnect(self) -> bool: ...
    async def is_connected(self) -> bool: ...
    def is_session_valid(self) -> bool:
        """Cheap session/token-validity check (True when not known-expired).

        Adapters that track an access-token lifecycle (e.g. Fyers' daily
        tokens) implement this so the execution layer can gate LIVE placement
        (mission §9 Q5). Adapters without a token concept should not declare
        it — callers use ``getattr(..., lambda: True)`` for backward compat.
        """
        return True
