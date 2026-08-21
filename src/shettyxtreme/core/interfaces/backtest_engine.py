"""BacktestEngine protocol — interface for backtesting adapters.

FR-005: Protocol defining the backtest engine contract. Implementations live
in integration/external/ (FR-004 ACL). Nothing above integration imports the
concrete backtest framework.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class BacktestTrade:
    """A single trade executed during a backtest."""

    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    exit_price: float
    quantity: int
    entry_time: datetime
    exit_time: datetime
    pnl: float
    cost: float
    net_pnl: float
    exit_reason: str  # "tp1", "tp2", "tp3", "trailing_stop", "eod", "cooldown"


@dataclass
class BacktestMetrics:
    """Aggregated backtest performance metrics."""

    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # bars
    avg_trade_duration: float  # bars
    cost_total: float
    net_return: float
    per_voter: dict[str, dict] = field(default_factory=dict)
    per_regime: dict[str, dict] = field(default_factory=dict)


@dataclass
class BacktestReport:
    """Full backtest report with trades and metrics."""

    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    metrics: BacktestMetrics
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""

    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float = 1_000_000.0
    lot_size: int = 65  # NIFTY default
    # TP/SL policy (from walkforward.py:42-51)
    tp1_pct: float = 0.30
    tp2_pct: float = 0.60
    tp3_pct: float = 1.00
    tsl_atr_multiplier: float = 1.5
    tsl_stop_fraction: float = 0.5
    eod_time: str = "15:15"
    # Cooldown
    cooldown_bars: int = 3
    # Cost model
    slippage_bps: float = 2.0
    brokerage_per_lot: float = 20.0
    # Position sizing
    base_position_pct: float = 0.02  # 2% of portfolio
    max_position_pct: float = 0.10  # 10% cap


@runtime_checkable
class BacktestEngine(Protocol):
    """Protocol for backtesting engines.

    Implementations translate ShettyXtreme signal/decision inputs into
    backtest framework calls, map cost models, sizing, and TP/SL policy.
    """

    def run_backtest(
        self,
        config: BacktestConfig,
        signals: list[dict],
        market_data: list[dict],
    ) -> BacktestReport:
        """Run a backtest with the given config, signals, and market data.

        Args:
            config: Backtest configuration (dates, capital, TP/SL policy).
            signals: List of signal decisions (from OutcomeTracker).
            market_data: Historical bar data (from DuckDB/Fyers).

        Returns:
            BacktestReport with metrics, trades, and equity curve.
        """
        ...

    def compare_strategies(
        self,
        reports: list[BacktestReport],
    ) -> dict:
        """Compare multiple backtest reports side-by-side.

        Args:
            reports: List of BacktestReport objects to compare.

        Returns:
            Comparison dict with per-strategy metrics and rankings.
        """
        ...
