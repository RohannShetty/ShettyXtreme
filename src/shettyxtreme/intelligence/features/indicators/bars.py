"""Bar aggregator — ticks into OHLC bars over a fixed timeframe."""
from __future__ import annotations

from shettyxtreme.core.data_models.market_data import Tick


class Bars:
    def __init__(self, timeframe_seconds: int = 60) -> None:
        self.timeframe_seconds = timeframe_seconds
        self._open: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._close: float | None = None
        self._volume = 0
        self._value: dict | None = None

    def update(self, tick: Tick) -> None:
        price = tick.ltp
        if self._open is None:
            self._open = price
            self._high = price
            self._low = price
        else:
            self._high = max(self._high, price)  # type: ignore[arg-type]
            self._low = min(self._low, price)  # type: ignore[arg-type]
        self._close = price
        self._volume += tick.volume if tick.volume else 0
        return None

    @property
    def value(self) -> None:
        return None

    def reset(self) -> None:
        self._open = None
        self._high = None
        self._low = None
        self._close = None
        self._volume = 0
        self._value = None
