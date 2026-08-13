"""MACD (Moving Average Convergence Divergence) — EMA-based, O(1) per tick.

Computes MACD line (fast EMA - slow EMA), signal line (EMA of MACD line),
and histogram (MACD - signal).
"""
from __future__ import annotations

from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.intelligence.features.indicators.ema import EMA


class MACD:
    """MACD indicator: fast EMA - slow EMA, plus signal line and histogram.

    Args:
        fast_period: Fast EMA period (default 12).
        slow_period: Slow EMA period (default 26).
        signal_period: Signal line EMA period (default 9).
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        self._fast = EMA(fast_period)
        self._slow = EMA(slow_period)
        self._signal_ema = EMA(signal_period)
        self._macd_value: float | None = None
        self._signal_value: float | None = None
        self._histogram: float | None = None

    def update(self, tick: Tick) -> float | None:
        """Update with a new tick; returns MACD line value (or None during warm-up)."""
        fast_val = self._fast.update(tick)
        slow_val = self._slow.update(tick)
        if fast_val is None or slow_val is None:
            return None
        self._macd_value = fast_val - slow_val
        # Feed MACD line into the signal EMA
        # Build a synthetic tick with ltp = macd_value for the signal EMA
        signal_tick = Tick(
            symbol=tick.symbol,
            exchange=tick.exchange,
            ltp=self._macd_value,
            volume=0,
            timestamp=tick.timestamp,
        )
        sig_val = self._signal_ema.update(signal_tick)
        if sig_val is not None:
            self._signal_value = sig_val
            self._histogram = self._macd_value - self._signal_value
        return self._macd_value

    @property
    def value(self) -> float | None:
        """MACD line value."""
        return self._macd_value

    @property
    def signal(self) -> float | None:
        """Signal line value."""
        return self._signal_value

    @property
    def histogram(self) -> float | None:
        """MACD histogram (MACD - signal)."""
        return self._histogram

    def reset(self) -> None:
        self._fast.reset()
        self._slow.reset()
        self._signal_ema.reset()
        self._macd_value = None
        self._signal_value = None
        self._histogram = None
