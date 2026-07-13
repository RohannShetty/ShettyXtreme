"""FastAPI application for the ShettyXtreme terminal.

Lifespan: starts event bus, mock data adapters, and feature engine.
Mounts static files and includes all routers.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from shettyxtreme.terminal.api.execution_router import router as execution_router
from shettyxtreme.terminal.api.health_router import router as health_router
from shettyxtreme.terminal.api.intelligence_router import router as intelligence_router
from shettyxtreme.terminal.api.scanner_router import router as scanner_router
from shettyxtreme.terminal.api.watchlist_router import router as watchlist_router
from shettyxtreme.terminal.api.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle."""
    logger.info("ShettyXtreme Terminal starting up...")
    # In production: start event bus, data adapters, feature engine here
    yield
    logger.info("ShettyXtreme Terminal shutting down...")


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


# ── Root: serve terminal HTML ──────────────────────────────────────────────
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint — returns API info (frontend served at /static/index.html)."""
    return {
        "name": "ShettyXtreme Terminal API",
        "version": "0.3.0",
        "docs": "/docs",
        "frontend": "/static/index.html",
    }


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
