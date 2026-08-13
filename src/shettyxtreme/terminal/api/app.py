"""FastAPI application for the ShettyXtreme terminal.

Lifespan: starts event bus, credential store, health monitor, Fyers adapters,
and the market-data bridge. Mounts static files and includes all routers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.fyers_oauth import FyersOAuthHelper
from shettyxtreme.auth.health_monitor import TokenHealthMonitor
from shettyxtreme.auth.validator import CredentialValidator
from shettyxtreme.core.config.config_manager import ConfigManager
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.core.settings import init_settings_store
from shettyxtreme.execution.execution_engine import ExecutionEngine
from shettyxtreme.execution.ledger import TradeLedger
from shettyxtreme.execution.ledger_recorder import LedgerRecorder
from shettyxtreme.execution.mode_router import ModeRoutingExecutor
from shettyxtreme.execution.paper_trading import PaperTradingEngine
from shettyxtreme.execution.signal_bridge import ExecutionSignalBridge
from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.learning.shadow_loop import ShadowLoop, session_outcome_label
from shettyxtreme.terminal.api.auth_router import init_auth
from shettyxtreme.terminal.api.auth_router import router as auth_router
from shettyxtreme.terminal.api.execution_router import (
    get_kill_switch_gate,
    get_mode_value,
    is_kill_switch_armed,
    router as execution_router,
)
from shettyxtreme.terminal.api.health_router import router as health_router
from shettyxtreme.terminal.api.terminal_init import (
    init_terminal_adapters,
    wire_terminal_init,
)
from shettyxtreme.terminal.api.intelligence_router import router as intelligence_router
from shettyxtreme.terminal.api.learning_router import router as learning_router
from shettyxtreme.terminal.api.market_router import router as market_router
from shettyxtreme.terminal.api.research_router import router as research_router
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.tools import set_data_source
from shettyxtreme.terminal.api.research_router import build_orchestrator, init_research
from shettyxtreme.terminal.api.research_source import ProjectionDataSource
from shettyxtreme.intelligence.regime.bus_bridge import RegimeBusBridge
from shettyxtreme.intelligence.risk.bus_bridge import RiskBusBridge
from shettyxtreme.intelligence.risk.risk_engine import RiskEngine
from shettyxtreme.intelligence.pipeline import IntelligencePipeline
from shettyxtreme.terminal.api import postback_router
from shettyxtreme.terminal.api import ws_bridge
from shettyxtreme.terminal.api.analytics_router import router as analytics_router
from shettyxtreme.terminal.api.greeks_store import GreeksStore
from shettyxtreme.terminal.api.knowledge_router import init_knowledge
from shettyxtreme.terminal.api.knowledge_router import router as knowledge_router
from shettyxtreme.terminal.api.v2 import router as v2_router
from shettyxtreme.terminal.api.scanner_data import GapDetector, LogCollector, ClusterDetector
from shettyxtreme.terminal.api.scanner_router import init_scanner_data, init_scanner_store
from shettyxtreme.terminal.api.scanner_router import router as scanner_router
from shettyxtreme.terminal.api.scanner_poller import (
    _SCANNER_POLL_CADENCE_SECONDS,
    _scanner_poll_loop,
)
from shettyxtreme.terminal.api.scanner_store import ScannerStore
from shettyxtreme.intelligence.scanners import instantiate_scanners, SCANNER_REGISTRY
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner
from shettyxtreme.terminal.api.settings_router import init_settings
from shettyxtreme.terminal.api.settings_router import router as settings_router
from shettyxtreme.terminal.api.watchlist_router import router as watchlist_router
from shettyxtreme.terminal.api.symbols_router import router as symbols_router
from shettyxtreme.terminal.api.ws_manager import WebSocketManager
from shettyxtreme.terminal.projections import (
    AlertProjection,
    HealthProjection,
    IntelligenceProjection,
    PositionProjection,
    RiskProjection,
    ScannerProjection,
    WatchlistProjection,
    set_greeks_store,
    set_scanner_store,
)

logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()
ws_bridge.configure(ws_manager)
_event_bus: EventBus | None = None
_event_bus_task: asyncio.Task | None = None
_health_monitor: TokenHealthMonitor | None = None
_intelligence_pipeline: IntelligencePipeline | None = None
_margin_poller_task: asyncio.Task | None = None

# Brokers disagree on the available-balance key name in get_margin() payloads;
# accept any known one (fix #2 — real margin, never a hardcoded stand-in).
_MARGIN_AVAILABLE_KEYS = ("availabelBalance", "availableMargin", "available", "balance")
_MARGIN_POLL_CADENCE_SECONDS = 30.0


def _csv_env(name: str) -> list[str] | None:
    """Parse a comma-separated env var into a list (None when empty)."""
    raw = os.environ.get(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()] or None


def _scheduler_env_interval() -> float:
    """Env RESEARCH_SCHEDULE_INTERVAL_MINUTES, clamped to a sane default."""
    try:
        interval = float(os.environ.get("RESEARCH_SCHEDULE_INTERVAL_MINUTES", "60"))
    except ValueError:
        interval = 60.0
    return interval if interval > 0 else 60.0


_MARGIN_UTILIZED_KEYS = ("utilized", "margin_used", "Margin Used", "usedMargin")
_MARGIN_TOTAL_KEYS = ("total", "totalMargin", "Total")


async def _margin_poll_loop(app: FastAPI) -> None:
    """Poll trading_adapter.get_margin() and publish real margin data.

    Margin starts UNKNOWN (None). We only publish a number once the broker
    reports one; on failure we publish nothing, so the risk projection keeps
    its previous honest value instead of a fabricated default.

    Now also publishes margin_used (utilized) and margin_total (total)
    to repair the existing UI bar and support the risk heat map.
    """
    while True:
        try:
            adapter = getattr(app.state, "trading_adapter", None)
            if adapter is not None and hasattr(adapter, "get_margin"):
                raw = await adapter.get_margin()
                payload = raw.get("data", raw) if isinstance(raw, dict) else {}
                if not isinstance(payload, dict):
                    payload = {}
                # Extract available margin
                available: float | None = None
                for key in _MARGIN_AVAILABLE_KEYS:
                    value = payload.get(key)
                    if value is not None:
                        try:
                            available = float(value)
                            break
                        except (TypeError, ValueError):
                            continue
                # Extract utilized margin (margin_used)
                utilized: float | None = None
                for key in _MARGIN_UTILIZED_KEYS:
                    value = payload.get(key)
                    if value is not None:
                        try:
                            utilized = float(value)
                            break
                        except (TypeError, ValueError):
                            continue
                # Extract total margin
                total: float | None = None
                for key in _MARGIN_TOTAL_KEYS:
                    value = payload.get(key)
                    if value is not None:
                        try:
                            total = float(value)
                            break
                        except (TypeError, ValueError):
                            continue

                if _event_bus is not None:
                    decision: dict[str, object] = {}
                    if available is not None:
                        decision["margin_available"] = available
                    if utilized is not None:
                        decision["margin_used"] = utilized
                    if total is not None:
                        decision["margin_total"] = total
                    if decision:
                        await _event_bus.publish(Event(
                            topic=Topic.RISK_DECISION,
                            data=decision,
                            source="margin_poller",
                        ))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("margin poller iteration failed")
        await asyncio.sleep(_MARGIN_POLL_CADENCE_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle."""
    global _event_bus, _event_bus_task, _health_monitor, _intelligence_pipeline, _margin_poller_task
    logger.info("ShettyXtreme Terminal starting up...")

    store = CredentialStore.load() or CredentialStore()
    oauth = FyersOAuthHelper()
    validator = CredentialValidator()
    init_auth(store, oauth, validator)

    _event_bus = EventBus()
    _event_bus_task = asyncio.create_task(_event_bus.start())
    postback_router.set_event_bus(_event_bus)
    postback_router.set_credential_store(store)
    _health_monitor = TokenHealthMonitor(store, _event_bus)
    await _health_monitor.start()

    # Margin poller: reads app.state.trading_adapter each tick (it is not
    # created until later in this lifespan / after login), publishes real
    # margin via RISK_DECISION → RiskProjection (fix #2).
    _margin_poller_task = asyncio.create_task(_margin_poll_loop(app))

    # ── Settings store (Phase 7 Wave 3) ─────────────────────────────────────
    # Single source of truth for risk limits / theme / scheduler config.
    # Initialized before the projections so the risk caps they seed come
    # from persisted settings rather than constants.
    settings_store = init_settings_store("data/settings.db")
    app.state.settings_store = settings_store

    # ── Create projection instances and subscribe to EventBus ───────────────
    watchlist_proj = WatchlistProjection()
    position_proj = PositionProjection()
    risk_proj = RiskProjection()
    alert_proj = AlertProjection()
    intel_proj = IntelligenceProjection()
    health_proj = HealthProjection()

    watchlist_proj.subscribe(_event_bus)
    position_proj.subscribe(_event_bus)
    risk_proj.subscribe(_event_bus)
    alert_proj.subscribe(_event_bus)
    intel_proj.subscribe(_event_bus)
    health_proj.subscribe(_event_bus)

    # ── Scanner data pipeline ────────────────────────────────────────────────
    gap_det = GapDetector()
    log_col = LogCollector()
    cluster_det = ClusterDetector()
    gap_det.subscribe(_event_bus)
    log_col.subscribe(_event_bus)
    cluster_det.subscribe(_event_bus)
    init_scanner_data(gap_det, log_col, cluster_det)

    # ── Scanner projection (11-type opportunity findings) ───────────────────
    scanner_proj = ScannerProjection()
    scanner_proj.subscribe(_event_bus)
    app.state.scanner_projection = scanner_proj

    # ── Persistent scanner findings store (Phase 3A.1) ─────────────────────
    # ScannerProjection broadcasts findings to WS and records them here so
    # /api/scanner/findings/history survives restarts.
    scanner_store = ScannerStore("data/scanner_findings.db")
    app.state.scanner_store = scanner_store
    init_scanner_store(scanner_store)
    set_scanner_store(scanner_store)

    # ── Regime & Risk EventBus bridges ──────────────────────────────────────
    regime_bridge = RegimeBusBridge(_event_bus)
    risk_bridge = RiskBusBridge(_event_bus)
    await regime_bridge.start()
    await risk_bridge.start()

    # ── Live intelligence pipeline (features → regime/signal) ──────────────
    # FeatureEngine + SignalEngine must be alive for FEATURES_COMPUTED /
    # SIGNAL_V2 to fire; the bridges and projections above are their sinks.
    # Runs regardless of credentials — without ticks it just stays idle.
    try:
        _intelligence_pipeline = IntelligencePipeline(_event_bus)
        _intelligence_pipeline.subscribe()
        app.state.feature_engine = _intelligence_pipeline.feature_engine
        app.state.signal_engine = _intelligence_pipeline.signal_engine
        app.state.intelligence_pipeline = "started"
        logger.info(
            "Intelligence pipeline started (voters=%s)",
            _intelligence_pipeline.voter_names,
        )
    except Exception:
        logger.exception("Intelligence pipeline failed to start")
        app.state.feature_engine = None
        app.state.signal_engine = None
        app.state.intelligence_pipeline = "degraded"

    # Store adapters and pipeline on app.state for router access
    app.state.trading_adapter = None
    app.state.data_adapter = None
    app.state.instrument_master = None
    app.state.symbol_resolver = None
    app.state.fyers_session = None
    app.state.event_bus = _event_bus

    # Store projections on app.state for router access
    app.state.watchlist_projection = watchlist_proj
    app.state.position_projection = position_proj
    app.state.risk_projection = risk_proj
    app.state.alert_projection = alert_proj
    app.state.intelligence_projection = intel_proj
    app.state.health_projection = health_proj

    # ── Hint outcome store (3A.2) ──────────────────────────────────────────
    # Tracks hints that became proposals and records outcomes when the
    # resulting position closes (win rate / avg PnL on the hints panel).
    from shettyxtreme.terminal.api.hint_store import HintStore

    hint_store = HintStore(db_path="data/hints.db")
    app.state.hint_store = hint_store
    position_proj.set_hint_store(hint_store)

    # ── Greeks history store (3A.4) ─────────────────────────────────────────
    # Records portfolio greeks snapshots on every position change (hooked in
    # PositionProjection) so the frontend can render greeks history charts.
    greeks_store = GreeksStore("data/greeks.db")
    app.state.greeks_store = greeks_store
    set_greeks_store(greeks_store)

    # ── Options analytics calculators (IV rank, OI tracker) ────────────────
    from shettyxtreme.options.iv_rank import IVRankCalculator
    from shettyxtreme.options.oi_tracker import OITracker

    iv_rank_calc = IVRankCalculator()
    oi_tracker = OITracker()
    app.state.iv_rank_calculator = iv_rank_calc
    app.state.oi_tracker = oi_tracker

    # ── Analytics history store (max pain / regime charts, Phase 3A.3) ─────
    from shettyxtreme.terminal.api.analytics_store import AnalyticsStore

    analytics_store = AnalyticsStore("data/analytics.db")
    app.state.analytics_store = analytics_store
    intel_proj.set_analytics_store(analytics_store)

    # ── 11-type opportunity scanners ───────────────────────────────────────
    _scanners: list[BaseScanner] = []
    _scanner_poller_task: asyncio.Task | None = None
    try:
        _scanners = instantiate_scanners(
            event_bus=_event_bus,
            iv_rank_calculator=iv_rank_calc,
            oi_tracker=oi_tracker,
            thresholds=settings_store.scanner_thresholds(),
        )
        for scanner in _scanners:
            await scanner.start()
        app.state.scanners = _scanners
        # Phase 3A.1: Tier-B poller — 8 of 11 scanners are snapshot-driven
        # and never ran before; this loop drives them from the chain cache.
        _scanner_poller_task = asyncio.create_task(_scanner_poll_loop(app))
        app.state.scanner_poller_task = _scanner_poller_task
        logger.info(
            "Opportunity scanners started: %d scanners (poller cadence %ss)",
            len(_scanners),
            _SCANNER_POLL_CADENCE_SECONDS,
        )
    except Exception:
        logger.exception("Scanner startup failed — scanners degraded")
        app.state.scanners = []

    # ── Research: data source, WS broadcast, scheduler (3C) ────────────────
    set_data_source(ProjectionDataSource(app.state))

    def _research_broadcast(data: dict) -> None:
        try:
            asyncio.create_task(ws_manager.broadcast("research", data))
        except Exception:
            logger.exception("research broadcast failed")

    # ── Research scheduler (Phase 7 Wave 3: settings-store driven) ──────────
    # The settings store is the source of truth for the scheduler config.
    # On first boot (keys never written) the effective env config is seeded
    # so legacy RESEARCH_SCHEDULE_* behavior is preserved; once the operator
    # touches /api/settings/scheduler the store wins.
    settings_store.seed_if_absent({
        "scheduler_enabled": os.environ.get("RESEARCH_SCHEDULE_ENABLED") == "1",
        "scheduler_interval_minutes": _scheduler_env_interval(),
        "scheduler_lenses": _csv_env("RESEARCH_SCHEDULE_LENSES"),
        "scheduler_tools": _csv_env("RESEARCH_SCHEDULE_TOOLS"),
    })
    sched_cfg = settings_store.scheduler_config()

    research_scheduler: ResearchScheduler | None = None
    if sched_cfg["enabled"]:
        if not os.environ.get("DEEPSEEK_API_KEY"):
            logger.info("research scheduler skipped: DEEPSEEK_API_KEY not set")
        else:
            orch = build_orchestrator()
            if orch is not None:
                research_scheduler = ResearchScheduler(
                    orchestrator=orch,
                    interval_minutes=sched_cfg["interval_minutes"],
                    lenses=sched_cfg["lenses"],
                    tools=sched_cfg["tools"],
                )
                research_scheduler.start()
                logger.info(
                    "research scheduler started (interval %s min)",
                    research_scheduler.interval_minutes,
                )
    else:
        logger.info("research scheduler disabled (settings store)")
    init_research(broadcast_fn=_research_broadcast, scheduler=research_scheduler)
    init_settings(scheduler=research_scheduler)

    # ── Knowledge store + session log (Phase 4) ────────────────────────────
    knowledge_store = KnowledgeStore("data/knowledge.db")
    app.state.knowledge_store = knowledge_store

    def _knowledge_broadcast(data: dict) -> None:
        try:
            asyncio.create_task(ws_manager.broadcast("knowledge", data))
        except Exception:
            logger.exception("knowledge broadcast failed")

    init_knowledge(store=knowledge_store, broadcast_fn=_knowledge_broadcast)

    session_log = SessionLog("data/sessions.db")
    app.state.session_log = session_log
    session_mode = getattr(app.state, "mode", None) or "OBSERVER"
    _session_id = session_log.start(session_mode)
    logger.info("session %s started (mode=%s)", _session_id, session_mode)

    trade_ledger = TradeLedger("data/ledger.db")
    app.state.trade_ledger = trade_ledger
    app.state.current_session_id = _session_id
    _ledger_recorder = LedgerRecorder(
        trade_ledger, lambda: getattr(app.state, "current_session_id", None)
    )
    _ledger_recorder.subscribe(_event_bus)

    # ── Learning loop wiring (P4c): decisions + shadow voters into stores ────
    def _learning_regime_provider() -> dict | None:
        proj = getattr(app.state, "intelligence_projection", None)
        if proj is None:
            return None
        try:
            return proj.get_regime() or {}
        except Exception:
            return None

    shadow_loop = ShadowLoop(
        shadow_db_path="data/shadow.db",
        learning_db_path="data/learning.db",
        session_id_provider=lambda: getattr(app.state, "current_session_id", None),
        feature_provider=lambda: getattr(
            getattr(app.state, "feature_engine", None), "features", None
        ),
        regime_provider=_learning_regime_provider,
    )
    shadow_loop.register()
    shadow_loop.subscribe(_event_bus)
    app.state.shadow_loop = shadow_loop

    # ── Execution wiring (P4b): proposal queue + mode-routed placement ───────
    # OBSERVER = proposals only; PAPER → PaperTradingEngine; LIVE → broker
    # adapter (Fyers; typed gate + session-validity gate, D10).
    cfg = ConfigManager("configs/default.yaml").config
    # P3-4.1: Build realism models from config
    _pt_cfg = getattr(cfg, "paper_trading", None) or {}
    if isinstance(_pt_cfg, dict):
        _slippage_model = _pt_cfg.get("slippage_model", "none")
        _fees_model = _pt_cfg.get("fees_model", "none")
        _fill_prob = _pt_cfg.get("fill_probability", False)
        _margin_check = _pt_cfg.get("margin_check", False)
        _slip_bps_mkt = _pt_cfg.get("slippage_bps_market", 5)
        _slip_bps_lim = _pt_cfg.get("slippage_bps_limit", 2)
    else:
        _slippage_model = getattr(_pt_cfg, "slippage_model", "none")
        _fees_model = getattr(_pt_cfg, "fees_model", "none")
        _fill_prob = getattr(_pt_cfg, "fill_probability", False)
        _margin_check = getattr(_pt_cfg, "margin_check", False)
        _slip_bps_mkt = getattr(_pt_cfg, "slippage_bps_market", 5)
        _slip_bps_lim = getattr(_pt_cfg, "slippage_bps_limit", 2)

    from shettyxtreme.execution.paper_realism import (
        FeesModel, FillProbabilityModel, MarginPolicy, SlippageModel,
    )
    _slip_m = SlippageModel(bps_market=_slip_bps_mkt, bps_limit=_slip_bps_lim) if _slippage_model == "layered" else None
    _fees_m = FeesModel() if _fees_model == "india" else None
    _margin_m = MarginPolicy() if _margin_check else None
    _fill_prob_m = FillProbabilityModel() if _fill_prob else None

    paper_engine = PaperTradingEngine(
        event_bus=_event_bus,
        initial_capital=cfg.paper_trading_margin or 1_000_000.0,
        slippage_model=_slip_m,
        fees_model=_fees_m,
        margin_policy=_margin_m,
        fill_probability_model=_fill_prob_m,
        enable_margin_check=bool(_margin_check),
    )
    app.state.paper_engine = paper_engine

    def _live_adapter_provider():
        return getattr(app.state, "trading_adapter", None)

    mode_executor = ModeRoutingExecutor(
        paper_engine=paper_engine,
        mode_provider=get_mode_value,
        kill_switch_provider=is_kill_switch_armed,
        kill_gate=get_kill_switch_gate(),
        live_provider=_live_adapter_provider,
    )
    app.state.mode_executor = mode_executor

    def _portfolio_provider():
        from shettyxtreme.core.data_models import Position
        from shettyxtreme.intelligence.risk.risk_engine import Portfolio

        pos_proj = getattr(app.state, "position_projection", None)
        risk_proj = getattr(app.state, "risk_projection", None)
        positions = []
        if pos_proj is not None:
            for p in pos_proj.get():
                positions.append(Position(
                    symbol=p.get("symbol", ""),
                    exchange=p.get("exchange", "NSE"),
                    quantity=p.get("quantity", 0),
                    buy_avg=p.get("buy_avg", 0.0),
                    sell_avg=p.get("sell_avg", 0.0),
                    net_quantity=p.get("net_quantity", 0),
                    m2m=p.get("m2m", 0.0),
                    pnl=p.get("pnl", 0.0),
                    product=p.get("product", "NRML"),
                ))
        risk = risk_proj.get() if risk_proj is not None else {}
        # Unknown margin (None) → 0.0: the risk engine then rejects proposals
        # it cannot verify rather than admitting them on phantom capital.
        # PAPER-mode fallback: use paper engine's portfolio for margin source.
        margin_available = risk.get("margin_available")
        margin_used = risk.get("margin_used", 0.0)
        equity: float | None = None
        if margin_available is None and get_mode_value().upper() == "PAPER":
            paper = getattr(app.state, "paper_engine", None)
            if paper:
                paper_port = paper.get_portfolio()
                margin_available = paper_port.available_margin
                margin_used = getattr(paper_port, "total_margin_used", 0.0)
                equity = margin_available + margin_used
        elif margin_available is not None:
            # LIVE mode: compute equity from margin data when both available
            total = risk.get("margin_total")
            if total is not None:
                equity = float(total)
            elif margin_used > 0:
                equity = float(margin_used) + float(margin_available)
        return Portfolio(
            positions=positions,
            daily_pnl=risk.get("daily_pnl", 0.0),
            total_margin_used=margin_used if margin_used is not None else 0.0,
            available_margin=margin_available if margin_available is not None else 0.0,
            equity=equity,
        )

    execution_engine = ExecutionEngine(
        executor=mode_executor,
        risk_engine=RiskEngine(),
        portfolio_provider=_portfolio_provider,
        db_path="data/proposals.db",
        event_bus=_event_bus,
    )
    app.state.execution_engine = execution_engine

    # P3-4.3: wire the chain hint builder so proposals carry full leg detail
    # (strike, expiry, CE/PE, lot size, premium, SL, target, rationale, EV).
    # The chain/spot providers pull from app.state.options_chain (populated by
    # prime_options_chain after login) and the watchlist LTP cache.
    from shettyxtreme.execution.signal_bridge import make_chain_hint_builder

    def _chain_provider(symbol: str) -> list[dict[str, object]]:
        """Return cached option chain rows for *symbol* (sync callable)."""
        cached = getattr(app.state, "options_chain", {})
        entry = cached.get(symbol, {})
        contracts = entry.get("contracts", [])
        return contracts if isinstance(contracts, list) else []

    def _spot_provider(symbol: str) -> float | None:
        """Return the last-known spot price from the watchlist cache."""
        wl = getattr(app.state, "watchlist_projection", None)
        if wl is None:
            return None
        item = wl.get_item(symbol)
        if item is None:
            return None
        ltp = item.get("ltp", 0.0)
        return float(ltp) if ltp and ltp > 0 else None

    instrument_master = getattr(app.state, "instrument_master", None)
    chain_hint_builder = make_chain_hint_builder(
        instrument_master=instrument_master,
        chain_provider=_chain_provider,
        spot_provider=_spot_provider,
    )

    execution_bridge = ExecutionSignalBridge(
        engine=execution_engine,
        event_bus=_event_bus,
        hint_builder=chain_hint_builder,
        instrument_master=instrument_master,
    )
    await execution_bridge.start()
    app.state.execution_bridge = execution_bridge
    logger.info("Execution layer wired: proposals + chain hint builder (P3-4.3)")

    # ── Seed watchlist from YAML FIRST (before pipeline needs it) ───────────
    watchlist_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "configs" / "default_watchlist.yaml"
    symbol_map: dict[str, str] = {}
    if watchlist_path.exists():
        import yaml
        with open(watchlist_path, "r") as f:
            watchlist_data = yaml.safe_load(f)
        for idx in watchlist_data.get("default_watchlist", {}).get("indices", []):
            sec_id = str(idx["security_id"])
            name = idx.get("name", sec_id)
            exchange = idx.get("exchange", "NSE_FNO")
            watchlist_proj.add(name, exchange, security_id=sec_id)
            symbol_map[sec_id] = name
        logger.info(
            "Default watchlist seeded with %d instruments",
            len(watchlist_data.get("default_watchlist", {}).get("indices", [])),
        )
    else:
        logger.warning("Default watchlist not found at %s", watchlist_path)

    # ── Merge persisted watchlist (user-added symbols survive restarts) ─────
    from shettyxtreme.terminal.api.watchlist_router import _load_persisted_watchlist
    persisted = _load_persisted_watchlist()
    for sym, entry in persisted.items():
        if sym not in watchlist_proj.get():
            exchange = entry.get("exchange", "NSE")
            security_id = entry.get("security_id", sym)
            expiry = entry.get("expiry")
            lot_size = entry.get("lot_size")
            watchlist_proj.add(sym, exchange, security_id=security_id, expiry=expiry, lot_size=lot_size)
            symbol_map[security_id or sym] = sym
    if persisted:
        logger.info("Merged %d persisted watchlist entries", len(persisted))

    # ── Initialize Fyers adapters + market-data bridge (lifespan & post-login) ──
    wire_terminal_init(lambda: init_terminal_adapters(app, store, symbol_map))
    if store.is_token_valid():
        ok = await init_terminal_adapters(app, store, symbol_map)
        logger.info("Fyers adapters initialized at lifespan: %s", ok)

    # Configure HealthProjection with actual adapter references. The token
    # health provider reads the FyersSession (daily token, no silent refresh)
    # so a known-expired token reports honestly instead of object existence.
    def _token_health() -> bool:
        session = getattr(app.state, "fyers_session", None)
        return True if session is None else session.is_valid()

    health_proj.configure(
        event_bus=_event_bus,
        data_adapter=app.state.data_adapter,
        trading_adapter=app.state.trading_adapter,
        feature_engine=app.state.feature_engine,
        signal_engine=app.state.signal_engine,
        token_health_provider=_token_health,
    )

    yield
    logger.info("ShettyXtreme Terminal shutting down...")
    try:
        # ── Stop opportunity scanners ───────────────────────────────────────
        scanners = getattr(app.state, "scanners", [])
        for scanner in scanners:
            try:
                await scanner.stop()
            except Exception:
                logger.exception("Scanner stop failed: %s", type(scanner).__name__)
        if _intelligence_pipeline is not None:
            _intelligence_pipeline.unsubscribe()
        try:
            execution_bridge = getattr(app.state, "execution_bridge", None)
            if execution_bridge is not None:
                await execution_bridge.stop()
        except Exception:
            logger.exception("execution bridge stop failed")
        await regime_bridge.stop()
        await risk_bridge.stop()
        if research_scheduler is not None:
            research_scheduler.stop()
        try:
            session_log.end(_session_id)
        except Exception:
            logger.exception("session end failed")
        try:
            fills = trade_ledger.list(session_id=_session_id)
            outcome = session_outcome_label(fills)
            shadow_loop.evaluate_session(_session_id, outcome)
            logger.info(
                "session %s learning outcome: %s",
                _session_id,
                outcome.value if outcome is not None else "none",
            )
        except Exception:
            logger.exception("session learning evaluation failed")
        try:
            shadow_loop.close()
        except Exception:
            logger.exception("shadow loop close failed")
        knowledge_store.close()
        trade_ledger.close()
        greeks_store = getattr(app.state, "greeks_store", None)
        if greeks_store is not None:
            try:
                greeks_store.close()
            except Exception:
                logger.exception("greeks store close failed")
        analytics_store.close()
        hint_store = getattr(app.state, "hint_store", None)
        if hint_store is not None:
            try:
                hint_store.close()
            except Exception:
                logger.exception("hint store close failed")
        bar_builder = getattr(app.state, "bar_builder", None)
        data_adapter = getattr(app.state, "data_adapter", None)
        trading_adapter = getattr(app.state, "trading_adapter", None)
        if bar_builder:
            await bar_builder.stop()
        # FyersDataAdapter.disconnect() tears down both the HSM data socket
        # and the JSON order socket (F3).
        if data_adapter:
            await data_adapter.disconnect()
        if trading_adapter:
            await trading_adapter.disconnect()
        if _health_monitor:
            await _health_monitor.stop()
        if _margin_poller_task:
            _margin_poller_task.cancel()
        if _scanner_poller_task:
            _scanner_poller_task.cancel()
        try:
            scanner_store.close()
        except Exception:
            logger.exception("scanner store close failed")
        init_scanner_store(None)
        set_scanner_store(None)
        if _event_bus:
            await _event_bus.stop()
        if _event_bus_task:
            _event_bus_task.cancel()
    except Exception:
        logger.exception("shutdown teardown failed")


app = FastAPI(
    title="ShettyXtreme Terminal",
    version="0.16.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files (frontend) ────────────────────────────────────────────────
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(_static_dir), html=True),
        name="static",
    )

# ── Settings redirect (before settings_router include) ──────────────────────
@app.get("/settings")
async def settings_redirect():
    return RedirectResponse(url="/static/#/settings")

# ── Include routers ────────────────────────────────────────────────────────
app.include_router(watchlist_router)
app.include_router(symbols_router)
app.include_router(intelligence_router)
app.include_router(execution_router)
app.include_router(scanner_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(postback_router.router)
app.include_router(settings_router)
app.include_router(learning_router)
app.include_router(research_router)
app.include_router(knowledge_router)
app.include_router(analytics_router)
app.include_router(market_router)
app.include_router(v2_router)


# ── Root: redirect to the Svelte SPA ────────────────────────────────────────
@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/static/")


@app.get("/setup")
async def setup_redirect() -> RedirectResponse:
    return RedirectResponse(url="/static/#/setup")


# ── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for live data push.

    Clients receive ticks/signals/alerts/regime changes. Frames: "ping"
    keepalive; subscribe/unsubscribe {"type": ..., "topics": [...]}.
    Only local terminal origins may connect (F-EXEC-001).
    """
    if not ws_manager.is_origin_allowed(websocket.headers.get("origin")):
        # Close before accept → the client receives HTTP 403 (F-EXEC-001).
        await websocket.close(code=1008)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"topic":"pong","data":{}}')
                continue
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            topics = msg.get("topics")
            if not isinstance(topics, list) or not all(
                isinstance(t, str) for t in topics
            ):
                continue
            if msg.get("type") == "subscribe":
                await ws_manager.subscribe(websocket, topics)
            elif msg.get("type") == "unsubscribe":
                await ws_manager.unsubscribe(websocket, topics)
    except Exception:
        await ws_manager.disconnect(websocket)

# Alias for cleaner access
ShettyXtremeAPI = app
