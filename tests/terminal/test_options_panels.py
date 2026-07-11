"""Tests for Options chain and strategy panels.

Verifies:
- OptionsChainPanel instantiation with/without OITracker
- OptionsStrategyPanel instantiation and parameter setters
- State management (private attrs checked directly)
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from shettyxtreme.options.oi_tracker import OITracker


# Patch Static.update to prevent recursion in Textual widgets outside an app
@patch("textual.widgets.Static.update", return_value=None)
class TestOptionsChainPanel:
    """Suite for OptionsChainPanel."""

    def test_init_no_tracker(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        panel = OptionsChainPanel()
        assert panel._underlying == ""
        assert panel._expiry == ""
        assert panel._expiries == []
        assert panel._contracts == []
        assert panel._spot == 0.0
        assert panel._oi_tracker is None

    def test_init_with_tracker(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        tracker = OITracker(event_bus=None)
        panel = OptionsChainPanel(oi_tracker=tracker)
        assert panel._oi_tracker is tracker

    def test_set_underlying(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        panel = OptionsChainPanel()
        panel.set_underlying("NIFTY")
        assert panel._underlying == "NIFTY"

    def test_set_expiry(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        panel = OptionsChainPanel()
        panel.set_expiry("2024-01-25")
        assert panel._expiry == "2024-01-25"

    def test_set_expiries(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        panel = OptionsChainPanel()
        expiries = ["2024-01-25", "2024-02-01"]
        panel.set_expiries(expiries)
        assert panel._expiries == expiries

    def test_update_chain(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        panel = OptionsChainPanel()
        contracts = [{"strike": 50000, "option_type": "CE", "ltp": 150.0, "iv": 0.15, "delta": 0.55, "gamma": 0.002, "theta": -0.5, "vega": 3.0, "oi": 1000}]
        panel.update_chain(contracts, spot=50200.0, expiry="2024-01-25")
        assert panel._contracts == contracts
        assert panel._spot == 50200.0
        assert panel._expiry == "2024-01-25"

    def test_handle_tick(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        from shettyxtreme.core.event_bus import Event, Topic
        from datetime import datetime, timezone
        panel = OptionsChainPanel()
        panel.set_underlying("NIFTY")
        event = Event(topic=Topic.MARKET_DATA_TICK, data={"symbol": "NIFTY", "ltp": 50500.0}, source="dhan", timestamp=datetime.now(timezone.utc))
        panel.handle_tick(event)
        assert panel._spot == 50500.0

    def test_handle_tick_wrong_symbol(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        from shettyxtreme.core.event_bus import Event, Topic
        from datetime import datetime, timezone
        panel = OptionsChainPanel()
        panel._spot = 50000.0
        panel.set_underlying("NIFTY")
        event = Event(topic=Topic.MARKET_DATA_TICK, data={"symbol": "BANKNIFTY", "ltp": 60000.0}, source="dhan", timestamp=datetime.now(timezone.utc))
        panel.handle_tick(event)
        assert panel._spot == 50000.0

    def test_default_css(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsChainPanel
        assert OptionsChainPanel.DEFAULT_CSS is not None
        assert "OptionsChainPanel" in OptionsChainPanel.DEFAULT_CSS


@patch("textual.widgets.Static.update", return_value=None)
class TestOptionsStrategyPanel:
    """Suite for OptionsStrategyPanel."""

    def test_init_defaults(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        panel = OptionsStrategyPanel()
        assert panel._current_strategy == "LONG_CALL"
        assert panel._spot == 0.0
        assert panel._strike == 0.0
        assert panel._strike2 == 0.0
        assert panel._premium == 0.0
        assert panel._premium2 == 0.0
        assert panel._iv == 0.0
        assert panel._tte == 0.0
        assert panel._analysis is None

    def test_has_analyzer(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        from shettyxtreme.options.strategy_analyzer import StrategyAnalyzer
        panel = OptionsStrategyPanel()
        assert isinstance(panel._analyzer, StrategyAnalyzer)

    def test_setters(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        panel = OptionsStrategyPanel()
        panel.set_spot(50000.0)
        panel.set_strike(50500.0)
        panel.set_strike2(51000.0)
        panel.set_premium(150.0)
        panel.set_premium2(75.0)
        panel.set_iv(0.15)
        panel.set_tte(0.5)
        assert panel._spot == 50000.0
        assert panel._strike == 50500.0
        assert panel._strike2 == 51000.0
        assert panel._premium == 150.0
        assert panel._premium2 == 75.0
        assert panel._iv == 0.15
        assert panel._tte == 0.5

    def test_select_strategy(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        from shettyxtreme.core.event_bus import Event
        panel = OptionsStrategyPanel()
        panel.select_strategy("IRON_CONDOR")
        assert panel._current_strategy == "IRON_CONDOR"

    def test_current_strategy(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        panel = OptionsStrategyPanel()
        panel.select_strategy("BULL_CALL_SPREAD")
        assert panel.current_strategy() == "BULL_CALL_SPREAD"

    def test_analysis_recomputed(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        panel = OptionsStrategyPanel()
        panel.set_spot(50000.0)
        panel.set_strike(50500.0)
        panel.set_premium(200.0)
        panel.set_iv(0.15)
        panel.set_tte(0.5)
        assert panel._analysis is not None
        assert panel._analysis.name == "LONG_CALL"
        assert panel._analysis.max_loss == 200.0

    def test_analysis_none_when_spot_zero(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        panel = OptionsStrategyPanel()
        panel.set_spot(0.0)
        assert panel._analysis is None

    def test_default_css(self, mock_update: MagicMock) -> None:
        from shettyxtreme.terminal.panels import OptionsStrategyPanel
        assert OptionsStrategyPanel.DEFAULT_CSS is not None
        assert "OptionsStrategyPanel" in OptionsStrategyPanel.DEFAULT_CSS
