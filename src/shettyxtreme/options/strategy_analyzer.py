"""Options strategy analyzer and payoff computation.

Evaluates 9 standard options strategies.
All computations are pure - no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Callable

StrategyName = Literal[
    "LONG_CALL",
    "LONG_PUT",
    "SHORT_CALL",
    "SHORT_PUT",
    "BULL_CALL_SPREAD",
    "BEAR_PUT_SPREAD",
    "IRON_CONDOR",
    "STRADDLE",
    "STRANGLE",
]


@dataclass
class StrategyParams:
    """Parameters defining an options strategy."""
    name: StrategyName
    long_strike: float = 0.0
    short_strike: float = 0.0
    long_strike2: float = 0.0
    short_strike2: float = 0.0
    premium_long: float = 0.0
    premium_short: float = 0.0
    premium_long2: float = 0.0
    premium_short2: float = 0.0
    spot: float = 0.0


@dataclass
class StrategyAnalysis:
    """Comprehensive analysis of an options strategy."""
    name: StrategyName
    display_name: str
    max_profit: float
    max_loss: float
    breakevens: list[float]
    probability_of_profit: float
    net_premium: float
    is_credit: bool
    payoff_at_expiry: list[tuple[float, float]]
    params: StrategyParams = field(default_factory=lambda: StrategyParams(name="LONG_CALL"))


class StrategyAnalyzer:
    """Evaluate standard options strategies."""

    PAYOFF_RANGE_MULT = 0.15
    PAYOFF_POINTS = 50

    STRATEGY_DISPLAY_NAMES = {
        "LONG_CALL": "Long Call",
        "LONG_PUT": "Long Put",
        "SHORT_CALL": "Short Call",
        "SHORT_PUT": "Short Put",
        "BULL_CALL_SPREAD": "Bull Call Spread",
        "BEAR_PUT_SPREAD": "Bear Put Spread",
        "IRON_CONDOR": "Iron Condor",
        "STRADDLE": "Straddle",
        "STRANGLE": "Strangle",
    }

    def analyze(self, params: StrategyParams, iv: float = 0.0, tte: float = 0.0) -> StrategyAnalysis:
        method_name = f"_analyze_{params.name.lower()}"
        analyzer = getattr(self, method_name, None)
        if analyzer is None:
            raise ValueError(f"Unknown strategy: {params.name}")
        return analyzer(params, iv, tte)

    @staticmethod
    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _estimate_pop(self, breakevens, spot, iv, tte, is_credit):
        if not breakevens or iv <= 0.0 or tte <= 0.0:
            return 0.5
        sigma = spot * iv * math.sqrt(tte)
        if sigma <= 0.0:
            return 0.5
        if len(breakevens) == 1:
            be = breakevens[0]
            prob = self._norm_cdf(abs(be - spot) / sigma)
            return prob if is_credit else 1.0 - prob
        elif len(breakevens) == 2:
            bl, bh = sorted(breakevens)
            return abs(self._norm_cdf((bh - spot) / sigma) - self._norm_cdf((bl - spot) / sigma))
        return 0.5

    def _build_payoff(self, spot, payoff_fn, num_points=50):
        spread = spot * self.PAYOFF_RANGE_MULT
        low = spot - spread
        high = spot + spread
        step = (high - low) / (num_points - 1) if num_points > 1 else 0
        return [(low + i * step, payoff_fn(low + i * step)) for i in range(num_points)]

    def _analyze_long_call(self, p, iv, tte):
        K, prem, spot = p.long_strike, p.premium_long, p.spot
        be = [K + prem]
        pop = self._estimate_pop(be, spot, iv, tte, False)
        fn = lambda x: max(x - K, 0) - prem
        return StrategyAnalysis(name="LONG_CALL", display_name="Long Call",
            max_profit=float("inf"), max_loss=prem, breakevens=be,
            probability_of_profit=pop, net_premium=-prem, is_credit=False,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_long_put(self, p, iv, tte):
        K, prem, spot = p.long_strike, p.premium_long, p.spot
        be = [K - prem]
        pop = self._estimate_pop(be, spot, iv, tte, False)
        fn = lambda x: max(K - x, 0) - prem
        return StrategyAnalysis(name="LONG_PUT", display_name="Long Put",
            max_profit=K - prem, max_loss=prem, breakevens=be,
            probability_of_profit=pop, net_premium=-prem, is_credit=False,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_short_call(self, p, iv, tte):
        K = p.short_strike or p.long_strike
        prem = p.premium_short or p.premium_long
        spot = p.spot
        be = [K + prem]
        pop = self._estimate_pop(be, spot, iv, tte, True)
        fn = lambda x: prem - max(x - K, 0)
        return StrategyAnalysis(name="SHORT_CALL", display_name="Short Call",
            max_profit=prem, max_loss=float("inf"), breakevens=be,
            probability_of_profit=pop, net_premium=prem, is_credit=True,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_short_put(self, p, iv, tte):
        K = p.short_strike or p.long_strike
        prem = p.premium_short or p.premium_long
        spot = p.spot
        be = [K - prem]
        pop = self._estimate_pop(be, spot, iv, tte, True)
        fn = lambda x: prem - max(K - x, 0)
        return StrategyAnalysis(name="SHORT_PUT", display_name="Short Put",
            max_profit=prem, max_loss=K - prem, breakevens=be,
            probability_of_profit=pop, net_premium=prem, is_credit=True,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_bull_call_spread(self, p, iv, tte):
        K1, K2 = p.long_strike, p.short_strike
        nd = p.premium_long - p.premium_short
        spot, w = p.spot, K2 - K1
        be = [K1 + nd]
        pop = self._estimate_pop(be, spot, iv, tte, False)
        fn = lambda x: max(x - K1, 0) - max(x - K2, 0) - nd
        return StrategyAnalysis(name="BULL_CALL_SPREAD", display_name="Bull Call Spread",
            max_profit=max(0.0, w - nd), max_loss=nd, breakevens=be,
            probability_of_profit=pop, net_premium=-nd, is_credit=False,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_bear_put_spread(self, p, iv, tte):
        K1, K2 = p.long_strike, p.short_strike
        nd = p.premium_long - p.premium_short
        spot, w = p.spot, K1 - K2
        be = [K1 - nd]
        pop = self._estimate_pop(be, spot, iv, tte, False)
        fn = lambda x: max(K1 - x, 0) - max(K2 - x, 0) - nd
        return StrategyAnalysis(name="BEAR_PUT_SPREAD", display_name="Bear Put Spread",
            max_profit=max(0.0, w - nd), max_loss=nd, breakevens=be,
            probability_of_profit=pop, net_premium=-nd, is_credit=False,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_iron_condor(self, p, iv, tte):
        nc = (p.premium_short + (p.premium_short2 or 0.0)
              - p.premium_long - (p.premium_long2 or 0.0))
        spot = p.spot
        w = max(p.short_strike - p.long_strike, p.long_strike2 - p.short_strike2)
        be = [p.short_strike + nc, p.short_strike2 - nc]
        pop = self._estimate_pop(be, spot, iv, tte, True)
        fn = lambda x: (max(p.short_strike - x, 0) - max(p.long_strike - x, 0)
                        + max(x - p.short_strike2, 0) - max(x - p.long_strike2, 0) + nc)
        return StrategyAnalysis(name="IRON_CONDOR", display_name="Iron Condor",
            max_profit=nc, max_loss=max(0.0, w - nc), breakevens=be,
            probability_of_profit=pop, net_premium=nc, is_credit=True,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_straddle(self, p, iv, tte):
        tp = p.premium_long + p.premium_short
        spot, K = p.spot, p.long_strike
        be = [K - tp, K + tp]
        pop = self._estimate_pop(be, spot, iv, tte, False)
        fn = lambda x: max(x - K, 0) + max(K - x, 0) - tp
        return StrategyAnalysis(name="STRADDLE", display_name="Straddle",
            max_profit=float("inf"), max_loss=tp, breakevens=be,
            probability_of_profit=pop, net_premium=-tp, is_credit=False,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    def _analyze_strangle(self, p, iv, tte):
        spot = p.spot
        Kc = max(p.short_strike or p.long_strike, p.long_strike2 or p.long_strike)
        Kp = min(p.short_strike or p.long_strike, p.long_strike2 or p.long_strike)
        tp = p.premium_long + p.premium_short
        be = [Kp - tp, Kc + tp]
        pop = self._estimate_pop(be, spot, iv, tte, False)
        fn = lambda x: max(x - Kc, 0) + max(Kp - x, 0) - tp
        return StrategyAnalysis(name="STRANGLE", display_name="Strangle",
            max_profit=float("inf"), max_loss=tp, breakevens=be,
            probability_of_profit=pop, net_premium=-tp, is_credit=False,
            payoff_at_expiry=self._build_payoff(spot, fn), params=p)

    @classmethod
    def supported_strategies(cls):
        return ["LONG_CALL","LONG_PUT","SHORT_CALL","SHORT_PUT",
                "BULL_CALL_SPREAD","BEAR_PUT_SPREAD",
                "IRON_CONDOR","STRADDLE","STRANGLE"]

    @classmethod
    def display_name(cls, name):
        return cls.STRATEGY_DISPLAY_NAMES.get(name, name.replace("_", " ").title())
