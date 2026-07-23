"""QuantLib-based advanced options pricing for Indian markets.

Wraps QuantLib complexity behind a clean interface. Provides:
- European option pricing (Black-76 via BSM with r=q)
- American option pricing (Barone-Adesi-Whaley approximation)
- Volatility surface construction
- SABR smile calibration
- Full Greeks computation

Uses ql.India(ql.India.NSE) calendar and Actual/365 day count.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Literal

OptionType = Literal["CALL", "PUT"]

_ql = None
_quantlib_import_error: Exception | None = None
_NSE_CALENDAR = None
_DAY_COUNT = None
_BUSINESS_DAY_CONVENTION = None

try:
    import QuantLib as ql

    _ql = ql
    _NSE_CALENDAR = ql.India(ql.India.NSE)
    _DAY_COUNT = ql.Actual365Fixed()
    _BUSINESS_DAY_CONVENTION = ql.ModifiedFollowing
except ImportError as e:
    _quantlib_import_error = e


class QuantLibPricer:
    """Advanced options pricer using QuantLib for Indian markets.

    Uses Black-76 model (via BSM with dividend yield = risk-free rate)
    with NSE calendar and Actual/365 day count convention.
    """

    def __init__(self, risk_free_rate: float = 0.065) -> None:
        if _ql is None:
            raise ImportError(
                "QuantLib is required for QuantLibPricer. "
                "Install with: pip install QuantLib"
            ) from _quantlib_import_error
        self.risk_free_rate = risk_free_rate
        self._ql = _ql
        self._calendar = _NSE_CALENDAR
        self._dc = _DAY_COUNT
        self._bdc = _BUSINESS_DAY_CONVENTION

    def _to_ql_date(self, d: date) -> object:
        return self._ql.Date(d.day, d.month, d.year)

    def _to_python_date(self, d: object) -> date:
        return date(d.year(), d.month(), d.day())

    def _add_business_days(self, from_date: date, days: int) -> date:
        ql_date = self._to_ql_date(from_date)
        result = self._calendar.advance(ql_date, days, self._bdc)
        return self._to_python_date(result)

    def _count_business_days(self, start: date, end: date) -> int:
        return self._calendar.businessDaysBetween(
            self._to_ql_date(start), self._to_ql_date(end)
        )

    def _build_bsm_process(
        self,
        spot: float,
        vol: float,
        rate: float,
    ) -> object:
        ql = self._ql
        today = ql.Date.todaysDate()
        s0 = ql.QuoteHandle(ql.SimpleQuote(spot))
        vol_ts = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(today, self._calendar, vol, self._dc)
        )
        div_ts = ql.YieldTermStructureHandle(
            ql.FlatForward(today, rate, self._dc)
        )
        rf_ts = ql.YieldTermStructureHandle(
            ql.FlatForward(today, rate, self._dc)
        )
        return ql.BlackScholesMertonProcess(s0, div_ts, rf_ts, vol_ts)

    def price_european(
        self,
        spot: float,
        strike: float,
        rate: float,
        vol: float,
        maturity: float,
        option_type: OptionType = "CALL",
    ) -> float:
        if maturity <= 0.0 or vol <= 0.0 or spot <= 0.0 or strike <= 0.0:
            return 0.0

        ql = self._ql
        today = ql.Date.todaysDate()
        expiry = self._calendar.adjust(
            today + ql.Period(max(int(maturity * 365), 1), ql.Days),
            self._bdc,
        )

        opt_type = ql.Option.Call if option_type.upper() == "CALL" else ql.Option.Put
        payoff = ql.PlainVanillaPayoff(opt_type, strike)
        exercise = ql.EuropeanExercise(expiry)
        option = ql.VanillaOption(payoff, exercise)

        process = self._build_bsm_process(spot, vol, rate)
        engine = ql.AnalyticEuropeanEngine(process)
        option.setPricingEngine(engine)

        return option.NPV()

    def price_american(
        self,
        spot: float,
        strike: float,
        rate: float,
        vol: float,
        maturity: float,
        option_type: OptionType = "CALL",
    ) -> float:
        if maturity <= 0.0 or vol <= 0.0 or spot <= 0.0 or strike <= 0.0:
            return 0.0

        ql = self._ql
        today = ql.Date.todaysDate()
        expiry = self._calendar.adjust(
            today + ql.Period(max(int(maturity * 365), 1), ql.Days),
            self._bdc,
        )

        opt_type = ql.Option.Call if option_type.upper() == "CALL" else ql.Option.Put
        payoff = ql.PlainVanillaPayoff(opt_type, strike)
        exercise = ql.AmericanExercise(today, expiry)
        option = ql.VanillaOption(payoff, exercise)

        process = self._build_bsm_process(spot, vol, rate)
        engine = ql.BaroneAdesiWhaleyApproximationEngine(process)
        option.setPricingEngine(engine)

        return option.NPV()

    def compute_greeks(
        self,
        spot: float,
        strike: float,
        rate: float,
        vol: float,
        maturity: float,
        option_type: OptionType = "CALL",
    ) -> dict[str, float]:
        if maturity <= 0.0 or vol <= 0.0 or spot <= 0.0 or strike <= 0.0:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0,
                    "vega": 0.0, "rho": 0.0, "price": 0.0}

        ql = self._ql
        today = ql.Date.todaysDate()
        expiry = self._calendar.adjust(
            today + ql.Period(max(int(maturity * 365), 1), ql.Days),
            self._bdc,
        )

        opt_type = ql.Option.Call if option_type.upper() == "CALL" else ql.Option.Put
        payoff = ql.PlainVanillaPayoff(opt_type, strike)
        exercise = ql.EuropeanExercise(expiry)
        option = ql.VanillaOption(payoff, exercise)

        process = self._build_bsm_process(spot, vol, rate)
        engine = ql.AnalyticEuropeanEngine(process)
        option.setPricingEngine(engine)

        return {
            "delta": option.delta(),
            "gamma": option.gamma(),
            "theta": option.theta() / 365.0,
            "vega": option.vega() / 100.0,
            "rho": option.rho() / 100.0,
            "price": option.NPV(),
        }

    def build_vol_surface(
        self,
        forward: float,
        strikes: list[float],
        expiries: list[float],
        vols: list[list[float]],
    ) -> object:
        ql = self._ql
        today = ql.Date.todaysDate()

        vol_matrix = ql.Matrix(len(expiries), len(strikes))
        for i, vol_row in enumerate(vols):
            for j, vol_val in enumerate(vol_row):
                vol_matrix[i][j] = vol_val

        dates = [
            self._calendar.adjust(
                today + ql.Period(max(int(e * 365), 1), ql.Days),
                self._bdc,
            )
            for e in expiries
        ]

        strikes_arr = ql.DoubleVector(strikes)

        vol_surface = ql.BlackVolTermStructureHandle(
            ql.BlackVarianceSurface(
                today, self._calendar, dates, strikes_arr,
                vol_matrix, self._dc
            )
        )

        return vol_surface

    def calibrate_sabr(
        self,
        strikes: list[float],
        market_vols: list[float],
        forward: float,
        expiry: float,
        beta: float = 0.5,
    ) -> dict[str, float]:
        if len(strikes) != len(market_vols):
            raise ValueError("strikes and market_vols must have same length")
        if len(strikes) < 3:
            raise ValueError("Need at least 3 strikes for SABR calibration")

        ql = self._ql
        strikes_arr = ql.Array(strikes)
        vols_arr = ql.Array(market_vols)

        alpha = 0.3
        rho = -0.1
        nu = 0.4

        sabr_interp = ql.SABRInterpolation(
            strikes_arr, vols_arr,
            expiry, forward,
            alpha, beta, nu, rho,
            alphaIsFixed=False,
            betaIsFixed=True,
            nuIsFixed=False,
            rhoIsFixed=False,
        )

        calibrated_alpha = sabr_interp.alpha()
        calibrated_nu = sabr_interp.nu()
        calibrated_rho = sabr_interp.rho()

        total_error = 0.0
        for k, vol in zip(strikes, market_vols):
            model_vol = sabr_interp(float(k))
            total_error += (model_vol - vol) ** 2
        rmse = math.sqrt(total_error / len(strikes))

        return {
            "alpha": calibrated_alpha,
            "beta": beta,
            "rho": calibrated_rho,
            "nu": calibrated_nu,
            "calibration_rmse": rmse,
        }

    def business_days_to_expiry(self, from_date: date, to_date: date) -> int:
        return self._count_business_days(from_date, to_date)

    def years_to_expiry(self, from_date: date, to_date: date) -> float:
        days = (to_date - from_date).days
        return max(days / 365.0, 1.0 / 365.0)
