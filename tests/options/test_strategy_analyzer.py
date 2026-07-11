"""Tests for StrategyAnalyzer.

Verifies:
- Long Call: max_loss = premium
- Bull Call Spread: max_profit = width - net_debit
- Iron Condor: max_profit = net_credit
- All 9 strategies supported
"""

from __future__ import annotations

import pytest
from shettyxtreme.options.strategy_analyzer import (
    StrategyAnalyzer, StrategyParams, StrategyAnalysis,
)


class TestStrategyAnalyzer:
    """Suite for StrategyAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> StrategyAnalyzer:
        return StrategyAnalyzer()

    def _nearest_payoff(self, payoffs, target_price):
        """Find payoff for the price point nearest to target_price."""
        return min(payoffs, key=lambda x: abs(x[0] - target_price))[1]

    # -- Long Call ------------------------------------------------------

    def test_long_call_max_loss(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="LONG_CALL", long_strike=100.0, premium_long=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.max_loss == 5.0

    def test_long_call_max_profit(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="LONG_CALL", long_strike=100.0, premium_long=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.max_profit == float("inf")

    def test_long_call_breakeven(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="LONG_CALL", long_strike=100.0, premium_long=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.breakevens == [105.0]

    def test_long_call_is_debit(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="LONG_CALL", long_strike=100.0, premium_long=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.is_credit is False
        assert a.net_premium == -5.0

    def test_long_call_payoff(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="LONG_CALL", long_strike=100.0, premium_long=5.0, spot=100.0)
        a = analyzer.analyze(p)
        # Find payoff nearest to strike price
        pnl = self._nearest_payoff(a.payoff_at_expiry, 100.0)
        assert pnl == pytest.approx(-5.0, abs=0.5)

    # -- Long Put -------------------------------------------------------

    def test_long_put_max_loss(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="LONG_PUT", long_strike=100.0, premium_long=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.max_loss == 5.0

    # -- Bull Call Spread -----------------------------------------------

    def test_bull_call_spread(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="BULL_CALL_SPREAD", long_strike=100.0, short_strike=110.0, premium_long=5.0, premium_short=2.0, spot=105.0)
        a = analyzer.analyze(p)
        assert a.max_profit == 7.0
        assert a.max_loss == 3.0
        assert a.breakevens == [103.0]

    # -- Bear Put Spread ------------------------------------------------

    def test_bear_put_spread(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="BEAR_PUT_SPREAD", long_strike=110.0, short_strike=100.0, premium_long=5.0, premium_short=2.0, spot=105.0)
        a = analyzer.analyze(p)
        assert a.max_loss == 3.0

    # -- Iron Condor ----------------------------------------------------

    def test_iron_condor(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="IRON_CONDOR", long_strike=90.0, short_strike=100.0, short_strike2=110.0, long_strike2=120.0, premium_long=2.0, premium_short=5.0, premium_long2=2.0, premium_short2=5.0, spot=105.0)
        a = analyzer.analyze(p)
        assert a.max_profit == 6.0
        assert a.is_credit is True
        assert a.net_premium > 0
        assert a.max_loss == 4.0

    # -- Short Options --------------------------------------------------

    def test_short_call(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="SHORT_CALL", short_strike=100.0, premium_short=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.max_profit == 5.0
        assert a.is_credit is True

    def test_short_put(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="SHORT_PUT", short_strike=100.0, premium_short=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.max_loss == 95.0

    # -- Straddle / Strangle --------------------------------------------

    def test_straddle(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="STRADDLE", long_strike=100.0, short_strike=100.0, premium_long=5.0, premium_short=6.0, spot=100.0)
        a = analyzer.analyze(p)
        assert a.max_loss == 11.0

    def test_strangle(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="STRANGLE", long_strike=100.0, short_strike2=120.0, premium_long=5.0, premium_short=4.0, spot=110.0)
        a = analyzer.analyze(p)
        assert len(a.breakevens) == 2

    # -- Meta -----------------------------------------------------------

    def test_supported(self) -> None:
        assert len(StrategyAnalyzer.supported_strategies()) == 9

    def test_display_name(self) -> None:
        assert StrategyAnalyzer.display_name("LONG_CALL") == "Long Call"
        assert StrategyAnalyzer.display_name("IRON_CONDOR") == "Iron Condor"

    def test_unknown(self, analyzer: StrategyAnalyzer) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            analyzer.analyze(StrategyParams(name="UNKNOWN"))

    def test_payoff_points(self, analyzer: StrategyAnalyzer) -> None:
        p = StrategyParams(name="LONG_CALL", long_strike=100.0, premium_long=5.0, spot=100.0)
        a = analyzer.analyze(p)
        assert len(a.payoff_at_expiry) == 50

    def test_all_strategies(self, analyzer: StrategyAnalyzer) -> None:
        base = {"long_strike": 100.0, "short_strike": 110.0, "short_strike2": 120.0, "long_strike2": 130.0, "premium_long": 5.0, "premium_short": 3.0, "premium_long2": 2.0, "premium_short2": 4.0, "spot": 105.0}
        for name in StrategyAnalyzer.supported_strategies():
            a = analyzer.analyze(StrategyParams(name=name, **base))
            assert isinstance(a, StrategyAnalysis)
            assert a.name == name
