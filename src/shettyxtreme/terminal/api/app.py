"""FastAPI application for the ShettyXtreme terminal.

Lifespan: starts event bus, credential store, health monitor.
Mounts static files and includes all routers.
"""
from __future__ import annotations

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
from shettyxtreme.terminal.api.auth_router import init_auth, router as auth_router
from shettyxtreme.terminal.api.execution_router import router as execution_router
from shettyxtreme.terminal.api.health_router import router as health_router
from shettyxtreme.terminal.api.intelligence_router import router as intelligence_router
from shettyxtreme.terminal.api.postback_router import router as postback_router
from shettyxtreme.terminal.api.scanner_router import router as scanner_router
from shettyxtreme.terminal.api.settings_router import init_settings, router as settings_router
from shettyxtreme.terminal.api.watchlist_router import router as watchlist_router
from shettyxtreme.terminal.api.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()
_event_bus: EventBus | None = None
_health_monitor: TokenHealthMonitor | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle."""
    global _event_bus, _health_monitor
    logger.info("ShettyXtreme Terminal starting up...")

    store = CredentialStore.load() or CredentialStore()
    oauth = DhanOAuthHelper()
    validator = CredentialValidator()
    init_auth(store, oauth, validator)
    init_settings(store, oauth, validator)

    _event_bus = EventBus()
    _health_monitor = TokenHealthMonitor(store, _event_bus)
    await _health_monitor.start()

    yield

    logger.info("ShettyXtreme Terminal shutting down...")
    if _health_monitor:
        await _health_monitor.stop()


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
