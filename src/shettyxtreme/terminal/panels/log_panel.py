"""Log panel — scrollable log viewer showing platform events.

Colour-coded by severity:
  INFO   → white
  WARN   → yellow
  ERROR  → red
  SIGNAL → cyan

Receives events from EventBus Topic.SYSTEM_STATUS.
"""

from datetime import datetime, timezone
from typing import Any

from rich.text import Text
from rich.table import Table
from textual.widgets import Static

from shettyxtreme.core.event_bus import Event, Topic


_LOG_LEVEL_STYLES: dict[str, str] = {
    "INFO": "white",
    "WARN": "yellow",
    "ERROR": "red",
    "SIGNAL": "cyan",
    "DEBUG": "grey62",
}


class LogPanel(Static):
    """Scrollable log viewer that renders colour-coded platform events."""

    DEFAULT_CSS = """
    LogPanel {
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        max_lines: int = 500,
        *,
        name: str | None = None,
        id: str | None = None,
    ) -> None:
        """Initialise the log panel.

        Args:
            max_lines: Maximum number of log entries retained in memory.
            name: Widget name for Textual.
            id: Widget DOM id.
        """
        super().__init__(name=name, id=id)
        self._max_lines: int = max_lines
        self._entries: list[dict[str, Any]] = []

    @property
    def entries(self) -> list[dict[str, Any]]:
        """Return a copy of current log entries."""
        return list(self._entries)

    def log(self, level: str, message: str, source: str = "system") -> None:
        """Append a log entry.

        Args:
            level: Severity label (INFO, WARN, ERROR, SIGNAL, DEBUG).
            message: The log message text.
            source: Component that generated the entry.
        """
        self._entries.append({
            "timestamp": datetime.now(timezone.utc),
            "level": level.upper(),
            "source": source,
            "message": message,
        })
        if len(self._entries) > self._max_lines:
            self._entries.pop(0)
        self.refresh()

    def handle_event(self, event: Event) -> None:
        """Generic handler for any EventBus event.

        Derives a log entry from the event's topic and data.

        Args:
            event: The event to log.
        """
        topic_str = event.topic.value if hasattr(event.topic, "value") else str(event.topic)
        level = "INFO"
        message = f"[{topic_str}] {event.data}"

        if event.topic == Topic.RISK_ALERT:
            level = "ERROR"
        elif event.topic == Topic.ORDER_REJECTED:
            level = "ERROR"
        elif event.topic == Topic.ORDER_PLACED:
            level = "SIGNAL"
        elif event.topic == Topic.SIGNAL_GENERATED:
            level = "SIGNAL"
        elif event.topic == Topic.CONFIG_CHANGED:
            level = "WARN"

        self.log(level, message, source=event.source)

    def handle_system_status(self, event: Event) -> None:
        """Handle SYSTEM_STATUS events specifically.

        Args:
            event: The system status event.
        """
        data = event.data
        if isinstance(data, dict):
            message = data.get("message", str(data))
        else:
            message = str(data)
        level = data.get("level", "INFO") if isinstance(data, dict) else "INFO"
        self.log(level, message, source=event.source)

    def clear(self) -> None:
        """Clear all log entries."""
        self._entries.clear()
        self.refresh()

    def on_mount(self) -> None:
        """Render initial empty log panel."""
        self._render_log()

    def _render_log(self) -> None:
        """Build the log table from current entries."""
        table = Table(expand=True, box=None, padding=(0, 1))
        table.add_column("Time", width=9, no_wrap=True)
        table.add_column("Level", width=6)
        table.add_column("Source", width=10, no_wrap=True)
        table.add_column("Message", min_width=30)

        # Show most recent entries at the bottom
        for entry in self._entries[-100:]:
            ts = entry["timestamp"]
            time_str = ts.strftime("%H:%M:%S")

            level = entry["level"]
            style = _LOG_LEVEL_STYLES.get(level, "white")

            source = entry["source"][:10]
            message = entry["message"]

            table.add_row(
                Text(time_str, style="grey62"),
                Text(level, style=style),
                Text(source, style="bold"),
                Text(message, style=style),
            )

        self.update(table)

    def refresh(self) -> None:
        """Rebuild and push the log display."""
        self._render_log()
        super().refresh()
