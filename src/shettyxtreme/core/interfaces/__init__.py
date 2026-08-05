# F-CORE-001: this package now holds the *protocols* and re-exports the
# canonical data classes from core.data_models. Both import paths resolve to
# the same classes, so `isinstance` dispatch works across the adapter side
# (interfaces) and the bus side (data_models).
from .order_executor import OrderExecutor
from .market_data_stream import MarketDataStream, TickCallback, BarCallback
from .account_info import AccountInfo
from .data_provider import DataProvider, DataFetcher
from .broker_gateway import BrokerGateway
from shettyxtreme.core.data_models import (
    Bar, Tick, Quote, OptionChain, OptionContract,
    Order, OrderRequest, OrderResult, OrderSide, OrderStatus, OrderType,
    ProductType, Fill, Position, Trade, Holding, OrderBook,
)
__all__ = [
    "OrderExecutor", "Order", "OrderRequest", "OrderResult", "OrderSide",
    "OrderType", "ProductType", "OrderStatus", "MarketDataStream", "Tick",
    "Bar", "TickCallback", "BarCallback", "AccountInfo", "Position",
    "Holding", "OrderBook", "DataProvider", "DataFetcher", "BrokerGateway",
    "Quote", "OptionChain", "OptionContract", "Fill", "Trade",
]
