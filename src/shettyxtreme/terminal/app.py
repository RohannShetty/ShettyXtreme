"""Main Textual Application for ShettyXtreme.

Four-panel (3×2 grid + log bar + status bar) layout:

    [Market Internals | Watchlist      | Positions/Orders]
    [Regime/Hints     | Scanners       | Options Chain   ]
    [Logs / Alerts (bottom bar)                          ]
    [Status Bar (very bottom)                            ]

Positions/Orders, Regime/Hints, and Options Chain are placeholders for Phase 1.
Hooks into EventBus to receive live market data.
"""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.widgets import Static, Header, Footer
from textual.binding import Binding
from textual.reactive import reactive

from shettyxtreme.core.event_bus import EventBus, Event, Topic
from shettyxtreme.core.config.config_manager import ConfigManager

from shettyxtreme.terminal.config import TerminalConfig
from shettyxtreme.terminal.panels import (
    WatchlistPanel,
    MarketInternalsPanel,
    StatusBar,
    LogPanel,
)


class PlaceholderPanel(Static):
    """Simple placeholder panel for Phase-1 unimplemented sections."""

    DEFAULT_CSS = """
    PlaceholderPanel {
        height: 100%;
        border: dashed $primary;
        padding: 1;
        content-align: center middle;
        color: $foreground-muted;
    }
    """

    def __init__(self, label: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._label = label

    def on_mount(self) -> None:
        self.update(f"[bold]{self._label}[/bold]\n[i]Phase 2[/i]")


class ShettyXtremeApp(App):
    """Main Textual application for the ShettyXtreme trading platform."""

    TITLE = "ShettyXtreme"
    SUB_TITLE = "Indian-Market Trading Intelligence"

    CSS = """
    Screen {
        background: $surface;
    }

    /* Main content grid: 3 columns × 2 rows */
    #main-grid {
        grid-size: 3 2;
        grid-gutter: 1;
        grid-rows: 1fr 1fr;
        grid-columns: 2fr 3fr 2fr;
        margin: 1 1 0 1;
        height: 3fr;
    }

    /* Log panel spans full width below the grid */
    #log-panel-container {
        height: 2fr;
        margin: 1 1 0 1;
    }

    #log-panel-container LogPanel {
        height: 100%;
    }

    /* Status bar fixed at the very bottom */
    StatusBar {
        dock: bottom;
        height: 1;
        margin: 0 1 0 1;
    }

    /* Individual panel sizing within the grid */
    #watchlist-panel {
        height: 100%;
    }

    #market-internals-panel {
        height: 100%;
    }
    """

    BINDINGS: list[Binding] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "reset_layout", "Reset Layout", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(
        self,
        event_bus: EventBus | None = None,
        terminal_config: TerminalConfig | None = None,
        config_manager: ConfigManager | None = None,
    ) -> None:
        """Initialise the application.

        Args:
            event_bus: Shared EventBus instance. Creates one if not provided.
            terminal_config: Terminal-specific configuration.
            config_manager: Platform configuration manager.
        """
        super().__init__()
        self._event_bus: EventBus = event_bus or EventBus()
        self._terminal_config: TerminalConfig = terminal_config or TerminalConfig()
        self._config_manager: ConfigManager = config_manager or ConfigManager()
        self._event_bus_task: Any = None

    def compose(self) -> ComposeResult:
        """Build the terminal layout by composing child widgets.

        Yields:
            Textual widget instances in display order.
        """
        # Get default watchlist from config
        default_symbols = list(self._terminal_config.default_watchlist)

        # Instantiate panels
        self._market_internals = MarketInternalsPanel(id="market-internals-panel")
        self._watchlist = WatchlistPanel(
            symbols=default_symbols,
            id="watchlist-panel",
        )
        self._positions = PlaceholderPanel("Positions / Orders", id="positions-panel")
        self._regime = PlaceholderPanel("Regime / Hints", id="regime-panel")
        self._scanners = PlaceholderPanel("Scanners", id="scanners-panel")
        self._options = PlaceholderPanel("Options Chain", id="options-panel")
        self._log = LogPanel(
            max_lines=self._terminal_config.log_max_lines,
            id="log-panel",
        )
        self._status_bar = StatusBar(
            mode=self._config_manager.config.mode,
            id="status-bar",
        )

        # Configure market hours from config
        tc = self._terminal_config
        self._status_bar.set_market_hours(
            tc.market_open_hour,
            tc.market_open_minute,
            tc.market_close_hour,
            tc.market_close_minute,
        )

        # Compose layout
        with Grid(id="main-grid"):
            yield self._market_internals
            yield self._watchlist
            yield self._positions
            yield self._regime
            yield self._scanners
            yield self._options

        with Container(id="log-panel-container"):
            yield self._log

        yield self._status_bar

    def on_mount(self) -> None:
        """Post-mount initialisation: start event bus listener."""
        self._start_event_bus_listener()

    def _start_event_bus_listener(self) -> None:
        """Subscribe to EventBus topics and start consuming events."""
        # Subscribe panels to relevant topics
        self._event_bus.subscribe(Topic.MARKET_DATA_TICK, self._on_market_tick)
        self._event_bus.subscribe(Topic.SYSTEM_STATUS, self._on_system_status)
        self._event_bus.subscribe(Topic.RISK_ALERT, self._on_log_event)
        self._event_bus.subscribe(Topic.ORDER_PLACED, self._on_log_event)
        self._event_bus.subscribe(Topic.ORDER_REJECTED, self._on_log_event)
        self._event_bus.subscribe(Topic.SIGNAL_GENERATED, self._on_log_event)

        # Start the bus consumer in a background task
        self._event_bus_task = self.set_interval(
            self._terminal_config.refresh_rate_ms / 1000.0,
            self._poll_event_bus,
        )

    async def _on_market_tick(self, event: Event) -> None:
        """Dispatch tick events to Watchlist and Market Internals panels.

        Args:
            event: The MARKET_DATA_TICK event.
        """
        self._watchlist.handle_tick(event)
        self._market_internals.handle_tick(event)

    async def _on_system_status(self, event: Event) -> None:
        """Dispatch system status events to relevant panels.

        Args:
            event: The SYSTEM_STATUS event.
        """
        self._market_internals.handle_system_status(event)
        self._status_bar.handle_system_status(event)
        self._log.handle_system_status(event)

    async def _on_log_event(self, event: Event) -> None:
        """Forward general events to the LogPanel.

        Args:
            event: The event to log.
        """
        self._log.handle_event(event)

    def _poll_event_bus(self) -> None:
        """Periodic no-op to keep the event bus flowing.

        The real event flow happens via the async handlers registered
        with the bus. This interval ensures Textual's event loop
        stays responsive.
        """

    def action_reset_layout(self) -> None:
        """Reset the terminal layout to default (keybinding r)."""
        self._log.log("INFO", "Layout reset requested", source="terminal")

    async def shutdown(self) -> None:
        """Clean shutdown: stop the event bus."""
        if self._event_bus:
            await self._event_bus.stop()
        await super().shutdown()
