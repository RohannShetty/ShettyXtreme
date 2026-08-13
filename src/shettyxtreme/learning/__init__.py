"""Learning loop — outcome tracking, voter quality, MFE/MAE, walkforward,
backtest, analytics, and calibration.

Wave 4 (execution learning) plus Wave 6 (calibration) owning the learning/
package entirely. First-party code: depends only on core/, intelligence/
interfaces, and other learning/ modules.

Backtest module (Wave 8) provides event-driven backtesting via IAF adapter.
"""
from __future__ import annotations

from shettyxtreme.learning.analytics import (
    AnalyticsEngine,
    CostAnalysis,
    PerformanceSummary,
    RegimeStats,
    VoterContribution,
    WinLossCount,
)
from shettyxtreme.learning.backtest import BacktestResult, BacktestRunner
from shettyxtreme.learning.calibration import CalibrationCurve, CalibrationPoint
from shettyxtreme.learning.mfe_mae import MfeMaeCalculator, MfeMaeRecord
from shettyxtreme.learning.outcome_tracker import (
    OutcomeLabel,
    OutcomeTracker,
    SignalDecision,
)
from shettyxtreme.learning.voter_quality import VoterQualityReport, VoterQualityTracker
from shettyxtreme.learning.walkforward import WalkforwardEvaluator, WalkforwardResult

__all__ = [
    "AnalyticsEngine",
    "BacktestResult",
    "BacktestRunner",
    "CostAnalysis",
    "PerformanceSummary",
    "RegimeStats",
    "VoterContribution",
    "WinLossCount",
    "CalibrationCurve",
    "CalibrationPoint",
    "MfeMaeCalculator",
    "MfeMaeRecord",
    "OutcomeLabel",
    "OutcomeTracker",
    "SignalDecision",
    "VoterQualityReport",
    "VoterQualityTracker",
    "WalkforwardEvaluator",
    "WalkforwardResult",
]
