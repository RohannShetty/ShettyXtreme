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
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
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
from shettyxtreme.terminal.api.knowledge_router import init_knowledge
from shettyxtreme.terminal.api.knowledge_router import router as knowledge_router
from shettyxtreme.terminal.api.scanner_data import GapDetector, LogCollector, ClusterDetector
from shettyxtreme.terminal.api.scanner_router import init_scanner_data
from shettyxtreme.terminal.api.scanner_router import router as scanner_router
from shettyxtreme.terminal.api.settings_router import router as settings_router
from shettyxtreme.terminal.api.watchlist_router import router as watchlist_router
from shettyxtreme.terminal.api.ws_manager import WebSocketManager
from shettyxtreme.terminal.projections import (
    AlertProjection,
    HealthProjection,
    IntelligenceProjection,
    PositionProjection,
    RiskProjection,
    WatchlistProjection,
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


async def _margin_poll_loop(app: FastAPI) -> None:
    """Poll trading_adapter.get_margin() and publish real available margin.

    Margin starts UNKNOWN (None). We only publish a number once the broker
    reports one; on failure we publish nothing, so the risk projection keeps
    its previous honest value instead of a fabricated default.
    """
    while True:
        try:
            adapter = getattr(app.state, "trading_adapter", None)
            if adapter is not None and hasattr(adapter, "get_margin"):
                raw = await adapter.get_margin()
                payload = raw.get("data", raw) if isinstance(raw, dict) else {}
                available: float | None = None
                if isinstance(payload, dict):
                    for key in _MARGIN_AVAILABLE_KEYS:
                        value = payload.get(key)
                        if value is not None:
                            try:
                                available = float(value)
                                break
                            except (TypeError, ValueError):
                                continue
                if available is not None and _event_bus is not None:
                    await _event_bus.publish(Event(
                        topic=Topic.RISK_DECISION,
                        data={"margin_available": available},
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

    # ── Research: data source, WS broadcast, scheduler (3C) ────────────────
    set_data_source(ProjectionDataSource(app.state))

    def _research_broadcast(data: dict) -> None:
        try:
            asyncio.create_task(ws_manager.broadcast("research", data))
        except Exception:
            logger.exception("research broadcast failed")

    research_scheduler: ResearchScheduler | None = None
    if os.environ.get("RESEARCH_SCHEDULE_ENABLED") == "1":
        if not os.environ.get("DEEPSEEK_API_KEY"):
            logger.info("research scheduler skipped: DEEPSEEK_API_KEY not set")
        else:
            orch = build_orchestrator()
            if orch is not None:
                def _csv_env(name: str) -> list[str] | None:
                    raw = os.environ.get(name, "")
                    return [x.strip() for x in raw.split(",") if x.strip()] or None

                try:
                    interval = float(os.environ.get("RESEARCH_SCHEDULE_INTERVAL_MINUTES", "60"))
                except ValueError:
                    interval = 60.0
                if interval <= 0:
                    interval = 60.0

                research_scheduler = ResearchScheduler(
                    orchestrator=orch,
                    interval_minutes=interval,
                    lenses=_csv_env("RESEARCH_SCHEDULE_LENSES"),
                    tools=_csv_env("RESEARCH_SCHEDULE_TOOLS"),
                )
                research_scheduler.start()
                logger.info(
                    "research scheduler started (interval %s min)",
                    research_scheduler.interval_minutes,
                )
    else:
        logger.info("research scheduler disabled (RESEARCH_SCHEDULE_ENABLED not set)")
    init_research(broadcast_fn=_research_broadcast, scheduler=research_scheduler)

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
    paper_engine = PaperTradingEngine(event_bus=_event_bus)
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
        margin_available = risk.get("margin_available")
        return Portfolio(
            positions=positions,
            daily_pnl=risk.get("daily_pnl", 0.0),
            total_margin_used=risk.get("margin_used", 0.0),
            available_margin=margin_available if margin_available is not None else 0.0,
        )

    execution_engine = ExecutionEngine(
        executor=mode_executor,
        risk_engine=RiskEngine(),
        portfolio_provider=_portfolio_provider,
        db_path="data/proposals.db",
    )
    app.state.execution_engine = execution_engine

    execution_bridge = ExecutionSignalBridge(
        engine=execution_engine,
        event_bus=_event_bus,
    )
    await execution_bridge.start()
    app.state.execution_bridge = execution_bridge
    logger.info("Execution layer wired: proposals + mode-routed placement")

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
        if _event_bus:
            await _event_bus.stop()
        if _event_bus_task:
            _event_bus_task.cancel()
    except Exception:
        logger.exception("shutdown teardown failed")


app = FastAPI(
    title="ShettyXtreme Terminal",
    version="0.13.0",
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
