"""Average Directional Index — Wilder's smoothing, O(1) per tick."""
from __future__ import annotations

from shettyxtreme.core.data_models.market_data import Tick


class ADX:
    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._value: float | None = None
        self._di_plus: float | None = None
        self._di_minus: float | None = None
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self._prev_close: float | None = None
        self._smoothed_plus_dm = 0.0
        self._smoothed_minus_dm = 0.0
        self._smoothed_tr = 0.0
        self._smoothed_dx = 0.0
        self._count = 0
        self._adx_count = 0

    def update(self, tick: Tick) -> float | None:
        high = tick.high if tick.high is not None else tick.ltp
        low = tick.low if tick.low is not None else tick.ltp
        close = tick.ltp

        self._count += 1

        if self._prev_high is None:
            self._prev_high = high
            self._prev_low = low
            self._prev_close = close
            return None

        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )

        plus_dm = max(high - self._prev_high, 0.0)
        minus_dm = max(self._prev_low - low, 0.0)

        # When both are positive, keep only the larger; zero the other
        if plus_dm > minus_dm:
            minus_dm = 0.0
        elif minus_dm > plus_dm:
            plus_dm = 0.0
        else:
            plus_dm = 0.0
            minus_dm = 0.0

        self._prev_high = high
        self._prev_low = low
        self._prev_close = close

        # Need period changes for initial seed
        if self._count <= self.period:
            self._smoothed_plus_dm += plus_dm
            self._smoothed_minus_dm += minus_dm
            self._smoothed_tr += tr
            if self._count < self.period:
                return None
            # Seed with simple average
            self._smoothed_plus_dm /= self.period
            self._smoothed_minus_dm /= self.period
            self._smoothed_tr /= self.period
        else:
            self._smoothed_plus_dm = (
                self._smoothed_plus_dm * (self.period - 1) + plus_dm
            ) / self.period
            self._smoothed_minus_dm = (
                self._smoothed_minus_dm * (self.period - 1) + minus_dm
            ) / self.period
            self._smoothed_tr = (
                self._smoothed_tr * (self.period - 1) + tr
            ) / self.period

        if self._smoothed_tr == 0:
            self._di_plus = 0.0
            self._di_minus = 0.0
        else:
            self._di_plus = (self._smoothed_plus_dm / self._smoothed_tr) * 100.0
            self._di_minus = (self._smoothed_minus_dm / self._smoothed_tr) * 100.0

        di_sum = self._di_plus + self._di_minus
        dx = (abs(self._di_plus - self._di_minus) / di_sum * 100.0) if di_sum > 0 else 0.0

        # ADX smoothing: Wilder's method over DX values
        self._adx_count += 1
        if self._adx_count == 1:
            self._smoothed_dx = dx
        elif self._adx_count <= self.period:
            self._smoothed_dx = (self._smoothed_dx * (self._adx_count - 1) + dx) / self._adx_count
        else:
            self._smoothed_dx = (self._smoothed_dx * (self.period - 1) + dx) / self.period

        self._value = self._smoothed_dx
        return self._value

    @property
    def value(self) -> float | None:
        return self._value

    @property
    def di_plus(self) -> float | None:
        return self._di_plus

    @property
    def di_minus(self) -> float | None:
        return self._di_minus

    def reset(self) -> None:
        self._value = None
        self._di_plus = None
        self._di_minus = None
        self._prev_high = None
        self._prev_low = None
        self._prev_close = None
        self._smoothed_plus_dm = 0.0
        self._smoothed_minus_dm = 0.0
        self._smoothed_tr = 0.0
        self._smoothed_dx = 0.0
        self._count = 0
        self._adx_count = 0
