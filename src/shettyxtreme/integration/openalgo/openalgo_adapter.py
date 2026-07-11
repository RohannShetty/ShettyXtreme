"""OpenAlgo REST API adapter.

Consumes OpenAlgo's REST API behind our core interfaces.
version: openalgo v2.0+ JSON API
docs: https://github.com/marketcalls/openalgo
"""
import httpx
from typing import Any

from shettyxtreme.core.interfaces import (
    OrderExecutor, Order, OrderResult, OrderSide, OrderType,
    ProductType, OrderStatus, MarketDataStream, Tick, Bar,
    AccountInfo, Position, Holding, OrderBook,
)

class OpenAlgoAdapter:
    def __init__(self, base_url: str = "http://localhost:5000", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=15)
        self._ws_connected = False
    
    async def connect(self) -> bool:
        try:
            r = await self._client.get(f"{self.base_url}/api/v1/analyzerstatus")
            return r.status_code == 200
        except Exception:
            return False
    
    async def disconnect(self):
        await self._client.aclose()
    
    async def is_connected(self) -> bool:
        return self._ws_connected
    
    async def place_order(self, order: Order) -> OrderResult:
        payload = {
            "apikey": self.api_key,
            "strategy": order.tag or "shettyxtreme",
            "symbol": order.symbol,
            "exchange": order.exchange,
            "action": order.side.value,
            "product": order.product.value,
            "pricetype": order.order_type.value,
            "quantity": order.quantity,
        }
        if order.price: payload["price"] = order.price
        if order.trigger_price: payload["trigger_price"] = order.trigger_price
        r = await self._client.post(f"{self.base_url}/api/v1/placeorder", json=payload)
        data = r.json()
        status = OrderStatus.FILLED if data.get("status") == "success" else OrderStatus.REJECTED
        return OrderResult(
            order_id=data.get("orderid", ""),
            status=status,
            message=data.get("message", ""),
        )
    
    async def cancel_order(self, order_id: str) -> bool:
        payload = {"apikey": self.api_key, "order_id": order_id}
        r = await self._client.post(f"{self.base_url}/api/v1/cancelorder", json=payload)
        return r.status_code == 200
    
    async def get_positions(self) -> list[Position]:
        r = await self._client.get(f"{self.base_url}/api/v1/positions?apikey={self.api_key}")
        data = r.json()
        positions = []
        for p in data if isinstance(data, list) else data.get("data", []):
            positions.append(Position(
                symbol=p.get("symbol", ""), exchange=p.get("exchange", "NFO"),
                quantity=int(p.get("quantity", 0)), buy_avg=float(p.get("buyavg", 0)),
                sell_avg=float(p.get("sellavg", 0)), net_quantity=int(p.get("netqty", 0)),
                day_buy_quantity=int(p.get("dayBuyQty", 0)), day_sell_quantity=int(p.get("daySellQty", 0)),
                m2m=float(p.get("m2m", 0)), pnl=float(p.get("pnl", 0)),
                product=p.get("product", "MIS"),
            ))
        return positions
    
    async def get_order_book(self) -> list[OrderBook]:
        r = await self._client.get(f"{self.base_url}/api/v1/orderbook?apikey={self.api_key}")
        data = r.json()
        orders = []
        for o in data if isinstance(data, list) else data.get("data", []):
            from datetime import datetime
            orders.append(OrderBook(
                order_id=o.get("orderid", ""), symbol=o.get("symbol", ""),
                exchange=o.get("exchange", "NFO"), side=o.get("side", "BUY"),
                order_type=o.get("ordertype", "MARKET"), quantity=int(o.get("quantity", 0)),
                filled_quantity=int(o.get("filledqty", 0)), price=float(o.get("price", 0)),
                status=o.get("status", ""), timestamp=datetime.now(),
            ))
        return orders
