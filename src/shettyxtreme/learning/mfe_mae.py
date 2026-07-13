"""MFE / MAE calculator — maximum favorable / adverse excursion tracking.

In-memory, per-signal tracking of how far a position moved in the trader's
favor (MFE) and against the trader (MAE) from entry. Used to tune targets and
stops from realized behavior rather than guesswork.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MfeMaeRecord:
    """Finalized MFE/MAE record for a closed signal."""

    signal_id: str
    entry_price: float
    mfe: float
    mae: float
    mfe_percentile: float
    mae_percentile: float
    direction: float


class MfeMaeCalculator:
    """Track MFE and MAE for open signals and finalize on close."""

    def __init__(self) -> None:
        self._mfe: dict[str, float] = {}
        self._mae: dict[str, float] = {}
        self._entry: dict[str, float] = {}
        self._direction: dict[str, float] = {}

    def update(
        self, signal_id: str, ltp: float, entry_price: float, direction: float
    ) -> None:
        """Update MFE/MAE for a signal using the latest price."""
        if signal_id not in self._mfe:
            self._mfe[signal_id] = 0.0
            self._mae[signal_id] = 0.0
            self._entry[signal_id] = entry_price
            self._direction[signal_id] = direction

        if direction > 0:
            favorable = ltp - entry_price
            adverse = entry_price - ltp
        else:
            favorable = entry_price - ltp
            adverse = ltp - entry_price

        if favorable > self._mfe[signal_id]:
            self._mfe[signal_id] = favorable
        if adverse > self._mae[signal_id]:
            self._mae[signal_id] = adverse

    def get_mfe(self, signal_id: str) -> Optional[float]:
        """Return MFE for a signal, or None if untracked."""
        return self._mfe.get(signal_id)

    def get_mae(self, signal_id: str) -> Optional[float]:
        """Return MAE for a signal, or None if untracked."""
        return self._mae.get(signal_id)

    def get_mfe_percentile(self, signal_id: str, all_signals: list[str]) -> float:
        """Percentile rank of this signal's MFE among all_signals (0-100)."""
        return self._percentile(signal_id, all_signals, self._mfe)

    def get_mae_percentile(self, signal_id: str, all_signals: list[str]) -> float:
        """Percentile rank of this signal's MAE among all_signals (0-100)."""
        return self._percentile(signal_id, all_signals, self._mae)

    def _percentile(
        self, signal_id: str, all_signals: list[str], store: dict[str, float]
    ) -> float:
        values = [store[s] for s in all_signals if s in store]
        if signal_id not in store or not values:
            return 0.0
        target = store[signal_id]
        below = sum(1 for v in values if v < target)
        equal = sum(1 for v in values if v == target)
        rank = (below + 0.5 * equal) / len(values)
        return rank * 100.0

    def close(self, signal_id: str) -> MfeMaeRecord:
        """Finalize and stop tracking a signal. Returns the record."""
        mfe = self._mfe.get(signal_id, 0.0)
        mae = self._mae.get(signal_id, 0.0)
        entry = self._entry.get(signal_id, 0.0)
        direction = self._direction.get(signal_id, 0.0)
        all_signals = list(self._mfe.keys())
        mfe_pct = self.get_mfe_percentile(signal_id, all_signals)
        mae_pct = self.get_mae_percentile(signal_id, all_signals)
        record = MfeMaeRecord(
            signal_id=signal_id,
            entry_price=entry,
            mfe=mfe,
            mae=mae,
            mfe_percentile=mfe_pct,
            mae_percentile=mae_pct,
            direction=direction,
        )
        self._mfe.pop(signal_id, None)
        self._mae.pop(signal_id, None)
        self._entry.pop(signal_id, None)
        self._direction.pop(signal_id, None)
        return record
