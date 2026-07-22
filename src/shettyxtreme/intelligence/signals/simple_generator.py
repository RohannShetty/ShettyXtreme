
"""SimpleSignalGenerator — combines scanner outputs into tradable signals."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Represents a generated trading signal."""

    symbol: str
    direction: str
    strength: float
    source: str
    reasoning: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate signal attributes after initialisation."""
        if self.direction not in ("bullish", "bearish"):
            raise ValueError(
                f"direction must be bullish or bearish, got {self.direction}"
            )
        if not 0.0 <= self.strength <= 10.0:
            raise ValueError(
                f"strength must be 0-10, got {self.strength}"
            )


_COOLDOWN_SECONDS = 300

_WEIGHTS: dict[str, float] = {
    "breakout": 2.0,
    "gap": 1.0,
    "volume": 0.5,
}


class SimpleSignalGenerator:
    """Combines scanner results into normalised tradable signals."""

    def __init__(
        self,
        event_bus: EventBus,
        min_strength: float = 4.0,
        cooldown_seconds: int = _COOLDOWN_SECONDS,
    ) -> None:
        """Initialise the signal generator."""
        self._event_bus = event_bus
        self.min_strength = min_strength
        self.cooldown_seconds = cooldown_seconds
        self._last_signal_time: dict[str, datetime] = {}
        self._signals_generated: list[Signal] = []
        self._running = False

    async def start(self) -> None:
        """Mark the generator as active."""
        if self._running:
            return
        self._running = True
        logger.info(
            "SimpleSignalGenerator started (min_strength=%.1f, cooldown=%ds)",
            self.min_strength,
            self.cooldown_seconds,
        )

    async def stop(self) -> None:
        """Stop the generator."""
        self._running = False
        logger.info("SimpleSignalGenerator stopped")

    async def process(
        self,
        scanner_results: dict[str, list[dict[str, Any]]],
    ) -> list[Signal]:
        """Process scanner outputs and emit signals for qualifying results."""
        signals: list[Signal] = []
        now = datetime.now(timezone.utc)

        for scanner_name, results in scanner_results.items():
            for result in results:
                signal = self._build_signal(scanner_name, result, now)
                if signal is None:
                    continue

                if self._is_on_cooldown(signal.symbol, signal.direction, now):
                    logger.debug(
                        "Signal on cooldown: %s %s", signal.symbol, signal.direction
                    )
                    continue

                if signal.strength < self.min_strength:
                    logger.debug(
                        "Signal below threshold: %s %.1f < %.1f",
                        signal.symbol,
                        signal.strength,
                        self.min_strength,
                    )
                    continue

                self._last_signal_time[
                    f"{signal.symbol}:{signal.direction}"
                ] = now

                await self._event_bus.publish(Event(
                    topic=Topic.SIGNAL_GENERATED,
                    data=signal,
                    source="signal_generator",
                    timestamp=now,
                ))

                signals.append(signal)
                self._signals_generated.append(signal)
                logger.info(
                    "Signal: %s %s strength=%.1f from %s",
                    signal.symbol,
                    signal.direction,
                    signal.strength,
                    signal.source,
                )

        return signals

    def _build_signal(
        self,
        scanner_name: str,
        result: dict[str, Any],
        now: datetime,
    ) -> Signal | None:
        """Build a Signal dataclass from a single scanner result."""
        symbol = result.get("symbol", "")
        direction = result.get("direction", "")
        if not symbol or not direction:
            return None

        weight = _WEIGHTS.get(scanner_name, 1.0)
        scanner_confidence = result.get("confidence", 50.0)
        volume_confirmed = result.get("volume_confirmed", False)

        base_strength = (scanner_confidence / 100.0) * 10.0
        weighted = base_strength * weight
        weighted = min(weighted, 10.0)

        if volume_confirmed:
            weighted += _WEIGHTS.get("volume", 0.5) * 0.5
            weighted = min(weighted, 10.0)

        strength = round(weighted, 1)

        reasoning_parts: list[str] = []
        gap_type = result.get("gap_type", "")
        breakout_price = result.get("breakout_price")
        level = result.get("level")

        if scanner_name == "breakout":
            dir_label = (
                "above resistance"
                if direction == "bullish"
                else "below support"
            )
            reasoning_parts.append(f"Price broke {dir_label}")
            if breakout_price and level:
                reasoning_parts.append(
                    f"at {breakout_price:.2f} (level: {level:.2f})"
                )
            if volume_confirmed:
                reasoning_parts.append("volume confirmed")
            reasoning_parts.append(f"confidence {scanner_confidence:.0f}%")
        elif scanner_name == "gap":
            gap_desc = {
                "breakaway": "Breakaway gap",
                "exhaustion": "Exhaustion gap",
                "common": "Common gap",
            }.get(gap_type, "Gap")
            gap_pct = result.get("gap_percent", 0)
            reasoning_parts.append(
                f"{gap_desc} {direction}: {gap_pct:.1f}%"
            )
        else:
            reasoning_parts.append(
                f"{scanner_name} detected {direction} setup"
            )

        return Signal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            source=scanner_name,
            reasoning=" | ".join(reasoning_parts),
            timestamp=now,
            metadata={
                "scanner_confidence": scanner_confidence,
                "volume_confirmed": volume_confirmed,
                "scanner_name": scanner_name,
                "raw_result": {
                    k: v for k, v in result.items() if k != "timestamp"
                },
            },
        )

    def _is_on_cooldown(
        self, symbol: str, direction: str, now: datetime
    ) -> bool:
        """Check if a symbol+direction pair is in cooldown."""
        key = f"{symbol}:{direction}"
        last = self._last_signal_time.get(key)
        if last is None:
            return False
        return (now - last).total_seconds() < self.cooldown_seconds

    @property
    def recent_signals(self) -> list[Signal]:
        """Return all signals generated so far in this session."""
        return list(self._signals_generated)

    def clear_history(self) -> None:
        """Clear cooldown tracking and signal history."""
        self._last_signal_time.clear()
        self._signals_generated.clear()
