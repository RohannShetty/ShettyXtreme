"""Settings router — risk limits, theme, scheduler (Phase 7 Wave 3).

Backend for the settings form. Values persist in a SQLite KV store
(``core/settings.py``); the risk engine, bus bridge, projections and the
execution router all read the same store, so the values exposed here are
the single source of truth (no more hardcoded ``-5000.0`` / ``5``).

Endpoints:
  GET/PUT /api/settings          — risk limits + theme (+ scheduler summary)
  GET/PUT /api/settings/scheduler — research scheduler config; PUT applies
                                     to the live scheduler (restart if the
                                     interval changed)
  GET/PUT /api/settings/theme    — theme; PUT broadcasts to WS clients

Changes are announced over the EventBus: a CONFIG_CHANGED event, plus a
RISK_DECISION event carrying the new caps so the risk projection (and
``/api/execution/risk``) reflects them immediately.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from shettyxtreme.core.event_bus.event_bus import Event, Topic
from shettyxtreme.core.settings import SettingsError, SettingsStore, get_settings_store
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.terminal.api import ws_bridge
from shettyxtreme.terminal.api.research_router import build_orchestrator, init_research

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

#: Live research scheduler handle, wired by the lifespan via init_settings.
#: None when no scheduler is running (env-gated startup / no DEEPSEEK_API_KEY).
_scheduler: ResearchScheduler | None = None


def init_settings(scheduler: ResearchScheduler | None) -> None:
    """Wire the live research scheduler handle (the lifespan calls this)."""
    global _scheduler
    _scheduler = scheduler


# ── Request / response models ──────────────────────────────────────────────
class SettingsUpdate(BaseModel):
    loss_limit: float | None = None
    max_positions: int | None = None
    theme: str | None = None


class SchedulerUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: float | None = None
    lenses: list[str] | None = None
    tools: list[str] | None = None


class SchedulerResponse(BaseModel):
    #: Configured intent (persisted). May be True while nothing is ticking
    #: (e.g. DEEPSEEK_API_KEY not set) — see ``running`` for the live state.
    enabled: bool
    interval_minutes: float
    lenses: list[str] | None
    tools: list[str] | None
    #: Live state: is a loop actually running right now?
    running: bool = False
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_result: str | None = None


class SettingsResponse(BaseModel):
    loss_limit: float
    max_positions: int
    theme: str
    scheduler: SchedulerResponse


class ThemeResponse(BaseModel):
    theme: str


class ThemeUpdate(BaseModel):
    theme: str


# ── Helpers ────────────────────────────────────────────────────────────────
def _scheduler_snapshot(store: SettingsStore) -> SchedulerResponse:
    """Stored config overlaid with live handle status (honest intent+reality)."""
    cfg = store.scheduler_config()
    cfg["running"] = False
    if _scheduler is not None:
        cfg["running"] = _scheduler.enabled
        cfg["next_run_at"] = _scheduler.next_run_at
        cfg["last_run_at"] = _scheduler.last_run_at
        cfg["last_result"] = _scheduler.last_result
    return SchedulerResponse(**cfg)


def _settings_response(store: SettingsStore) -> SettingsResponse:
    return SettingsResponse(
        loss_limit=store.loss_limit(),
        max_positions=store.max_positions(),
        theme=store.theme(),
        scheduler=_scheduler_snapshot(store),
    )


async def _announce_changes(
    request: Request,
    updates: dict[str, Any],
    store: SettingsStore,
) -> None:
    """Publish config-change events so live components update immediately.

    - CONFIG_CHANGED carries the raw updates (execution_router uses the
      same topic for mode switches).
    - A RISK_DECISION with the new caps refreshes RiskProjection, so
      ``/api/execution/risk`` and the UI show the new limits right away.
    """
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None:
        return
    try:
        await bus.publish(Event(
            topic=Topic.CONFIG_CHANGED,
            data={"settings": updates},
            source="settings_router",
        ))
        if "loss_limit" in updates or "max_positions" in updates:
            await bus.publish(Event(
                topic=Topic.RISK_DECISION,
                data={
                    "loss_limit": store.loss_limit(),
                    "max_positions": store.max_positions(),
                },
                source="settings_router",
            ))
    except Exception:
        logger.exception("settings change broadcast failed")


def _start_scheduler_from_config(cfg: dict[str, Any]) -> None:
    """Spin up a scheduler from persisted config (needs DEEPSEEK_API_KEY)."""
    global _scheduler
    orch = build_orchestrator()
    if orch is None:
        logger.info("settings: scheduler not started — DEEPSEEK_API_KEY not set")
        return
    _scheduler = ResearchScheduler(
        orchestrator=orch,
        interval_minutes=cfg["interval_minutes"],
        lenses=cfg["lenses"],
        tools=cfg["tools"],
    )
    _scheduler.start()
    init_research(scheduler=_scheduler)
    logger.info(
        "settings: research scheduler started (interval %s min)",
        cfg["interval_minutes"],
    )


def _apply_scheduler() -> None:
    """Restart / stop / start the live scheduler to match persisted config.

    Restart is required only when the interval changed; lens/tool edits on
    a running loop mutate the handle in place.
    """
    global _scheduler
    store = get_settings_store()
    cfg = store.scheduler_config()
    if _scheduler is None:
        if cfg["enabled"]:
            _start_scheduler_from_config(cfg)
        return
    _scheduler.lenses = cfg["lenses"]
    _scheduler.tools = cfg["tools"]
    if not cfg["enabled"]:
        _scheduler.stop()
        _scheduler = None
        init_research(scheduler=None)
        logger.info("settings: research scheduler stopped")
        return
    if _scheduler.enabled and abs(_scheduler.interval_minutes - cfg["interval_minutes"]) < 1e-9:
        return  # already running at the requested interval
    _scheduler.stop()
    _scheduler.interval_minutes = cfg["interval_minutes"]
    _scheduler.start()
    init_research(scheduler=_scheduler)
    logger.info(
        "settings: research scheduler restarted (interval %s min)",
        cfg["interval_minutes"],
    )


# ── Settings (risk limits + theme) ─────────────────────────────────────────
@router.get("", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """Return all settings (risk limits, theme, scheduler summary)."""
    return _settings_response(get_settings_store())


@router.put("", response_model=SettingsResponse)
async def update_settings(payload: SettingsUpdate, request: Request) -> SettingsResponse:
    """Update risk limits / theme. Invalid values → 400, store untouched."""
    store = get_settings_store()
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="no settings provided")
    try:
        store.update(updates)
    except SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _announce_changes(request, updates, store)
    return _settings_response(store)


# ── Theme ──────────────────────────────────────────────────────────────────
@router.get("/theme", response_model=ThemeResponse)
async def get_theme() -> ThemeResponse:
    """Return the current theme (dark / light)."""
    return ThemeResponse(theme=get_settings_store().theme())


@router.put("/theme", response_model=ThemeResponse)
async def update_theme(payload: ThemeUpdate) -> ThemeResponse:
    """Set the theme and broadcast it to connected WS clients."""
    store = get_settings_store()
    try:
        store.update({"theme": payload.theme})
    except SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    theme = store.theme()
    await ws_bridge.broadcast("theme", {"theme": theme})
    return ThemeResponse(theme=theme)


# ── Research scheduler ─────────────────────────────────────────────────────
@router.get("/scheduler", response_model=SchedulerResponse)
async def get_scheduler() -> SchedulerResponse:
    """Return the configured scheduler state + live running status."""
    return _scheduler_snapshot(get_settings_store())


@router.put("/scheduler", response_model=SchedulerResponse)
async def update_scheduler(payload: SchedulerUpdate) -> SchedulerResponse:
    """Update scheduler config and apply it to the live scheduler.

    Restarts the loop when the interval changes; stops it when disabled;
    starts it when enabled (requires DEEPSEEK_API_KEY at runtime).
    """
    store = get_settings_store()
    # The wire model uses the short field names; the store keys carry the
    # ``scheduler_`` prefix.
    _KEY_MAP = {
        "enabled": "scheduler_enabled",
        "interval_minutes": "scheduler_interval_minutes",
        "lenses": "scheduler_lenses",
        "tools": "scheduler_tools",
    }
    updates = {
        _KEY_MAP[key]: value
        for key, value in payload.model_dump(exclude_none=True).items()
    }
    if not updates:
        raise HTTPException(status_code=400, detail="no scheduler settings provided")
    try:
        store.update(updates)
    except SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _apply_scheduler()
    return _scheduler_snapshot(store)
