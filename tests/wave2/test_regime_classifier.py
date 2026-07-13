"""Tests for RegimeClassifier."""
from __future__ import annotations

import pytest

from shettyxtreme.intelligence.regime import RegimeClassifier, Regime


class TestRegimeClassifier:
    def setup_method(self) -> None:
        self.classifier = RegimeClassifier()

    # ------------------------------------------------------------------
    # TRENDING_UP: ADX > 25 + DI+ > DI-
    # ------------------------------------------------------------------
    def test_trending_up(self) -> None:
        features: dict[str, float] = {
            "adx": 30.0,
            "di_plus": 28.0,
            "di_minus": 15.0,
            "atr_percentile": 50.0,
        }
        regime = self.classifier.classify(features)
        assert regime == Regime.TRENDING_UP

    # ------------------------------------------------------------------
    # TRENDING_DOWN: ADX > 25 + DI- > DI+
    # ------------------------------------------------------------------
    def test_trending_down(self) -> None:
        features: dict[str, float] = {
            "adx": 30.0,
            "di_plus": 12.0,
            "di_minus": 26.0,
            "atr_percentile": 50.0,
        }
        regime = self.classifier.classify(features)
        assert regime == Regime.TRENDING_DOWN

    # ------------------------------------------------------------------
    # RANGE_BOUND: ADX < 20
    # ------------------------------------------------------------------
    def test_range_bound(self) -> None:
        features: dict[str, float] = {
            "adx": 15.0,
            "di_plus": 10.0,
            "di_minus": 12.0,
            "atr_percentile": 50.0,
        }
        regime = self.classifier.classify(features)
        assert regime == Regime.RANGE_BOUND

    # ------------------------------------------------------------------
    # VOLATILE: ATR percentile > 80 (overrides ADX)
    # ------------------------------------------------------------------
    def test_volatile_overrides(self) -> None:
        """ATR percentile > 80 should return VOLATILE even with low ADX."""
        features: dict[str, float] = {
            "adx": 15.0,
            "di_plus": 10.0,
            "di_minus": 12.0,
            "atr_percentile": 85.0,
        }
        regime = self.classifier.classify(features)
        assert regime == Regime.VOLATILE

    def test_volatile_with_high_adx(self) -> None:
        """ATR percentile > 80 should override even trending regimes."""
        features: dict[str, float] = {
            "adx": 35.0,
            "di_plus": 30.0,
            "di_minus": 10.0,
            "atr_percentile": 90.0,
        }
        regime = self.classifier.classify(features)
        assert regime == Regime.VOLATILE

    # ------------------------------------------------------------------
    # TRANSITION: ADX dropping from >25 to <25
    # ------------------------------------------------------------------
    def test_transition(self) -> None:
        """First classify with high ADX, then with low ADX → TRANSITION."""
        # First call: trending
        features_high: dict[str, float] = {
            "adx": 30.0,
            "di_plus": 25.0,
            "di_minus": 10.0,
            "atr_percentile": 50.0,
        }
        self.classifier.classify(features_high)

        # Second call: ADX dropped
        features_low: dict[str, float] = {
            "adx": 18.0,
            "di_plus": 10.0,
            "di_minus": 9.0,
            "atr_percentile": 50.0,
        }
        regime = self.classifier.classify(features_low)
        assert regime == Regime.TRANSITION

    # ------------------------------------------------------------------
    # Confidence bounds
    # ------------------------------------------------------------------
    def test_confidence_is_between_0_and_1(self) -> None:
        features: dict[str, float] = {
            "adx": 30.0,
            "di_plus": 25.0,
            "di_minus": 10.0,
            "atr_percentile": 50.0,
        }
        confidence = self.classifier.compute_confidence(features, Regime.TRENDING_UP)
        assert 0.0 <= confidence <= 1.0

    def test_confidence_low_adx(self) -> None:
        features: dict[str, float] = {
            "adx": 5.0,
            "di_plus": 3.0,
            "di_minus": 4.0,
            "atr_percentile": 50.0,
        }
        confidence = self.classifier.compute_confidence(features, Regime.RANGE_BOUND)
        assert 0.0 <= confidence <= 1.0
        assert confidence < 0.5  # Low ADX = low confidence

    def test_confidence_volatile(self) -> None:
        features: dict[str, float] = {
            "adx": 15.0,
            "atr_percentile": 85.0,
        }
        confidence = self.classifier.compute_confidence(features, Regime.VOLATILE)
        assert confidence == 0.8

    # ------------------------------------------------------------------
    # Transition detection
    # ------------------------------------------------------------------
    def test_detect_transition_prev_trending_up_to_range(self) -> None:
        result = self.classifier.detect_transition(
            prev=Regime.TRENDING_UP,
            curr=Regime.RANGE_BOUND,
        )
        assert result is True

    def test_detect_transition_same_regime(self) -> None:
        result = self.classifier.detect_transition(
            prev=Regime.TRENDING_UP,
            curr=Regime.TRENDING_UP,
        )
        assert result is False

    def test_detect_transition_to_volatile(self) -> None:
        result = self.classifier.detect_transition(
            prev=Regime.RANGE_BOUND,
            curr=Regime.VOLATILE,
        )
        assert result is True

    def test_detect_transition_to_transition(self) -> None:
        result = self.classifier.detect_transition(
            prev=Regime.TRENDING_UP,
            curr=Regime.TRANSITION,
        )
        assert result is True
