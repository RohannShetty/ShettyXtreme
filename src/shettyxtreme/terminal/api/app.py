"""FastAPI application for the ShettyXtreme terminal.

Lifespan: starts event bus, credential store, health monitor,
Dhan adapters, and ingestion pipeline.
Mounts static files and includes all routers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import DhanOAuthHelper
from shettyxtreme.auth.health_monitor import TokenHealthMonitor
from shettyxtreme.auth.validator import CredentialValidator
from shettyxtreme.core.event_bus.event_bus import EventBus
from shettyxtreme.core.storage.time_series_store import TimeSeriesStore
from shettyxtreme.data.ingestion import IngestionPipeline
from shettyxtreme.execution.ledger import TradeLedger
from shettyxtreme.execution.ledger_recorder import LedgerRecorder
from shettyxtreme.integration.dhan.data_adapter import DhanDataAdapter
from shettyxtreme.integration.dhan.trading_adapter import DhanTradingAdapter
from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.terminal.api.auth_router import init_auth
from shettyxtreme.terminal.api.auth_router import router as auth_router
from shettyxtreme.terminal.api.execution_router import router as execution_router
from shettyxtreme.terminal.api.health_router import router as health_router
from shettyxtreme.terminal.api.intelligence_router import router as intelligence_router
from shettyxtreme.terminal.api.learning_router import router as learning_router
from shettyxtreme.terminal.api.research_router import router as research_router
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.tools import set_data_source
from shettyxtreme.terminal.api.research_router import build_orchestrator, init_research
from shettyxtreme.terminal.api.research_source import ProjectionDataSource
from shettyxtreme.intelligence.regime.bus_bridge import RegimeBusBridge
from shettyxtreme.intelligence.risk.bus_bridge import RiskBusBridge
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
_trading_adapter: DhanTradingAdapter | None = None
_data_adapter: DhanDataAdapter | None = None
_ingestion_pipeline: IngestionPipeline | None = None
_intelligence_pipeline: IntelligencePipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle."""
    global _event_bus, _event_bus_task, _health_monitor, _trading_adapter, _data_adapter, _ingestion_pipeline
    global _intelligence_pipeline
    logger.info("ShettyXtreme Terminal starting up...")

    store = CredentialStore.load() or CredentialStore()
    oauth = DhanOAuthHelper()
    validator = CredentialValidator()
    init_auth(store, oauth, validator)

    _event_bus = EventBus()
    _event_bus_task = asyncio.create_task(_event_bus.start())
    postback_router.set_event_bus(_event_bus)
    _health_monitor = TokenHealthMonitor(store, _event_bus)
    await _health_monitor.start()

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
    app.state.ingestion_pipeline = None
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
                    interval = float(
                        os.environ.get("RESEARCH_SCHEDULE_INTERVAL_MINUTES", "60")
                    )
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

    # ── Seed watchlist from YAML FIRST (before pipeline needs it) ───────────
    watchlist_path = Path(__file__).resolve().parent.parent.parent.parent.parent / "configs" / "default_watchlist.yaml"
    if watchlist_path.exists():
        import yaml
        with open(watchlist_path, "r") as f:
            watchlist_data = yaml.safe_load(f)
        for idx in watchlist_data.get("default_watchlist", {}).get("indices", []):
            sec_id = idx["security_id"]
            exchange = idx.get("exchange", "NSE_FNO")
            watchlist_proj.add(str(sec_id), exchange)
        logger.info(
            "Default watchlist seeded with %d instruments",
            len(watchlist_data.get("default_watchlist", {}).get("indices", [])),
        )
    else:
        logger.warning("Default watchlist not found at %s", watchlist_path)

    # ── Initialize Dhan adapters and start data pipeline ─────────────────────
    if store.is_token_valid():
        try:
            _trading_adapter = DhanTradingAdapter(
                client_id=store.client_id,
                access_token=store.access_token,
            )
            app.state.trading_adapter = _trading_adapter
            logger.info("DhanTradingAdapter initialized")
        except Exception as exc:
            logger.error("Failed to initialize DhanTradingAdapter: %s", exc)

        try:
            _data_adapter = DhanDataAdapter(
                client_id=store.client_id,
                access_token=store.access_token,
                data_access_token=store.data_access_token,
            )
            app.state.data_adapter = _data_adapter
            logger.info("DhanDataAdapter initialized")

            # Group watchlist symbols by exchange for correct MarketFeed subscription
            watchlist_data_proj = watchlist_proj.get()
            if watchlist_data_proj:
                # Group symbols by their exchange segment
                exchange_groups: dict[str, list[str]] = {}
                for sym, info in watchlist_data_proj.items():
                    exch = info.get("exchange", "NSE_FNO")
                    # Map exchange names to Dhan feed segments
                    feed_segment = {"NSE_FNO": "NSE_FNO", "NSE": "NSE_EQ", "BSE": "BSE_EQ"}.get(exch, exch)
                    exchange_groups.setdefault(feed_segment, []).append(sym)

                ts_store = TimeSeriesStore()
                # Start one pipeline per exchange segment
                for feed_segment, symbols in exchange_groups.items():
                    # Map feed segment back to exchange name for IngestionPipeline
                    pipeline_exchange = {"NSE_FNO": "NFO", "NSE_EQ": "NSE", "BSE_EQ": "BSE"}.get(feed_segment, "NSE")
                    _ingestion_pipeline = IngestionPipeline(
                        event_bus=_event_bus,
                        ts_store=ts_store,
                        dhan_client_id=store.client_id,
                        dhan_access_token=store.access_token,
                        exchange=pipeline_exchange,
                    )
                    app.state.ingestion_pipeline = _ingestion_pipeline
                    await _ingestion_pipeline.start(symbols)
                    logger.info("IngestionPipeline started for %s with symbols: %s", feed_segment, symbols)
            else:
                logger.warning("Watchlist empty — pipeline not started")
        except Exception as exc:
            logger.error("Failed to initialize DhanDataAdapter or IngestionPipeline: %s", exc)

    # Configure HealthProjection with actual adapter references
    health_proj.configure(
        event_bus=_event_bus,
        data_adapter=app.state.data_adapter,
        trading_adapter=app.state.trading_adapter,
        feature_engine=app.state.feature_engine,
        signal_engine=app.state.signal_engine,
    )

    yield

    logger.info("ShettyXtreme Terminal shutting down...")
    if _intelligence_pipeline is not None:
        _intelligence_pipeline.unsubscribe()
    await regime_bridge.stop()
    await risk_bridge.stop()
    if research_scheduler is not None:
        research_scheduler.stop()
    try:
        session_log.end(_session_id)
    except Exception:
        logger.exception("session end failed")
    knowledge_store.close()
    trade_ledger.close()
    if _ingestion_pipeline:
        await _ingestion_pipeline.stop()
    if _data_adapter:
        await _data_adapter.disconnect()
    if _trading_adapter:
        await _trading_adapter.disconnect()
    if _health_monitor:
        await _health_monitor.stop()
    if _event_bus:
        await _event_bus.stop()
    if _event_bus_task:
        _event_bus_task.cancel()


app = FastAPI(
    title="ShettyXtreme Terminal",
    version="0.11.0",
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


# ── Root: redirect to the Svelte SPA ────────────────────────────────────────
@app.get("/")
async def root() -> RedirectResponse:
    """Root endpoint — redirect to the Svelte SPA."""
    return RedirectResponse(url="/static/")


@app.get("/setup")
async def setup_redirect() -> RedirectResponse:
    """Setup endpoint — redirect to the Svelte setup view."""
    return RedirectResponse(url="/static/#/setup")


# ── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for live data push.

    Clients connect and receive: ticks, signals, alerts, regime changes.
    Client frames: "ping" (plain text) keeps the connection warm;
    {"type": "subscribe", "topics": [...]} / {"type": "unsubscribe",
    "topics": [...]} declare per-client topic interest. Clients that never
    subscribe receive all topics (backward compatible).
    """
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
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)

# Alias for cleaner access
ShettyXtremeAPI = app
