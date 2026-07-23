"""Volume Weighted Average Price — cumulative, O(1) per tick."""
from __future__ import annotations

from shettyxtreme.core.data_models.market_data import Tick


class VWAP:
    def __init__(self) -> None:
        self._cum_pv = 0.0
        self._cum_vol = 0
        self._value: float | None = None

    def update(self, tick: Tick) -> float:
        vol = tick.volume if tick.volume else 0
        self._cum_pv += tick.ltp * vol
        self._cum_vol += vol
        if self._cum_vol == 0:
            self._value = tick.ltp
        else:
            self._value = self._cum_pv / self._cum_vol
        return self._value

    @property
    def value(self) -> float | None:
        return self._value

    def reset(self) -> None:
        self._cum_pv = 0.0
        self._cum_vol = 0
        self._value = None
