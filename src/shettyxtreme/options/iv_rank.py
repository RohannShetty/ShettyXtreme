"""IV Rank and IV Percentile calculator.

Tracks historical implied volatility data and computes IV rank/percentile
to classify current IV environment as LOW, NORMAL, or HIGH.

Uses an in-memory store for historical IV data (deque-based ring buffer).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

IVClassification = Literal["LOW", "NORMAL", "HIGH"]


@dataclass
class IVSnapshot:
    """A single IV data point at a point in time."""

    symbol: str
    iv: float
    strike: float = 0.0
    expiry: str = ""
    option_type: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class IVRankResult:
    """Result of an IV rank/percentile computation.

    NOTE (F-INTEL-008): ``iv_rank_percent`` and ``iv_percentile`` are on the
    0-100 (percent) scale. The canonical 0-1 IV-rank function is
    ``intelligence.options.compute_iv_rank`` — do not mix the scales.
    """

    symbol: str
    current_iv: float
    iv_rank_percent: float
    iv_percentile: float
    min_iv: float
    max_iv: float
    mean_iv: float
    classification: IVClassification
    num_data_points: int


class IVRankCalculator:
    """Compute IV rank and percentile from historical IV data.

    IV Rank (percent): (current_iv - min_iv) / (max_iv - min_iv) * 100
    IV Percentile: percentage of historical IV data points below current IV.

    F-INTEL-008: this calculator returns rank on the 0-100 percent scale and
    is deliberately named ``compute_iv_rank_percent`` so it cannot be confused
    with the canonical 0-1 ``intelligence.options.compute_iv_rank``.

    Stores historical IV data in-memory using deques (ring buffers).
    Each symbol has its own buffer to keep memory bounded.
    """

    def __init__(self, max_history: int = 5000) -> None:
        """Initialise the IV rank calculator.

        Args:
            max_history: Maximum historical IV data points to retain per symbol.
        """
        self._max_history = max_history
        self._historical_iv: dict[str, deque[float]] = {}
        self._snapshots: dict[str, deque[IVSnapshot]] = {}

    def record_iv(
        self,
        symbol: str,
        iv: float,
        strike: float = 0.0,
        expiry: str = "",
        option_type: str = "",
    ) -> None:
        """Record a historical IV data point for a symbol."""
        if symbol not in self._historical_iv:
            self._historical_iv[symbol] = deque(maxlen=self._max_history)
            self._snapshots[symbol] = deque(maxlen=self._max_history)

        self._historical_iv[symbol].append(iv)
        self._snapshots[symbol].append(
            IVSnapshot(
                symbol=symbol,
                iv=iv,
                strike=strike,
                expiry=expiry,
                option_type=option_type,
            )
        )

    def record_iv_batch(self, symbol: str, iv_values: list[float]) -> None:
        """Record multiple historical IV values for a symbol."""
        for iv in iv_values:
            self.record_iv(symbol=symbol, iv=iv)

    def compute_iv_rank_percent(
        self, symbol: str, current_iv: float | None = None
    ) -> IVRankResult | None:
        """Compute IV rank (0-100 percent scale) and percentile for a symbol.

        F-INTEL-008: this is the 0-100 variant — the canonical 0-1 IV-rank
        function is ``intelligence.options.compute_iv_rank``.

        Args:
            symbol: Instrument symbol to compute rank for.
            current_iv: Current IV value. If None, uses the latest recorded IV.

        Returns:
            IVRankResult with rank, percentile, and classification, or None if
            insufficient data.
        """
        hist = self._historical_iv.get(symbol)
        if not hist or len(hist) < 2:
            return None

        iv_values = list(hist)
        if current_iv is None:
            current_iv = iv_values[-1]

        min_iv = min(iv_values)
        max_iv = max(iv_values)
        mean_iv = sum(iv_values) / len(iv_values)

        # IV Rank: position between min and max
        if max_iv > min_iv:
            iv_rank = (current_iv - min_iv) / (max_iv - min_iv) * 100.0
        else:
            iv_rank = 50.0

        # IV Percentile: % of historical data <= current IV
        count_below = sum(1 for v in iv_values if v <= current_iv)
        iv_percentile = (count_below / len(iv_values)) * 100.0

        # Classification
        if iv_percentile < 30.0:
            classification: IVClassification = "LOW"
        elif iv_percentile <= 70.0:
            classification = "NORMAL"
        else:
            classification = "HIGH"

        return IVRankResult(
            symbol=symbol,
            current_iv=current_iv,
            iv_rank_percent=round(iv_rank, 2),
            iv_percentile=round(iv_percentile, 2),
            min_iv=round(min_iv, 4),
            max_iv=round(max_iv, 4),
            mean_iv=round(mean_iv, 4),
            classification=classification,
            num_data_points=len(iv_values),
        )

    def classify_iv(
        self, symbol: str, current_iv: float | None = None
    ) -> IVClassification:
        """Classify current IV as LOW, NORMAL, or HIGH."""
        result = self.compute_iv_rank_percent(symbol, current_iv)
        if result is None:
            return "NORMAL"
        return result.classification

    def clear_history(self, symbol: str | None = None) -> None:
        """Clear historical IV data for one or all symbols."""
        if symbol:
            self._historical_iv.pop(symbol, None)
            self._snapshots.pop(symbol, None)
        else:
            self._historical_iv.clear()
            self._snapshots.clear()

    @property
    def symbols(self) -> list[str]:
        """Return all symbols with recorded IV data."""
        return list(self._historical_iv.keys())

    def data_count(self, symbol: str) -> int:
        """Return the number of IV data points for a symbol."""
        hist = self._historical_iv.get(symbol)
        return len(hist) if hist else 0

    def get_history(self, symbol: str, days: int = 30) -> list[dict[str, Any]]:
        """Return timestamped IV snapshots for a symbol, filtered to N days.

        Phase 3A.3: exposes the in-memory snapshot deque as a time series for
        the IV-rank history chart. Each entry reports the IV rank (0-100
        percent scale, F-INTEL-008) and classification of that snapshot's IV
        against the full recorded history.

        Args:
            symbol: Instrument symbol to fetch history for.
            days: How many days of history to return (default 30). Clamped
                to >= 1.

        Returns:
            Chronological list of ``{timestamp, iv_rank_percent,
            iv_classification}`` dicts; empty when the symbol has no recorded
            IV data (or fewer than two data points, which cannot be ranked).
        """
        snapshots = self._snapshots.get(symbol)
        if not snapshots:
            return []
        cutoff = datetime.now(UTC) - timedelta(days=max(1, days))
        result: list[dict[str, Any]] = []
        for snap in snapshots:
            if snap.timestamp < cutoff:
                continue
            rank = self.compute_iv_rank_percent(symbol, current_iv=snap.iv)
            if rank is None:
                continue
            result.append({
                "timestamp": snap.timestamp.isoformat(),
                "iv_rank_percent": rank.iv_rank_percent,
                "iv_classification": rank.classification,
            })
        return result
