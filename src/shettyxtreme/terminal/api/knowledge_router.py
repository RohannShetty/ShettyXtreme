"""Knowledge router — search/review/activate the D12 knowledge store (Phase 4A).

The store is wired in lifespan via init_knowledge(store, broadcast_fn). The
sync endpoint is the ONLY place research and knowledge meet: it reads decided
briefs from the research store and ingests them (knowledge/ never imports
research/). All DB failures degrade to empty/404 payloads — never 500.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from shettyxtreme.knowledge.ingest import ingest_decided_briefs
from shettyxtreme.knowledge.notes import ingest_note
from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.terminal.api.knowledge_models import (
    KnowledgeDocResponse,
    KnowledgeListResponse,
    KnowledgeNoteRequest,
    KnowledgeSearchHitResponse,
    KnowledgeSearchResponse,
    KnowledgeStatusResponse,
    KnowledgeSyncResponse,
    KnowledgeTagResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

RESEARCH_DB_PATH = "data/research.db"
_STORE: KnowledgeStore | None = None
_broadcast_fn: Callable[[dict], None] | None = None


def init_knowledge(
    store: KnowledgeStore | None = None,
    broadcast_fn: Callable[[dict], None] | None = None,
) -> None:
    """Wire the store + WS broadcast (lifespan calls this)."""
    global _STORE, _broadcast_fn
    _STORE = store
    _broadcast_fn = broadcast_fn


def _store() -> KnowledgeStore:
    global _STORE
    if _STORE is None:
        _STORE = KnowledgeStore("data/knowledge.db")
    return _STORE


def _broadcast(event: dict) -> None:
    if _broadcast_fn is None:
        return
    try:
        _broadcast_fn(event)
    except Exception:
        logger.exception("knowledge broadcast failed")


def _doc_response(doc) -> KnowledgeDocResponse:
    return KnowledgeDocResponse(
        doc_id=doc.doc_id,
        kind=doc.kind,
        source_ref=doc.source_ref,
        payload=doc.payload,
        status=doc.status,
        created_at=doc.created_at,
        activated_at=doc.activated_at,
        tags=[KnowledgeTagResponse(**t) for t in doc.tags],
    )


@router.get("/search", response_model=KnowledgeSearchResponse)
async def search(
    q: str = "",
    status: str | None = None,
    tags: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> KnowledgeSearchResponse:
    """Full-text search over the knowledge store (FTS5 bm25 + snippet)."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    try:
        hits = _store().search(q, status=status, tags=tag_list, limit=limit)
    except Exception as exc:
        logger.warning("Knowledge search failed: %s", exc)
        return KnowledgeSearchResponse()
    return KnowledgeSearchResponse(
        hits=[
            KnowledgeSearchHitResponse(
                doc_id=h.doc_id,
                kind=h.kind,
                source_ref=h.source_ref,
                status=h.status,
                title=h.title,
                snippet=h.snippet,
                tags=[KnowledgeTagResponse(**t) for t in h.tags],
                bm25_score=h.bm25_score,
            )
            for h in hits
        ]
    )


@router.get("/docs", response_model=KnowledgeListResponse)
async def list_docs(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> KnowledgeListResponse:
    """List knowledge documents, newest first, optionally filtered."""
    try:
        docs = _store().list_docs(status=status, limit=limit)
    except Exception as exc:
        logger.warning("Knowledge list failed: %s", exc)
        return KnowledgeListResponse()
    return KnowledgeListResponse(docs=[_doc_response(d) for d in docs])


@router.get("/status", response_model=KnowledgeStatusResponse)
async def status() -> KnowledgeStatusResponse:
    """Store counts (docs, proposed, activated, tags) + last sync time."""
    try:
        counts = _store().counts()
        return KnowledgeStatusResponse(
            **counts,
            last_sync_at=_store().get_last_sync(),
        )
    except Exception as exc:
        logger.warning("Knowledge status failed: %s", exc)
        return KnowledgeStatusResponse()


@router.post("/sync", response_model=KnowledgeSyncResponse)
async def sync() -> KnowledgeSyncResponse:
    """Ingest decided research briefs into the knowledge store (idempotent)."""
    try:
        rstore = ResearchStore(RESEARCH_DB_PATH)
    except Exception as exc:
        logger.warning("Knowledge sync: research store unavailable: %s", exc)
        return KnowledgeSyncResponse(error=f"research store unavailable: {exc}")
    try:
        briefs = rstore.list()
    except Exception as exc:
        logger.warning("Knowledge sync: research list failed: %s", exc)
        return KnowledgeSyncResponse(error=f"research list failed: {exc}")
    finally:
        rstore.close()
    try:
        result = ingest_decided_briefs(_store(), briefs)
        _store().set_last_sync(datetime.now(UTC).isoformat())
    except Exception as exc:
        logger.warning("Knowledge sync failed: %s", exc)
        return KnowledgeSyncResponse(error=f"ingest failed: {exc}")
    return KnowledgeSyncResponse(
        ingested=result.ingested,
        skipped_undecided=result.skipped_undecided,
        skipped_duplicate=result.skipped_duplicate,
    )


@router.post("/docs/{doc_id}/activate", response_model=KnowledgeDocResponse)
async def activate(doc_id: str) -> KnowledgeDocResponse:
    """Activate a knowledge document (idempotent); it becomes a research source."""
    try:
        doc = _store().activate(doc_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="document not found") from exc
    except Exception as exc:
        logger.warning("Knowledge activate failed: %s", exc)
        raise HTTPException(status_code=500, detail="activate failed") from exc
    _broadcast({"event": "activated", "data": _doc_response(doc).model_dump()})
    return _doc_response(doc)


@router.post("/notes", response_model=KnowledgeDocResponse)
async def create_note(req: KnowledgeNoteRequest) -> KnowledgeDocResponse:
    """Ingest an operator note (proposed; activate to make it a research source)."""
    try:
        doc = ingest_note(_store(), req.title, req.body)
    except Exception as exc:
        logger.warning("Knowledge note failed: %s", exc)
        raise HTTPException(status_code=500, detail="note ingest failed") from exc
    return _doc_response(doc)
