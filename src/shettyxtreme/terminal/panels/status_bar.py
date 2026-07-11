"""Status bar — shows connection status (OpenAlgo, Dhan), mode indicator,
current time IST, and market open/closed status.

Positioned at the very bottom of the terminal layout.
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from rich.text import Text
from textual.widgets import Static
from textual.reactive import reactive

from shettyxtreme.core.event_bus import Event, Topic


IST = timezone(timedelta(hours=5, minutes=30))


def _ist_now() -> datetime:
    """Return the current time in Indian Standard Time."""
    return datetime.now(IST)


class StatusBar(Static):
    """Bottom status bar displaying broker connectivity, mode, time, and market state."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    """

    mode: str = reactive("observer")
    market_status_open: bool = reactive(False)
    dhan_connected: bool = reactive(False)
    openalgo_connected: bool = reactive(False)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        mode: str = "observer",
    ) -> None:
        """Initialise the status bar.

        Args:
            name: Widget name for Textual.
            id: Widget DOM id.
            mode: Initial platform mode (observer/live/paper).
        """
        super().__init__(name=name, id=id)
        self.mode = mode
        self._market_open_hour: int = 9
        self._market_open_minute: int = 15
        self._market_close_hour: int = 15
        self._market_close_minute: int = 30
        self._update_timer: Any = None

    def set_market_hours(
        self,
        open_hour: int,
        open_minute: int,
        close_hour: int,
        close_minute: int,
    ) -> None:
        """Configure the expected market hours for status detection.

        Args:
            open_hour: Market open hour (IST, 24h).
            open_minute: Market open minute.
            close_hour: Market close hour (IST, 24h).
            close_minute: Market close minute.
        """
        self._market_open_hour = open_hour
        self._market_open_minute = open_minute
        self._market_close_hour = close_hour
        self._market_close_minute = close_minute

    def handle_system_status(self, event: Event) -> None:
        """Process a SYSTEM_STATUS event.

        Args:
            event: The event containing status data.
        """
        data = event.data
        if isinstance(data, dict):
            if "dhan_connected" in data:
                self.dhan_connected = bool(data["dhan_connected"])
            if "openalgo_connected" in data:
                self.openalgo_connected = bool(data["openalgo_connected"])
            if "mode" in data:
                self.mode = str(data["mode"])
            session = data.get("session_state", "")
            if session:
                self.market_status_open = session == "live"

    def _check_market_status(self) -> bool:
        """Determine whether the market is currently open based on IST time.

        Returns:
            True if current IST time falls within market hours.
        """
        now = _ist_now()
        open_td = timedelta(hours=self._market_open_hour, minutes=self._market_open_minute)
        close_td = timedelta(hours=self._market_close_hour, minutes=self._market_close_minute)
        now_td = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
        return open_td <= now_td <= close_td and now.weekday() < 5

    def on_mount(self) -> None:
        """Start the periodic clock update timer."""
        self.set_interval(1.0, self._tick_clock)

    def _tick_clock(self) -> None:
        """Update the displayed time and market status every second."""
        self.market_status_open = self._check_market_status()
        self.refresh()

    def watch_mode(self, new_mode: str) -> None:
        """Reactively update display when mode changes."""
        self.refresh()

    def _render_content(self) -> Text:
        """Build the status bar line as a Rich Text object.

        Layout:
          [OpenAlgo status] [DhanHQ status] | [Mode] | [IST time] | [Market status]
        """
        parts: list[tuple[str, str]] = []

        # OpenAlgo
        if self.openalgo_connected:
            parts.append((" OpenAlgo ● ", "green"))
        else:
            parts.append((" OpenAlgo ○ ", "red"))

        parts.append((" ", ""))

        # Dhan
        if self.dhan_connected:
            parts.append((" DhanHQ ● ", "green"))
        else:
            parts.append((" DhanHQ ○ ", "red"))

        parts.append((" │ ", "grey62"))

        # Mode
        mode_colour = {"observer": "cyan", "live": "green", "paper": "yellow"}.get(
            self.mode, "white"
        )
        parts.append((f" Mode:{self.mode} ", mode_colour))

        parts.append((" │ ", "grey62"))

        # IST time
        now = _ist_now()
        time_str = now.strftime("%H:%M:%S IST")
        parts.append((f" {time_str} ", "bold"))

        parts.append((" │ ", "grey62"))

        # Market status
        if self.market_status_open:
            parts.append((" MARKET OPEN ", "green"))
        else:
            parts.append((" MARKET CLOSED ", "red"))

        parts.append((" ", ""))

        text = Text.assemble(*parts)
        return text

    def refresh(self) -> None:
        """Update the status bar display."""
        self.update(self._render_content())
        super().refresh()
