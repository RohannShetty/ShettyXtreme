"""Paper trading engine - simulates order execution, positions, and P&L in-memory.

Emits ORDER_PLACED, ORDER_FILLED, ORDER_REJECTED, and POSITION_CHANGED events
on the EventBus. Market orders fill immediately; limit orders fill when a matching
Tick event arrives. No real broker or exchange is contacted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from shettyxtreme.core.data_models.orders import Order, OrderResult, Fill, Position
from shettyxtreme.core.event_bus import EventBus, Event, Topic

class PaperTradingEngine:
    """In-memory paper trading engine that simulates order execution.

    Maintains virtual order book, positions, and running P&L.
    Subscribes to MARKET_DATA_TICK events to simulate limit-order fills.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        initial_capital: float = 1_000_000.0,
    ) -> None:
        """Initialise the paper trading engine."""
        self._event_bus: EventBus | None = event_bus
        self._capital: float = initial_capital
        self._initial_capital: float = initial_capital
        self._positions: dict[str, Position] = {}
        self._orders: list[Order] = []
        self._pending_orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self._ltp_cache: dict[str, float] = {}
        if self._event_bus:
            self._event_bus.subscribe(Topic.MARKET_DATA_TICK, self._on_tick)
        self._trade_seq: int = 0

    async def place_order(
        self, symbol: str, exchange: str, side: str, order_type: str,
        quantity: int, price: float = 0.0,
        trigger_price: float | None = None, tag: str | None = None,
    ) -> OrderResult:
        """Place a simulated order."""
        if quantity <= 0:
            result = OrderResult(order_id="", status="REJECTED", message="Quantity must be > 0")
            await self._emit_order_rejected(result, symbol)
            return result
        order_id = self._next_order_id()
        now = datetime.now(timezone.utc)
        order = Order(
            order_id=order_id, symbol=symbol.upper(), exchange=exchange.upper(),
            side=side.upper(), order_type=order_type.upper(), quantity=quantity,
            price=price, status="PENDING", filled_quantity=0, average_price=0.0,
            trigger_price=trigger_price, tag=tag, created_at=now,
        )
        self._orders.append(order)
        await self._emit_order_placed(order)
        if order_type.upper() in ("MARKET",):
            return await self._fill_order(order)
        if order_type.upper() in ("LIMIT", "SL"):
            self._pending_orders[order_id] = order
            return OrderResult(order_id=order_id, status="OPEN",
                message=f"{order_type} order placed - waiting for fill")
        result = OrderResult(order_id=order_id, status="REJECTED",
            message=f"Unsupported order type: {order_type}")
        await self._emit_order_rejected(result, symbol)
        return result

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        order = self._pending_orders.pop(order_id, None)
        if order is None:
            return False
        order.status = "CANCELLED"
        for o in self._orders:
            if o.order_id == order_id:
                o.status = "CANCELLED"
                break
        return True

    def get_positions(self) -> list[Position]:
        """Return all current open positions with updated P&L."""
        self._recalculate_pnl()
        return list(self._positions.values())

    def get_order_book(self) -> list[Order]:
        """Return all orders placed through this engine."""
        return list(self._orders)

    def get_pnl(self) -> dict[str, Any]:
        """Return P&L summary dict."""
        self._recalculate_pnl()
        realised = sum(t.pnl or 0.0 for t in self._fills)
        unrealised = sum(
            abs(pos.net_quantity) * (self._ltp_cache.get(pos.symbol, pos.buy_avg) - pos.buy_avg)
            if pos.net_quantity > 0
            else abs(pos.net_quantity) * (pos.sell_avg - self._ltp_cache.get(pos.symbol, pos.sell_avg))
            for pos in self._positions.values()
        )
        total_exposure = sum(
            abs(pos.net_quantity) * self._ltp_cache.get(pos.symbol, pos.buy_avg or pos.sell_avg)
            for pos in self._positions.values()
        )
        return {
            "realised_pnl": round(realised, 2), "unrealised_pnl": round(unrealised, 2),
            "total_pnl": round(realised + unrealised, 2),
            "available_cash": round(self._capital, 2),
            "total_invested": round(self._initial_capital - self._capital, 2),
            "total_exposure": round(total_exposure, 2),
        }

    async def _on_tick(self, event: Event) -> None:
        """Process MARKET_DATA_TICK to simulate limit/SL fills."""
        data = event.data
        if isinstance(data, dict):
            symbol = str(data.get("symbol", "")).upper()
            ltp = float(data.get("ltp", 0.0))
        else:
            try:
                symbol = data.symbol.upper()
                ltp = data.ltp
            except AttributeError:
                return
        if not symbol or ltp <= 0:
            return
        self._ltp_cache[symbol] = ltp
        to_fill: list[str] = []
        for oid, order in list(self._pending_orders.items()):
            if order.symbol != symbol:
                continue
            if order.order_type == "LIMIT":
                if order.side == "BUY" and ltp <= order.price:
                    to_fill.append(oid)
                elif order.side == "SELL" and ltp >= order.price:
                    to_fill.append(oid)
            elif order.order_type == "SL" and order.trigger_price is not None:
                if order.side == "BUY" and ltp >= order.trigger_price:
                    to_fill.append(oid)
                elif order.side == "SELL" and ltp <= order.trigger_price:
                    to_fill.append(oid)
        for oid in to_fill:
            order = self._pending_orders.pop(oid, None)
            if order:
                await self._fill_order(order)


    async def _fill_order(self, order: Order) -> OrderResult:
        """Fill an order and update positions."""
        order.status = "FILLED"
        order.filled_quantity = order.quantity
        order.average_price = order.price
        now = datetime.now(timezone.utc)
        self._trade_seq += 1
        fill = Fill(
            trade_id=f"TRADE{self._trade_seq:06d}",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            timestamp=now,
            order_tag=order.tag,
        )
        self._fills.append(fill)
        self._update_positions(order)
        await self._emit_order_filled(order)
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.POSITION_CHANGED, {
                "symbol": order.symbol, "side": order.side,
                "quantity": order.quantity, "price": order.price,
            }, source="paper_trading"))
        return OrderResult(
            order_id=order.order_id, status="FILLED",
            message=f"Filled {order.quantity} {order.symbol} @ {order.price}",
            filled_quantity=order.quantity, average_price=order.price,
        )

    def _update_positions(self, order: Order) -> None:
        """Update positions after a fill."""
        pos = self._positions.get(order.symbol)
        if pos is None:
            net_qty = order.quantity if order.side == "BUY" else -order.quantity
            buy_avg = order.price if order.side == "BUY" else 0.0
            sell_avg = order.price if order.side == "SELL" else 0.0
            self._positions[order.symbol] = Position(
                symbol=order.symbol, exchange=order.exchange,
                quantity=order.quantity, buy_avg=buy_avg,
                sell_avg=sell_avg, net_quantity=net_qty,
                m2m=0.0, pnl=0.0, product="MIS",
            )
        else:
            if order.side == "BUY":
                total_qty = pos.net_quantity + order.quantity
                pos.quantity += order.quantity
                if pos.net_quantity >= 0:
                    pos.buy_avg = ((pos.buy_avg * pos.net_quantity) + (order.price * order.quantity)) / total_qty if total_qty > 0 else order.price
                else:
                    pnl = (pos.sell_avg - order.price) * order.quantity
                    pos.pnl += pnl
                pos.net_quantity = total_qty
            else:
                total_qty = pos.net_quantity - order.quantity
                if pos.net_quantity <= 0:
                    pos.sell_avg = ((pos.sell_avg * abs(pos.net_quantity)) + (order.price * order.quantity)) / abs(total_qty) if total_qty < 0 else order.price
                else:
                    pnl = (order.price - pos.buy_avg) * order.quantity
                    pos.pnl += pnl
                pos.net_quantity = total_qty
                pos.quantity += order.quantity

    def _recalculate_pnl(self) -> None:
        """Recalculate P&L for all positions based on LTP cache."""
        for pos in self._positions.values():
            ltp = self._ltp_cache.get(pos.symbol, pos.buy_avg or pos.sell_avg)
            if pos.net_quantity > 0:
                pos.m2m = abs(pos.net_quantity) * (ltp - pos.buy_avg)
            elif pos.net_quantity < 0:
                pos.m2m = abs(pos.net_quantity) * (pos.sell_avg - ltp)
            else:
                pos.m2m = 0.0

    def _next_order_id(self) -> str:
        """Generate a unique order ID."""
        return f"PAPER{uuid.uuid4().hex[:8].upper()}"

    async def _emit_order_placed(self, order: Order) -> None:
        """Emit ORDER_PLACED event."""
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.ORDER_PLACED, {
                "order_id": order.order_id, "symbol": order.symbol,
                "side": order.side, "order_type": order.order_type,
                "quantity": order.quantity, "price": order.price,
            }, source="paper_trading"))

    async def _emit_order_filled(self, order: Order) -> None:
        """Emit ORDER_FILLED event."""
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.ORDER_FILLED, {
                "order_id": order.order_id, "symbol": order.symbol,
                "side": order.side, "quantity": order.quantity,
                "price": order.price,
            }, source="paper_trading"))

    async def _emit_order_rejected(self, result: OrderResult, symbol: str) -> None:
        """Emit ORDER_REJECTED event."""
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.ORDER_REJECTED, {
                "order_id": result.order_id, "symbol": symbol,
                "reason": result.message,
            }, source="paper_trading"))
