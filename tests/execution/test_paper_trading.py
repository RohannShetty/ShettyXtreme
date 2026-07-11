"""Tests for PaperTradingEngine."""

import pytest
from shettyxtreme.execution.paper_trading import PaperTradingEngine


class TestPaperTradingEngine:
    @pytest.mark.asyncio
    async def test_market_order_fills(self):
        engine = PaperTradingEngine()
        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.status == "FILLED" or "FILL" in str(result.status)
        positions = engine.get_positions()
        assert len(positions) > 0

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
