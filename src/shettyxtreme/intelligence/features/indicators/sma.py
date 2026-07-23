"""Simple Moving Average — O(1) streaming computation."""
from __future__ import annotations

from collections import deque

from shettyxtreme.core.data_models.market_data import Tick


class SMA:
    def __init__(self, period: int = 5) -> None:
        self.period = period
        self._buf: deque[float] = deque(maxlen=period)
        self._value: float | None = None

    def update(self, tick: Tick) -> float | None:
        self._buf.append(tick.ltp)
        if len(self._buf) < self.period:
            return None
        self._value = sum(self._buf) / self.period
        return self._value

    @property
    def value(self) -> float | None:
        return self._value

    def reset(self) -> None:
        self._buf.clear()
        self._value = None
