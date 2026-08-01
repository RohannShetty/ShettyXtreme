"""Calibrated position sizing — scale base quantity by calibrated win rate.

Consumes a fitted CalibrationCurve. The caller decides whether the curve is
reliable (e.g. via is_reliable on the decision list) and flips `active` on;
sizing itself never touches the database.
"""
from __future__ import annotations

from shettyxtreme.learning.calibration import CalibrationCurve


class CalibratedSizing:
    """Scale a base quantity by the calibrated win-rate multiplier."""

    def __init__(
        self,
        curve: CalibrationCurve,
        base_rate: float = 0.5,
        min_multiplier: float = 0.25,
        max_multiplier: float = 2.0,
    ) -> None:
        self._curve = curve
        self._base_rate = base_rate
        self._min_multiplier = min_multiplier
        self._max_multiplier = max_multiplier
        self._active = False

    @property
    def active(self) -> bool:
        """Whether calibrated sizing is currently applied."""
        return self._active

    def set_active(self, active: bool) -> None:
        """Enable/disable calibrated sizing (reliability decided by caller)."""
        self._active = active

    def adjust(self, base_quantity: int, conviction: float) -> int:
        """Scale base_quantity by the calibrated win-rate multiplier.

        Raises ValueError when base_quantity is not positive; conviction is
        clamped to [0, 1]; the multiplier is clamped to [min, max] and the
        result is at least 1.
        """
        if base_quantity <= 0:
            raise ValueError(
                f"base_quantity must be positive, got {base_quantity}"
            )
        if not self._active:
            return base_quantity
        c = max(0.0, min(1.0, conviction))
        p = self._curve.predict(c)
        mult = max(self._min_multiplier, min(self._max_multiplier, p / self._base_rate))
        return max(1, round(base_quantity * mult))
