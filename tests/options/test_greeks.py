"""Tests for GreeksCalculator (Black-76 model).

Verifies:
- ITM call delta > 0.5, OTM call delta < 0.5
- Gamma positive for both calls and puts
- Theta negative for long options
"""

from __future__ import annotations

import pytest
from shettyxtreme.options.greeks import GreeksCalculator, _norm_cdf, _norm_pdf


class TestGreeksCalculator:
    """Suite for GreeksCalculator."""

    @pytest.fixture
    def calc(self) -> GreeksCalculator:
        return GreeksCalculator()

    def test_itm_call_delta_greater_than_half(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=90.0, tte=0.5, iv=0.20, option_type="CALL")
        assert result["delta"] > 0.5

    def test_otm_call_delta_less_than_half(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=110.0, tte=0.5, iv=0.20, option_type="CALL")
        assert result["delta"] < 0.5

    def test_atm_call_delta_approx_half(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="CALL")
        assert 0.45 <= result["delta"] <= 0.55

    def test_put_delta_negative(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="PUT")
        assert result["delta"] < 0

    def test_call_put_delta_parity(self, calc: GreeksCalculator) -> None:
        call = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="CALL")
        put = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="PUT")
        assert abs(call["delta"] - put["delta"] - 1.0) < 0.01

    def test_gamma_positive_for_call(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="CALL")
        assert result["gamma"] > 0

    def test_gamma_positive_for_put(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="PUT")
        assert result["gamma"] > 0

    def test_gamma_highest_atm(self, calc: GreeksCalculator) -> None:
        otm = calc.calculate_all(spot=100.0, strike=130.0, tte=0.5, iv=0.20, option_type="CALL")
        atm = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="CALL")
        itm = calc.calculate_all(spot=100.0, strike=70.0, tte=0.5, iv=0.20, option_type="CALL")
        assert atm["gamma"] > otm["gamma"]
        assert atm["gamma"] > itm["gamma"]

    def test_theta_negative_for_long_call(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="CALL")
        assert result["theta"] < 0

    def test_theta_negative_for_long_put(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="PUT")
        assert result["theta"] < 0

    def test_theta_magnitude_increases_near_expiry(self, calc: GreeksCalculator) -> None:
        far = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="CALL")
        near = calc.calculate_all(spot=100.0, strike=100.0, tte=0.1, iv=0.20, option_type="CALL")
        assert abs(near["theta"]) > abs(far["theta"])

    def test_vega_positive(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type="CALL")
        assert result["vega"] > 0

    def test_zero_tte_returns_zero_greeks(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.0, iv=0.20, option_type="CALL")
        assert all(v == 0.0 for v in result.values())

    def test_zero_iv_returns_zero_greeks(self, calc: GreeksCalculator) -> None:
        result = calc.calculate_all(spot=100.0, strike=100.0, tte=0.5, iv=0.0, option_type="CALL")
        assert all(v == 0.0 for v in result.values())

    def test_option_price_non_negative(self, calc: GreeksCalculator) -> None:
        for opt_type in ("CALL", "PUT"):
            price = calc.calculate_option_price(spot=100.0, strike=100.0, tte=0.5, iv=0.20, option_type=opt_type)
            assert price >= 0

    def test_itm_call_price_higher_than_otm(self, calc: GreeksCalculator) -> None:
        itm = calc.calculate_option_price(spot=100.0, strike=95.0, tte=0.5, iv=0.20, option_type="CALL")
        otm = calc.calculate_option_price(spot=100.0, strike=105.0, tte=0.5, iv=0.20, option_type="CALL")
        assert itm > otm


class TestHelpers:
    def test_norm_cdf_symmetric(self) -> None:
        for x in [0.0, 0.5, 1.0, 2.0]:
            assert abs(_norm_cdf(-x) - (1.0 - _norm_cdf(x))) < 1e-10

    def test_norm_cdf_at_zero(self) -> None:
        assert abs(_norm_cdf(0.0) - 0.5) < 1e-10

    def test_norm_pdf_symmetric(self) -> None:
        for x in [0.5, 1.0, 2.0]:
            assert abs(_norm_pdf(-x) - _norm_pdf(x)) < 1e-10
