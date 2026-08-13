"""Bollinger Bands — SMA ± k*stddev, O(1) per tick via Welford's online algorithm.

Computes upper band, lower band, middle band (SMA), and %B (position within bands).
"""
from __future__ import annotations

import math

from shettyxtreme.core.data_models.market_data import Tick


class BollingerBands:
    """Bollinger Bands: SMA(period) ± k * stddev(period).

    Uses Welford's online algorithm for streaming variance — O(1) memory
    and O(1) per tick. Requires a circular buffer of size `period`.

    Args:
        period: Lookback period (default 20).
        num_std: Number of standard deviations for bands (default 2.0).
    """

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        self.period = period
        self.num_std = num_std
        self._buf: list[float] = []
        self._idx: int = 0
        self._n: int = 0
        self._mean: float = 0.0
        self._m2: float = 0.0  # sum of squares of differences from mean
        self._upper: float | None = None
        self._lower: float | None = None
        self._middle: float | None = None
        self._pct_b: float | None = None

    def update(self, tick: Tick) -> float | None:
        """Update with a new tick; returns middle band (SMA) or None during warm-up."""
        price = tick.ltp

        if len(self._buf) < self.period:
            # Still filling the buffer
            self._buf.append(price)
            self._n += 1
            delta = price - self._mean
            self._mean += delta / self._n
            delta2 = price - self._mean
            self._m2 += delta * delta2
            if len(self._buf) < self.period:
                return None
            # Buffer just filled — compute first bands
            self._compute_bands(price)
            return self._middle

        # Buffer full — rolling update (Welford's remove + add)
        old_price = self._buf[self._idx]
        self._buf[self._idx] = price
        self._idx = (self._idx + 1) % self.period

        # Update running stats: remove old, add new
        old_mean = self._mean
        self._mean += (price - old_price) / self.period
        self._m2 += (price - old_price) * (price - self._mean + old_price - old_mean)

        self._compute_bands(price)
        return self._middle

    def _compute_bands(self, current_price: float) -> None:
        """Compute bands from current running stats."""
        self._middle = self._mean
        if self._n >= 2:
            variance = self._m2 / (self._n - 1)
            stddev = math.sqrt(max(0.0, variance))
        else:
            stddev = 0.0
        self._upper = self._middle + self.num_std * stddev
        self._lower = self._middle - self.num_std * stddev
        band_width = self._upper - self._lower
        if band_width > 0:
            self._pct_b = (current_price - self._lower) / band_width
        else:
            self._pct_b = 0.5

    @property
    def value(self) -> float | None:
        """Middle band (SMA)."""
        return self._middle

    @property
    def upper(self) -> float | None:
        """Upper band."""
        return self._upper

    @property
    def lower(self) -> float | None:
        """Lower band."""
        return self._lower

    @property
    def pct_b(self) -> float | None:
        """%B: position within bands (0 = lower, 1 = upper)."""
        return self._pct_b

    @property
    def bandwidth(self) -> float | None:
        """Bandwidth: (upper - lower) / middle."""
        if self._middle and self._upper is not None and self._lower is not None:
            return (self._upper - self._lower) / self._middle if self._middle != 0 else 0.0
        return None

    def reset(self) -> None:
        self._buf.clear()
        self._idx = 0
        self._n = 0
        self._mean = 0.0
        self._m2 = 0.0
        self._upper = None
        self._lower = None
        self._middle = None
        self._pct_b = None
