"""Paper trading engine - simulates order execution, positions, and P&L in-memory.

Emits ORDER_PLACED, ORDER_FILLED, ORDER_REJECTED, and POSITION_CHANGED events
on the EventBus. Market orders fill immediately; limit orders fill when a matching
Tick event arrives. No real broker or exchange is contacted.

Realism layer (P3-4.1): optional slippage, fees, margin, fill probability.
All new behaviour is injected via configurable model objects; when None the
engine behaves identically to the pre-P3-4.1 deterministic simulator.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from shettyxtreme.core.data_models.orders import Fill, Order, OrderResult, Position
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.execution.paper_realism import (
    FeeBreakdown,
    FeesModel,
    FillProbabilityModel,
    MarginPolicy,
    MarginResult,
    SlippageModel,
    SlippageResult,
)
from shettyxtreme.intelligence.risk.risk_engine import Portfolio


class PaperTradingEngine:
    """In-memory paper trading engine that simulates order execution.

    Maintains virtual order book, positions, and running P&L.
    Subscribes to MARKET_DATA_TICK events to simulate limit-order fills.

    Realism models (all optional, all default to no-op/backward-compatible):
      - slippage_model: adjusts fill price based on bid/ask or fixed bps
      - fees_model: deducts brokerage/STT/GST/SEBI/stamp on each fill
      - margin_policy: rejects orders exceeding available margin
      - fill_probability: makes limit fills probabilistic instead of certain
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        initial_capital: float = 1_000_000.0,
        slippage_model: SlippageModel | None = None,
        fees_model: FeesModel | None = None,
        margin_policy: MarginPolicy | None = None,
        fill_probability_model: FillProbabilityModel | None = None,
        enable_margin_check: bool = False,
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

        # --- Realism models ---
        self._slippage = slippage_model
        self._fees = fees_model
        self._margin_policy = margin_policy
        self._fill_prob = fill_probability_model
        self._enable_margin = enable_margin_check

        # Tick-level state for fill probability and spread
        self._bid_cache: dict[str, float] = {}
        self._ask_cache: dict[str, float] = {}
        self._volume_cache: dict[str, int] = {}
        self._order_tick_count: dict[str, int] = {}
        self._total_fees: float = 0.0

    async def place_order(
        self, symbol: str, exchange: str, side: str, order_type: str,
        quantity: int, price: float = 0.0,
        trigger_price: float | None = None, tag: str | None = None,
        # Trade context (P3-4.3): option identity + plan, carried from
        # OrderRequest so the order book can reconstruct full leg detail.
        strike: float | None = None,
        expiry: str | None = None,
        option_type: str | None = None,
        lot_size: int | None = None,
        stop_loss: float | None = None,
        target: float | None = None,
        rationale: str | None = None,
        confidence: float | None = None,
        signal_id: str | None = None,
    ) -> OrderResult:
        """Place a simulated order."""
        if quantity <= 0:
            result = OrderResult(order_id="", status="REJECTED", message="Quantity must be > 0")
            await self._emit_order_rejected(result, symbol)
            return result
        order_id = self._next_order_id()
        now = datetime.now(UTC)
        order = Order(
            order_id=order_id, symbol=symbol.upper(), exchange=exchange.upper(),
            side=side.upper(), order_type=order_type.upper(), quantity=quantity,
            price=price, status="PENDING", filled_quantity=0, average_price=0.0,
            trigger_price=trigger_price, tag=tag, created_at=now,
            strike=strike, expiry=expiry, option_type=option_type,
            lot_size=lot_size, stop_loss=stop_loss, target=target,
            rationale=rationale, confidence=confidence, signal_id=signal_id,
        )
        self._orders.append(order)
        await self._emit_order_placed(order)

        # --- Margin check (before filling) ---
        if self._enable_margin and self._margin_policy:
            ref_price = price if price > 0 else self._ltp_cache.get(symbol.upper(), 0.0)
            if ref_price > 0:
                margin_result = self._check_margin(order, ref_price)
                if not margin_result.ok:
                    order.status = "REJECTED"
                    result = OrderResult(
                        order_id=order_id, status="REJECTED",
                        message=(
                            f"Insufficient margin: need ₹{margin_result.required:,.0f}, "
                            f"have ₹{margin_result.available:,.0f}"
                        ),
                    )
                    await self._emit_order_rejected(result, symbol)
                    return result

        if order_type.upper() in ("MARKET",):
            return await self._fill_order(order)
        if order_type.upper() in ("LIMIT", "SL"):
            self._pending_orders[order_id] = order
            self._order_tick_count[order_id] = 0
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
        self._order_tick_count.pop(order_id, None)
        for o in self._orders:
            if o.order_id == order_id:
                o.status = "CANCELLED"
                break
        await self._emit_order_cancelled(order)
        return True

    def get_positions(self) -> list[Position]:
        """Return all current open positions with updated P&L."""
        self._recalculate_pnl()
        return list(self._positions.values())

    def get_order_book(self) -> list[Order]:
        """Return all orders placed through this engine."""
        return list(self._orders)

    def get_pnl(self) -> dict[str, Any]:
        """Return P&L summary dict.

        Realised P&L is the sum of accumulated pos.pnl on fully closed
        positions (net_quantity == 0).  Unrealised is mark-to-market on
        open positions.  Total fees are tracked across all fills.
        """
        self._recalculate_pnl()
        # Realised: sum pos.pnl for positions that have been closed (net_qty == 0)
        # or partially closed (pos.pnl accumulated from closing trades).
        realised = sum(pos.pnl for pos in self._positions.values())
        unrealised = 0.0
        for pos in self._positions.values():
            ltp = self._ltp_cache.get(pos.symbol)
            if ltp is None:
                continue
            if pos.net_quantity > 0:
                unrealised += abs(pos.net_quantity) * (ltp - pos.buy_avg)
            elif pos.net_quantity < 0:
                unrealised += abs(pos.net_quantity) * (pos.sell_avg - ltp)
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
            "total_fees": round(self._total_fees, 2),
        }

    def get_portfolio(self) -> Portfolio:
        """Return a Portfolio reflecting current paper capital and open position notional."""
        self._recalculate_pnl()
        open_notional = sum(
            abs(pos.net_quantity) * (self._ltp_cache.get(pos.symbol, pos.buy_avg or pos.sell_avg))
            for pos in self._positions.values()
            if pos.net_quantity != 0
        )
        realised = sum(pos.pnl for pos in self._positions.values())
        unrealised = 0.0
        for pos in self._positions.values():
            ltp = self._ltp_cache.get(pos.symbol)
            if ltp is None:
                continue
            if pos.net_quantity > 0:
                unrealised += abs(pos.net_quantity) * (ltp - pos.buy_avg)
            elif pos.net_quantity < 0:
                unrealised += abs(pos.net_quantity) * (pos.sell_avg - ltp)
        return Portfolio(
            positions=list(self._positions.values()),
            daily_pnl=round(realised + unrealised, 2),
            total_margin_used=round(open_notional, 2),
            available_margin=round(self._capital, 2),
            equity=round(self._capital + open_notional, 2),
        )

    async def _on_tick(self, event: Event) -> None:
        """Process MARKET_DATA_TICK to simulate limit/SL fills."""
        data = event.data
        bid: float | None = None
        ask: float | None = None
        volume: int = 0
        if isinstance(data, dict):
            symbol = str(data.get("symbol", "")).upper()
            ltp = float(data.get("ltp", 0.0))
            bid = data.get("bid")
            ask = data.get("ask")
            volume = int(data.get("volume", 0) or 0)
        else:
            try:
                symbol = data.symbol.upper()
                ltp = data.ltp
                bid = data.bid
                ask = data.ask
                volume = int(data.volume or 0)
            except AttributeError:
                return
        if not symbol or ltp <= 0:
            return
        self._ltp_cache[symbol] = ltp
        if bid is not None and bid > 0:
            self._bid_cache[symbol] = bid
        if ask is not None and ask > 0:
            self._ask_cache[symbol] = ask
        if volume > 0:
            self._volume_cache[symbol] = volume

        to_fill: list[str] = []
        to_cancel: list[str] = []
        for oid, order in list(self._pending_orders.items()):
            if order.symbol != symbol:
                continue

            # Increment tick counter for this order
            self._order_tick_count[oid] = self._order_tick_count.get(oid, 0) + 1

            if order.order_type == "LIMIT":
                # Gap-through check: cancel if LTP ran past the limit
                if self._fill_prob is not None:
                    if self._fill_prob.check_gap_through(order.price, order.side, ltp):
                        to_cancel.append(oid)
                        continue

                touched = (
                    (order.side == "BUY" and ltp <= order.price)
                    or (order.side == "SELL" and ltp >= order.price)
                )
                if touched:
                    if self._fill_prob is not None:
                        ticks_waiting = self._order_tick_count.get(oid, 0)
                        should_fill, _ = self._fill_prob.should_fill(
                            order_price=order.price,
                            side=order.side,
                            ltp=ltp,
                            bid=bid,
                            ask=ask,
                            volume=volume,
                            quantity=order.quantity - order.filled_quantity,
                            ticks_waiting=ticks_waiting,
                        )
                        if should_fill:
                            to_fill.append(oid)
                    else:
                        to_fill.append(oid)

            elif order.order_type == "SL" and order.trigger_price is not None:
                if (
                    (order.side == "BUY" and ltp >= order.trigger_price)
                    or (order.side == "SELL" and ltp <= order.trigger_price)
                ):
                    to_fill.append(oid)

        # Cancel gap-through orders
        for oid in to_cancel:
            order = self._pending_orders.pop(oid, None)
            self._order_tick_count.pop(oid, None)
            if order:
                order.status = "CANCELLED"
                for o in self._orders:
                    if o.order_id == oid:
                        o.status = "CANCELLED"
                        break
                await self._emit_order_cancelled(order)

        for oid in to_fill:
            order = self._pending_orders.pop(oid, None)
            self._order_tick_count.pop(oid, None)
            if order:
                # Partial fill check: large order vs thin volume
                remaining = order.quantity - order.filled_quantity
                fill_qty = self._compute_partial_fill(remaining, volume, order.order_type)
                if fill_qty < remaining:
                    # Partial fill: fill part, keep rest pending
                    await self._fill_order(order, override_qty=fill_qty)
                    order.filled_quantity += fill_qty
                    order.status = "PARTIALLY_FILLED"
                    self._pending_orders[oid] = order
                    self._order_tick_count[oid] = 0
                else:
                    await self._fill_order(order)

    def _compute_partial_fill(self, remaining: int, volume: int, order_type: str) -> int:
        """Compute fill quantity — partial for large orders vs thin volume.

        If remaining qty > 10% of tick volume, fill 50-80% randomly.
        Only applies when fill probability model is active.
        """
        if self._fill_prob is None:
            return remaining
        if volume <= 0 or remaining <= volume * 0.1:
            return remaining
        pct = random.uniform(0.5, 0.8)
        return max(1, int(remaining * pct))

    def _check_margin(self, order: Order, ref_price: float) -> MarginResult:
        """Check if available margin covers the order's requirement."""
        assert self._margin_policy is not None
        required = self._margin_policy.required_margin(
            quantity=order.quantity,
            price=ref_price,
            side=order.side,
            exchange=order.exchange,
        )
        available = self._capital
        ok = available >= required
        return MarginResult(required=round(required, 2), available=round(available, 2), ok=ok)

    async def _fill_order(self, order: Order, override_qty: int | None = None) -> OrderResult:
        """Fill an order and update positions.

        Args:
            order: The order to fill.
            override_qty: If set, fill only this quantity (partial fill).
        """
        fill_qty = override_qty if override_qty is not None else order.quantity
        fill_price = order.price

        if order.order_type == "MARKET":
            # F-EXEC-004: a MARKET order fills at the last traded price, not
            # the order's (zero) limit price. No LTP yet → reject honestly;
            # filling at 0.0 would poison paper P&L and learning data.
            ltp = self._ltp_cache.get(order.symbol)
            if ltp is None or ltp <= 0:
                if override_qty is None:
                    order.status = "REJECTED"
                    result = OrderResult(
                        order_id=order.order_id, status="REJECTED",
                        message=f"MARKET order rejected: no LTP available for {order.symbol}",
                    )
                    await self._emit_order_rejected(result, order.symbol)
                    return result
                return OrderResult(order_id=order.order_id, status="REJECTED", message="no LTP")
            # Apply slippage to market fill price
            fill_price = self._apply_slippage(
                base_price=ltp,
                side=order.side,
                order_type=order.order_type,
                symbol=order.symbol,
                quantity=fill_qty,
            )
            # Record the actual fill price on the order so downstream reads it
            order.price = fill_price

        elif order.order_type == "SL":
            # SL triggered → fill at market (LTP) with slippage
            ltp = self._ltp_cache.get(order.symbol)
            if ltp is not None and ltp > 0:
                fill_price = self._apply_slippage(
                    base_price=ltp,
                    side=order.side,
                    order_type="MARKET",  # SL → market fill
                    symbol=order.symbol,
                    quantity=fill_qty,
                )
                order.price = fill_price

        # For LIMIT orders: fill at the limit price (no price improvement)
        # Slippage for LIMIT is applied via the model's fixed_bps_limit if enabled

        # --- Compute fees ---
        fees = self._compute_fees(fill_qty, fill_price, order.side, order.exchange)
        self._total_fees += fees

        # --- Update order state ---
        order.average_price = fill_price
        if override_qty is not None:
            # Partial fill — don't set status to FILLED yet
            pass
        else:
            order.status = "FILLED"
            order.filled_quantity = order.quantity

        now = datetime.now(UTC)
        self._trade_seq += 1
        fill = Fill(
            trade_id=f"TRADE{self._trade_seq:06d}",
            order_id=order.order_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            quantity=fill_qty,
            price=fill_price,
            timestamp=now,
            order_tag=order.tag,
            fees=fees,
        )
        self._fills.append(fill)

        # --- Margin accounting: debit notional + fees on BUY, credit on SELL ---
        notional = fill_qty * fill_price
        if order.side == "BUY":
            self._capital -= (notional + fees)
        else:  # SELL — restore capital from closing position, minus fees
            self._capital += (notional - fees)

        self._update_positions(order, fill_qty)

        if override_qty is None:
            await self._emit_order_filled(order)
        if self._event_bus:
            # P3-4.3: carry trade context through the fill event so the
            # position projection can link back to the originating proposal.
            pos_data: dict[str, object] = {
                "symbol": order.symbol, "side": order.side,
                "quantity": fill_qty, "price": order.price,
            }
            if order.signal_id:
                pos_data["signal_id"] = order.signal_id
            if order.stop_loss is not None:
                pos_data["stop_loss"] = order.stop_loss
            if order.target is not None:
                pos_data["target"] = order.target
            if order.rationale is not None:
                pos_data["rationale"] = order.rationale
            if order.confidence is not None:
                pos_data["confidence"] = order.confidence
            if order.lot_size is not None:
                pos_data["lot_size"] = order.lot_size
            await self._event_bus.publish(Event(
                Topic.POSITION_CHANGED, pos_data, source="paper_trading",
            ))
        return OrderResult(
            order_id=order.order_id, status="FILLED" if override_qty is None else "PARTIALLY_FILLED",
            message=f"Filled {fill_qty} {order.symbol} @ {fill_price}",
            filled_quantity=fill_qty, average_price=fill_price,
        )

    def _apply_slippage(
        self,
        base_price: float,
        side: str,
        order_type: str,
        symbol: str,
        quantity: int,
    ) -> float:
        """Apply slippage to a fill price using the configured model."""
        if self._slippage is None:
            return base_price
        bid = self._bid_cache.get(symbol)
        ask = self._ask_cache.get(symbol)
        volume = self._volume_cache.get(symbol, 0)
        result = self._slippage.compute(
            base_price=base_price,
            side=side,
            order_type=order_type,
            bid=bid,
            ask=ask,
            volume=volume,
            quantity=quantity,
        )
        return result.adjusted_price

    def _compute_fees(
        self,
        quantity: int,
        price: float,
        side: str,
        exchange: str,
    ) -> float:
        """Compute transaction fees using the configured model."""
        if self._fees is None:
            return 0.0
        breakdown = self._fees.compute(
            quantity=quantity,
            price=price,
            side=side,
            exchange=exchange,
        )
        return breakdown.total

    def _update_positions(self, order: Order, fill_qty: int) -> None:
        """Update positions after a fill."""
        pos = self._positions.get(order.symbol)
        if pos is None:
            net_qty = fill_qty if order.side == "BUY" else -fill_qty
            buy_avg = order.price if order.side == "BUY" else 0.0
            sell_avg = order.price if order.side == "SELL" else 0.0
            self._positions[order.symbol] = Position(
                symbol=order.symbol, exchange=order.exchange,
                quantity=fill_qty, buy_avg=buy_avg,
                sell_avg=sell_avg, net_quantity=net_qty,
                m2m=0.0, pnl=0.0, product="MIS",
            )
        else:
            if order.side == "BUY":
                total_qty = pos.net_quantity + fill_qty
                pos.quantity += fill_qty
                if pos.net_quantity >= 0:
                    pos.buy_avg = ((pos.buy_avg * pos.net_quantity) + (order.price * fill_qty)) / total_qty if total_qty > 0 else order.price
                else:
                    pnl = (pos.sell_avg - order.price) * min(fill_qty, abs(pos.net_quantity))
                    pos.pnl += pnl
                    if total_qty > 0:
                        pos.buy_avg = order.price
                pos.net_quantity = total_qty
            else:
                total_qty = pos.net_quantity - fill_qty
                if pos.net_quantity <= 0:
                    pos.sell_avg = ((pos.sell_avg * abs(pos.net_quantity)) + (order.price * fill_qty)) / abs(total_qty) if total_qty < 0 else order.price
                else:
                    pnl = (order.price - pos.buy_avg) * min(fill_qty, pos.net_quantity)
                    pos.pnl += pnl
                    if total_qty < 0:
                        pos.sell_avg = order.price
                pos.net_quantity = total_qty
                pos.quantity += fill_qty

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

    @staticmethod
    def _order_event_data(order: "Order") -> dict[str, Any]:
        """Full order record for ORDER_* bus events (P4: order WS topic).

        Carries every Order field so the OrderWSProjection can serialize a
        complete OrderResponse without a broker round-trip. Extra keys the
        projection does not need (none today) are simply ignored.
        """
        return asdict(order)

    async def _emit_order_placed(self, order: Order) -> None:
        """Emit ORDER_PLACED event."""
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.ORDER_PLACED, {
                "order_id": order.order_id, "symbol": order.symbol,
                "side": order.side, "order_type": order.order_type,
                "quantity": order.quantity, "price": order.price,
                **self._order_event_data(order),
            }, source="paper_trading"))

    async def _emit_order_filled(self, order: Order) -> None:
        """Emit ORDER_FILLED event."""
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.ORDER_FILLED, {
                "order_id": order.order_id, "symbol": order.symbol,
                "side": order.side, "quantity": order.quantity,
                "price": order.price,
                **self._order_event_data(order),
            }, source="paper_trading"))

    async def _emit_order_rejected(self, result: OrderResult, symbol: str) -> None:
        """Emit ORDER_REJECTED event."""
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.ORDER_REJECTED, {
                "order_id": result.order_id, "symbol": symbol,
                "reason": result.message,
                # P4: minimal full-record shape so OrderWSProjection can build
                # an OrderResponse (unknown fields stay honest empties).
                "exchange": "", "side": "", "order_type": "",
                "quantity": 0, "price": 0.0, "status": "REJECTED",
                "filled_quantity": 0, "average_price": 0.0,
                "created_at": datetime.now(UTC),
            }, source="paper_trading"))

    async def _emit_order_cancelled(self, order: Order) -> None:
        """Emit ORDER_CANCELLED event (P4: order WS topic)."""
        if self._event_bus:
            await self._event_bus.publish(Event(Topic.ORDER_CANCELLED, {
                **self._order_event_data(order),
            }, source="paper_trading"))
