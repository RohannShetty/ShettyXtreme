"""Options Strategy panel — strategy selection, parameters, and payoff diagram.

Displays a dropdown of available strategies, computed metrics (max profit,
max loss, breakeven, POP), and a text-based payoff diagram.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.layout import Layout
from textual.widgets import Static
from textual.message import Message

from shettyxtreme.options.strategy_analyzer import (
    StrategyAnalyzer,
    StrategyAnalysis,
    StrategyParams,
    StrategyName,
)


class StrategySelected(Message):
    """Posted when the user changes the selected strategy."""

    def __init__(self, strategy: StrategyName) -> None:
        self.strategy = strategy
        super().__init__()


class OptionsStrategyPanel(Static):
    """Panel for selecting and analysing options strategies.

    Shows strategy parameters, risk/reward metrics, and a simple
    text-based payoff diagram.
    """

    DEFAULT_CSS = """
    OptionsStrategyPanel {
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
        self._analyzer = StrategyAnalyzer()
        self._current_strategy: StrategyName = "LONG_CALL"
        self._spot: float = 0.0
        self._strike: float = 0.0
        self._strike2: float = 0.0
        self._premium: float = 0.0
        self._premium2: float = 0.0
        self._iv: float = 0.0
        self._tte: float = 0.0
        self._analysis: StrategyAnalysis | None = None

    def set_spot(self, spot: float) -> None:
        """Set the current underlying price."""
        self._spot = spot
        self._recompute()
        self.refresh()

    def set_strike(self, strike: float) -> None:
        """Set the primary strike price."""
        self._strike = strike
        self._recompute()
        self.refresh()

    def set_strike2(self, strike: float) -> None:
        """Set the secondary strike price (for spreads)."""
        self._strike2 = strike
        self._recompute()
        self.refresh()

    def set_premium(self, premium: float) -> None:
        """Set the premium for the primary leg."""
        self._premium = premium
        self._recompute()
        self.refresh()

    def set_premium2(self, premium: float) -> None:
        """Set the premium for the secondary leg."""
        self._premium2 = premium
        self._recompute()
        self.refresh()

    def set_iv(self, iv: float) -> None:
        """Set implied volatility for POP estimation."""
        self._iv = iv
        self._recompute()
        self.refresh()

    def set_tte(self, tte: float) -> None:
        """Set time to expiry in years."""
        self._tte = tte
        self._recompute()
        self.refresh()

    def select_strategy(self, strategy: StrategyName) -> None:
        """Change the selected strategy and recompute."""
        self._current_strategy = strategy
        self._recompute()
        self.post_message(StrategySelected(strategy))
        self.refresh()

    def current_strategy(self) -> StrategyName:
        """Return the currently selected strategy name."""
        return self._current_strategy

    def _recompute(self) -> None:
        """Recompute strategy analysis with current parameters."""
        if self._spot <= 0:
            self._analysis = None
            return

        name = self._current_strategy
        params = StrategyParams(
            name=name,
            long_strike=self._strike,
            short_strike=self._strike2 if self._strike2 > 0 else self._strike + 500,
            long_strike2=self._strike - 500 if name in ("IRON_CONDOR", "STRANGLE") else 0,
            short_strike2=self._strike + 1000 if name == "IRON_CONDOR" else 0,
            premium_long=self._premium,
            premium_short=self._premium2 or self._premium * 0.6,
            premium_long2=self._premium * 0.3 if name in ("IRON_CONDOR",) else 0,
            premium_short2=self._premium * 0.5 if name == "IRON_CONDOR" else 0,
            spot=self._spot,
        )
        self._analysis = self._analyzer.analyze(params, self._iv, self._tte)

    def on_mount(self) -> None:
        """Render initial panel content."""
        self._render_content()

    def _render_content(self) -> None:
        """Build the panel content with strategy metrics and payoff diagram."""
        from rich.console import Group

        elements = []

        # Strategy name header
        display = StrategyAnalyzer.display_name(self._current_strategy)
        elements.append(Text(f"[bold]{display}[/bold]\n"))

        if self._analysis is None:
            elements.append(Text("Set spot price and strike to analyse", style="grey62"))
            self.update(Group(*elements))
            return

        a = self._analysis

        # Metrics table
        metrics = Table(expand=True, box=None, padding=(0, 1))
        metrics.add_column("Metric", style="bold", width=16)
        metrics.add_column("Value", justify="right", width=16)

        max_profit_str = "Unlimited" if a.max_profit == float("inf") else f"{a.max_profit:,.2f}"
        max_loss_str = "Unlimited" if a.max_loss == float("inf") else f"{a.max_loss:,.2f}"
        credit_str = "Credit" if a.is_credit else "Debit"

        metrics.add_row("Max Profit", max_profit_str)
        metrics.add_row("Max Loss", max_loss_str)
        metrics.add_row("Net Premium", f"{a.net_premium:,.2f} ({credit_str})")

        for i, be in enumerate(a.breakevens):
            metrics.add_row(f"Breakeven {i+1}", f"{be:,.2f}")

        metrics.add_row("POP", f"{a.probability_of_profit:.1%}")

        elements.append(metrics)

        # Payoff diagram (text-based)
        elements.append(Text(""))
        elements.append(Text("[bold]Payoff at Expiry[/bold]"))
        payoff_diagram = self._render_payoff_diagram(a)
        elements.append(payoff_diagram)

        self.update(Group(*elements))

    def _render_payoff_diagram(self, analysis: StrategyAnalysis) -> Text:
        """Render a simple text-based payoff diagram.

        Creates a 20-char wide representation showing the P&L shape.
        """
        payoffs = analysis.payoff_at_expiry
        if not payoffs:
            return Text("No payoff data", style="grey62")

        prices = [p for p, _ in payoffs]
        pnl_values = [pnl for _, pnl in payoffs]

        min_pnl = min(pnl_values)
        max_pnl = max(pnl_values)
        pnl_range = max_pnl - min_pnl if max_pnl > min_pnl else 1

        # Normalize to 5 rows
        rows = 5
        cols = 20

        # Sample every nth point
        step = max(1, len(pnl_values) // cols)
        sampled = pnl_values[::step][:cols]

        if len(sampled) < 2:
            return Text("Insufficient data", style="grey62")

        # Build rows
        lines: list[str] = []
        for row in range(rows - 1, -1, -1):
            threshold = min_pnl + (pnl_range * row / (rows - 1)) if rows > 1 else min_pnl
            line_chars: list[str] = []
            for val in sampled:
                if (row == 0 and val >= threshold) or (
                    row > 0 and val >= threshold
                ):
                    # Above this row's threshold
                    if val >= 0:
                        line_chars.append("+")
                    else:
                        line_chars.append("x")
                elif row == rows // 2:
                    line_chars.append("-")
                else:
                    line_chars.append(" ")
            lines.append("".join(line_chars))

        # Add price labels
        price_low = prices[0]
        price_high = prices[-1]
        lines.append(f"{price_low:,.0f}{' ' * (cols - 8)}{price_high:,.0f}")

        return Text("\n".join(lines))

    def refresh(self, **kwargs: Any) -> None:
        """Rebuild and re-render the panel."""
        self._render_content()
        super().refresh(**kwargs)
