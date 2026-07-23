"""Exponential Moving Average — O(1) streaming computation."""
from __future__ import annotations

from shettyxtreme.core.data_models.market_data import Tick


class EMA:
    def __init__(self, period: int = 5) -> None:
        self.period = period
        self._k = 2.0 / (period + 1)
        self._value: float | None = None
        self._count = 0

    def update(self, tick: Tick) -> float | None:
        price = tick.ltp
        self._count += 1
        if self._count == 1:
            self._value = price
            return self._value
        self._value = price * self._k + self._value * (1 - self._k)  # type: ignore[operator]
        return self._value

    @property
    def value(self) -> float | None:
        return self._value

    def reset(self) -> None:
        self._value = None
        self._count = 0
