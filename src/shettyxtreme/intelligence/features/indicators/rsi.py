"""Relative Strength Index — Wilder's smoothing, O(1) per tick."""
from __future__ import annotations

from shettyxtreme.core.data_models.market_data import Tick


class RSI:
    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._value: float | None = None
        self._prev_price: float | None = None
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0
        self._count = 0

    def update(self, tick: Tick) -> float | None:
        price = tick.ltp
        if self._prev_price is None:
            self._prev_price = price
            return None

        change = price - self._prev_price
        self._prev_price = price
        self._count += 1

        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        # Need period changes before we can compute (period-1 after first tick)
        if self._count < self.period - 1:
            self._avg_gain += gain
            self._avg_loss += loss
            return None

        # Seed: simple average of first (period-1) gains/losses
        if self._count == self.period - 1:
            self._avg_gain = (self._avg_gain + gain) / (self.period - 1)
            self._avg_loss = (self._avg_loss + loss) / (self.period - 1)
        else:
            # Wilder's smoothing
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period

        if self._avg_loss == 0:
            self._value = 100.0
        else:
            rs = self._avg_gain / self._avg_loss
            self._value = 100.0 - (100.0 / (1.0 + rs))
        return self._value

    @property
    def value(self) -> float | None:
        return self._value

    def reset(self) -> None:
        self._value = None
        self._prev_price = None
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._count = 0
