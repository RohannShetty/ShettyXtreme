"""Average True Range — Wilder's smoothing, O(1) per tick."""
from __future__ import annotations

from shettyxtreme.core.data_models.market_data import Tick


class ATR:
    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._value: float | None = None
        self._prev_close: float | None = None
        self._tr_sum = 0.0
        self._count = 0

    def update(self, tick: Tick) -> float | None:
        high = tick.high if tick.high is not None else tick.ltp
        low = tick.low if tick.low is not None else tick.ltp
        close = tick.ltp

        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close),
            )

        self._prev_close = close
        self._count += 1

        if self._count < self.period:
            self._tr_sum += tr
            return None

        if self._count == self.period:
            self._tr_sum += tr
            self._value = self._tr_sum / self.period
            return self._value

        # Wilder's smoothing: atr = (prev_atr * (N-1) + tr) / N
        self._value = (self._value * (self.period - 1) + tr) / self.period  # type: ignore[operator]
        return self._value

    @property
    def value(self) -> float | None:
        return self._value

    def reset(self) -> None:
        self._value = None
        self._prev_close = None
        self._tr_sum = 0.0
        self._count = 0
