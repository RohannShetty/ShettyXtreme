"""Tests for OITracker.

Verifies:
- OI change detection
- Alert significance levels
- Put/Call ratio computation
- F-KNOW-004: MARKET_DATA_BAR event shape handling (Bar vs chain dict)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.options.oi_tracker import OITracker


class TestOITracker:
    """Suite for OITracker."""

    @pytest.fixture
    def tracker(self) -> OITracker:
        return OITracker(event_bus=None)

    def test_init_state(self, tracker: OITracker) -> None:
        assert tracker.tracked_symbols == []
        assert tracker.get_alerts() == []

    def test_update_stores_oi(self, tracker: OITracker) -> None:
        contracts = [{"strike": 50000, "option_type": "CE", "oi": 1000}]
        tracker.update_from_chain("NIFTY", "2024-01-25", contracts)
        assert tracker.get_oi("NIFTY", "2024-01-25", 50000, "CE") == 1000

    def test_oi_change_detected(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 1000}])
        alerts = tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 2000}])
        assert len(alerts) == 1
        assert alerts[0].oi_change_percent == 100.0
        assert alerts[0].current_oi == 2000
        assert alerts[0].previous_oi == 1000

    def test_oi_decrease(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 2000}])
        alerts = tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 1000}])
        assert alerts[0].oi_change_percent == -50.0

    def test_no_change_no_alert(self, tracker: OITracker) -> None:
        c = [{"strike": 50000, "option_type": "CE", "oi": 1000}]
        tracker.update_from_chain("NIFTY", "2024-01-25", c)
        assert len(tracker.update_from_chain("NIFTY", "2024-01-25", c)) == 0

    def test_significance_high(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        alerts = tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 300}])
        assert alerts[0].significance == "HIGH"

    def test_significance_medium(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        alerts = tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 160}])
        assert alerts[0].significance == "MEDIUM"

    def test_significance_low(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        alerts = tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 130}])
        assert alerts[0].significance == "LOW"

    def test_below_threshold(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        assert len(tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 110}])) == 0

    def test_get_oi_change(self, tracker: OITracker) -> None:
        assert tracker.get_oi_change("NIFTY", "2024-01-25", 50000, "CE") == 0.0
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 200}])
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 300}])
        assert tracker.get_oi_change("NIFTY", "2024-01-25", 50000, "CE") == 50.0

    def test_pcr(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [
            {"strike": 50000, "option_type": "CE", "oi": 1000},
            {"strike": 50000, "option_type": "PE", "oi": 800},
            {"strike": 50100, "option_type": "CE", "oi": 500},
            {"strike": 50100, "option_type": "PE", "oi": 700},
        ])
        assert tracker.get_pcr("NIFTY") == 1.0

    def test_pcr_zero_call_oi(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "PE", "oi": 800}])
        assert tracker.get_pcr("NIFTY") == 0.0

    def test_pcr_by_expiry(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 1000}, {"strike": 50000, "option_type": "PE", "oi": 500}])
        tracker.update_from_chain("NIFTY", "2024-02-01", [{"strike": 50000, "option_type": "CE", "oi": 2000}, {"strike": 50000, "option_type": "PE", "oi": 2000}])
        assert tracker.get_pcr("NIFTY", "2024-01-25") == 0.5
        assert tracker.get_pcr("NIFTY", "2024-02-01") == 1.0

    def test_get_alerts_filtered(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 130}])
        assert len(tracker.get_alerts("LOW")) == 1
        assert len(tracker.get_alerts("MEDIUM")) == 0

    def test_clear_alerts(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 300}])
        assert len(tracker.get_alerts()) > 0
        tracker.clear_alerts()
        assert tracker.get_alerts() == []

    def test_clear_symbol(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        tracker.update_from_chain("BANKNIFTY", "2024-01-25", [{"strike": 50000, "option_type": "PE", "oi": 200}])
        tracker.clear_oi_data("NIFTY")
        assert "NIFTY" not in tracker.tracked_symbols
        assert "BANKNIFTY" in tracker.tracked_symbols

    def test_clear_all(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": 100}])
        tracker.clear_oi_data()
        assert tracker.tracked_symbols == []

    def test_non_cepe_skipped(self, tracker: OITracker) -> None:
        alerts = tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "XX", "oi": 100}])
        assert len(alerts) == 0

    def test_empty_contracts(self, tracker: OITracker) -> None:
        assert tracker.update_from_chain("NIFTY", "2024-01-25", []) == []

    def test_oi_as_string(self, tracker: OITracker) -> None:
        tracker.update_from_chain("NIFTY", "2024-01-25", [{"strike": 50000, "option_type": "CE", "oi": "1500"}])
        assert tracker.get_oi("NIFTY", "2024-01-25", 50000, "CE") == 1500


# ---------------------------------------------------------------------------
# F-KNOW-004: MARKET_DATA_BAR event shape handling
# ---------------------------------------------------------------------------
class TestMarketDataEvents:
    """The bus's MARKET_DATA_BAR topic carries ``Bar`` objects (not the
    ``{symbol, expiry, contracts}`` dict the old handler assumed)."""

    @staticmethod
    def _make_bar(oi: int | None) -> Bar:
        return Bar(
            symbol="NIFTY",
            exchange="NSE",
            timeframe="5min",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1200,
            timestamp=datetime.now(timezone.utc),
            oi=oi,
        )

    @staticmethod
    async def _run_event_bus(payload: object) -> None:
        """Publish a MARKET_DATA_BAR payload through a live bus and drain it."""
        bus = EventBus()
        tracker = OITracker(event_bus=bus)
        bus_task = asyncio.create_task(bus.start())
        try:
            await bus.publish_nowait(
                Event(Topic.MARKET_DATA_BAR, payload, source="test"),
            )
            await asyncio.sleep(0.05)
        finally:
            await bus.stop()
            try:
                await asyncio.wait_for(bus_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        return tracker

    @pytest.mark.asyncio
    async def test_bar_event_records_symbol_oi(self) -> None:
        """A Bar event's aggregate OI is recorded as symbol-level OI."""
        tracker = await self._run_event_bus(self._make_bar(oi=12345))
        assert tracker.get_symbol_oi("NIFTY") == [12345]
        # A bar carries no per-contract chain — no expiry/strike tracked.
        assert tracker.tracked_symbols == []

    @pytest.mark.asyncio
    async def test_bar_without_oi_skipped(self) -> None:
        """Bars without an OI value are ignored cleanly (no crash)."""
        tracker = await self._run_event_bus(self._make_bar(oi=None))
        assert tracker.get_symbol_oi("NIFTY") == []

    @pytest.mark.asyncio
    async def test_chain_dict_event_updates_chain(self) -> None:
        """An option-chain dict payload still feeds update_from_chain."""
        payload = {
            "symbol": "NIFTY",
            "expiry": "2026-08-27",
            "contracts": [{"strike": 50000, "option_type": "CE", "oi": 1000}],
        }
        tracker = await self._run_event_bus(payload)
        assert tracker.get_oi("NIFTY", "2026-08-27", 50000, "CE") == 1000

    @pytest.mark.asyncio
    async def test_bar_shaped_dict_records_oi(self) -> None:
        """A dict-shaped bar payload {symbol, oi} records symbol OI too."""
        tracker = await self._run_event_bus({"symbol": "NIFTY", "oi": "77"})
        assert tracker.get_symbol_oi("NIFTY") == [77]

    @pytest.mark.asyncio
    async def test_unrelated_payload_ignored(self) -> None:
        """Arbitrary payloads must not crash or corrupt state."""
        tracker = await self._run_event_bus({"symbol": "NIFTY", "ltp": 100.0, "volume": 5})
        assert tracker.get_symbol_oi("NIFTY") == []
        assert tracker.tracked_symbols == []
