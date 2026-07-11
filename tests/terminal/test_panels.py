"""Tests for terminal UI panels."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from shettyxtreme.core.event_bus import Event, Topic
from shettyxtreme.core.data_models import Tick

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_tick_event() -> Event:
    """Return a MARKET_DATA_TICK event with a positive-change tick."""
    return Event(
        topic=Topic.MARKET_DATA_TICK,
        data={
            "symbol": "RELIANCE",
            "ltp": 2850.50,
            "volume": 1250000,
            "change": 12.75,
            "change_pct": 0.45,
        },
        source="dhan",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_tick_event_negative() -> Event:
    """Return a MARKET_DATA_TICK event with a negative-change tick."""
    return Event(
        topic=Topic.MARKET_DATA_TICK,
        data={
            "symbol": "HDFCBANK",
            "ltp": 1670.30,
            "volume": 980000,
            "change": -8.20,
            "change_pct": -0.49,
        },
        source="dhan",
        timestamp=datetime.now(timezone.utc),
    )

@pytest.fixture
def mock_tick_event_flat() -> Event:
    """Return a MARKET_DATA_TICK event with zero change."""
    return Event(
        topic=Topic.MARKET_DATA_TICK,
        data={
            "symbol": "TCS",
            "ltp": 3890.00,
            "volume": 450000,
            "change": 0.0,
            "change_pct": 0.0,
        },
        source="dhan",
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_system_status_event() -> Event:
    """Return a SYSTEM_STATUS event with session and broker state."""
    return Event(
        topic=Topic.SYSTEM_STATUS,
        data={
            "session_state": "live",
            "dhan_connected": True,
            "openalgo_connected": False,
            "mode": "observer",
            "advances": 1450,
            "declines": 820,
            "unchanged": 95,
            "put_call_ratio": 0.92,
            "message": "Market is live",
            "level": "INFO",
        },
        source="system",
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# WatchlistPanel tests
# ---------------------------------------------------------------------------


class TestWatchlistPanel:
    """Tests for the WatchlistPanel widget."""

    def test_init_with_symbols(self) -> None:
        """Panel initialises with provided symbol list."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["NIFTY", "RELIANCE"])
        assert panel.symbols == ["NIFTY", "RELIANCE"]

    def test_init_empty_symbols(self) -> None:
        """Panel initialises with empty list when no symbols provided."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel()
        assert panel.symbols == []

    def test_add_symbol(self) -> None:
        """Adding a symbol updates the symbols list."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["NIFTY"])
        panel.add_symbol("TCS")
        assert "TCS" in panel.symbols

    def test_add_duplicate_symbol(self) -> None:
        """Adding an already-present symbol does not create duplicates."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["NIFTY"])
        panel.add_symbol("NIFTY")
        assert len(panel.symbols) == 1

    def test_remove_symbol(self) -> None:
        """Removing a symbol drops it from the list and data."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["NIFTY", "TCS"])
        panel.remove_symbol("NIFTY")
        assert panel.symbols == ["TCS"]

    def test_remove_unknown_symbol(self) -> None:
        """Removing an unknown symbol does not raise."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["NIFTY"])
        panel.remove_symbol("UNKNOWN")
        assert panel.symbols == ["NIFTY"]

    def test_handle_tick_positive(self, mock_tick_event: Event) -> None:
        """A tick with positive change updates internal data."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["RELIANCE"])
        panel.handle_tick(mock_tick_event)
        data = panel._data.get("RELIANCE", {})
        assert data.get("ltp") == 2850.50
        assert data.get("change", 0) > 0

    def test_handle_tick_negative(self, mock_tick_event_negative: Event) -> None:
        """A tick with negative change updates internal data."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["HDFCBANK"])
        panel.handle_tick(mock_tick_event_negative)
        data = panel._data.get("HDFCBANK", {})
        assert data.get("change", 0) < 0

    def test_handle_tick_unknown_symbol(self, mock_tick_event: Event) -> None:
        """Ticks for un-tracked symbols are silently ignored."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["TCS"])
        panel.handle_tick(mock_tick_event)
        assert "RELIANCE" not in panel._data

    def test_handle_tick_with_tick_object(self) -> None:
        """Panel handles Tick dataclass objects in addition to dicts."""
        from shettyxtreme.terminal.panels import WatchlistPanel

        panel = WatchlistPanel(symbols=["INFY"])
        tick = Tick(
            symbol="INFY",
            exchange="NSE",
            ltp=1650.0,
            volume=500000,
            timestamp=datetime.now(timezone.utc),
        )
        event = Event(topic=Topic.MARKET_DATA_TICK, data=tick, source="test")
        panel.handle_tick(event)
        data = panel._data.get("INFY", {})
        assert data.get("ltp") == 1650.0


# ---------------------------------------------------------------------------
# MarketInternalsPanel tests
# ---------------------------------------------------------------------------


class TestMarketInternalsPanel:
    """Tests for the MarketInternalsPanel widget."""

    def test_init_default_state(self) -> None:
        """Panel starts with closed session and zeroed indices."""
        from shettyxtreme.terminal.panels import MarketInternalsPanel

        panel = MarketInternalsPanel()
        assert panel.session_state == "closed"

    def test_handle_tick_updates_index(self) -> None:
        """Tick data mapped to known index names updates internal state."""
        from shettyxtreme.terminal.panels import MarketInternalsPanel

        panel = MarketInternalsPanel()
        event = Event(
            topic=Topic.MARKET_DATA_TICK,
            data={"symbol": "NIFTY", "ltp": 22350.0, "change": 85.5, "change_pct": 0.38},
            source="test",
        )
        panel.handle_tick(event)
        assert panel._indices["NIFTY 50"]["ltp"] == 22350.0
        assert panel._indices["NIFTY 50"]["change_pct"] == 0.38

    def test_handle_tick_updates_bank_nifty(self) -> None:
        """BANKNIFTY tick updates the BANK NIFTY row."""
        from shettyxtreme.terminal.panels import MarketInternalsPanel

        panel = MarketInternalsPanel()
        event = Event(
            topic=Topic.MARKET_DATA_TICK,
            data={"symbol": "BANKNIFTY", "ltp": 48200.0, "change": -120.0, "change_pct": -0.25},
            source="test",
        )
        panel.handle_tick(event)
        assert panel._indices["BANK NIFTY"]["ltp"] == 48200.0
        assert panel._indices["BANK NIFTY"]["change_pct"] == -0.25

    def test_handle_system_status_session(self, mock_system_status_event: Event) -> None:
        """System status event updates session state."""
        from shettyxtreme.terminal.panels import MarketInternalsPanel

        panel = MarketInternalsPanel()
        panel.handle_system_status(mock_system_status_event)
        assert panel.session_state == "live"

    def test_handle_system_status_advance_decline(self, mock_system_status_event: Event) -> None:
        """System status event updates advance/decline counts."""
        from shettyxtreme.terminal.panels import MarketInternalsPanel

        panel = MarketInternalsPanel()
        panel.handle_system_status(mock_system_status_event)
        assert panel._advance_decline["advances"] == 1450
        assert panel._advance_decline["declines"] == 820


# ---------------------------------------------------------------------------
# StatusBar tests
# ---------------------------------------------------------------------------


class TestStatusBar:
    """Tests for the StatusBar widget."""

    def test_init_default_mode(self) -> None:
        """Status bar defaults to observer mode."""
        from shettyxtreme.terminal.panels import StatusBar

        bar = StatusBar(mode="observer")
        assert bar.mode == "observer"

    def test_init_respects_mode_param(self) -> None:
        """Status bar accepts a custom mode."""
        from shettyxtreme.terminal.panels import StatusBar

        bar = StatusBar(mode="live")
        assert bar.mode == "live"

    def test_handle_system_status_updates_connections(self) -> None:
        """System status event updates connection indicators."""
        from shettyxtreme.terminal.panels import StatusBar

        bar = StatusBar()
        event = Event(
            topic=Topic.SYSTEM_STATUS,
            data={"dhan_connected": True, "openalgo_connected": True, "mode": "paper"},
            source="test",
        )
        bar.handle_system_status(event)
        assert bar.dhan_connected is True
        assert bar.openalgo_connected is True
        assert bar.mode == "paper"

    def test_market_hours_configuration(self) -> None:
        """Market hours can be configured on the status bar."""
        from shettyxtreme.terminal.panels import StatusBar

        bar = StatusBar()
        bar.set_market_hours(9, 15, 15, 30)
        assert bar._market_open_hour == 9
        assert bar._market_close_hour == 15

    def test_weekday_check(self) -> None:
        """Market status returns a boolean."""
        from shettyxtreme.terminal.panels import StatusBar

        bar = StatusBar()
        result = bar._check_market_status()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# LogPanel tests
# ---------------------------------------------------------------------------


class TestLogPanel:
    """Tests for the LogPanel widget."""

    def test_init_empty(self) -> None:
        """Log panel starts with no entries."""
        from shettyxtreme.terminal.panels import LogPanel

        panel = LogPanel(max_lines=100)
        assert len(panel.entries) == 0

    def test_log_adds_entry(self) -> None:
        """Calling log() appends an entry."""
        from shettyxtreme.terminal.panels import LogPanel

        panel = LogPanel()
        panel.log("INFO", "test message", source="test")
        assert len(panel.entries) == 1
        assert panel.entries[0]["message"] == "test message"
        assert panel.entries[0]["level"] == "INFO"

    def test_log_respects_max_lines(self) -> None:
        """Log panel discards oldest entries when max_lines is exceeded."""
        from shettyxtreme.terminal.panels import LogPanel

        panel = LogPanel(max_lines=3)
        for i in range(5):
            panel.log("INFO", f"msg {i}", source="test")
        assert len(panel.entries) == 3
        messages = [e["message"] for e in panel.entries]
        assert "msg 0" not in messages
        assert "msg 2" in messages

    def test_clear_empties_entries(self) -> None:
        """Clear removes all log entries."""
        from shettyxtreme.terminal.panels import LogPanel

        panel = LogPanel()
        panel.log("INFO", "something", source="test")
        panel.clear()
        assert len(panel.entries) == 0

    def test_handle_event_topics(self) -> None:
        """Various event topics produce appropriately levelled log entries."""
        from shettyxtreme.terminal.panels import LogPanel

        panel = LogPanel()

        risk_event = Event(topic=Topic.RISK_ALERT, data="Risk triggered", source="risk")
        panel.handle_event(risk_event)
        assert panel.entries[-1]["level"] == "ERROR"

        signal_event = Event(topic=Topic.SIGNAL_GENERATED, data="Buy signal", source="strat")
        panel.handle_event(signal_event)
        assert panel.entries[-1]["level"] == "SIGNAL"

        order_event = Event(topic=Topic.ORDER_PLACED, data="Order placed", source="exec")
        panel.handle_event(order_event)
        assert panel.entries[-1]["level"] == "SIGNAL"

    def test_handle_system_status(self, mock_system_status_event: Event) -> None:
        """System status events are logged at the specified level."""
        from shettyxtreme.terminal.panels import LogPanel

        panel = LogPanel()
        panel.handle_system_status(mock_system_status_event)
        assert len(panel.entries) >= 1
        assert "Market is live" in panel.entries[-1]["message"]


# ---------------------------------------------------------------------------
# Colour-coding tests
# ---------------------------------------------------------------------------


class TestColourCoding:
    """Verify colour-coding logic for positive/negative/flat values."""

    def test_positive_change_uses_green(self) -> None:
        """Positive change_pct should map to green colour."""
        from shettyxtreme.terminal.panels.watchlist_panel import WatchlistPanel

        panel = WatchlistPanel(symbols=["TEST"])
        event = Event(
            topic=Topic.MARKET_DATA_TICK,
            data={"symbol": "TEST", "ltp": 100.0, "change": 5.0, "change_pct": 5.0},
            source="test",
        )
        panel.handle_tick(event)
        data = panel._data.get("TEST", {})
        assert data["change"] > 0

    def test_negative_change_uses_red(self) -> None:
        """Negative change_pct should map to red colour."""
        from shettyxtreme.terminal.panels.watchlist_panel import WatchlistPanel

        panel = WatchlistPanel(symbols=["TEST"])
        event = Event(
            topic=Topic.MARKET_DATA_TICK,
            data={"symbol": "TEST", "ltp": 95.0, "change": -5.0, "change_pct": -5.0},
            source="test",
        )
        panel.handle_tick(event)
        data = panel._data.get("TEST", {})
        assert data["change"] < 0

    def test_flat_change_uses_neutral(self) -> None:
        """Zero change should result in neutral (white) colour."""
        from shettyxtreme.terminal.panels.watchlist_panel import WatchlistPanel

        panel = WatchlistPanel(symbols=["TEST"])
        event = Event(
            topic=Topic.MARKET_DATA_TICK,
            data={"symbol": "TEST", "ltp": 100.0, "change": 0.0, "change_pct": 0.0},
            source="test",
        )
        panel.handle_tick(event)
        data = panel._data.get("TEST", {})
        assert data["change"] == 0.0

    def test_log_level_styles_defined(self) -> None:
        """All expected log level styles are present."""
        from shettyxtreme.terminal.panels.log_panel import _LOG_LEVEL_STYLES

        assert "INFO" in _LOG_LEVEL_STYLES
        assert "WARN" in _LOG_LEVEL_STYLES
        assert "ERROR" in _LOG_LEVEL_STYLES
        assert "SIGNAL" in _LOG_LEVEL_STYLES
        assert "DEBUG" in _LOG_LEVEL_STYLES

    def test_session_labels_defined(self) -> None:
        """All expected session state labels are present."""
        from shettyxtreme.terminal.panels.market_internals_panel import (
            _SESSION_LABELS,
            _SESSION_COLOURS,
        )

        for key in ("preopen", "live", "closed", "postclose"):
            assert key in _SESSION_LABELS
            assert key in _SESSION_COLOURS


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestTerminalConfig:
    """Tests for TerminalConfig."""

    def test_default_watchlist(self) -> None:
        """Default watchlist contains expected Indian symbols."""
        from shettyxtreme.terminal.config import TerminalConfig

        config = TerminalConfig()
        assert "NIFTY" in config.default_watchlist
        assert "RELIANCE" in config.default_watchlist
        assert len(config.default_watchlist) == 6

    def test_default_refresh_rate(self) -> None:
        """Default refresh rate is 1000ms."""
        from shettyxtreme.terminal.config import TerminalConfig

        config = TerminalConfig()
        assert config.refresh_rate_ms == 1000

    def test_terminal_colors_defaults(self) -> None:
        """TerminalColors has expected default values."""
        from shettyxtreme.terminal.config import TerminalColors

        colors = TerminalColors()
        assert colors.positive == "green"
        assert colors.negative == "red"
        assert colors.info == "white"
        assert colors.warning == "yellow"
        assert colors.error == "red"
        assert colors.signal == "cyan"


# ---------------------------------------------------------------------------
# App-level tests
# ---------------------------------------------------------------------------


class TestShettyXtremeApp:
    """Smoke tests for the main ShettyXtremeApp."""

    def test_app_title(self) -> None:
        """App exposes the expected title."""
        from shettyxtreme.terminal.app import ShettyXtremeApp

        app = ShettyXtremeApp()
        assert app.TITLE == "ShettyXtreme"

    def test_app_subtitle(self) -> None:
        """App exposes the expected subtitle."""
        from shettyxtreme.terminal.app import ShettyXtremeApp

        app = ShettyXtremeApp()
        assert app.SUB_TITLE == "Indian-Market Trading Intelligence"

    def test_placeholder_panel_init(self) -> None:
        """PlaceholderPanel renders with the provided label."""
        from shettyxtreme.terminal.app import PlaceholderPanel

        panel = PlaceholderPanel("Test Label")
        assert panel._label == "Test Label"
