"""Tests for SimpleSignalGenerator and Signal dataclass.

Verifies signal creation, strength calculation, cooldown enforcement,
and minimum strength threshold filtering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from shettyxtreme.core.event_bus import EventBus, Topic
from shettyxtreme.intelligence.signals import Signal


class TestSignalDataclass:
    """Suite for the Signal dataclass."""

    def test_create_signal(self) -> None:
        """Signal can be created with required fields."""
        signal = Signal(
            symbol="RELIANCE",
            direction="bullish",
            strength=7.5,
            source="breakout",
            reasoning="Price broke above resistance",
        )
        assert signal.symbol == "RELIANCE"
        assert signal.direction == "bullish"
        assert signal.strength == 7.5
        assert signal.source == "breakout"

    def test_signal_with_metadata(self) -> None:
        """Signal can carry optional metadata."""
        signal = Signal(
            symbol="TCS",
            direction="bearish",
            strength=3.0,
            source="gap",
            reasoning="Gap down 2%",
            metadata={"gap_percent": 2.0},
        )
        assert signal.metadata is not None
        assert signal.metadata["gap_percent"] == 2.0

    def test_invalid_direction_raises(self) -> None:
        """Signal creation with invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="direction"):
            Signal(
                symbol="TEST",
                direction="invalid",
                strength=5.0,
                source="test",
                reasoning="bad",
            )

    def test_strength_out_of_range_raises(self) -> None:
        """Signal creation with strength outside 0-10 raises ValueError."""
        with pytest.raises(ValueError, match="strength"):
            Signal(
                symbol="TEST",
                direction="bullish",
                strength=15.0,
                source="test",
                reasoning="too strong",
            )

    def test_strength_zero_is_valid(self) -> None:
        """Strength of 0 is valid (minimum boundary)."""
        signal = Signal(
            symbol="TEST",
            direction="bullish",
            strength=0.0,
            source="test",
            reasoning="zero",
        )
        assert signal.strength == 0.0

    def test_strength_ten_is_valid(self) -> None:
        """Strength of 10 is valid (maximum boundary)."""
        signal = Signal(
            symbol="TEST",
            direction="bearish",
            strength=10.0,
            source="test",
            reasoning="max",
        )
        assert signal.strength == 10.0

    def test_timestamp_defaults_to_now(self) -> None:
        """Signal timestamp defaults to current time."""
        signal = Signal(
            symbol="TEST",
            direction="bullish",
            strength=5.0,
            source="test",
            reasoning="default time",
        )
        assert signal.timestamp is not None
        assert isinstance(signal.timestamp, datetime)


class TestSimpleSignalGenerator:
    """Suite for SimpleSignalGenerator."""

    @pytest.fixture
    def event_bus(self) -> EventBus:
        return EventBus()

    @pytest.fixture
    def generator(self, event_bus: EventBus) -> Any:
        from shettyxtreme.intelligence.signals import SimpleSignalGenerator
        gen = SimpleSignalGenerator(
            event_bus=event_bus,
            min_strength=4.0,
            cooldown_seconds=300,
        )
        return gen

    def test_init_defaults(self) -> None:
        """Generator initialises with sensible defaults."""
        from shettyxtreme.intelligence.signals import SimpleSignalGenerator
        bus: EventBus = EventBus()
        gen = SimpleSignalGenerator(event_bus=bus)
        assert gen.min_strength == 4.0
        assert gen.cooldown_seconds == 300

    @pytest.mark.asyncio
    async def test_process_breakout_signal(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """Breakout scanner result produces a Signal with correct fields."""
        result: dict[str, Any] = {
            "symbol": "RELIANCE",
            "direction": "bullish",
            "confidence": 80.0,
            "volume_confirmed": True,
            "breakout_price": 2850.0,
            "level": 2800.0,
        }
        scanner_results = {"breakout": [result]}
        signals = await generator.process(scanner_results)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.symbol == "RELIANCE"
        assert sig.direction == "bullish"
        assert sig.source == "breakout"
        assert sig.strength > 4.0
        assert "resistance" in sig.reasoning.lower()
        assert "volume confirmed" in sig.reasoning.lower()

    @pytest.mark.asyncio
    async def test_process_gap_signal(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """Gap scanner result produces a Signal with gap details."""
        result: dict[str, Any] = {
            "symbol": "TCS",
            "direction": "bearish",
            "gap_type": "breakaway",
            "gap_percent": 2.5,
            "confidence": 80.0,
            "volume_confirmed": False,
        }
        scanner_results = {"gap": [result]}
        signals = await generator.process(scanner_results)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.source == "gap"
        assert "breakaway gap" in sig.reasoning.lower()

    @pytest.mark.asyncio
    async def test_cooldown_suppresses_duplicate(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """Same symbol+direction within cooldown period is suppressed."""
        result: dict[str, Any] = {
            "symbol": "INFY",
            "direction": "bullish",
            "confidence": 80.0,
            "volume_confirmed": True,
        }
        scanner_results = {"breakout": [result]}

        signals1 = await generator.process(scanner_results)
        assert len(signals1) == 1

        signals2 = await generator.process(scanner_results)
        assert len(signals2) == 0

    @pytest.mark.asyncio
    async def test_below_min_strength_filtered(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """Results below min_strength threshold are filtered out."""
        result: dict[str, Any] = {
            "symbol": "HDFC",
            "direction": "bearish",
            "confidence": 20.0,
            "volume_confirmed": False,
        }
        scanner_results = {"breakout": [result]}
        signals = await generator.process(scanner_results)
        assert len(signals) == 0

    @pytest.mark.asyncio
    async def test_strength_calculation_with_weights(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """Strength calculation incorporates scanner weights and volume bonus."""
        result: dict[str, Any] = {
            "symbol": "SBIN",
            "direction": "bullish",
            "confidence": 100.0,
            "volume_confirmed": True,
        }
        scanner_results = {"breakout": [result]}
        signals = await generator.process(scanner_results)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.strength == 10.0

    @pytest.mark.asyncio
    async def test_different_direction_no_cooldown(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """Opposite direction for same symbol is NOT on cooldown."""
        result_bull: dict[str, Any] = {
            "symbol": "WIPRO",
            "direction": "bullish",
            "confidence": 80.0,
            "volume_confirmed": False,
        }
        result_bear: dict[str, Any] = {
            "symbol": "WIPRO",
            "direction": "bearish",
            "confidence": 80.0,
            "volume_confirmed": False,
        }

        sigs1 = await generator.process({"breakout": [result_bull]})
        assert len(sigs1) == 1

        sigs2 = await generator.process({"breakout": [result_bear]})
        assert len(sigs2) == 1

    @pytest.mark.asyncio
    async def test_recent_signals_property(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """recent_signals returns accumulated signals."""
        result: dict[str, Any] = {
            "symbol": "ITC",
            "direction": "bullish",
            "confidence": 70.0,
            "volume_confirmed": False,
        }
        await generator.process({"breakout": [result]})
        assert len(generator.recent_signals) == 1
        assert generator.recent_signals[0].symbol == "ITC"

    @pytest.mark.asyncio
    async def test_clear_history(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """clear_history resets cooldown tracking and signal history."""
        result: dict[str, Any] = {
            "symbol": "M&M",
            "direction": "bullish",
            "confidence": 70.0,
            "volume_confirmed": False,
        }
        await generator.process({"breakout": [result]})
        assert len(generator.recent_signals) == 1
        generator.clear_history()
        assert len(generator.recent_signals) == 0

        sigs = await generator.process({"breakout": [result]})
        assert len(sigs) == 1

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(
        self, generator: Any, event_bus: EventBus
    ) -> None:
        """Generator can start and stop without error."""
        await generator.start()
        assert generator._running is True
        await generator.stop()
        assert generator._running is False
