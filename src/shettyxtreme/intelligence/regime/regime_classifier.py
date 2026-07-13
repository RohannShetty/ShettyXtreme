"""Regime classifier — pure feature-based market regime detection.

Classifies market state from computed features using deterministic rules:
  - TRENDING_UP / TRENDING_DOWN (ADX > 25 + directional)
  - RANGE_BOUND (ADX < 20)
  - VOLATILE (ATR percentile > 80, overrides everything)
  - TRANSITION (ADX dropping from >25 to <25)

No Markov chains, no hidden state models.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Any


class Regime(Enum):
    """Market regime categories."""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGE_BOUND = "range_bound"
    VOLATILE = "volatile"
    TRANSITION = "transition"

    def __str__(self) -> str:
        return self.value


_ADX_HIGH_THRESHOLD = 25.0
_ADX_LOW_THRESHOLD = 20.0
_ATR_VOLATILE_PERCENTILE = 80.0
_CONFIDENCE_ADX_MAX = 50.0


class RegimeClassifier:
    """Classify market regime from computed features.

    Classification logic:
    1. If ATR percentile > 80 → VOLATILE (overrides)
    2. If ADX > 25 + DI+ > DI- → TRENDING_UP
    3. If ADX > 25 + DI- > DI+ → TRENDING_DOWN
    4. If ADX < 20 → RANGE_BOUND
    5. If ADX dropping from >25 to <25 → TRANSITION
    """

    def __init__(self) -> None:
        self._prev_adx: float | None = None
        self._prev_regime: Regime | None = None

    def classify(self, features: dict[str, float]) -> Regime:
        """Classify market regime from a feature dict.

        Args:
            features: Dictionary of computed indicator values.
                      Expected keys: 'adx', 'di_plus', 'di_minus',
                      'atr_percentile' (optional).

        Returns:
            Regime enum value.
        """
        adx = features.get("adx", 0.0)
        di_plus = features.get("di_plus", 0.0)
        di_minus = features.get("di_minus", 0.0)
        atr_pct = features.get("atr_percentile", 0.0)

        # Volatile override
        if atr_pct > _ATR_VOLATILE_PERCENTILE:
            self._prev_adx = adx
            self._prev_regime = Regime.VOLATILE
            return Regime.VOLATILE

        # Transition detection: ADX dropping from high range to low range
        if self._prev_adx is not None:
            if self._prev_adx > _ADX_HIGH_THRESHOLD and adx < _ADX_LOW_THRESHOLD:
                self._prev_adx = adx
                self._prev_regime = Regime.TRANSITION
                return Regime.TRANSITION

        # Trending
        if adx > _ADX_HIGH_THRESHOLD:
            if di_plus > di_minus:
                self._prev_adx = adx
                self._prev_regime = Regime.TRENDING_UP
                return Regime.TRENDING_UP
            elif di_minus > di_plus:
                self._prev_adx = adx
                self._prev_regime = Regime.TRENDING_DOWN
                return Regime.TRENDING_DOWN

        # Range bound
        if adx < _ADX_LOW_THRESHOLD:
            self._prev_adx = adx
            self._prev_regime = Regime.RANGE_BOUND
            return Regime.RANGE_BOUND

        # Fallback — if ADX between 20-25 with no clear direction
        if adx < _ADX_HIGH_THRESHOLD:
            self._prev_adx = adx
            self._prev_regime = Regime.RANGE_BOUND
            return Regime.RANGE_BOUND

        self._prev_adx = adx
        self._prev_regime = Regime.RANGE_BOUND
        return Regime.RANGE_BOUND

    def compute_confidence(self, features: dict[str, float], regime: Regime) -> float:
        """Compute classification confidence (0.0-1.0).

        Based on:
        - ADX strength relative to max (capped at 50)
        - ATR stability (how far from extreme)
        """
        if regime == Regime.VOLATILE:
            return 0.8

        adx = features.get("adx", 0.0)
        atr_pct = features.get("atr_percentile", 50.0)

        # ADX component: how strong the trend is
        adx_component = min(adx / _CONFIDENCE_ADX_MAX, 1.0)

        # Stability component: penalty if ATR is too high (noisy)
        stability = 1.0 - abs(atr_pct - 50.0) / 100.0

        confidence = adx_component * 0.7 + stability * 0.3
        return max(0.0, min(1.0, confidence))

    def detect_transition(
        self,
        prev: Regime,
        curr: Regime,
        features: dict[str, float] | None = None,
    ) -> bool:
        """Detect if a regime transition has occurred.

        Args:
            prev: Previous regime.
            curr: Current regime.
            features: Optional feature dict for additional checks.

        Returns:
            True if a meaningful transition is detected.
        """
        # Direct regime change = transition
        if prev != curr:
            # TRENDING_UP -> RANGE_BOUND or TRENDING_DOWN -> RANGE_BOUND
            if prev in (Regime.TRENDING_UP, Regime.TRENDING_DOWN) and curr == Regime.RANGE_BOUND:
                return True
            # RANGE_BOUND -> trending
            if prev == Regime.RANGE_BOUND and curr in (Regime.TRENDING_UP, Regime.TRENDING_DOWN):
                return True
            # Any -> TRANSITION
            if curr == Regime.TRANSITION:
                return True
            # Any -> VOLATILE
            if curr == Regime.VOLATILE:
                return True
        return False
