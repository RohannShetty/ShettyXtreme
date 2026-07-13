"""Terminal-specific configuration: colorscheme, refresh rate, default watchlist symbols."""

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class TerminalColors:
    """Color scheme definition for the terminal UI."""

    positive: str = "green"
    negative: str = "red"
    neutral: str = "white"
    info: str = "white"
    warning: str = "yellow"
    error: str = "red"
    signal: str = "cyan"
    highlight: str = "bold"
    muted: str = "grey62"
    header_bg: str = "blue"
    accent: str = "cyan"


@dataclass
class TerminalConfig:
    """All terminal UI configuration parameters."""

    # Color scheme
    colors: TerminalColors = field(default_factory=TerminalColors)

    # Refresh / update rates
    refresh_rate_ms: int = 1000  # How often panels update (milliseconds)
    log_max_lines: int = 500  # Max log entries to keep in buffer

    # Default watchlist symbols (Indian equities/indices)
    default_watchlist: list[str] = field(
        default_factory=lambda: [
            "NIFTY",
            "BANKNIFTY",
            "RELIANCE",
            "HDFCBANK",
            "TCS",
            "INFY",
        ]
    )

    # Broker connection status labels
    dhan_label: str = "DhanHQ"

    # Market status
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 30

    # Layout fractions (proportions of available space)
    top_row_height: int = 3  # 3 rows out of 5 for top content
    bottom_row_height: int = 2  # 2 rows out of 5 for bottom (log)

    # Supported modes
    SUPPORTED_MODES: ClassVar[list[str]] = ["observer", "live", "paper"]
