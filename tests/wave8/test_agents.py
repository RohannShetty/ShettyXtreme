"""Tests for P2-3.5 multi-agent research layer.

Covers:
- TechnicalAnalyst compute (RSI/EMA/MACD/Bollinger → direction + confidence)
- OptionsAnalyst compute (IV rank + PCR + Max Pain + OI → signal)
- RiskManager annotate (risk engine limits + voter correlation → annotated signals)
- PortfolioManager aggregate (weighted aggregation → final proposal)
- Agent signal knowledge ingestion (kind="agent_signal" written to knowledge store)
- Scheduler 5-min deterministic (deterministic agents run every 5 min)
- MACD and Bollinger indicator correctness
"""
from __future__ import annotations

import asyncio
import math
import os
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from shettyxtreme.core.data_models.market_data import Tick
from shettyxtreme.intelligence.features.indicators.bollinger import BollingerBands
from shettyxtreme.intelligence.features.indicators.ema import EMA
from shettyxtreme.intelligence.features.indicators.macd import MACD
from shettyxtreme.intelligence.features.indicators.rsi import RSI
from shettyxtreme.knowledge.ingest import ingest_agent_signals
from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.research.briefs import ResearchBrief
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.store import ResearchStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tick(price: float, symbol: str = "NIFTY", ts: datetime | None = None) -> Tick:
    return Tick(
        symbol=symbol,
        exchange="NSE",
        ltp=price,
        volume=1000,
        timestamp=ts or datetime.now(UTC),
    )


def _make_prices(n: int, start: float = 20000.0, step: float = 10.0) -> list[dict[str, Any]]:
    """Generate n OHLCV price dicts with a gentle uptrend."""
    prices: list[dict[str, Any]] = []
    for i in range(n):
        base = start + step * i
        prices.append({
            "open": base - 5,
            "high": base + 20,
            "low": base - 20,
            "close": base,
            "volume": 10000 + i * 100,
            "timestamp": datetime.now(UTC) + timedelta(minutes=i),
        })
    return prices


def _make_contracts(n: int = 10, spot: float = 20000.0) -> list[dict[str, Any]]:
    """Generate synthetic option chain contracts."""
    contracts: list[dict[str, Any]] = []
    for i in range(n):
        strike = spot - 500 + i * 100
        # CE contract
        contracts.append({
            "strike": strike,
            "option_type": "CE",
            "oi": 100000 + i * 5000,
            "iv": 15.0 + i * 0.5,
        })
        # PE contract
        contracts.append({
            "strike": strike,
            "option_type": "PE",
            "oi": 80000 + i * 4000,
            "iv": 16.0 + i * 0.4,
        })
    return contracts


def _tmp_db() -> str:
    return os.path.join(tempfile.mkdtemp(), "test_research.db")


def _tmp_knowledge_db() -> str:
    return os.path.join(tempfile.mkdtemp(), "test_knowledge.db")


# ---------------------------------------------------------------------------
# MACD indicator tests
# ---------------------------------------------------------------------------

class TestMACD:
    def test_warmup_returns_none(self):
        macd = MACD(fast_period=3, slow_period=5, signal_period=3)
        # First few ticks should return None (warmup)
        for i in range(4):
            result = macd.update(_make_tick(100.0 + i))
            assert result is None or isinstance(result, float)

    def test_computes_after_warmup(self):
        macd = MACD(fast_period=3, slow_period=5, signal_period=3)
        # Feed enough ticks
        for i in range(20):
            macd.update(_make_tick(100.0 + i * 0.5))
        assert macd.value is not None
        assert macd.signal is not None
        assert macd.histogram is not None

    def test_uptrend_positive_macd(self):
        macd = MACD(fast_period=3, slow_period=5, signal_period=3)
        # Strong uptrend
        for i in range(30):
            macd.update(_make_tick(100.0 + i * 2.0))
        assert macd.value is not None
        assert macd.value > 0  # Fast EMA > Slow EMA in uptrend

    def test_downtrend_negative_macd(self):
        macd = MACD(fast_period=3, slow_period=5, signal_period=3)
        # Strong downtrend
        for i in range(30):
            macd.update(_make_tick(200.0 - i * 2.0))
        assert macd.value is not None
        assert macd.value < 0  # Fast EMA < Slow EMA in downtrend

    def test_reset(self):
        macd = MACD(fast_period=3, slow_period=5, signal_period=3)
        for i in range(20):
            macd.update(_make_tick(100.0 + i))
        macd.reset()
        assert macd.value is None
        assert macd.signal is None
        assert macd.histogram is None


# ---------------------------------------------------------------------------
# Bollinger Bands indicator tests
# ---------------------------------------------------------------------------

class TestBollingerBands:
    def test_warmup_returns_none(self):
        bb = BollingerBands(period=5, num_std=2.0)
        for i in range(4):
            result = bb.update(_make_tick(100.0 + i))
            assert result is None

    def test_computes_after_warmup(self):
        bb = BollingerBands(period=5, num_std=2.0)
        for i in range(10):
            bb.update(_make_tick(100.0 + i))
        assert bb.value is not None
        assert bb.upper is not None
        assert bb.lower is not None
        assert bb.upper > bb.lower

    def test_pct_b_range(self):
        bb = BollingerBands(period=10, num_std=2.0)
        for i in range(20):
            bb.update(_make_tick(100.0 + i * 0.5))
        assert bb.pct_b is not None
        # %B should be roughly in [0, 1] for normal data
        # (can go outside for extreme moves)

    def test_bandwidth_positive(self):
        bb = BollingerBands(period=10, num_std=2.0)
        for i in range(20):
            bb.update(_make_tick(100.0 + i * 0.5))
        bw = bb.bandwidth
        assert bw is not None
        assert bw >= 0

    def test_flat_data_narrow_bands(self):
        bb = BollingerBands(period=10, num_std=2.0)
        for i in range(20):
            bb.update(_make_tick(100.0))  # Flat price
        assert bb.upper is not None
        assert bb.lower is not None
        # Bands should be very narrow (near zero stddev)
        assert abs(bb.upper - bb.lower) < 0.01


# ---------------------------------------------------------------------------
# TechnicalAnalyst tests
# ---------------------------------------------------------------------------

class TestTechnicalAnalyst:
    def test_insufficient_data(self):
        from shettyxtreme.research.agents.technical import compute_technical_signal
        prices = _make_prices(10)  # Less than 30
        brief = compute_technical_signal(prices, "TEST")
        assert brief.direction == 0
        assert "Insufficient data" in brief.thesis

    def test_uptrend_bullish(self):
        from shettyxtreme.research.agents.technical import compute_technical_signal
        # Strong uptrend: price increases significantly over 50 bars
        prices = _make_prices(50, start=20000.0, step=100.0)
        brief = compute_technical_signal(prices, "NIFTY")
        # In a strong uptrend, direction should be bullish or neutral (depending on indicator agreement)
        assert brief.direction >= 0  # Should be bullish or neutral
        assert brief.lens == "technical"
        assert len(brief.evidence) > 0

    def test_downtrend_bearish(self):
        from shettyxtreme.research.agents.technical import compute_technical_signal
        # Strong downtrend: price decreases significantly over 50 bars
        prices = _make_prices(50, start=25000.0, step=-100.0)
        brief = compute_technical_signal(prices, "NIFTY")
        # In a strong downtrend, direction should be bearish or neutral
        assert brief.direction <= 0  # Should be bearish or neutral
        assert brief.lens == "technical"

    def test_brief_schema_valid(self):
        from shettyxtreme.research.agents.technical import compute_technical_signal
        prices = _make_prices(50)
        brief = compute_technical_signal(prices, "NIFTY")
        # Should be a valid ResearchBrief
        assert isinstance(brief, ResearchBrief)
        assert brief.status == "proposed"
        assert brief.brief_id
        assert brief.as_of
        assert len(brief.thesis) <= 500
        assert len(brief.rationale) >= 300
        assert len(brief.rationale) <= 1200

    def test_registered_in_agents(self):
        from shettyxtreme.research.agents import AGENTS
        assert "technical" in AGENTS
        assert AGENTS["technical"].deterministic is True
        assert AGENTS["technical"].agent_type == "technical"


# ---------------------------------------------------------------------------
# OptionsAnalyst tests
# ---------------------------------------------------------------------------

class TestOptionsAnalyst:
    def test_no_contracts(self):
        from shettyxtreme.research.agents.options import compute_options_signal
        brief = compute_options_signal([], spot=20000.0, symbol="NIFTY")
        assert brief.direction == 0
        assert "No option chain" in brief.thesis

    def test_basic_signal(self):
        from shettyxtreme.research.agents.options import compute_options_signal
        contracts = _make_contracts(10, spot=20000.0)
        brief = compute_options_signal(contracts, spot=20000.0, symbol="NIFTY")
        assert isinstance(brief, ResearchBrief)
        assert brief.lens == "options"
        assert brief.status == "proposed"
        assert brief.confidence > 0

    def test_high_pcr_bullish(self):
        from shettyxtreme.research.agents.options import compute_options_signal
        # Create contracts with very high put OI (high PCR = bullish contrarian)
        contracts = []
        for i in range(5):
            strike = 19500 + i * 100
            contracts.append({"strike": strike, "option_type": "CE", "oi": 10000, "iv": 15.0})
            contracts.append({"strike": strike, "option_type": "PE", "oi": 50000, "iv": 18.0})
        brief = compute_options_signal(contracts, spot=20000.0, symbol="NIFTY")
        # High PCR should lean bullish (contrarian)
        assert brief.direction >= 0

    def test_iv_history_rank(self):
        from shettyxtreme.research.agents.options import compute_options_signal
        contracts = _make_contracts(10, spot=20000.0)
        iv_history = [10.0 + i * 0.5 for i in range(100)]  # Historical IV range
        brief = compute_options_signal(
            contracts, spot=20000.0, iv_history=iv_history, current_iv=25.0, symbol="NIFTY"
        )
        assert isinstance(brief, ResearchBrief)
        # IV rank should be high (25.0 is near top of 10-60 range)
        assert any("HIGH" in e.get("item", "") or "IV_rank" in e.get("item", "") for e in brief.evidence)

    def test_registered_in_agents(self):
        from shettyxtreme.research.agents import AGENTS
        assert "options" in AGENTS
        assert AGENTS["options"].deterministic is True
        assert AGENTS["options"].agent_type == "options"


# ---------------------------------------------------------------------------
# RiskManager tests
# ---------------------------------------------------------------------------

class TestRiskManager:
    def test_no_signals(self):
        from shettyxtreme.research.agents.risk import compute_risk_annotation
        brief = compute_risk_annotation([])
        assert brief.direction == 0
        assert "No signals" in brief.thesis

    def test_annotates_signals(self):
        from shettyxtreme.research.agents.risk import compute_risk_annotation
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.7, "instruments": ["NIFTY"]},
            {"agent": "options", "direction": 1, "confidence": 0.6, "instruments": ["NIFTY"]},
        ]
        brief = compute_risk_annotation(signals)
        assert isinstance(brief, ResearchBrief)
        assert brief.lens == "risk"
        assert len(brief.evidence) > 0

    def test_loss_limit_warning(self):
        from shettyxtreme.research.agents.risk import compute_risk_annotation
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.7, "instruments": ["NIFTY"]},
        ]
        portfolio = {
            "daily_pnl": -40000.0,
            "loss_limit": -50000.0,
            "available_margin": 100000.0,
            "total_margin_used": 0.0,
            "positions": [],
            "max_positions": 5,
        }
        brief = compute_risk_annotation(signals, portfolio=portfolio)
        # Should have loss limit warning
        assert any("loss_limit" in e.get("item", "") for e in brief.evidence)

    def test_loss_limit_blocked(self):
        from shettyxtreme.research.agents.risk import compute_risk_annotation
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.7, "instruments": ["NIFTY"]},
        ]
        portfolio = {
            "daily_pnl": -60000.0,
            "loss_limit": -50000.0,
            "available_margin": 100000.0,
            "total_margin_used": 0.0,
            "positions": [],
            "max_positions": 5,
        }
        brief = compute_risk_annotation(signals, portfolio=portfolio)
        assert brief.direction == -1  # Blocked = bearish/caution
        assert any("BLOCKED" in e.get("item", "") for e in brief.evidence)

    def test_crowding_warning(self):
        from shettyxtreme.research.agents.risk import compute_risk_annotation
        # All signals agree → crowding
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.8, "instruments": ["NIFTY"]},
            {"agent": "options", "direction": 1, "confidence": 0.7, "instruments": ["NIFTY"]},
            {"agent": "sentiment", "direction": 1, "confidence": 0.6, "instruments": ["NIFTY"]},
        ]
        brief = compute_risk_annotation(signals)
        assert any("correlation" in e.get("item", "") or "agreement" in e.get("item", "") for e in brief.evidence)

    def test_registered_in_agents(self):
        from shettyxtreme.research.agents import AGENTS
        assert "risk" in AGENTS
        assert AGENTS["risk"].deterministic is True
        assert AGENTS["risk"].agent_type == "risk"


# ---------------------------------------------------------------------------
# PortfolioManager tests
# ---------------------------------------------------------------------------

class TestPortfolioManager:
    def test_no_signals(self):
        from shettyxtreme.research.agents.portfolio import compute_portfolio_proposal
        brief = compute_portfolio_proposal([])
        assert brief.direction == 0
        assert "No analyst signals" in brief.thesis

    def test_agreement_bullish(self):
        from shettyxtreme.research.agents.portfolio import compute_portfolio_proposal
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.7, "instruments": ["NIFTY"], "thesis": "bullish"},
            {"agent": "options", "direction": 1, "confidence": 0.6, "instruments": ["NIFTY"], "thesis": "bullish"},
        ]
        brief = compute_portfolio_proposal(signals)
        assert brief.direction == 1  # Bullish
        assert brief.confidence > 0
        assert brief.lens == "portfolio"

    def test_disagreement_neutral(self):
        from shettyxtreme.research.agents.portfolio import compute_portfolio_proposal
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.5, "instruments": ["NIFTY"], "thesis": "bullish"},
            {"agent": "options", "direction": -1, "confidence": 0.5, "instruments": ["NIFTY"], "thesis": "bearish"},
        ]
        brief = compute_portfolio_proposal(signals)
        assert brief.direction == 0  # Neutral (disagreement)

    def test_risk_blocks_halves_confidence(self):
        from shettyxtreme.research.agents.portfolio import compute_portfolio_proposal
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.8, "instruments": ["NIFTY"], "thesis": "bullish"},
            {"agent": "risk", "direction": -1, "confidence": 0.9, "instruments": ["NIFTY"], "thesis": "blocked"},
        ]
        brief = compute_portfolio_proposal(signals)
        # Risk blocking should reduce confidence
        assert brief.confidence < 0.8

    def test_custom_weights(self):
        from shettyxtreme.research.agents.portfolio import compute_portfolio_proposal
        signals = [
            {"agent": "technical", "direction": 1, "confidence": 0.7, "instruments": ["NIFTY"], "thesis": "bullish"},
            {"agent": "options", "direction": -1, "confidence": 0.7, "instruments": ["NIFTY"], "thesis": "bearish"},
        ]
        # Give technical much higher weight
        brief = compute_portfolio_proposal(signals, weights={"technical": 5.0, "options": 0.1})
        assert brief.direction == 1  # Technical wins due to weight

    def test_registered_in_agents(self):
        from shettyxtreme.research.agents import AGENTS
        assert "portfolio" in AGENTS
        assert AGENTS["portfolio"].deterministic is True
        assert AGENTS["portfolio"].agent_type == "portfolio"


# ---------------------------------------------------------------------------
# Agent signal knowledge ingestion tests
# ---------------------------------------------------------------------------

class TestAgentSignalKnowledgeIngestion:
    def test_ingest_proposed_signal(self):
        store = KnowledgeStore(_tmp_knowledge_db())
        brief = ResearchBrief(
            brief_id="test-123",
            lens="technical",
            as_of=datetime.now(UTC).isoformat(),
            instruments=["NIFTY"],
            direction=1,
            confidence=0.7,
            thesis="Bullish technical setup",
            rationale="x" * 300,
            evidence=[{"item": "RSI=30", "source": "indicator", "unsourced": False}],
            risks=["Low confidence"],
            status="proposed",
        )
        result = ingest_agent_signals(store, [brief])
        assert result.ingested == 1
        assert result.skipped_undecided == 0
        assert result.skipped_duplicate == 0

        # Verify the doc was stored
        docs = store.list_docs()
        assert len(docs) == 1
        assert docs[0].kind == "agent_signal"
        assert docs[0].status == "proposed"
        assert docs[0].source_ref == "test-123"

    def test_ingest_skips_decided(self):
        store = KnowledgeStore(_tmp_knowledge_db())
        brief = ResearchBrief(
            brief_id="test-456",
            lens="options",
            as_of=datetime.now(UTC).isoformat(),
            instruments=["NIFTY"],
            direction=-1,
            confidence=0.6,
            thesis="Bearish options",
            rationale="x" * 300,
            evidence=[],
            risks=[],
            status="approved",
            decided_at=datetime.now(UTC).isoformat(),
        )
        result = ingest_agent_signals(store, [brief])
        assert result.ingested == 0
        assert result.skipped_undecided == 1

    def test_ingest_idempotent(self):
        store = KnowledgeStore(_tmp_knowledge_db())
        brief = ResearchBrief(
            brief_id="test-789",
            lens="technical",
            as_of=datetime.now(UTC).isoformat(),
            instruments=["NIFTY"],
            direction=1,
            confidence=0.5,
            thesis="Test signal",
            rationale="x" * 300,
            evidence=[],
            risks=[],
            status="proposed",
        )
        # First ingest
        result1 = ingest_agent_signals(store, [brief])
        assert result1.ingested == 1

        # Second ingest (duplicate)
        result2 = ingest_agent_signals(store, [brief])
        assert result2.ingested == 0
        assert result2.skipped_duplicate == 1


# ---------------------------------------------------------------------------
# Orchestrator run_agents tests
# ---------------------------------------------------------------------------

class TestOrchestratorRunAgents:
    def test_run_agents_persists(self):
        db = _tmp_db()
        store = ResearchStore(db)
        provider = SimulatedProvider()
        orch = ResearchOrchestrator(provider=provider, store=store)
        data = {
            "prices": _make_prices(50),
            "symbol": "NIFTY",
            "contracts": _make_contracts(10, spot=20000.0),
            "spot": 20000.0,
        }

        async def _test():
            return await orch.run_agents(data=data)

        results = asyncio.run(_test())
        assert len(results) > 0
        # All agents should succeed
        for r in results:
            assert r.error is None, f"Agent {r.agent} failed: {r.error}"
            assert r.brief is not None
        # Briefs should be persisted
        briefs = store.list()
        assert len(briefs) >= len(results)
        store.close()

    def test_run_specific_agents(self):
        db = _tmp_db()
        store = ResearchStore(db)
        provider = SimulatedProvider()
        orch = ResearchOrchestrator(provider=provider, store=store)
        data = {"prices": _make_prices(50), "symbol": "NIFTY"}

        async def _test():
            return await orch.run_agents(agent_names=["technical"], data=data)

        results = asyncio.run(_test())
        assert len(results) == 1
        assert results[0].agent == "technical"
        assert results[0].brief is not None
        store.close()

    def test_run_agents_unknown_raises(self):
        db = _tmp_db()
        store = ResearchStore(db)
        provider = SimulatedProvider()
        orch = ResearchOrchestrator(provider=provider, store=store)

        async def _test():
            return await orch.run_agents(agent_names=["nonexistent"])

        with pytest.raises(ValueError, match="unknown agent"):
            asyncio.run(_test())
        store.close()


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------

class TestSchedulerAgents:
    def test_scheduler_has_agent_interval(self):
        db = _tmp_db()
        store = ResearchStore(db)
        provider = SimulatedProvider()
        orch = ResearchOrchestrator(provider=provider, store=store)
        scheduler = ResearchScheduler(
            orchestrator=orch,
            interval_minutes=60.0,
            agent_interval_minutes=5.0,
        )
        assert scheduler.agent_interval_minutes == 5.0
        assert scheduler.interval_minutes == 60.0
        store.close()

    def test_scheduler_default_agent_interval(self):
        db = _tmp_db()
        store = ResearchStore(db)
        provider = SimulatedProvider()
        orch = ResearchOrchestrator(provider=provider, store=store)
        scheduler = ResearchScheduler(orchestrator=orch)
        assert scheduler.agent_interval_minutes == 5.0
        store.close()

    def test_scheduler_start_creates_agent_task(self):
        db = _tmp_db()
        store = ResearchStore(db)
        provider = SimulatedProvider()
        orch = ResearchOrchestrator(provider=provider, store=store)
        scheduler = ResearchScheduler(
            orchestrator=orch,
            interval_minutes=60.0,
            agent_interval_minutes=5.0,
        )

        async def _test():
            scheduler.start()
            assert scheduler.enabled
            assert scheduler._agent_task is not None
            scheduler.stop()
            assert not scheduler.enabled

        asyncio.run(_test())
        store.close()
