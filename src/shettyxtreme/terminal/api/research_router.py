"""Research router — run briefers, tools, decisions, scoring (Phase 3B + 3C).

The orchestrator is created lazily on first run; without DEEPSEEK_API_KEY
the run endpoint returns 503 with an explicit message. DB failures on
read paths degrade to empty/404 payloads — never 500. Broadcasts go out
on WS topic `research` via the broadcast_fn wired in lifespan.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
)
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, OutcomeTracker
from shettyxtreme.research.briefs import ResearchBrief
from shettyxtreme.research.lenses import list_lenses
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import DeepSeekProvider
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.store import (
    AlreadyDecidedError,
    BriefNotDecidedError,
    ResearchStore,
)
from shettyxtreme.research.tools import list_tools
from shettyxtreme.terminal.api.models import (
    LensInfoResponse,
    LensListResponse,
    ResearchBriefListResponse,
    ResearchBriefResponse,
    ResearchDecisionResponse,
    ResearchOutcomeRequest,
    ResearchOutcomeResponse,
    ResearchRunItem,
    ResearchRunRequest,
    ResearchRunResponse,
    ResearchSchedulerResponse,
    ResearchScoringItem,
    ResearchScoringResponse,
    ResearchToolResponse,
    ResearchToolsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

RESEARCH_DB_PATH = "data/research.db"
LEARNING_DB_PATH = "data/learning.db"
_ORCHESTRATOR: ResearchOrchestrator | None = None
_broadcast_fn: Callable[[dict], None] | None = None
_SCHEDULER: ResearchScheduler | None = None


def init_research(
    broadcast_fn: Callable[[dict], None] | None = None,
    scheduler: ResearchScheduler | None = None,
) -> None:
    """Wire WS broadcast + the scheduled-run handle (lifespan calls this)."""
    global _broadcast_fn, _SCHEDULER
    _broadcast_fn = broadcast_fn
    _SCHEDULER = scheduler


def _broadcast(event: dict) -> None:
    if _broadcast_fn is None:
        return
    try:
        _broadcast_fn(event)
    except Exception:
        logger.exception("research broadcast failed")


def _brief_response(brief: ResearchBrief) -> ResearchBriefResponse:
    return ResearchBriefResponse(**brief.model_dump(), expired=brief.is_expired())


def _on_brief(brief: ResearchBrief) -> None:
    _broadcast({"event": "new_brief", "data": _brief_response(brief).model_dump()})


def build_orchestrator() -> ResearchOrchestrator | None:
    """Build a key-gated orchestrator wired for broadcasts (router + scheduler)."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return None
    return ResearchOrchestrator(
        provider=DeepSeekProvider(),
        store=ResearchStore(RESEARCH_DB_PATH),
        on_brief=_on_brief,
    )


def _get_orchestrator() -> ResearchOrchestrator | None:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is not None:
        return _ORCHESTRATOR
    _ORCHESTRATOR = build_orchestrator()
    return _ORCHESTRATOR


def _open_store() -> ResearchStore:
    """Open the research store; propagate exceptions to callers."""
    return ResearchStore(RESEARCH_DB_PATH)


@router.get("/lenses", response_model=LensListResponse)
async def lenses() -> LensListResponse:
    """Available briefer lenses."""
    return LensListResponse(
        lenses=[
            LensInfoResponse(name=l.name, description=l.description)
            for l in list_lenses()
        ]
    )


@router.get("/tools", response_model=ResearchToolsResponse)
async def tools() -> ResearchToolsResponse:
    """Read-only tool definitions (single source for REST + function calling)."""
    return ResearchToolsResponse(
        tools=[
            ResearchToolResponse(
                name=t.name, description=t.description, params_schema=t.params_schema
            )
            for t in list_tools()
        ]
    )


@router.get("/scheduler", response_model=ResearchSchedulerResponse)
async def scheduler_status() -> ResearchSchedulerResponse:
    """Scheduler status; enabled only when the lifespan started it."""
    if _SCHEDULER is None:
        return ResearchSchedulerResponse()
    return ResearchSchedulerResponse(
        enabled=_SCHEDULER.enabled,
        interval_minutes=_SCHEDULER.interval_minutes,
        lenses=_SCHEDULER.lenses,
        tools=_SCHEDULER.tools,
        next_run_at=_SCHEDULER.next_run_at,
        last_run_at=_SCHEDULER.last_run_at,
        last_result=_SCHEDULER.last_result,
    )


@router.post("/run", response_model=ResearchRunResponse)
async def run(req: ResearchRunRequest) -> ResearchRunResponse:
    """Run one research pass across the requested (or all) lenses."""
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY is not set — set it to enable research runs",
        )
    if req.lenses:
        valid = {l.name for l in list_lenses()}
        unknown = [n for n in req.lenses if n not in valid]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown lenses: {unknown}; valid: {sorted(valid)}",
            )
    if req.tools:
        valid_tools = {t.name for t in list_tools()}
        unknown_tools = [n for n in req.tools if n not in valid_tools]
        if unknown_tools:
            raise HTTPException(
                status_code=400,
                detail=f"unknown tools: {unknown_tools}; valid: {sorted(valid_tools)}",
            )
    results = await orch.run(lenses=req.lenses, sources=req.context, tools=req.tools)
    items = [
        ResearchRunItem(
            lens=r.lens,
            brief=_brief_response(r.brief) if r.brief else None,
            error=r.error,
        )
        for r in results
    ]
    return ResearchRunResponse(results=items)


@router.get("/briefs", response_model=ResearchBriefListResponse)
async def list_briefs(
    status: str | None = None, lens: str | None = None
) -> ResearchBriefListResponse:
    """List briefs, newest first, optionally filtered."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        return ResearchBriefListResponse()
    try:
        return ResearchBriefListResponse(
            briefs=[_brief_response(b) for b in store.list(status=status, lens=lens)]
        )
    except Exception as exc:
        logger.warning("Research list failed: %s", exc)
        return ResearchBriefListResponse()
    finally:
        store.close()


@router.get("/briefs/{brief_id}", response_model=ResearchBriefResponse)
async def get_brief(brief_id: str) -> ResearchBriefResponse:
    """Fetch one brief by id."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        brief = store.get(brief_id)
    finally:
        store.close()
    if brief is None:
        raise HTTPException(status_code=404, detail="brief not found")
    return _brief_response(brief)


@router.post("/briefs/{brief_id}/approve", response_model=ResearchDecisionResponse)
async def approve(brief_id: str, request: Request) -> ResearchDecisionResponse:
    """Approve a proposed brief (immutable decision)."""
    return _decide(request, brief_id, "approved")


@router.post("/briefs/{brief_id}/reject", response_model=ResearchDecisionResponse)
async def reject(brief_id: str, request: Request) -> ResearchDecisionResponse:
    """Reject a proposed brief (immutable decision)."""
    return _decide(request, brief_id, "rejected")


_KNOWN_REGIMES = {"trending_up", "trending_down", "range_bound", "volatile", "transition"}


def _normalize_regime(value: object) -> str | None:
    """Lowercase enum value for regime strings; None for anything unknown."""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text in _KNOWN_REGIMES else None


def _current_regime(request: Request) -> str | None:
    """Best-effort current regime from the intelligence projection."""
    proj = getattr(request.app.state, "intelligence_projection", None)
    if proj is None:
        return None
    try:
        regime = proj.get_regime() or {}
    except Exception:
        return None
    value = regime.get("regime")
    return _normalize_regime(value)


def _record_brief_decision(brief: ResearchBrief) -> None:
    """Mirror an approved brief into the learning store (best-effort).

    Learning is a side effect of research: a failure here is logged and
    never changes the research response. Decisions key on ``research:<id>``
    so the outcome endpoint can link WIN/LOSS back without a lookup table.
    """
    if brief.status != "approved":
        return
    direction = {1: SignalDirection.UP, -1: SignalDirection.DOWN, 0: SignalDirection.NEUTRAL}.get(
        brief.direction, SignalDirection.NEUTRAL
    )
    try:
        decided_at = (
            datetime.fromisoformat(brief.decided_at)
            if brief.decided_at
            else datetime.now(UTC)
        )
    except ValueError:
        decided_at = datetime.now(UTC)
    signal = Signal(
        direction=direction,
        conviction=brief.confidence,
        voters=[],
        timestamp=decided_at,
    )
    try:
        tracker = OutcomeTracker(LEARNING_DB_PATH)
        try:
            tracker.record_decision_with_id(
                f"research:{brief.brief_id}",
                signal,
                {
                    "kind": "research",
                    "brief_id": brief.brief_id,
                    "lens": brief.lens,
                    "status": brief.status,
                    "direction": brief.direction,
                    "regime_at_decision": brief.regime_at_decision,
                },
            )
        finally:
            tracker.close()
    except Exception as exc:
        logger.warning("learning decision recording failed for %s: %s", brief.brief_id, exc)


def _record_brief_outcome(brief: ResearchBrief) -> None:
    """Mirror a realized research outcome into the learning store (best-effort)."""
    if not brief.outcome or brief.outcome not in ("WIN", "LOSS"):
        return
    try:
        tracker = OutcomeTracker(LEARNING_DB_PATH)
        try:
            tracker.record_outcome_idempotent(
                f"research:{brief.brief_id}", OutcomeLabel(brief.outcome.lower())
            )
        finally:
            tracker.close()
    except Exception as exc:
        logger.warning("learning outcome recording failed for %s: %s", brief.brief_id, exc)


def _decide(request: Request, brief_id: str, decision: str) -> ResearchDecisionResponse:
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        try:
            brief = store.decide(
                brief_id,
                decision,
                regime=_normalize_regime(_current_regime(request)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="brief not found") from exc
        except AlreadyDecidedError as exc:
            raise HTTPException(status_code=409, detail="brief already decided") from exc
    finally:
        store.close()
    _broadcast(
        {"event": "decision", "data": {"brief_id": brief.brief_id, "status": brief.status}}
    )
    _record_brief_decision(brief)
    return ResearchDecisionResponse(brief_id=brief.brief_id, status=brief.status)


@router.post("/briefs/{brief_id}/outcome", response_model=ResearchOutcomeResponse)
async def set_outcome(
    brief_id: str, body: ResearchOutcomeRequest
) -> ResearchOutcomeResponse:
    """Record a realized outcome (WIN|LOSS) for a decided brief."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        try:
            brief = store.set_outcome(brief_id, body.outcome)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="brief not found") from exc
        except BriefNotDecidedError as exc:
            raise HTTPException(
                status_code=409,
                detail="outcome can only be recorded for a decided brief",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        store.close()
    _record_brief_outcome(brief)
    return ResearchOutcomeResponse(
        brief_id=brief.brief_id, outcome=brief.outcome or ""
    )


@router.get("/scoring", response_model=ResearchScoringResponse)
async def scoring() -> ResearchScoringResponse:
    """Per-lens brief scoring aggregates; empty DB -> []."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        return ResearchScoringResponse()
    try:
        return ResearchScoringResponse(
            lenses=[ResearchScoringItem(**row) for row in store.scoring()]
        )
    except Exception as exc:
        logger.warning("Research scoring failed: %s", exc)
        return ResearchScoringResponse()
    finally:
        store.close()
