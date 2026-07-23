"""Options intelligence module for ShettyXtreme.

Provides Greeks computation, IV rank tracking, strategy analysis,
and open interest monitoring.
"""

from .greeks import GreeksCalculator
from .iv_rank import IVRankCalculator, IVRankResult, IVSnapshot
from .strategy_analyzer import StrategyAnalyzer, StrategyAnalysis, StrategyParams
from .oi_tracker import OITracker, OIAlert, OISnapshot
try:
    from .quantlib_pricer import QuantLibPricer
except ImportError:
    QuantLibPricer = None  # type: ignore

__all__ = [
    "GreeksCalculator",
    "IVRankCalculator",
    "IVRankResult",
    "IVSnapshot",
    "StrategyAnalyzer",
    "StrategyAnalysis",
    "StrategyParams",
    "OITracker",
    "OIAlert",
    "OISnapshot",
    "QuantLibPricer",
]
