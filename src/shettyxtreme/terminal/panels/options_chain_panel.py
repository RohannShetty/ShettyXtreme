"""Options Chain panel — displays full option chain in a Rich Table.

Shows strike, CE LTP/IV/Delta/OI and PE LTP/IV/Delta/OI.
Color-coded by moneyness: OTM in gray, ATM highlighted, ITM in bold.
Highlights unusual OI changes from OITracker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from textual.message import Message

from shettyxtreme.core.event_bus import Event, Topic
from shettyxtreme.options.oi_tracker import OITracker, OIAlert


class ExpirySelected(Message):
    """Posted when the user selects a different expiry."""

    def __init__(self, expiry: str) -> None:
        self.expiry = expiry
        super().__init__()


class OptionsChainPanel(Static):
    """Displays an option chain with Greeks and OI data.

    Layout: Strike | CE LTP | CE IV | CE Delta | CE OI |
            PE LTP | PE IV | PE Delta | PE OI
    """

    class StrikeClicked(Message):
        """Posted when a strike row is clicked."""

        def __init__(self, strike: float) -> None:
            self.strike = strike
            super().__init__()

    DEFAULT_CSS = """
    OptionsChainPanel {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        oi_tracker: OITracker | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id)
        self._underlying: str = ""
        self._expiry: str = ""
        self._expiries: list[str] = []
        self._contracts: list[dict[str, Any]] = []
        self._spot: float = 0.0
        self._oi_tracker: OITracker | None = oi_tracker

    def set_underlying(self, symbol: str) -> None:
        """Set the underlying symbol."""
        self._underlying = symbol
        self.refresh()

    def set_expiry(self, expiry: str) -> None:
        """Set the current expiry."""
        self._expiry = expiry
        self.refresh()

    def set_expiries(self, expiries: list[str]) -> None:
        """Set the list of available expiries."""
        self._expiries = expiries
        self.refresh()

    def update_chain(
        self,
        contracts: list[dict[str, Any]],
        spot: float | None = None,
        expiry: str | None = None,
    ) -> None:
        """Update the full option chain.

        Args:
            contracts: List of contract dictionaries. Each dict should have:
                strike, option_type, ltp, iv, delta, gamma, theta, vega, oi
            spot: Current underlying price (for moneyness coloring).
            expiry: Expiry date string.
        """
        self._contracts = contracts
        if spot is not None:
            self._spot = spot
        if expiry is not None:
            self._expiry = expiry
        self.refresh()

    def handle_tick(self, event: Event) -> None:
        """Process MARKET_DATA_TICK events for spot updates.

        Args:
            event: The event containing tick data.
        """
        data = event.data
        if isinstance(data, dict):
            symbol = data.get("symbol", "")
            if symbol == self._underlying:
                self._spot = float(data.get("ltp", self._spot))
                self.refresh()

    def on_mount(self) -> None:
        """Render initial panel content."""
        self._render_table()

    def _get_moneyness_style(
        self, strike: float, option_type: str,
    ) -> tuple[str, bool, bool]:
        """Return (style, is_atm, is_itm) for a strike/type combo.

        Args:
            strike: Option strike price.
            option_type: 'CE' or 'PE'.

        Returns:
            Tuple of (style_string, is_atm, is_itm).
        """
        if self._spot <= 0:
            return "", False, False

        diff_pct = abs(strike - self._spot) / self._spot
        is_atm = diff_pct < 0.005  # Within 0.5% = ATM

        if option_type == "CE":
            is_itm = strike < self._spot
        else:
            is_itm = strike > self._spot

        if is_atm:
            return "bold yellow", True, False
        elif is_itm:
            return "bold", False, True
        else:
            return "grey62", False, False

    def _render_table(self) -> None:
        """Build the Rich table with option chain data."""
        table = Table(expand=True, box=None, padding=(0, 1))
        table.add_column("Strike", justify="right", width=10, style="bold")
        table.add_column("CE LTP", justify="right", width=10)
        table.add_column("CE IV%", justify="right", width=8)
        table.add_column("CE Delta", justify="right", width=8)
        table.add_column("CE OI", justify="right", width=10)
        table.add_column("PE LTP", justify="right", width=10)
        table.add_column("PE IV%", justify="right", width=8)
        table.add_column("PE Delta", justify="right", width=8)
        table.add_column("PE OI", justify="right", width=10)

        # Group contracts by strike
        strikes: dict[float, dict[str, dict[str, Any]]] = {}
        for contract in self._contracts:
            strike = float(contract.get("strike", 0))
            opt_type = str(contract.get("option_type", "")).upper()
            if strike not in strikes:
                strikes[strike] = {"CE": {}, "PE": {}}
            if opt_type in ("CE", "PE"):
                strikes[strike][opt_type] = contract

        # Sort strikes ascending
        sorted_strikes = sorted(strikes.keys())

        for strike in sorted_strikes:
            ce = strikes[strike].get("CE", {})
            pe = strikes[strike].get("PE", {})

            ce_ltp = ce.get("ltp", 0) or 0
            ce_iv = ce.get("iv", 0) or 0
            ce_delta = ce.get("delta", 0) or 0
            ce_oi = ce.get("oi", 0) or 0
            pe_ltp = pe.get("ltp", 0) or 0
            pe_iv = pe.get("iv", 0) or 0
            pe_delta = pe.get("delta", 0) or 0
            pe_oi = pe.get("oi", 0) or 0

            # Get OI change data
            oi_alert_ce = ""
            oi_alert_pe = ""
            if self._oi_tracker and self._expiry:
                ce_change = self._oi_tracker.get_oi_change(
                    self._underlying, self._expiry, strike, "CE"
                )
                pe_change = self._oi_tracker.get_oi_change(
                    self._underlying, self._expiry, strike, "PE"
                )
                if abs(ce_change) >= 25:
                    oi_alert_ce = " *" if ce_change > 0 else " v"
                if abs(pe_change) >= 25:
                    oi_alert_pe = " *" if pe_change > 0 else " v"

            # Moneyness styling
            ce_style, _, _ = self._get_moneyness_style(strike, "CE")
            pe_style, _, _ = self._get_moneyness_style(strike, "PE")

            strike_text = Text(f"{strike:,.0f}")
            if self._spot > 0:
                diff_pct = abs(strike - self._spot) / self._spot
                if diff_pct < 0.005:
                    strike_text.stylize("bold yellow")

            table.add_row(
                strike_text,
                Text(f"{ce_ltp:.2f}", style=ce_style),
                Text(f"{ce_iv*100:.1f}%", style=ce_style),
                Text(f"{ce_delta:.3f}", style=ce_style),
                Text(f"{ce_oi:,}{oi_alert_ce}", style=ce_style),
                Text(f"{pe_ltp:.2f}", style=pe_style),
                Text(f"{pe_iv*100:.1f}%", style=pe_style),
                Text(f"{pe_delta:.3f}", style=pe_style),
                Text(f"{pe_oi:,}{oi_alert_pe}", style=pe_style),
            )

        self._renderable = table

    def refresh(self, **kwargs: Any) -> None:
        """Rebuild and re-render the panel."""
        self._render_table()
        super().refresh(**kwargs)
