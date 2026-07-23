"""FastAPI application for the ShettyXtreme terminal.

Lifespan: starts event bus, credential store, health monitor,
Dhan adapters, and ingestion pipeline.
Mounts static files and includes all routers.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import DhanOAuthHelper
from shettyxtreme.auth.health_monitor import TokenHealthMonitor
from shettyxtreme.auth.validator import CredentialValidator
from shettyxtreme.core.event_bus.event_bus import EventBus
from shettyxtreme.core.storage.time_series_store import TimeSeriesStore
from shettyxtreme.data.ingestion import IngestionPipeline
from shettyxtreme.integration.dhan.data_adapter import DhanDataAdapter
from shettyxtreme.integration.dhan.trading_adapter import DhanTradingAdapter
from shettyxtreme.terminal.api.auth_router import init_auth, router as auth_router
from shettyxtreme.terminal.api.execution_router import router as execution_router
from shettyxtreme.terminal.api.health_router import router as health_router
from shettyxtreme.terminal.api.intelligence_router import router as intelligence_router
from shettyxtreme.terminal.api.postback_router import router as postback_router
from shettyxtreme.terminal.api.scanner_router import router as scanner_router
from shettyxtreme.terminal.api.settings_router import init_settings, router as settings_router
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
_event_bus: EventBus | None = None
_event_bus_task: asyncio.Task | None = None
_health_monitor: TokenHealthMonitor | None = None
_trading_adapter: DhanTradingAdapter | None = None
_data_adapter: DhanDataAdapter | None = None
_ingestion_pipeline: IngestionPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle."""
    global _event_bus, _event_bus_task, _health_monitor, _trading_adapter, _data_adapter, _ingestion_pipeline
    logger.info("ShettyXtreme Terminal starting up...")

    store = CredentialStore.load() or CredentialStore()
    oauth = DhanOAuthHelper()
    validator = CredentialValidator()
    init_auth(store, oauth, validator)
    init_settings(store, oauth, validator)

    _event_bus = EventBus()
    _event_bus_task = asyncio.create_task(_event_bus.start())
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

    # Only proceed with Dhan adapters if credentials are valid
    if store.is_trading_valid() and store.data_access_token:
        try:
            _trading_adapter = DhanTradingAdapter(
                client_id=store.trading_client_id,
                access_token=store.trading_access_token,
            )
            app.state.trading_adapter = _trading_adapter
            logger.info("DhanTradingAdapter initialized")
        except Exception as exc:
            logger.error("Failed to initialize DhanTradingAdapter: %s", exc)

    # Seed watchlist projection from default_watchlist.yaml regardless of credentials
    watchlist_path = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "default_watchlist.yaml"
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

    if store.is_data_valid() and store.data_access_token:
        try:
            _data_adapter = DhanDataAdapter(
                client_id=store.data_client_id,
                access_token=store.data_access_token,
            )
            app.state.data_adapter = _data_adapter
            logger.info("DhanDataAdapter initialized")

            # Start ingestion pipeline with default watchlist
            ts_store = TimeSeriesStore()
            _ingestion_pipeline = IngestionPipeline(
                event_bus=_event_bus,
                ts_store=ts_store,
                dhan_client_id=store.data_client_id,
                dhan_access_token=store.data_access_token,
                exchange="NSE",
            )
            app.state.ingestion_pipeline = _ingestion_pipeline

            # Start streaming existing watchlist
            watchlist_data_proj = watchlist_proj.get()
            if watchlist_data_proj:
                symbols = list(watchlist_data_proj.keys())
                await _ingestion_pipeline.start(symbols)
                logger.info("IngestionPipeline started with symbols: %s", symbols)
        except Exception as exc:
            logger.error("Failed to initialize DhanDataAdapter or IngestionPipeline: %s", exc)

    # Configure HealthProjection with actual adapter references
    health_proj.configure(
        event_bus=_event_bus,
        data_adapter=app.state.data_adapter,
        trading_adapter=app.state.trading_adapter,
    )

    yield

    logger.info("ShettyXtreme Terminal shutting down...")
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
    version="0.3.0",
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
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

# ── Include routers ────────────────────────────────────────────────────────
app.include_router(watchlist_router)
app.include_router(intelligence_router)
app.include_router(execution_router)
app.include_router(scanner_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(postback_router)
app.include_router(settings_router)


# ── Root: redirect to terminal HTML ─────────────────────────────────────────
@app.get("/")
async def root() -> RedirectResponse:
    """Root endpoint — redirect to terminal HTML."""
    return RedirectResponse(url="/static/index.html")


@app.get("/setup")
async def setup_redirect() -> RedirectResponse:
    """Setup endpoint — redirect to setup wizard."""
    return RedirectResponse(url="/static/setup.html")


# ── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for live data push.

    Clients connect and receive: ticks, signals, alerts, regime changes.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, listen for client commands
            data = await websocket.receive_text()
            # Future: handle client-side subscriptions
            if data == "ping":
                await websocket.send_text('{"topic":"pong","data":{}}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)

# Alias for cleaner access
ShettyXtremeAPI = app
