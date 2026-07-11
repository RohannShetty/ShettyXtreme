"""Watchlist panel — displays user-defined instruments with live LTP, change%, volume.

Colour-coded: green for positive change, red for negative, neutral for flat.
Supports add/remove symbols. Data sourced from EventBus (MARKET_DATA_TICK).
"""

from datetime import datetime, timezone
from typing import Any, ClassVar

from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from textual.message import Message

from shettyxtreme.core.event_bus import Event, Topic
from shettyxtreme.core.data_models import Tick


class WatchlistPanel(Static):
    """A panel that displays a watchlist of instruments with live market data."""

    class SymbolAdded(Message):
        """Posted when a symbol is added to the watchlist."""

        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            super().__init__()

    class SymbolRemoved(Message):
        """Posted when a symbol is removed from the watchlist."""

        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            super().__init__()

    DEFAULT_CSS = """
    WatchlistPanel {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Initialise the watchlist panel.

        Args:
            symbols: Initial list of instrument symbols to track.
            name: Widget name for Textual.
            id: Widget DOM id.
        """
        super().__init__(name=name, id=id)
        self._symbols: list[str] = symbols or []
        self._data: dict[str, dict[str, Any]] = {}
        self._config_refresh_rate: int = 1000

    def set_refresh_rate(self, ms: int) -> None:
        """Update the internal refresh rate hint."""
        self._config_refresh_rate = ms

    @property
    def symbols(self) -> list[str]:
        """Return the current list of tracked symbols."""
        return list(self._symbols)

    def add_symbol(self, symbol: str) -> None:
        """Add a symbol to the watchlist and post SymbolAdded.

        Args:
            symbol: Instrument symbol (e.g. 'RELIANCE').
        """
        if symbol and symbol not in self._symbols:
            self._symbols.append(symbol)
            self.post_message(self.SymbolAdded(symbol))
            self.refresh()

    def remove_symbol(self, symbol: str) -> None:
        """Remove a symbol from the watchlist and post SymbolRemoved.

        Args:
            symbol: Instrument symbol to remove.
        """
        if symbol in self._symbols:
            self._symbols.remove(symbol)
            self._data.pop(symbol, None)
            self.post_message(self.SymbolRemoved(symbol))
            self.refresh()

    def handle_tick(self, event: Event) -> None:
        """Process a MARKET_DATA_TICK event from the EventBus.

        Args:
            event: The event containing tick data.
        """
        tick_data = event.data
        if isinstance(tick_data, dict):
            symbol = tick_data.get("symbol", "")
            ltp = tick_data.get("ltp", 0.0)
            volume = tick_data.get("volume", 0)
        elif isinstance(tick_data, Tick):
            symbol = tick_data.symbol
            ltp = tick_data.ltp
            volume = tick_data.volume
        else:
            return

        if symbol not in self._symbols:
            return

        prev = self._data.get(symbol, {})
        prev_ltp = prev.get("ltp", ltp)
        change = ltp - prev_ltp if prev_ltp else 0.0
        change_pct = (change / prev_ltp * 100) if prev_ltp else 0.0

        self._data[symbol] = {
            "ltp": ltp,
            "volume": volume,
            "change": change,
            "change_pct": change_pct,
            "timestamp": (
                tick_data.timestamp if isinstance(tick_data, Tick)
                else datetime.now(timezone.utc)
            ),
        }
        self.refresh()

    def on_mount(self) -> None:
        """Render the initial watchlist table."""
        self._render_table()

    def _render_table(self) -> None:
        """Build and set the Rich table for display."""
        table = Table(expand=True, box=None, padding=(0, 1))
        table.add_column("Symbol", style="bold", width=12)
        table.add_column("LTP", justify="right", width=10)
        table.add_column("Chg%", justify="right", width=8)
        table.add_column("Vol", justify="right", width=10)

        for symbol in self._symbols:
            data = self._data.get(symbol, {})
            ltp = data.get("ltp", 0.0)
            change = data.get("change", 0.0)
            change_pct = data.get("change_pct", 0.0)
            volume = data.get("volume", 0)

            if change > 0:
                colour = "green"
                arrow = "▲"
            elif change < 0:
                colour = "red"
                arrow = "▼"
            else:
                colour = "white"
                arrow = "–"

            ltp_str = f"{ltp:.2f}" if ltp else "—"
            chg_str = f"{arrow}{change_pct:.2f}%" if change != 0 else f" {change_pct:.2f}%"
            vol_str = f"{volume:,}" if volume else "—"

            table.add_row(
                symbol,
                Text(ltp_str, style=colour),
                Text(chg_str, style=colour),
                Text(vol_str, style="grey62"),
            )

        self.update(table)

    def refresh(self) -> None:
        """Rebuild the table and push the new renderable."""
        self._render_table()
        super().refresh()
