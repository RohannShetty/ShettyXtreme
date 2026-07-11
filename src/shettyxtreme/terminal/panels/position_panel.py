"""Position panel — Rich Table display of open positions with P&L coloring.

Subscribes to EventBus Topic.POSITION_CHANGED for auto-updates.
Shows a summary row with total P&L and total exposure.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from shettyxtreme.execution.paper_trading import PaperTradingEngine
from shettyxtreme.core.event_bus import EventBus, Event, Topic
from shettyxtreme.core.data_models.orders import Position


class PositionPanel(Static):
    """Displays open positions in a Rich Table with P&L colouring.

    Columns: Symbol, Qty, Avg Price, LTP, P&L, P&L%.
    Green for profit, red for loss.
    Includes a summary row: total P&L, total exposure.
    """

    DEFAULT_CSS = """
    PositionPanel {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }

    PositionPanel #positions-title {
        text-style: bold;
        margin: 0 0 1 0;
    }
    """

    def __init__(
        self,
        paper_trading_engine: PaperTradingEngine | None = None,
        event_bus: EventBus | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Initialise the position panel.

        Args:
            paper_trading_engine: Source of position data.
            event_bus: EventBus for auto-update subscriptions.
            name: Widget name for Textual.
            id: Widget DOM id.
        """
        super().__init__(name=name, id=id)
        self._engine: PaperTradingEngine | None = paper_trading_engine
        self._event_bus: EventBus | None = event_bus

    def set_engine(self, engine: PaperTradingEngine) -> None:
        """Set or replace the paper trading engine reference."""
        self._engine = engine

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Set the EventBus and subscribe to POSITION_CHANGED."""
        self._event_bus = event_bus
        self._event_bus.subscribe(Topic.POSITION_CHANGED, self._on_position_changed)

    async def _on_position_changed(self, event: Event) -> None:
        """Handle POSITION_CHANGED events by refreshing the table.

        Args:
            event: The position changed event (ignored; full refresh).
        """
        self.refresh()

    def on_mount(self) -> None:
        """Subscribe to EventBus on mount if available."""
        if self._event_bus:
            self._event_bus.subscribe(Topic.POSITION_CHANGED, self._on_position_changed)
        self._render_table()

    def _render_table(self) -> None:
        """Build the Rich Table from engine position data and summary."""
        table = Table(expand=True, box=None, padding=(0, 1), title="Positions")
        table.add_column("Symbol", style="bold", width=12)
        table.add_column("Qty", justify="right", width=8)
        table.add_column("Avg Price", justify="right", width=10)
        table.add_column("LTP", justify="right", width=10)
        table.add_column("P&L", justify="right", width=12)
        table.add_column("P&L%", justify="right", width=8)

        positions: list[Position] = []
        total_pnl = 0.0
        total_exposure = 0.0

        if self._engine:
            positions = self._engine.get_positions()
            pnl_data = self._engine.get_pnl()
            total_pnl = pnl_data.get("total_pnl", 0.0)
            total_exposure = pnl_data.get("total_exposure", 0.0)
            ltp_cache = getattr(self._engine, "_ltp_cache", {})

            for pos in positions:
                symbol = pos.symbol
                qty = pos.net_quantity
                avg_price = pos.buy_avg if qty > 0 else pos.sell_avg
                ltp = ltp_cache.get(symbol, avg_price)
                pnl = pos.m2m + pos.pnl
                pnl_pct = (pnl / (abs(qty) * avg_price) * 100) if avg_price > 0 and qty != 0 else 0.0

                colour = "green" if pnl >= 0 else "red"
                arrow = "▲" if pnl >= 0 else "▼"

                table.add_row(
                    Text(symbol, style="bold"),
                    Text(str(qty), style=colour),
                    Text(f"{avg_price:.2f}"),
                    Text(f"{ltp:.2f}" if ltp else "-"),
                    Text(f"{arrow}{abs(pnl):.2f}", style=colour),
                    Text(f"{pnl_pct:+.2f}%", style=colour),
                )

        # Summary row
        total_colour = "green" if total_pnl >= 0 else "red"
        table.add_row(
            Text("TOTAL", style="bold underline"),
            Text(""),
            Text(""),
            Text(""),
            Text(f"{total_pnl:+.2f}", style=f"bold {total_colour}"),
            Text(""),
        )
        table.add_row(
            Text("Exposure", style="bold"),
            Text(f"{total_exposure:,.0f}", style="cyan"),
            Text(""),
            Text(""),
            Text(""),
            Text(""),
        )

        self.update(table)

    def refresh(self) -> None:
        """Rebuild the table and push the new renderable."""
        self._render_table()
        super().refresh()
