"""Research router — run briefers, list/approve/reject briefs (Phase 3B).

The orchestrator is created lazily on first run; without DEEPSEEK_API_KEY
the run endpoint returns 503 with an explicit message. DB failures on
read paths degrade to empty/404 payloads — never 500.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from shettyxtreme.research.briefs import ResearchBrief
from shettyxtreme.research.lenses import list_lenses
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import DeepSeekProvider
from shettyxtreme.research.store import AlreadyDecidedError, ResearchStore
from shettyxtreme.terminal.api.models import (
    LensInfoResponse,
    LensListResponse,
    ResearchBriefListResponse,
    ResearchBriefResponse,
    ResearchDecisionResponse,
    ResearchRunItem,
    ResearchRunRequest,
    ResearchRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

RESEARCH_DB_PATH = "data/research.db"
_ORCHESTRATOR: ResearchOrchestrator | None = None


def _get_orchestrator() -> ResearchOrchestrator | None:
    """Lazily build the orchestrator; None when the API key is absent."""
    global _ORCHESTRATOR
    if _ORCHESTRATOR is not None:
        return _ORCHESTRATOR
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return None
    _ORCHESTRATOR = ResearchOrchestrator(
        provider=DeepSeekProvider(), store=ResearchStore(RESEARCH_DB_PATH)
    )
    return _ORCHESTRATOR


def _brief_response(brief: ResearchBrief) -> ResearchBriefResponse:
    return ResearchBriefResponse(**brief.model_dump(), expired=brief.is_expired())


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
    results = await orch.run(lenses=req.lenses, sources=req.context)
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
async def approve(brief_id: str) -> ResearchDecisionResponse:
    """Approve a proposed brief (immutable decision)."""
    return _decide(brief_id, "approved")


@router.post("/briefs/{brief_id}/reject", response_model=ResearchDecisionResponse)
async def reject(brief_id: str) -> ResearchDecisionResponse:
    """Reject a proposed brief (immutable decision)."""
    return _decide(brief_id, "rejected")


def _decide(brief_id: str, decision: str) -> ResearchDecisionResponse:
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        try:
            brief = store.decide(brief_id, decision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="brief not found") from exc
        except AlreadyDecidedError as exc:
            raise HTTPException(status_code=409, detail="brief already decided") from exc
    finally:
        store.close()
    return ResearchDecisionResponse(brief_id=brief.brief_id, status=brief.status)
