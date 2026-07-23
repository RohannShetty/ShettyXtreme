"""Black-76 Greeks calculator for options on futures/indices.

Provides delta, gamma, theta, vega, and rho using the Black-76 model.
Pure computation — takes parameters, returns dicts. No I/O.

Optionally uses QuantLib for advanced pricing when use_quantlib=True.
"""

from __future__ import annotations

import math
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from .quantlib_pricer import QuantLibPricer

OptionType = Literal["CALL", "PUT"]


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1_d2(
    futures_price: float,
    strike: float,
    tte_years: float,
    iv: float,
    rate: float = 0.0,
) -> tuple[float, float]:
    """Compute Black-76 d1 and d2."""
    if tte_years <= 0.0 or iv <= 0.0:
        return (0.0, 0.0)
    vol_sqrt_t = iv * math.sqrt(tte_years)
    d1 = (math.log(futures_price / strike) + (vol_sqrt_t * vol_sqrt_t) / 2.0) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return (d1, d2)


class GreeksCalculator:
    """Compute all option Greeks using the Black-76 model.

    Black-76 is the standard model for pricing European options on futures,
    which is the convention for Indian index options (Nifty, Bank Nifty, etc.).

    Optionally uses QuantLib for advanced pricing when use_quantlib=True.
    """

    def __init__(self, use_quantlib: bool = False) -> None:
        """Initialize the Greeks calculator.

        Args:
            use_quantlib: If True, delegate to QuantLibPricer for advanced
                pricing. Falls back to pure-Python Black-76 on ImportError.
        """
        self._use_quantlib = use_quantlib
        self._quantlib_pricer = None
        if use_quantlib:
            try:
                from .quantlib_pricer import QuantLibPricer
                self._quantlib_pricer = QuantLibPricer()
            except ImportError:
                self._use_quantlib = False

    @property
    def use_quantlib(self) -> bool:
        """Return whether QuantLib is being used."""
        return self._use_quantlib

    def calculate_all(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        option_type: OptionType,
        rate: float = 0.0,
    ) -> dict[str, float]:
        """Compute all Greeks for a single option.

        Args:
            spot: Current underlying/futures price.
            strike: Option strike price.
            tte: Time to expiry in years.
            iv: Implied volatility (decimal, e.g. 0.15 = 15%).
            option_type: 'CALL' or 'PUT'.
            rate: Risk-free interest rate (decimal, default 0.0).

        Returns:
            Dictionary with keys: delta, gamma, theta, vega, rho.
        """
        if self._use_quantlib and self._quantlib_pricer is not None:
            return self._quantlib_pricer.compute_greeks(
                spot, strike, rate, iv, tte, option_type
            )
        if tte <= 0.0:
            return self._zero_greeks()
        if iv <= 0.0 or spot <= 0.0 or strike <= 0.0:
            return self._zero_greeks()

        is_call = option_type.upper() == "CALL"
        d1, d2 = _d1_d2(spot, strike, tte, iv, rate)
        disc = math.exp(-rate * tte)

        n_d1 = _norm_cdf(d1)
        n_d2 = _norm_cdf(d2)
        n_neg_d1 = _norm_cdf(-d1)
        n_neg_d2 = _norm_cdf(-d2)
        n_prime_d1 = _norm_pdf(d1)

        # --- Delta ---
        if is_call:
            delta = disc * n_d1
        else:
            delta = disc * (n_d1 - 1.0)

        # --- Gamma (same for call and put) ---
        if spot * iv * math.sqrt(tte) > 0:
            gamma = (disc * n_prime_d1) / (spot * iv * math.sqrt(tte))
        else:
            gamma = 0.0

        # --- Vega (per 1% IV change) ---
        vega = disc * spot * n_prime_d1 * math.sqrt(tte) / 100.0

        # --- Theta (per calendar day) ---
        base_theta = -(spot * n_prime_d1 * iv) / (2.0 * math.sqrt(tte))
        if is_call:
            theta = base_theta + rate * (spot * n_d1 - strike * n_d2)
        else:
            theta = base_theta - rate * (spot * n_neg_d1 - strike * n_neg_d2)
        theta /= 365.0

        # --- Rho (per 1% rate change) ---
        if is_call:
            rho = tte * strike * disc * n_d2 / 100.0
        else:
            rho = -tte * strike * disc * n_neg_d2 / 100.0

        return {
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "rho": rho,
        }

    def calculate_delta(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        option_type: OptionType,
        rate: float = 0.0,
    ) -> float:
        """Compute option delta only."""
        return self.calculate_all(spot, strike, tte, iv, option_type, rate)["delta"]

    def calculate_gamma(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        rate: float = 0.0,
    ) -> float:
        """Compute option gamma (same for call and put)."""
        if tte <= 0.0 or iv <= 0.0 or spot <= 0.0 or strike <= 0.0:
            return 0.0
        d1, _ = _d1_d2(spot, strike, tte, iv, rate)
        disc = math.exp(-rate * tte)
        n_prime_d1 = _norm_pdf(d1)
        if spot * iv * math.sqrt(tte) > 0:
            return (disc * n_prime_d1) / (spot * iv * math.sqrt(tte))
        return 0.0

    def calculate_theta(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        option_type: OptionType,
        rate: float = 0.0,
    ) -> float:
        """Compute option theta (daily decay)."""
        return self.calculate_all(spot, strike, tte, iv, option_type, rate)["theta"]

    def calculate_vega(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        rate: float = 0.0,
    ) -> float:
        """Compute option vega (per 1% IV change)."""
        if tte <= 0.0 or iv <= 0.0 or spot <= 0.0:
            return 0.0
        d1, _ = _d1_d2(spot, strike, tte, iv, rate)
        disc = math.exp(-rate * tte)
        n_prime_d1 = _norm_pdf(d1)
        return disc * spot * n_prime_d1 * math.sqrt(tte) / 100.0

    def calculate_option_price(
        self,
        spot: float,
        strike: float,
        tte: float,
        iv: float,
        option_type: OptionType,
        rate: float = 0.0,
    ) -> float:
        """Compute the Black-76 option premium."""
        if self._use_quantlib and self._quantlib_pricer is not None:
            return self._quantlib_pricer.price_european(
                spot, strike, rate, iv, tte, option_type
            )
        if tte <= 0.0 or iv <= 0.0 or spot <= 0.0 or strike <= 0.0:
            return 0.0
        is_call = option_type.upper() == "CALL"
        d1, d2 = _d1_d2(spot, strike, tte, iv, rate)
        disc = math.exp(-rate * tte)
        if is_call:
            return disc * (spot * _norm_cdf(d1) - strike * _norm_cdf(d2))
        return disc * (strike * _norm_cdf(-d2) - spot * _norm_cdf(-d1))

    @staticmethod
    def _zero_greeks() -> dict[str, float]:
        """Return a zeroed greeks dict."""
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
