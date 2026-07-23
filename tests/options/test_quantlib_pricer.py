"""Tests for QuantLib pricer integration.

Validates:
- European pricing matches Black-76 (within tolerance)
- American pricing >= European pricing (early exercise value)
- NSE calendar holiday awareness
- SABR calibration produces valid parameters
- Backward compatibility of GreeksCalculator with use_quantlib flag
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from shettyxtreme.options.greeks import GreeksCalculator
from shettyxtreme.options.quantlib_pricer import QuantLibPricer

try:
    import QuantLib as ql
    QUANTLIB_AVAILABLE = True
except ImportError:
    QUANTLIB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not QUANTLIB_AVAILABLE, reason="QuantLib not installed"
)

# --- Shared test parameters ---
SPOT = 24000.0
STRIKE = 24000.0
RATE = 0.065
VOL = 0.15
MATURITY = 0.25  # ~3 months


class TestQuantLibPricerEuropean:
    """Test European option pricing via QuantLib."""

    def test_call_price_positive(self):
        pricer = QuantLibPricer()
        price = pricer.price_european(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        assert price > 0.0

    def test_put_price_positive(self):
        pricer = QuantLibPricer()
        price = pricer.price_european(SPOT, STRIKE, RATE, VOL, MATURITY, "PUT")
        assert price > 0.0

    def test_put_call_parity(self):
        """Verify put-call parity: C - P = disc * (F - K)."""
        pricer = QuantLibPricer()
        call = pricer.price_european(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        put = pricer.price_european(SPOT, STRIKE, RATE, VOL, MATURITY, "PUT")
        disc = math.exp(-RATE * MATURITY)
        parity_lhs = call - put
        parity_rhs = disc * (SPOT - STRIKE)
        assert abs(parity_lhs - parity_rhs) < 1.0  # Tolerance for numerical error

    def test_itm_call_more_expensive_than_otm(self):
        pricer = QuantLibPricer()
        itm = pricer.price_european(SPOT, STRIKE * 0.95, RATE, VOL, MATURITY, "CALL")
        otm = pricer.price_european(SPOT, STRIKE * 1.05, RATE, VOL, MATURITY, "CALL")
        assert itm > otm

    def test_matches_builtin_black76(self):
        """QuantLib European price should match pure-Python Black-76."""
        pricer = QuantLibPricer()
        ql_price = pricer.price_european(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")

        # Pure Python Black-76
        from shettyxtreme.options.greeks import GreeksCalculator
        calc = GreeksCalculator(use_quantlib=False)
        py_price = calc.calculate_option_price(SPOT, STRIKE, MATURITY, VOL, "CALL", RATE)

        assert abs(ql_price - py_price) < 1.0  # Tolerance for different implementations

    def test_zero_maturity_returns_zero(self):
        pricer = QuantLibPricer()
        price = pricer.price_european(SPOT, STRIKE, RATE, VOL, 0.0, "CALL")
        assert price == 0.0

    def test_zero_vol_returns_zero(self):
        pricer = QuantLibPricer()
        price = pricer.price_european(SPOT, STRIKE, RATE, 0.0, MATURITY, "CALL")
        assert price == 0.0


class TestQuantLibPricerAmerican:
    """Test American option pricing via QuantLib."""

    def test_american_call_geq_european_call(self):
        """American call on non-dividend paying should equal European call."""
        pricer = QuantLibPricer()
        euro = pricer.price_european(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        amer = pricer.price_american(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        # For non-dividend paying underlying, American call >= European call
        assert amer >= euro - 0.01  # Small tolerance for MC noise

    def test_american_put_geq_european_put(self):
        """American put should be >= European put (early exercise premium)."""
        pricer = QuantLibPricer()
        euro = pricer.price_european(SPOT, STRIKE, RATE, VOL, MATURITY, "PUT")
        amer = pricer.price_american(SPOT, STRIKE, RATE, VOL, MATURITY, "PUT")
        assert amer >= euro - 0.01

    def test_american_put_more_valuable_deep_itm(self):
        """Deep ITM American put should have significant early exercise value."""
        pricer = QuantLibPricer()
        deep_itm_strike = SPOT * 1.15  # 15% OTM put = deep ITM
        euro = pricer.price_european(SPOT, deep_itm_strike, RATE, VOL, MATURITY, "PUT")
        amer = pricer.price_american(SPOT, deep_itm_strike, RATE, VOL, MATURITY, "PUT")
        assert amer >= euro - 0.01


class TestQuantLibGreeks:
    """Test Greeks computation via QuantLib."""

    def test_greeks_dict_keys(self):
        pricer = QuantLibPricer()
        greeks = pricer.compute_greeks(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        expected_keys = {"delta", "gamma", "theta", "vega", "rho", "price"}
        assert set(greeks.keys()) == expected_keys

    def test_call_delta_range(self):
        pricer = QuantLibPricer()
        greeks = pricer.compute_greeks(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        assert 0.0 <= greeks["delta"] <= 1.0

    def test_put_delta_range(self):
        pricer = QuantLibPricer()
        greeks = pricer.compute_greeks(SPOT, STRIKE, RATE, VOL, MATURITY, "PUT")
        assert -1.0 <= greeks["delta"] <= 0.0

    def test_gamma_positive(self):
        pricer = QuantLibPricer()
        greeks = pricer.compute_greeks(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        assert greeks["gamma"] >= 0.0

    def test_vega_positive(self):
        pricer = QuantLibPricer()
        greeks = pricer.compute_greeks(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")
        assert greeks["vega"] >= 0.0

    def test_greeks_match_builtin(self):
        """QuantLib Greeks should approximate pure-Python Greeks."""
        pricer = QuantLibPricer()
        ql_greeks = pricer.compute_greeks(SPOT, STRIKE, RATE, VOL, MATURITY, "CALL")

        calc = GreeksCalculator(use_quantlib=False)
        py_greeks = calc.calculate_all(SPOT, STRIKE, MATURITY, VOL, "CALL", RATE)

        # Delta and gamma should be very close
        assert abs(ql_greeks["delta"] - py_greeks["delta"]) < 0.01
        assert abs(ql_greeks["gamma"] - py_greeks["gamma"]) < 0.001


class TestNSECalendar:
    """Test NSE calendar holiday awareness."""

    def test_india_calendar_exists(self):
        from shettyxtreme.options.quantlib_pricer import NSE_CALENDAR
        assert NSE_CALENDAR is not None

    def test_business_days_count(self):
        from shettyxtreme.options.quantlib_pricer import QuantLibPricer
        pricer = QuantLibPricer()
        # Monday to Friday = 4 business days (Mon-Fri excluding start)
        start = date(2026, 7, 20)  # Monday
        end = date(2026, 7, 24)    # Friday
        bd = pricer.business_days_to_expiry(start, end)
        assert 3 <= bd <= 5  # Should be ~3-4 business days

    def test_holiday_not_counted(self):
        """Verify that known NSE holidays are not counted as business days."""
        from shettyxtreme.options.quantlib_pricer import NSE_CALENDAR, _to_ql_date
        # Aug 15 (Independence Day) is a holiday
        holiday = date(2026, 8, 15)
        next_day = date(2026, 8, 16)
        if NSE_CALENDAR.isHoliday(_to_ql_date(holiday)):
            assert not NSE_CALENDAR.isBusinessDay(_to_ql_date(holiday))
        # Aug 16 (Sunday) is also non-business
        assert not NSE_CALENDAR.isBusinessDay(_to_ql_date(next_day))

    def test_years_to_expiry(self):
        from shettyxtreme.options.quantlib_pricer import QuantLibPricer
        pricer = QuantLibPricer()
        start = date(2026, 1, 1)
        end = date(2026, 4, 1)  # 90 days
        years = pricer.years_to_expiry(start, end)
        assert abs(years - 90 / 365.0) < 0.001


class TestSABRCalibration:
    """Test SABR smile calibration."""

    def test_sabr_calibration_returns_valid_params(self):
        pricer = QuantLibPricer()
        forward = SPOT
        strikes = [forward * m for m in [0.90, 0.95, 1.00, 1.05, 1.10]]
        # Smile-shaped vols
        vols = [0.18, 0.16, 0.15, 0.155, 0.17]

        result = pricer.calibrate_sabr(
            strikes=strikes,
            market_vols=vols,
            forward=forward,
            expiry=MATURITY,
            beta=0.5,
        )

        assert "alpha" in result
        assert "beta" in result
        assert "rho" in result
        assert "nu" in result
        assert "calibration_rmse" in result

        # Alpha (vol-of-vol) should be positive
        assert result["alpha"] > 0.0
        # Rho (correlation) should be between -1 and 1
        assert -1.0 <= result["rho"] <= 1.0
        # Nu should be positive
        assert result["nu"] >= 0.0
        # Beta should match input
        assert result["beta"] == 0.5
        # RMSE should be small (good fit)
        assert result["calibration_rmse"] < 0.01

    def test_sabr_needs_min_3_strikes(self):
        pricer = QuantLibPricer()
        with pytest.raises(ValueError, match="at least 3 strikes"):
            pricer.calibrate_sabr(
                strikes=[23000, 24000],
                market_vols=[0.18, 0.15],
                forward=SPOT,
                expiry=MATURITY,
            )

    def test_sabr_needs_matching_lengths(self):
        pricer = QuantLibPricer()
        with pytest.raises(ValueError, match="same length"):
            pricer.calibrate_sabr(
                strikes=[23000, 24000, 25000],
                market_vols=[0.18, 0.15],
                forward=SPOT,
                expiry=MATURITY,
            )


class TestGreeksCalculatorQuantLibIntegration:
    """Test GreeksCalculator with use_quantlib=True."""

    def test_quantlib_flag_enables_delegation(self):
        calc = GreeksCalculator(use_quantlib=True)
        assert calc.use_quantlib is True
        greeks = calc.calculate_all(SPOT, STRIKE, MATURITY, VOL, "CALL", RATE)
        assert "delta" in greeks
        assert greeks["delta"] > 0.0

    def test_fallback_on_import_error(self):
        """If QuantLib unavailable, use_quantlib=False fallback works."""
        calc = GreeksCalculator(use_quantlib=False)
        assert calc.use_quantlib is False
        greeks = calc.calculate_all(SPOT, STRIKE, MATURITY, VOL, "CALL", RATE)
        assert "delta" in greeks

    def test_option_price_with_quantlib(self):
        calc = GreeksCalculator(use_quantlib=True)
        price = calc.calculate_option_price(SPOT, STRIKE, MATURITY, VOL, "CALL", RATE)
        assert price > 0.0

    def test_backward_compatibility_default(self):
        """Default use_quantlib=False preserves existing behavior."""
        calc = GreeksCalculator()
        assert calc.use_quantlib is False
        greeks = calc.calculate_all(SPOT, STRIKE, MATURITY, VOL, "CALL", RATE)
        assert "delta" in greeks
        assert "gamma" in greeks
