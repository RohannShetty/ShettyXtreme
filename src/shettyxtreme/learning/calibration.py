"""Calibration — map raw conviction to realized win probability via binning.

Fits a calibration curve over historical decisions using 10 equal-width
conviction bins, then predicts a calibrated win probability. Falls back to
raw conviction when insufficient data is available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shettyxtreme.learning.outcome_tracker import OutcomeLabel, SignalDecision

NUM_BINS = 10
RELIABLE_THRESHOLD = 30


@dataclass
class CalibrationPoint:
    """A single calibration bin."""

    conviction_bin: tuple[float, float]
    actual_win_rate: float
    sample_size: int
    confidence_interval: tuple[float, float]


class CalibrationCurve:
    """Binning-based conviction calibration (no scipy dependency)."""

    def __init__(self) -> None:
        self._bins: list[Optional[CalibrationPoint]] = [None] * NUM_BINS
        self._total_fitted: int = 0

    def fit(self, decisions: list[SignalDecision]) -> None:
        """Fit calibration bins from historical decisions."""
        self._total_fitted = len(decisions)
        buckets: list[list[bool]] = [[] for _ in range(NUM_BINS)]
        for d in decisions:
            if d.outcome is None:
                continue
            c = max(0.0, min(0.9999, d.signal.conviction))
            idx = min(NUM_BINS - 1, int(c * NUM_BINS))
            buckets[idx].append(d.outcome == OutcomeLabel.WIN)
        for i in range(NUM_BINS):
            low = i / NUM_BINS
            high = (i + 1) / NUM_BINS
            samples = buckets[i]
            n = len(samples)
            wins = sum(1 for s in samples if s)
            rate = wins / n if n > 0 else 0.0
            ci = self._wilson(wins, n)
            self._bins[i] = CalibrationPoint(
                conviction_bin=(low, high),
                actual_win_rate=rate,
                sample_size=n,
                confidence_interval=ci,
            )

    def predict(self, conviction: float) -> float:
        """Return calibrated win probability for a conviction level."""
        if self._total_fitted < RELIABLE_THRESHOLD:
            return conviction
        idx = min(NUM_BINS - 1, max(0, int(conviction * NUM_BINS)))
        point = self._bins[idx]
        if point is None or point.sample_size == 0:
            return conviction
        return point.actual_win_rate

    def is_reliable(self, decisions: list[SignalDecision]) -> bool:
        """True only when enough historical decisions exist."""
        return len(decisions) > RELIABLE_THRESHOLD

    def get_curve(self) -> list[CalibrationPoint]:
        """Return fitted calibration points (may contain zero-sample bins)."""
        return [b for b in self._bins if b is not None]

    def _wilson(self, wins: int, n: int) -> tuple[float, float]:
        if n == 0:
            return (0.0, 0.0)
        p = wins / n
        z = 1.96
        denom = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denom
        margin = (z * ((p * (1 - p) / n) + z * z / (4 * n * n)) ** 0.5) / denom
        return (max(0.0, centre - margin), min(1.0, centre + margin))
