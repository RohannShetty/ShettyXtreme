"""Order entry panel."""
from __future__ import annotations
from rich.text import Text
from textual.containers import Horizontal
from textual.widgets import Button, Input, Label, Select, Static
from textual.message import Message
from shettyxtreme.execution.paper_trading import PaperTradingEngine

class OrderPanel(Static):
    """Order entry form with validation."""

    class OrderSubmitted(Message):
        """Posted on successful order placement."""
        def __init__(self, order_id, symbol, side, quantity, price):
            self.order_id = order_id
            self.symbol = symbol
            self.side = side
            self.quantity = quantity
            self.price = price
            super().__init__()

    DEFAULT_CSS = """
    OrderPanel { height: 100%; border: solid $primary; padding: 0 1; }
    OrderPanel #order-title { text-style: bold; margin: 0 0 1 0; }
    OrderPanel .form-row { height: 3; margin: 0 0 1 0; }
    OrderPanel .form-label { width: 16; padding: 0 1; }
    OrderPanel .form-input { width: 1fr; }
    OrderPanel #order-side-group { height: 3; margin: 0 0 1 0; }
    OrderPanel #buy-btn { width: 10; background: green; color: white; }
    OrderPanel #sell-btn { width: 10; background: red; color: white; }
    OrderPanel #order-submit-btn { width: 20; margin: 1 0 0 0; background: $accent; }
    OrderPanel #order-status { height: 3; margin: 1 0 0 0; padding: 0 1; }
    """

    def __init__(self, paper_trading_engine=None, *, name=None, id=None):
        super().__init__(name=name, id=id)
        self._engine = paper_trading_engine
        self._side = "BUY"

    def set_engine(self, engine):
        self._engine = engine

    def compose(self):
        yield Label("Order Entry", id="order-title")
        with Horizontal(classes="form-row"):
            yield Label("Symbol", classes="form-label")
            yield Input(placeholder="e.g. RELIANCE", id="order-symbol", classes="form-input")
        with Horizontal(id="order-side-group"):
            yield Button("BUY", id="buy-btn", variant="success")
            yield Button("SELL", id="sell-btn", variant="error")
        with Horizontal(classes="form-row"):
            yield Label("Qty", classes="form-label")
            yield Input(value="1", placeholder="Quantity", id="order-qty", classes="form-input", type="integer")
        with Horizontal(classes="form-row"):
            yield Label("Order Type", classes="form-label")
            yield Select(id="order-type", classes="form-input", prompt="Select type",
                         options=[("MARKET","MARKET"),("LIMIT","LIMIT"),("SL","SL")], value="MARKET")
        with Horizontal(classes="form-row"):
            yield Label("Price", classes="form-label")
            yield Input(placeholder="Price (required for LIMIT/SL)", id="order-price", classes="form-input", type="float")
        with Horizontal(classes="form-row"):
            yield Label("Trigger Price", classes="form-label")
            yield Input(placeholder="Trigger (required for SL)", id="order-trigger", classes="form-input", type="float")
        with Horizontal(classes="form-row"):
            yield Button("Submit Order", id="order-submit-btn")
        yield Static("", id="order-status")

    def on_button_pressed(self, event):
        bid = event.button.id or ""
        if bid == "buy-btn": self._side = "BUY"
        elif bid == "sell-btn": self._side = "SELL"
        elif bid == "order-submit-btn": self._on_submit()

    def _on_submit(self):
        symbol = self.query_one("#order-symbol", Input).value.strip().upper()
        qty_str = self.query_one("#order-qty", Input).value.strip()
        order_type = str(self.query_one("#order-type", Select).value or "MARKET")
        price_str = self.query_one("#order-price", Input).value.strip()
        trigger_str = self.query_one("#order-trigger", Input).value.strip()
        status = self.query_one("#order-status", Static)

        if not symbol: status.update(Text("Symbol is required", style="red")); return
        if not qty_str: status.update(Text("Quantity is required", style="red")); return
        try: qty = int(qty_str)
        except ValueError: status.update(Text("Quantity must be an integer", style="red")); return
        if qty <= 0: status.update(Text("Quantity must be > 0", style="red")); return

        price = 0.0
        if price_str:
            try: price = float(price_str)
            except ValueError: status.update(Text("Price must be a number", style="red")); return

        if order_type in ("LIMIT","SL") and price <= 0:
            status.update(Text(f"Price > 0 is required for {order_type} orders", style="red")); return

        trigger_price = None
        if trigger_str:
            try: trigger_price = float(trigger_str)
            except ValueError: status.update(Text("Trigger price must be a number", style="red")); return

        if order_type == "SL" and (trigger_price is None or trigger_price <= 0):
            status.update(Text("Trigger price > 0 is required for SL orders", style="red")); return

        if self._engine is None:
            status.update(Text("Paper trading engine not available", style="red")); return

        self._submit_async(symbol, "NSE", self._side, order_type, qty, price, trigger_price)

    def _submit_async(self, symbol, exchange, side, order_type, qty, price, trigger_price=None):
        status = self.query_one("#order-status", Static)
        status.update(Text("Submitting order...", style="yellow"))

        async def _place():
            try:
                result = await self._engine.place_order(
                    symbol=symbol, exchange=exchange, side=side,
                    order_type=order_type, quantity=qty,
                    price=price, trigger_price=trigger_price, tag="terminal")
                if result.status == "REJECTED":
                    status.update(Text(f"Rejected: {result.message}", style="red"))
                else:
                    status.update(Text(f"{result.status}: {result.message}", style="green"))
                    self.post_message(self.OrderSubmitted(result.order_id, symbol, side, qty, price))
            except Exception as exc:
                status.update(Text(f"Error: {exc}", style="red"))

        self.call_from_thread(_place)
