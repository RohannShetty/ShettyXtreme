from typing import Protocol, runtime_checkable
from .order_executor import OrderExecutor
from .market_data_stream import MarketDataStream
from .account_info import AccountInfo

@runtime_checkable
class BrokerGateway(OrderExecutor, MarketDataStream, AccountInfo, Protocol):
    broker_name: str
    async def connect(self) -> bool: ...
    async def disconnect(self) -> bool: ...
    async def is_connected(self) -> bool: ...
