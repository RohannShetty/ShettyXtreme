"""Tests for PaperTradingEngine."""

import pytest
from shettyxtreme.execution.paper_trading import PaperTradingEngine


def _seed_ltp(engine: PaperTradingEngine, symbol: str, ltp: float) -> None:
    """Push a MARKET_DATA_TICK so the engine's LTP cache knows the price."""
    engine._ltp_cache[symbol.upper()] = ltp


class TestPaperTradingEngine:
    @pytest.mark.asyncio
    async def test_market_order_fills(self):
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 18450.0)
        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.status == "FILLED" or "FILL" in str(result.status)
        positions = engine.get_positions()
        assert len(positions) > 0

    @pytest.mark.asyncio
    async def test_market_order_fills_at_ltp_not_zero(self):
        """F-EXEC-004: a MARKET order fills at the last traded price, not 0.0."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 18450.0)
        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.status == "FILLED"
        assert result.average_price == 18450.0
        assert result.message.endswith("@ 18450.0")
        positions = engine.get_positions()
        assert positions[0].buy_avg == 18450.0
        assert positions[0].pnl == 0.0  # filled at LTP → no phantom P&L
        fills = engine.get_order_book()
        assert fills[0].average_price == 18450.0

    @pytest.mark.asyncio
    async def test_market_order_rejected_without_ltp(self):
        """F-EXEC-004: no LTP available → honest rejection, never a 0.0 fill."""
        engine = PaperTradingEngine()
        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.status == "REJECTED"
        assert "no ltp" in result.message.lower()
        assert engine.get_positions() == []
        # The rejected order stays in the book, marked REJECTED — no fill.
        book = engine.get_order_book()
        assert len(book) == 1
        assert book[0].status == "REJECTED"
        assert book[0].filled_quantity == 0

    @pytest.mark.asyncio
    async def test_limit_order_pending(self):
        engine = PaperTradingEngine()
        result = await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 50, price=100)
        assert result.status == "OPEN" or "PENDING" in str(result.status)

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        engine = PaperTradingEngine()
        result = await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 50, price=100)
        cancelled = await engine.cancel_order(result.order_id)
        assert cancelled

    @pytest.mark.asyncio
    async def test_cancel_unknown_returns_false(self):
        engine = PaperTradingEngine()
        result = await engine.cancel_order("unknown-id")
        assert not result

    def test_get_pnl_returns_dict(self):
        engine = PaperTradingEngine()
        pnl = engine.get_pnl()
        assert isinstance(pnl, dict)
        assert "total_pnl" in pnl

    @pytest.mark.asyncio
    async def test_get_pnl_after_first_fill(self):
        """F-CORE-003: get_pnl() must not raise after the first fill.

        Fill carries no pnl field; the old `t.pnl` access blew up the moment
        _fills became non-empty. Guarded with getattr — this regression proves
        the first fill is safe.
        """
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 18450.0)
        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.status == "FILLED"
        pnl = engine.get_pnl()  # must not raise AttributeError
        assert isinstance(pnl, dict)
        assert "realised_pnl" in pnl
        assert "total_pnl" in pnl
        assert pnl["realised_pnl"] == 0.0

    def test_paper_engine_get_portfolio_initial_capital(self):
        """get_portfolio().available_margin == initial_capital at start."""
        engine = PaperTradingEngine(initial_capital=1_000_000.0)
        portfolio = engine.get_portfolio()
        assert portfolio.available_margin == 1_000_000.0
        assert portfolio.total_margin_used == 0.0
        assert portfolio.positions == []

    @pytest.mark.asyncio
    async def test_paper_engine_buy_fill_reduces_margin(self):
        """After a BUY fill, available_margin decreases by notional."""
        engine = PaperTradingEngine(initial_capital=1_000_000.0)
        _seed_ltp(engine, "NIFTY", 18450.0)
        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        portfolio = engine.get_portfolio()
        # notional = 50 * 18450 = 922_500
        assert portfolio.available_margin == 1_000_000.0 - (50 * 18450.0)
        assert portfolio.total_margin_used == 50 * 18450.0

    @pytest.mark.asyncio
    async def test_paper_engine_sell_restores_margin(self):
        """After a BUY then SELL, margin is restored."""
        engine = PaperTradingEngine(initial_capital=1_000_000.0)
        _seed_ltp(engine, "NIFTY", 18450.0)
        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert engine.get_portfolio().available_margin == 1_000_000.0 - (50 * 18450.0)
        await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 50)
        assert engine.get_portfolio().available_margin == 1_000_000.0
