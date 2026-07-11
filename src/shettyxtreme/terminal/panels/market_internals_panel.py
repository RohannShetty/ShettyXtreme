"""Market Internals panel — shows Nifty 50, Bank Nifty, VIX, A/D ratio, P/C ratio.

Also displays session state (pre-open, live, post-close).
Auto-updates from EventBus MARKET_DATA_TICK events.
"""

from datetime import datetime, timezone
from typing import Any

from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from shettyxtreme.core.event_bus import Event, Topic


_SESSION_LABELS: dict[str, str] = {
    "preopen": "Pre-Open",
    "live": "Live",
    "closed": "Closed",
    "postclose": "Post-Close",
}

_SESSION_COLOURS: dict[str, str] = {
    "preopen": "yellow",
    "live": "green",
    "closed": "red",
    "postclose": "grey62",
}


class MarketInternalsPanel(Static):
    """Displays key market indices and session-level statistics."""

    DEFAULT_CSS = """
    MarketInternalsPanel {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id)
        self._indices: dict[str, dict[str, Any]] = {
            "NIFTY 50": {"ltp": 0.0, "change": 0.0, "change_pct": 0.0},
            "BANK NIFTY": {"ltp": 0.0, "change": 0.0, "change_pct": 0.0},
            "VIX": {"ltp": 0.0, "change": 0.0, "change_pct": 0.0},
        }
        self._session_state: str = "closed"
        self._advance_decline: dict[str, int] = {"advances": 0, "declines": 0, "unchanged": 0}
        self._put_call_ratio: float = 0.0

    @property
    def session_state(self) -> str:
        """Return the current market session state identifier."""
        return self._session_state

    def handle_tick(self, event: Event) -> None:
        """Process a MARKET_DATA_TICK event for index data.

        Args:
            event: The event containing tick data.
        """
        data = event.data
        if isinstance(data, dict):
            symbol = str(data.get("symbol", ""))
            ltp = float(data.get("ltp", 0.0))
            change = float(data.get("change", 0.0))
            change_pct = float(data.get("change_pct", 0.0))

            # Map common symbols to our internal names
            symbol_map: dict[str, str] = {
                "NIFTY": "NIFTY 50",
                "NIFTY50": "NIFTY 50",
                "BANKNIFTY": "BANK NIFTY",
                "BANK_NIFTY": "BANK NIFTY",
                "INDIAVIX": "VIX",
                "VIX": "VIX",
            }
            key = symbol_map.get(symbol.upper())
            if key and key in self._indices:
                self._indices[key] = {"ltp": ltp, "change": change, "change_pct": change_pct}
                self.refresh()

    def handle_system_status(self, event: Event) -> None:
        """Process a SYSTEM_STATUS event for session state changes.

        Args:
            event: The event containing system status data.
        """
        data = event.data
        if isinstance(data, dict):
            session = data.get("session_state", "")
            if session:
                self._session_state = session
                self.refresh()

            adv = data.get("advances")
            dec = data.get("declines")
            unc = data.get("unchanged")
            if adv is not None and dec is not None:
                self._advance_decline = {
                    "advances": int(adv),
                    "declines": int(dec),
                    "unchanged": int(unc) if unc is not None else 0,
                }
                self.refresh()

            pcr = data.get("put_call_ratio")
            if pcr is not None:
                self._put_call_ratio = float(pcr)
                self.refresh()

    def on_mount(self) -> None:
        """Render initial panel content."""
        self._render_table()

    def _render_table(self) -> None:
        """Build the Rich table with index data and market internals."""
        table = Table(expand=True, box=None, padding=(0, 1), title="Market Internals")
        table.add_column("Index", style="bold", width=14)
        table.add_column("LTP", justify="right", width=10)
        table.add_column("Chg%", justify="right", width=8)

        for name, data in self._indices.items():
            ltp = data["ltp"]
            chg = data["change_pct"]
            if chg > 0:
                colour = "green"
                arrow = "▲"
            elif chg < 0:
                colour = "red"
                arrow = "▼"
            else:
                colour = "white"
                arrow = "–"

            ltp_str = f"{ltp:.2f}" if ltp else "—"
            chg_str = f"{arrow}{abs(chg):.2f}%" if chg != 0 else f" {chg:.2f}%"
            table.add_row(name, Text(ltp_str, style=colour), Text(chg_str, style=colour))

        # Session state row
        session_label = _SESSION_LABELS.get(self._session_state, self._session_state.title())
        session_colour = _SESSION_COLOURS.get(self._session_state, "white")
        table.add_row(
            Text("Session", style="bold"),
            Text("—", style="grey62"),
            Text(session_label, style=session_colour),
        )

        # Advance / Decline
        ad = self._advance_decline
        a_d_text = f"A:{ad['advances']} D:{ad['declines']} U:{ad['unchanged']}"
        table.add_row(
            Text("A/D", style="bold"),
            Text(a_d_text, style="grey62"),
            Text(""),
        )

        # Put / Call ratio
        pcr_text = f"{self._put_call_ratio:.2f}" if self._put_call_ratio else "—"
        table.add_row(
            Text("P/C Ratio", style="bold"),
            Text(pcr_text, style="cyan"),
            Text(""),
        )

        self.update(table)

    def refresh(self) -> None:
        """Rebuild the panel content."""
        self._render_table()
        super().refresh()
