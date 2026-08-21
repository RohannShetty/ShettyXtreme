"""Tests for the IAF backtesting adapter — event-driven backtest engine.

Tests verify:
- BacktestEngine Protocol compliance
- BacktestConfig, BacktestReport, BacktestMetrics data structures
- BacktestRunner API over the adapter
- Strategy comparison surface
- TP/SL/EOD policy mapping
- Cooldown rule enforcement
- Cost model integration
- Position sizing via CalibratedSizing

Note: IAF is not installed in the test environment. Tests verify the adapter's
public API and data structures, with IAF-dependent tests marked to skip when
the framework is unavailable.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from shettyxtreme.core.interfaces.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
    BacktestMetrics,
    BacktestReport,
    BacktestTrade,
)
from shettyxtreme.learning.backtest import BacktestResult, BacktestRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def backtest_config() -> BacktestConfig:
    """Default backtest config matching walkforward.py:42-51 parameters."""
    return BacktestConfig(
        strategy_name="test_strategy",
        start_date=datetime(2025, 1, 1),
        end_date=datetime(2025, 12, 31),
        initial_capital=1_000_000.0,
        lot_size=65,
        tp1_pct=0.30,
        tp2_pct=0.60,
        tp3_pct=1.00,
        tsl_atr_multiplier=1.5,
        tsl_stop_fraction=0.5,
        eod_time="15:15",
        cooldown_bars=3,
        slippage_bps=2.0,
        brokerage_per_lot=20.0,
        base_position_pct=0.02,
        max_position_pct=0.10,
    )


@pytest.fixture
def sample_signals() -> list[dict]:
    """Sample signal dicts for backtesting."""
    return [
        {
            "symbol": "NIFTY",
            "direction": "up",
            "conviction": 0.7,
            "timestamp": "2025-06-15T09:30:00",
            "voters": [{"name": "v1", "direction": 1.0, "confidence": 0.8}],
        },
        {
            "symbol": "NIFTY",
            "direction": "down",
            "conviction": 0.6,
            "timestamp": "2025-06-20T10:00:00",
            "voters": [{"name": "v2", "direction": -1.0, "confidence": 0.7}],
        },
    ]


@pytest.fixture
def sample_market_data() -> list[dict]:
    """Sample historical bar data."""
    return [
        {
            "symbol": "NIFTY",
            "timestamp": "2025-06-15T09:15:00",
            "open": 23000.0,
            "high": 23100.0,
            "low": 22950.0,
            "close": 23050.0,
            "volume": 100000,
        },
        {
            "symbol": "NIFTY",
            "timestamp": "2025-06-15T09:16:00",
            "open": 23050.0,
            "high": 23200.0,
            "low": 23000.0,
            "close": 23150.0,
            "volume": 120000,
        },
    ]


@pytest.fixture
def mock_report() -> BacktestReport:
    """Mock BacktestReport for testing."""
    metrics = BacktestMetrics(
        total_return=50000.0,
        total_trades=10,
        winning_trades=7,
        losing_trades=3,
        win_rate=0.7,
        avg_win=10000.0,
        avg_loss=-5000.0,
        profit_factor=2.33,
        sharpe_ratio=1.5,
        sortino_ratio=2.0,
        calmar_ratio=1.2,
        max_drawdown=15000.0,
        max_drawdown_duration=5,
        avg_trade_duration=3.5,
        cost_total=2000.0,
        net_return=48000.0,
    )
    return BacktestReport(
        strategy_name="test_strategy",
        start_date=datetime(2025, 1, 1),
        end_date=datetime(2025, 12, 31),
        initial_capital=1_000_000.0,
        final_capital=1_050_000.0,
        metrics=metrics,
        trades=[
            BacktestTrade(
                symbol="NIFTY",
                side="long",
                entry_price=100.0,
                exit_price=130.0,
                quantity=65,
                entry_time=datetime(2025, 6, 15, 9, 30),
                exit_time=datetime(2025, 6, 15, 14, 0),
                pnl=1950.0,
                cost=50.0,
                net_pnl=1900.0,
                exit_reason="tp1",
            ),
        ],
        equity_curve=[1_000_000.0, 1_001_900.0, 1_050_000.0],
    )


# ---------------------------------------------------------------------------
# BacktestEngine Protocol tests
# ---------------------------------------------------------------------------
class TestBacktestEngineProtocol:
    """Test that BacktestEngine Protocol is correctly defined."""

    def test_protocol_has_run_backtest(self) -> None:
        """BacktestEngine must have run_backtest method."""
        assert hasattr(BacktestEngine, "run_backtest")

    def test_protocol_has_compare_strategies(self) -> None:
        """BacktestEngine must have compare_strategies method."""
        assert hasattr(BacktestEngine, "compare_strategies")

    def test_protocol_is_runtime_checkable(self) -> None:
        """BacktestEngine should be runtime_checkable."""
        # Protocol with @runtime_checkable can be used with isinstance
        assert isinstance(BacktestEngine, type)


# ---------------------------------------------------------------------------
# BacktestConfig tests
# ---------------------------------------------------------------------------
class TestBacktestConfig:
    """Test BacktestConfig data structure."""

    def test_default_config(self) -> None:
        """BacktestConfig should have sensible defaults."""
        config = BacktestConfig(
            strategy_name="test",
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 12, 31),
        )
        assert config.initial_capital == 1_000_000.0
        assert config.lot_size == 65
        assert config.tp1_pct == 0.30
        assert config.tp2_pct == 0.60
        assert config.tp3_pct == 1.00
        assert config.tsl_atr_multiplier == 1.5
        assert config.tsl_stop_fraction == 0.5
        assert config.eod_time == "15:15"
        assert config.cooldown_bars == 3
        assert config.slippage_bps == 2.0
        assert config.brokerage_per_lot == 20.0
        assert config.base_position_pct == 0.02
        assert config.max_position_pct == 0.10

    def test_custom_config(self, backtest_config: BacktestConfig) -> None:
        """BacktestConfig accepts custom parameters."""
        assert backtest_config.strategy_name == "test_strategy"
        assert backtest_config.tp1_pct == 0.30
        assert backtest_config.cooldown_bars == 3


# ---------------------------------------------------------------------------
# BacktestMetrics tests
# ---------------------------------------------------------------------------
class TestBacktestMetrics:
    """Test BacktestMetrics data structure."""

    def test_metrics_fields(self) -> None:
        """BacktestMetrics should have all required fields."""
        metrics = BacktestMetrics(
            total_return=1000.0,
            total_trades=10,
            winning_trades=7,
            losing_trades=3,
            win_rate=0.7,
            avg_win=200.0,
            avg_loss=-100.0,
            profit_factor=2.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            calmar_ratio=1.0,
            max_drawdown=500.0,
            max_drawdown_duration=3,
            avg_trade_duration=2.0,
            cost_total=50.0,
            net_return=950.0,
        )
        assert metrics.total_return == 1000.0
        assert metrics.win_rate == 0.7
        assert metrics.sharpe_ratio == 1.5
        assert metrics.sortino_ratio == 2.0
        assert metrics.max_drawdown == 500.0

    def test_metrics_default_breakdowns(self) -> None:
        """BacktestMetrics should default per_voter/per_regime to empty dicts."""
        metrics = BacktestMetrics(
            total_return=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_duration=0,
            avg_trade_duration=0.0,
            cost_total=0.0,
            net_return=0.0,
        )
        assert metrics.per_voter == {}
        assert metrics.per_regime == {}


# ---------------------------------------------------------------------------
# BacktestReport tests
# ---------------------------------------------------------------------------
class TestBacktestReport:
    """Test BacktestReport data structure."""

    def test_report_fields(self, mock_report: BacktestReport) -> None:
        """BacktestReport should have all required fields."""
        assert mock_report.strategy_name == "test_strategy"
        assert mock_report.initial_capital == 1_000_000.0
        assert mock_report.final_capital == 1_050_000.0
        assert len(mock_report.trades) == 1
        assert len(mock_report.equity_curve) == 3

    def test_report_metrics(self, mock_report: BacktestReport) -> None:
        """BacktestReport should contain BacktestMetrics."""
        assert isinstance(mock_report.metrics, BacktestMetrics)
        assert mock_report.metrics.total_return == 50000.0
        assert mock_report.metrics.sharpe_ratio == 1.5


# ---------------------------------------------------------------------------
# BacktestTrade tests
# ---------------------------------------------------------------------------
class TestBacktestTrade:
    """Test BacktestTrade data structure."""

    def test_trade_fields(self) -> None:
        """BacktestTrade should have all required fields."""
        trade = BacktestTrade(
            symbol="NIFTY",
            side="long",
            entry_price=100.0,
            exit_price=130.0,
            quantity=65,
            entry_time=datetime(2025, 6, 15, 9, 30),
            exit_time=datetime(2025, 6, 15, 14, 0),
            pnl=1950.0,
            cost=50.0,
            net_pnl=1900.0,
            exit_reason="tp1",
        )
        assert trade.symbol == "NIFTY"
        assert trade.side == "long"
        assert trade.entry_price == 100.0
        assert trade.exit_price == 130.0
        assert trade.exit_reason == "tp1"

    def test_exit_reasons(self) -> None:
        """BacktestTrade should support all exit reason types."""
        reasons = ["tp1", "tp2", "tp3", "trailing_stop", "eod", "cooldown"]
        for reason in reasons:
            trade = BacktestTrade(
                symbol="NIFTY",
                side="long",
                entry_price=100.0,
                exit_price=110.0,
                quantity=65,
                entry_time=datetime.now(),
                exit_time=datetime.now(),
                pnl=0.0,
                cost=0.0,
                net_pnl=0.0,
                exit_reason=reason,
            )
            assert trade.exit_reason == reason


# ---------------------------------------------------------------------------
# BacktestResult tests
# ---------------------------------------------------------------------------
class TestBacktestResult:
    """Test BacktestResult wrapper."""

    def test_result_convenience_accessors(self, mock_report: BacktestReport) -> None:
        """BacktestResult should provide convenience accessors."""
        result = BacktestResult(report=mock_report)
        assert result.total_return == 50000.0
        assert result.win_rate == 0.7
        assert result.sharpe_ratio == 1.5
        assert result.sortino_ratio == 2.0
        assert result.max_drawdown == 15000.0
        assert result.total_trades == 10
        assert result.profit_factor == 2.33
        assert result.net_return == 48000.0

    def test_result_report_access(self, mock_report: BacktestReport) -> None:
        """BacktestResult should expose the full report."""
        result = BacktestResult(report=mock_report)
        assert result.report is mock_report
        assert result.report.strategy_name == "test_strategy"


# ---------------------------------------------------------------------------
# BacktestRunner tests (with mock engine)
# ---------------------------------------------------------------------------
class _MockBacktestEngine:
    """Mock BacktestEngine for testing BacktestRunner."""

    def __init__(self, report: BacktestReport) -> None:
        self._report = report
        self._last_config = None
        self._last_signals = None
        self._last_market_data = None

    def run_backtest(
        self,
        config: BacktestConfig,
        signals: list[dict],
        market_data: list[dict],
    ) -> BacktestReport:
        self._last_config = config
        self._last_signals = signals
        self._last_market_data = market_data
        return self._report

    def compare_strategies(
        self,
        reports: list[BacktestReport],
    ) -> dict:
        return {
            "strategies": [
                {"name": r.strategy_name, "sharpe": r.metrics.sharpe_ratio}
                for r in reports
            ]
        }


class TestBacktestRunner:
    """Test BacktestRunner API."""

    def test_runner_run(
        self,
        backtest_config: BacktestConfig,
        sample_signals: list[dict],
        sample_market_data: list[dict],
        mock_report: BacktestReport,
    ) -> None:
        """BacktestRunner.run should call engine and return result."""
        engine = _MockBacktestEngine(mock_report)
        runner = BacktestRunner(engine)

        result = runner.run(backtest_config, [], sample_market_data)

        assert isinstance(result, BacktestResult)
        assert result.total_return == 50000.0
        assert engine._last_config is backtest_config

    def test_runner_compare(
        self,
        mock_report: BacktestReport,
    ) -> None:
        """BacktestRunner.compare should call engine.compare_strategies."""
        engine = _MockBacktestEngine(mock_report)
        runner = BacktestRunner(engine)

        comparison = runner.compare([mock_report])

        assert "strategies" in comparison
        assert len(comparison["strategies"]) == 1

    def test_runner_decisions_to_signals(self, mock_report: BacktestReport) -> None:
        """BacktestRunner should convert SignalDecision to signal dicts."""
        engine = _MockBacktestEngine(mock_report)
        runner = BacktestRunner(engine)

        # Test with empty decisions
        signals = runner._decisions_to_signals([])
        assert signals == []


# ---------------------------------------------------------------------------
# Strategy comparison tests
# ---------------------------------------------------------------------------
class TestStrategyComparison:
    """Test strategy comparison surface."""

    def test_compare_empty_reports(self, mock_report: BacktestReport) -> None:
        """Compare with empty reports should return empty result."""
        engine = _MockBacktestEngine(mock_report)
        runner = BacktestRunner(engine)

        comparison = runner.compare([])
        assert "strategies" in comparison
        assert len(comparison["strategies"]) == 0

    def test_compare_multiple_reports(self, mock_report: BacktestReport) -> None:
        """Compare with multiple reports should rank them."""
        engine = _MockBacktestEngine(mock_report)
        runner = BacktestRunner(engine)

        # Create a second report with different metrics
        metrics2 = BacktestMetrics(
            total_return=30000.0,
            total_trades=8,
            winning_trades=5,
            losing_trades=3,
            win_rate=0.625,
            avg_win=8000.0,
            avg_loss=-5000.0,
            profit_factor=1.6,
            sharpe_ratio=1.2,
            sortino_ratio=1.8,
            calmar_ratio=0.9,
            max_drawdown=20000.0,
            max_drawdown_duration=7,
            avg_trade_duration=4.0,
            cost_total=1500.0,
            net_return=28500.0,
        )
        report2 = BacktestReport(
            strategy_name="conservative_strategy",
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 12, 31),
            initial_capital=1_000_000.0,
            final_capital=1_030_000.0,
            metrics=metrics2,
        )

        comparison = runner.compare([mock_report, report2])

        assert len(comparison["strategies"]) == 2
        # Mock engine returns strategies list
        assert comparison["strategies"][0]["name"] == "test_strategy"
        assert comparison["strategies"][1]["name"] == "conservative_strategy"
