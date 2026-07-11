"""ScannerPanel — displays scan results and generated signals in a Rich Table.

Colour-coded by direction (bullish=green, bearish=red, neutral=gray).
Auto-updates from EventBus SIGNAL_GENERATED events dispatched by the app.
Rows post a SignalClicked message to allow the app to show reasoning detail.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table
from rich.text import Text
from textual.message import Message
from textual.widgets import Static

from shettyxtreme.core.event_bus import Event
from shettyxtreme.intelligence.signals import Signal


class ScannerPanel(Static):
    """Displays recent scan signals in a colour-coded Rich Table.

    Receives SIGNAL_GENERATED events forwarded by the app.  Keeps a
    rolling window of the *N* most recent signals (default 50).
    """

    class SignalClicked(Message):
        """Posted when a user clicks a signal row to see reasoning detail.

        Attributes:
            signal: The Signal dataclass with full reasoning text.
        """

        def __init__(self, signal: Signal) -> None:
            self.signal = signal
            super().__init__()

    DEFAULT_CSS = """
    ScannerPanel {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        max_signals: int = 50,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Initialise the scanner panel.

        Args:
            max_signals: Maximum number of signals to retain in the view.
            name: Widget name for Textual.
            id: Widget DOM id.
        """
        super().__init__(name=name, id=id)
        self._max_signals = max_signals
        self._signals: list[Signal] = []

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def signals(self) -> list[Signal]:
        """Return a copy of the current signal list (newest last)."""
        return list(self._signals)

    def clear(self) -> None:
        """Remove all signals from the display."""
        self._signals.clear()
        self.refresh()

    def handle_signal(self, event: Event) -> None:
        """Process a SIGNAL_GENERATED event forwarded by the app.

        Args:
            event: The event whose *data* attribute is a ``Signal`` instance.
        """
        signal = event.data
        if not isinstance(signal, Signal):
            return
        self._signals.append(signal)
        if len(self._signals) > self._max_signals:
            self._signals.pop(0)
        self.refresh()

    # ── Textual lifecycle ───────────────────────────────────────────────

    def on_mount(self) -> None:
        """Render the initial (empty) table."""
        self._render_table()

    # ── Rendering helpers ───────────────────────────────────────────────

    def _render_table(self) -> None:
        """Build the Rich :class:`Table` and push it as the widget content."""
        table = Table(expand=True, box=None, padding=(0, 1), title="Scanner Signals")
        table.add_column("Symbol", style="bold", width=10)
        table.add_column("Type", width=12)
        table.add_column("Direction", width=10)
        table.add_column("Strength", justify="right", width=8)
        table.add_column("Time", width=16)

        for signal in reversed(self._signals):
            direction_colour, arrow = self._direction_style(signal.direction)

            source_label = {
                "breakout": "Breakout",
                "gap": "Gap",
            }.get(signal.source, signal.source.title())

            strength_bar = self._render_strength(signal.strength)
            time_str = (
                signal.timestamp.strftime("%H:%M:%S")
                if signal.timestamp
                else "—"
            )

            table.add_row(
                signal.symbol,
                Text(source_label, style="cyan"),
                Text(f"{arrow} {signal.direction.title()}", style=direction_colour),
                Text(strength_bar, style=self._strength_colour(signal.strength)),
                Text(time_str, style="grey62"),
            )

        if not self._signals:
            table.add_row(
                Text("No signals yet...", style="grey54"),
                "",
                "",
                "",
                "",
            )

        self.update(table)

    @staticmethod
    def _direction_style(direction: str) -> tuple[str, str]:
        """Return (colour, arrow) for a given signal direction."""
        if direction == "bullish":
            return "green", "▲"
        if direction == "bearish":
            return "red", "▼"
        return "gray", "–"

    @staticmethod
    def _render_strength(strength: float) -> str:
        """Render a strength value (0-10) as a unicode bar."""
        filled = max(0, min(10, int(strength / 10.0 * 10)))
        return "█" * filled + "░" * (10 - filled)

    @staticmethod
    def _strength_colour(strength: float) -> str:
        """Return a Rich colour name for the given strength."""
        if strength >= 7.0:
            return "bright_green"
        if strength >= 4.0:
            return "yellow"
        return "grey62"

    # ── Refresh ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Rebuild the table and schedule a UI refresh."""
        self._render_table()
        super().refresh()
