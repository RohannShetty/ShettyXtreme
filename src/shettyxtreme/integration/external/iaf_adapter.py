"""IAF Adapter — BacktestEngine implementation using investing-algorithm-framework.

FR-004: This is the ONLY file in src/ that imports investing_algorithm_framework.
FR-005: Implements the BacktestEngine Protocol from core/interfaces.

Translates ShettyXtreme signal/decision inputs into IAF TradingStrategy,
maps cost model to TradingCost, sizing to PositionSize, TP/SL policy to
TakeProfitRule/StopLossRule, and adds CooldownRules.
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any

from shettyxtreme.core.interfaces.backtest_engine import (
    BacktestConfig,
    BacktestMetrics,
    BacktestReport,
    BacktestTrade,
)
from shettyxtreme.core.risk.cost_model import CostBreakdown, compute_cost

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IAF import guard — only import inside this module
# ---------------------------------------------------------------------------
try:
    from investing_algorithm_framework import (
        App,
        TradingStrategy,
        PositionSize,
        ScalingRule,
        StopLossRule,
        TakeProfitRule,
        CooldownRule,
        TradingCost,
        MarketDataType,
    )
    _IAF_AVAILABLE = True
except ImportError:
    _IAF_AVAILABLE = False
    logger.warning(
        "investing_algorithm_framework not installed; "
        "IAF backtest adapter will raise on use"
    )


class IAFBacktestError(Exception):
    """Raised when IAF backtest operations fail."""


class IAFBacktestAdapter:
    """BacktestEngine implementation backed by IAF.

    Translates ShettyXtreme signals → IAF TradingStrategy, runs event-driven
    backtests, and returns BacktestReport.
    """

    def __init__(self) -> None:
        if not _IAF_AVAILABLE:
            raise IAFBacktestError(
                "investing_algorithm_framework is not installed. "
                "Install with: pip install investing-algorithm-framework==8.*"
            )
        self._app = App()

    def run_backtest(
        self,
        config: BacktestConfig,
        signals: list[dict],
        market_data: list[dict],
    ) -> BacktestReport:
        """Run an event-driven backtest via IAF.

        Args:
            config: Backtest configuration (dates, capital, TP/SL policy).
            signals: List of signal dicts with keys:
                - symbol: str
                - direction: "up" or "down"
                - conviction: float [0, 1]
                - timestamp: ISO datetime string
                - voters: list of voter dicts (optional)
            market_data: Historical bar dicts with keys:
                - symbol: str
                - timestamp: ISO datetime string
                - open, high, low, close: float
                - volume: int

        Returns:
            BacktestReport with metrics, trades, and equity curve.
        """
        # Build IAF TradingStrategy from ShettyXtreme config
        strategy = self._build_strategy(config)

        # Register market data as IAF MarketDataType
        self._register_market_data(strategy, market_data)

        # Register signal-driven entries
        self._register_signals(strategy, signals, config)

        # Run the backtest
        try:
            result = self._app.run_backtest(strategy)
        except Exception as e:
            raise IAFBacktestError(f"IAF backtest failed: {e}") from e

        # Translate IAF result → BacktestReport
        return self._translate_result(result, config)

    def compare_strategies(
        self,
        reports: list[BacktestReport],
    ) -> dict:
        """Compare multiple BacktestReports side-by-side.

        Returns a dict with per-strategy metrics and rankings.
        """
        if not reports:
            return {"strategies": [], "rankings": {}}

        comparisons = []
        for report in reports:
            comparisons.append({
                "name": report.strategy_name,
                "total_return": report.metrics.total_return,
                "sharpe_ratio": report.metrics.sharpe_ratio,
                "sortino_ratio": report.metrics.sortino_ratio,
                "calmar_ratio": report.metrics.calmar_ratio,
                "max_drawdown": report.metrics.max_drawdown,
                "win_rate": report.metrics.win_rate,
                "profit_factor": report.metrics.profit_factor,
                "total_trades": report.metrics.total_trades,
                "net_return": report.metrics.net_return,
            })

        # Rank by Sharpe (primary), then Sortino (secondary)
        by_sharpe = sorted(comparisons, key=lambda x: x["sharpe_ratio"], reverse=True)
        by_sortino = sorted(comparisons, key=lambda x: x["sortino_ratio"], reverse=True)
        by_return = sorted(comparisons, key=lambda x: x["total_return"], reverse=True)

        return {
            "strategies": comparisons,
            "rankings": {
                "by_sharpe": [s["name"] for s in by_sharpe],
                "by_sortino": [s["name"] for s in by_sortino],
                "by_return": [s["name"] for s in by_return],
            },
        }

    def _build_strategy(self, config: BacktestConfig) -> Any:
        """Build an IAF TradingStrategy from ShettyXtreme config."""
        # Position sizing — percentage of portfolio
        position_size = PositionSize(
            percentage=config.base_position_pct,
        )

        # Scaling rule
        scaling = ScalingRule(
            scale_in_percentage=config.base_position_pct,
            max_entries=3,
            cooldown_in_bars=config.cooldown_bars,
        )

        # Stop-loss rule (trailing)
        stop_loss = StopLossRule(
            trailing=True,
            trailing_stop_percentage=config.tsl_stop_fraction,
            sell_percentage=1.0,  # full exit on stop
        )

        # Take-profit rules (TP1, TP2, TP3)
        take_profit = TakeProfitRule(
            take_profit_targets=[
                {"percentage": config.tp1_pct, "sell_percentage": 0.33},
                {"percentage": config.tp2_pct, "sell_percentage": 0.33},
                {"percentage": config.tp3_pct, "sell_percentage": 1.0},
            ],
        )

        # Cooldown rule — prevent re-entry after stop-out
        cooldown = CooldownRule(
            cooldown_in_bars=config.cooldown_bars,
            trigger="stop_loss",
            bars=config.cooldown_bars,
        )

        # Trading cost — India-correct model
        cost = TradingCost(
            slippage=config.slippage_bps / 10000.0,  # bps → decimal
            brokerage=config.brokerage_per_lot,
        )

        # Build strategy
        strategy = TradingStrategy(
            name=config.strategy_name,
            position_size=position_size,
            scaling_rule=scaling,
            stop_loss_rule=stop_loss,
            take_profit_rule=take_profit,
            cooldown_rule=cooldown,
            trading_cost=cost,
        )

        return strategy

    def _register_market_data(
        self, strategy: Any, market_data: list[dict]
    ) -> None:
        """Register historical bar data with IAF."""
        for bar in market_data:
            strategy.add_market_data(
                MarketDataType(
                    symbol=bar["symbol"],
                    timestamp=datetime.fromisoformat(bar["timestamp"]),
                    open=bar["open"],
                    high=bar["high"],
                    low=bar["low"],
                    close=bar["close"],
                    volume=bar.get("volume", 0),
                )
            )

    def _register_signals(
        self,
        strategy: Any,
        signals: list[dict],
        config: BacktestConfig,
    ) -> None:
        """Register signal-driven entries with IAF strategy."""
        for sig in signals:
            direction = sig.get("direction", "up")
            conviction = sig.get("conviction", 0.5)
            symbol = sig.get("symbol", "NIFTY")

            # Map conviction to position size percentage
            position_pct = config.base_position_pct * min(
                2.0, max(0.25, conviction / 0.5)
            )

            strategy.add_signal(
                symbol=symbol,
                side="buy" if direction == "up" else "sell",
                conviction=conviction,
                position_percentage=position_pct,
            )

    def _translate_result(
        self, result: Any, config: BacktestConfig
    ) -> BacktestReport:
        """Translate IAF result → BacktestReport."""
        # Extract metrics from IAF result
        metrics_data = getattr(result, "metrics", result)

        # Build BacktestMetrics
        metrics = BacktestMetrics(
            total_return=getattr(metrics_data, "total_return", 0.0),
            total_trades=getattr(metrics_data, "total_trades", 0),
            winning_trades=getattr(metrics_data, "winning_trades", 0),
            losing_trades=getattr(metrics_data, "losing_trades", 0),
            win_rate=getattr(metrics_data, "win_rate", 0.0),
            avg_win=getattr(metrics_data, "avg_win", 0.0),
            avg_loss=getattr(metrics_data, "avg_loss", 0.0),
            profit_factor=getattr(metrics_data, "profit_factor", 0.0),
            sharpe_ratio=getattr(metrics_data, "sharpe_ratio", 0.0),
            sortino_ratio=getattr(metrics_data, "sortino_ratio", 0.0),
            calmar_ratio=getattr(metrics_data, "calmar_ratio", 0.0),
            max_drawdown=getattr(metrics_data, "max_drawdown", 0.0),
            max_drawdown_duration=getattr(
                metrics_data, "max_drawdown_duration", 0
            ),
            avg_trade_duration=getattr(metrics_data, "avg_trade_duration", 0.0),
            cost_total=getattr(metrics_data, "cost_total", 0.0),
            net_return=getattr(metrics_data, "net_return", 0.0),
        )

        # Extract trades
        trades = []
        for t in getattr(result, "trades", []):
            trades.append(
                BacktestTrade(
                    symbol=getattr(t, "symbol", ""),
                    side=getattr(t, "side", "long"),
                    entry_price=getattr(t, "entry_price", 0.0),
                    exit_price=getattr(t, "exit_price", 0.0),
                    quantity=getattr(t, "quantity", 0),
                    entry_time=getattr(t, "entry_time", datetime.now()),
                    exit_time=getattr(t, "exit_time", datetime.now()),
                    pnl=getattr(t, "pnl", 0.0),
                    cost=getattr(t, "cost", 0.0),
                    net_pnl=getattr(t, "net_pnl", 0.0),
                    exit_reason=getattr(t, "exit_reason", "unknown"),
                )
            )

        # Extract equity curve
        equity_curve = getattr(result, "equity_curve", [])

        return BacktestReport(
            strategy_name=config.strategy_name,
            start_date=config.start_date,
            end_date=config.end_date,
            initial_capital=config.initial_capital,
            final_capital=config.initial_capital + metrics.total_return,
            metrics=metrics,
            trades=trades,
            equity_curve=equity_curve,
            metadata={
                "engine": "iaf",
                "version": "v8",
                "config": {
                    "tp1_pct": config.tp1_pct,
                    "tp2_pct": config.tp2_pct,
                    "tp3_pct": config.tp3_pct,
                    "tsl_atr_multiplier": config.tsl_atr_multiplier,
                    "cooldown_bars": config.cooldown_bars,
                    "lot_size": config.lot_size,
                },
            },
        )
