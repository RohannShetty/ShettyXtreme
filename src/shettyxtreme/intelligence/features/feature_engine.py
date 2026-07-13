"""Streaming indicators computed O(1) per tick.

Each indicator is a class with:
  - update(tick: Tick) -> float | None  (returns new value or None)
  - value -> float | None               (current value, None if not enough data)

All updates are O(1) — no re-computation from scratch.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus import Event, EventBus, Topic

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_FRESHNESS_SECONDS = 10.0


# ---------------------------------------------------------------------------
# Bars — aggregate ticks into OHLC
# ---------------------------------------------------------------------------
class Bars:
    """Aggregate ticks into OHLC bars for a given timeframe.

    Each call to update() accumulates ticks; when the bar period elapses,
    the completed bar is returned and a new bar starts.
    """

    def __init__(self, timeframe_seconds: int = 60) -> None:
        self._timeframe = timeframe_seconds
        self._open: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._close: float | None = None
        self._volume: int = 0
        self._bar_start: float = 0.0
        self._last_value: dict[str, float | int | None] | None = None

    def update(self, tick: Tick) -> dict[str, float | int] | None:
        """Feed a tick, return completed bar dict or None."""
        ts = tick.timestamp.timestamp() if hasattr(tick.timestamp, 'timestamp') else time.time()
        if self._open is None:
            self._open = tick.ltp
            self._high = tick.ltp
            self._low = tick.ltp
            self._close = tick.ltp
            self._volume = tick.volume
            self._bar_start = ts
            return None

        if ts - self._bar_start >= self._timeframe:
            completed = {
                "open": self._open,
                "high": self._high,
                "low": self._low,
                "close": self._close,
                "volume": self._volume,
            }
            self._open = tick.ltp
            self._high = tick.ltp
            self._low = tick.ltp
            self._close = tick.ltp
            self._volume = tick.volume
            self._bar_start = ts
            self._last_value = completed
            return completed

        self._high = max(self._high, tick.ltp) if self._high is not None else tick.ltp
        self._low = min(self._low, tick.ltp) if self._low is not None else tick.ltp
        self._close = tick.ltp
        self._volume += tick.volume
        return None

    @property
    def value(self) -> dict[str, float | int] | None:
        return self._last_value


# ---------------------------------------------------------------------------
# SMA — Simple Moving Average (running sum / count)
# ---------------------------------------------------------------------------
class SMA:
    """Simple Moving Average via running sum."""

    def __init__(self, period: int = 5) -> None:
        if period < 1:
            raise ValueError("SMA period must be >= 1")
        self._period = period
        self._buffer: deque[float] = deque(maxlen=period)
        self._sum: float = 0.0
        self._value: float | None = None

    def update(self, tick: Tick) -> float | None:
        price = tick.ltp
        if len(self._buffer) == self._period:
            self._sum -= self._buffer[0]
        self._buffer.append(price)
        self._sum += price
        if len(self._buffer) == self._period:
            self._value = self._sum / self._period
        return self._value

    @property
    def value(self) -> float | None:
        return self._value


# ---------------------------------------------------------------------------
# EMA — Exponential Moving Average (alpha = 2/(N+1))
# ---------------------------------------------------------------------------
class EMA:
    """Exponential Moving Average — O(1) update."""

    def __init__(self, period: int = 5) -> None:
        if period < 1:
            raise ValueError("EMA period must be >= 1")
        self._period = period
        self._alpha = 2.0 / (period + 1)
        self._value: float | None = None

    def update(self, tick: Tick) -> float | None:
        price = tick.ltp
        if self._value is None:
            self._value = price
        else:
            self._value = self._alpha * price + (1.0 - self._alpha) * self._value
        return self._value

    @property
    def value(self) -> float | None:
        return self._value


# ---------------------------------------------------------------------------
# ATR — Average True Range (Wilder's smoothing)
# ---------------------------------------------------------------------------
class ATR:
    """Average True Range with Wilder's smoothing."""

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError("ATR period must be >= 1")
        self._period = period
        self._prev_close: float | None = None
        self._atr: float | None = None
        self._count: int = 0
        self._value: float | None = None

    def update(self, tick: Tick) -> float | None:
        if tick.high is None or tick.low is None:
            return self._value
        high, low, close = tick.high, tick.low, tick.ltp

        true_range = high - low
        if self._prev_close is not None:
            true_range = max(true_range, abs(high - self._prev_close), abs(low - self._prev_close))
        self._prev_close = close

        self._count += 1
        if self._count == 1:
            self._atr = true_range
        elif self._count <= self._period:
            self._atr = ((self._atr * (self._count - 1)) + true_range) / self._count
        else:
            self._atr = (self._atr * (self._period - 1) + true_range) / self._period

        if self._count >= self._period:
            self._value = self._atr
        return self._value

    @property
    def value(self) -> float | None:
        return self._value


# ---------------------------------------------------------------------------
# VWAP — Volume-Weighted Average Price
# ---------------------------------------------------------------------------
class VWAP:
    """Running VWAP: cumulative (price * volume) / cumulative volume."""

    def __init__(self) -> None:
        self._cum_pv: float = 0.0
        self._cum_vol: int = 0
        self._value: float | None = None

    def update(self, tick: Tick) -> float | None:
        self._cum_pv += tick.ltp * tick.volume
        self._cum_vol += tick.volume
        if self._cum_vol > 0:
            self._value = self._cum_pv / self._cum_vol
        return self._value

    @property
    def value(self) -> float | None:
        return self._value


# ---------------------------------------------------------------------------
# RSI — Relative Strength Index (Wilder's)
# ---------------------------------------------------------------------------
class RSI:
    """Relative Strength Index using Wilder's smoothing."""

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError("RSI period must be >= 1")
        self._period = period
        self._prev_price: float | None = None
        self._avg_gain: float | None = None
        self._avg_loss: float | None = None
        self._count: int = 0
        self._value: float | None = None

    def update(self, tick: Tick) -> float | None:
        price = tick.ltp
        if self._prev_price is None:
            self._prev_price = price
            return None

        diff = price - self._prev_price
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        self._prev_price = price

        self._count += 1
        if self._count == 1:
            self._avg_gain = gain
            self._avg_loss = loss
        elif self._count <= self._period:
            self._avg_gain = (self._avg_gain * (self._count - 1) + gain) / self._count
            self._avg_loss = (self._avg_loss * (self._count - 1) + loss) / self._count
        else:
            self._avg_gain = (self._avg_gain * (self._period - 1) + gain) / self._period
            self._avg_loss = (self._avg_loss * (self._period - 1) + loss) / self._period

        if self._count >= self._period - 1 and self._avg_loss is not None and (self._avg_loss + self._avg_gain) > 0:
            rs = self._avg_gain / self._avg_loss if self._avg_loss > 0 else 100.0
            self._value = 100.0 - (100.0 / (1.0 + rs))
        return self._value

    @property
    def value(self) -> float | None:
        return self._value


# ---------------------------------------------------------------------------
# ADX — Average Directional Index (DI+/DI-/ADX)
# ---------------------------------------------------------------------------
class ADX:
    """Average Directional Index with DI+ and DI- (Wilder's smoothing).

    Process:
      1. Compute True Range (TR) and directional movements (+DM, -DM)
      2. Wilder-smooth TR, +DM, -DM over `period` bars
      3. DI+ = 100 * smoothed(+DM) / smoothed(TR)
         DI- = 100 * smoothed(-DM) / smoothed(TR)
      4. DX = 100 * |DI+ - DI-| / (DI+ + DI-)
      5. ADX = Wilder-smoothed DX over `period` DX values
    """

    def __init__(self, period: int = 14) -> None:
        if period < 1:
            raise ValueError("ADX period must be >= 1")
        self._period = period
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self._prev_close: float | None = None
        self._tr: float | None = None
        self._dm_plus: float | None = None
        self._dm_minus: float | None = None
        self._bar_count: int = 0
        self._di_plus: float | None = None
        self._di_minus: float | None = None
        self._adx: float | None = None
        self._dx_buffer: list[float] = []
        self._dx_sum: float = 0.0
        self._dx_count: int = 0
        self._value: float | None = None

    def update(self, tick: Tick) -> float | None:
        if tick.high is None or tick.low is None:
            return self._value
        high, low, close = tick.high, tick.low, tick.ltp

        if self._prev_high is not None:
            # True Range
            tr = high - low
            tr = max(tr, abs(high - self._prev_close), abs(low - self._prev_close))

            # Directional Movement
            up_move = high - self._prev_high
            down_move = self._prev_low - low
            dm_plus = up_move if up_move > down_move and up_move > 0 else 0.0
            dm_minus = down_move if down_move > up_move and down_move > 0 else 0.0

            self._bar_count += 1

            if self._bar_count == 1:
                self._tr = tr
                self._dm_plus = dm_plus
                self._dm_minus = dm_minus
            elif self._bar_count < self._period:
                self._tr = (self._tr * (self._bar_count - 1) + tr) / self._bar_count
                self._dm_plus = (self._dm_plus * (self._bar_count - 1) + dm_plus) / self._bar_count
                self._dm_minus = (self._dm_minus * (self._bar_count - 1) + dm_minus) / self._bar_count
            else:
                # Wilder's smoothing
                self._tr = (self._tr * (self._period - 1) + tr) / self._period
                self._dm_plus = (self._dm_plus * (self._period - 1) + dm_plus) / self._period
                self._dm_minus = (self._dm_minus * (self._period - 1) + dm_minus) / self._period

            # DI+/DI- can be computed after we have enough data to have non-zero TR
            if self._tr is not None and self._tr > 0 and self._dm_plus is not None and self._dm_minus is not None:
                di_plus_val = 100.0 * self._dm_plus / self._tr
                di_minus_val = 100.0 * self._dm_minus / self._tr
                self._di_plus = di_plus_val
                self._di_minus = di_minus_val

                # DX
                if (di_plus_val + di_minus_val) > 0:
                    dx = 100.0 * abs(di_plus_val - di_minus_val) / (di_plus_val + di_minus_val)
                else:
                    dx = 0.0

                # Wilder's smooth of DX
                if self._dx_count < self._period:
                    self._dx_buffer.append(dx)
                    self._dx_sum += dx
                    self._dx_count += 1
                    if self._dx_count == self._period:
                        self._adx = self._dx_sum / self._period
                else:
                    self._adx = (self._adx * (self._period - 1) + dx) / self._period

                if self._dx_count >= self._period:
                    self._value = self._adx

        self._prev_high = high
        self._prev_low = low
        self._prev_close = close
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


# ---------------------------------------------------------------------------
# FeaturesComputed event payload
# ---------------------------------------------------------------------------
@dataclass
class FeaturesComputed:
    """Published by FeatureEngine after computing indicators from a tick."""
    symbol: str
    features: dict[str, float]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stale: bool = False


# ---------------------------------------------------------------------------
# FeatureEngine — orchestrates indicators and publishes events
# ---------------------------------------------------------------------------
class FeatureEngine:
    """Registry of named indicators. Feed ticks → get FeaturesComputed events."""

    def __init__(self, event_bus: EventBus, symbol: str = "") -> None:
        self._event_bus = event_bus
        self._symbol = symbol
        self._indicators: dict[str, Any] = {}
        self._last_tick_time: float = 0.0
        self._last_features: dict[str, float] = {}

    def register(self, name: str, indicator: Any) -> None:
        """Register an indicator by name."""
        self._indicators[name] = indicator

    def get_indicator(self, name: str) -> Any | None:
        """Get a registered indicator by name."""
        return self._indicators.get(name)

    @property
    def indicator_names(self) -> list[str]:
        return list(self._indicators.keys())

    async def process_tick(self, tick: Tick) -> FeaturesComputed | None:
        """Feed a tick, compute all indicators, publish event."""
        now = time.time()
        tick_ts = tick.timestamp.timestamp() if hasattr(tick.timestamp, 'timestamp') else now

        freshness_check = abs(now - tick_ts) if tick_ts > 0 else 0.0
        stale = freshness_check > _FRESHNESS_SECONDS

        if hasattr(tick, 'ltp'):
            self._last_tick_time = now

        features: dict[str, float] = {}
        for name, ind in self._indicators.items():
            try:
                if hasattr(ind, 'update'):
                    ind.update(tick)
                val = ind.value if hasattr(ind, 'value') else None
                if val is not None and not stale:
                    if isinstance(val, dict):
                        for k, v in val.items():
                            features[f"{name}_{k}"] = float(v) if v is not None else 0.0
                    else:
                        features[name] = float(val)
            except Exception:
                continue

        self._last_features = features if not stale else self._last_features

        result = FeaturesComputed(
            symbol=tick.symbol if hasattr(tick, 'symbol') else self._symbol,
            features=self._last_features if stale else features,
            stale=stale,
        )

        await self._event_bus.publish(Event(
            topic=Topic.FEATURES_COMPUTED,
            data=result,
            source="feature_engine",
        ))
        return result
