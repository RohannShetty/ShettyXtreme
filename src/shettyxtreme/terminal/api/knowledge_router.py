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

from fastapi import APIRouter, HTTPException, Query, Response

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


def _build_markdown(doc) -> str:
    """Render a KnowledgeDoc to the S2 markdown template (pure Python, no deps)."""
    payload = doc.payload or {}
    title = str(payload.get("thesis") or payload.get("title") or doc.doc_id)
    # Body: prefer body, then rationale, then thesis (avoid duplicating title)
    body_parts: list[str] = []
    if payload.get("body"):
        body_parts.append(str(payload["body"]))
    if payload.get("rationale"):
        body_parts.append(str(payload["rationale"]))
    if payload.get("thesis") and str(payload["thesis"]) != title:
        body_parts.append(str(payload["thesis"]))
    if not body_parts:
        body_parts.append(str(payload.get("thesis") or payload.get("body") or ""))
    body = "\n\n".join(p for p in body_parts if p) or "No content"
    # Tags
    tags = doc.tags or []
    if tags:
        tags_block = "\n".join(f"- {t.get('tag', '')} ({t.get('kind', '')})" for t in tags)
    else:
        tags_block = "- None"
    # Evidence
    evidence = payload.get("evidence") or []
    ev_lines: list[str] = []
    for item in evidence:
        if isinstance(item, dict):
            text = str(item.get("item", "") or item.get("text", "") or "")
            source = str(item.get("source", "") or "")
            if source:
                ev_lines.append(f"- {text} — {source}" if text else f"- {source}")
            elif text:
                ev_lines.append(f"- {text}")
        elif isinstance(item, str) and item.strip():
            ev_lines.append(f"- {item.strip()}")
    evidence_block = "\n".join(ev_lines) if ev_lines else "- None"
    created = doc.created_at or "Unknown"
    activated = doc.activated_at or "Not activated"
    lines = [
        f"# Knowledge Document: {title}",
        "",
        f"**Kind:** {doc.kind}  ",
        f"**Status:** {doc.status}  ",
        f"**Source:** {doc.source_ref}  ",
        f"**Created:** {created}  ",
        f"**Activated:** {activated}",
        "",
        "## Tags",
        tags_block,
        "",
        "## Content",
        body,
        "",
        "## Evidence",
        evidence_block,
        "",
        "## Metadata",
        f"- **Document ID:** {doc.doc_id}",
        "- **BM25 Score:** N/A",
        "",
    ]
    return "\n".join(lines)


def _markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    """Convert markdown text to a minimal PDF (no external deps).

    Produces a single-page PDF with Helvetica; truncated to ~60 lines to fit.
    The output always starts with %PDF- and is sufficient for the S2 contract
    (valid PDF header, non-empty). Styled as clean/monospace where applicable
    is approximated by the fixed-width wrapping.
    """
    import textwrap

    raw_lines = markdown_text.splitlines()
    wrapped: list[str] = []
    for line in raw_lines:
        if not line:
            wrapped.append("")
        else:
            # Wrap long lines at 90 chars to stay within 612pt page width.
            chunks = textwrap.wrap(line, width=90, replace_whitespace=False, drop_whitespace=False)
            if not chunks:
                wrapped.append("")
            else:
                wrapped.extend(chunks)
    # Single page ~55 lines at 13pt leading fits 720pt height.
    if len(wrapped) > 60:
        wrapped = wrapped[:60]
        wrapped.append("... (truncated)")

    # Build content stream: one BT/ET block with Td moves.
    stream_lines: list[str] = ["BT", "/F1 9 Tf", "72 720 Td"]
    for i, line in enumerate(wrapped):
        # ASCII-safe + escape PDF string delimiters.
        esc = line.encode("ascii", "replace").decode("ascii")
        esc = esc.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if i == 0:
            stream_lines.append(f"({esc}) Tj")
        else:
            stream_lines.append("0 -13 Td")
            stream_lines.append(f"({esc}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("utf-8")

    # PDF objects (catalog, pages, page, contents). Offsets computed dynamically.
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>\nendobj\n"
    )
    obj4_head = f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("utf-8")
    obj4_tail = b"\nendstream\nendobj\n"

    parts: list[bytes] = [header, obj1, obj2, obj3, obj4_head, stream, obj4_tail]
    # Compute xref offsets: each object's byte offset from start of file.
    offsets: list[int] = []
    off = 0
    # Objects start at offsets of obj1..obj4 (header is not an object)
    # We need offsets for objects 1..4.
    obj_starts: list[bytes] = [obj1, obj2, obj3, obj4_head + stream + obj4_tail]
    cur = len(header)
    for ob in obj_starts:
        offsets.append(cur)
        cur += len(ob)

    xref_offset = len(header) + sum(len(o) for o in obj_starts)
    # Build xref table (object 0 + 1..4)
    xref = [b"xref\n0 5\n0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    trailer = b"trailer\n<< /Size 5 /Root 1 0 R >>\n"
    startxref = f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")

    pdf = b"".join(parts + xref + [trailer, startxref])
    return pdf


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
    """Store counts (docs, proposed, activated, tags) + last sync telemetry."""
    try:
        counts = _store().counts()
        return KnowledgeStatusResponse(
            **counts,
            last_sync_at=_store().get_last_sync(),
            last_sync_result=_store().get_last_sync_result(),
        )
    except Exception as exc:
        logger.warning("Knowledge status failed: %s", exc)
        return KnowledgeStatusResponse()


@router.post("/sync", response_model=KnowledgeSyncResponse)
async def sync() -> KnowledgeSyncResponse:
    """Ingest decided research briefs into the knowledge store (idempotent).

    Records sync telemetry on every attempt: ``last_sync_at`` (attempt time)
    and ``last_sync_result`` — "success" (nothing skipped), "partial"
    (undecided/duplicate briefs skipped), or "failed" (research store or
    ingest error). All failures degrade to a 200 payload, never 500.
    """

    def _record(result: str) -> None:
        try:
            store = _store()
            store.set_last_sync(datetime.now(UTC).isoformat())
            store.set_last_sync_result(result)
        except Exception:
            logger.warning("Knowledge sync telemetry record failed", exc_info=True)

    try:
        rstore = ResearchStore(RESEARCH_DB_PATH)
    except Exception as exc:
        logger.warning("Knowledge sync: research store unavailable: %s", exc)
        _record("failed")
        return KnowledgeSyncResponse(error=f"research store unavailable: {exc}")
    try:
        briefs = rstore.list()
    except Exception as exc:
        logger.warning("Knowledge sync: research list failed: %s", exc)
        _record("failed")
        return KnowledgeSyncResponse(error=f"research list failed: {exc}")
    finally:
        rstore.close()
    try:
        result = ingest_decided_briefs(_store(), briefs)
    except Exception as exc:
        logger.warning("Knowledge sync failed: %s", exc)
        _record("failed")
        return KnowledgeSyncResponse(error=f"ingest failed: {exc}")
    outcome = (
        "partial"
        if result.skipped_undecided > 0 or result.skipped_duplicate > 0
        else "success"
    )
    _record(outcome)
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


@router.get("/docs/{doc_id}/export")
async def export_doc(
    doc_id: str,
    format: str = Query("md"),
) -> Response:
    """Export a knowledge document as Markdown or PDF (S2).

    Query ``format`` is ``md`` (default) or ``pdf``. Returns 404 if the doc
    is missing, 400 if the format is unsupported, and 500 only on genuine
    PDF generation failures (logged). The response carries
    Content-Disposition: attachment so browsers trigger a download.
    """
    doc = _store().get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    if format not in ("md", "pdf"):
        raise HTTPException(status_code=400, detail="unsupported format; use md or pdf")
    markdown_text = _build_markdown(doc)
    if format == "md":
        return Response(
            content=markdown_text,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="doc-{doc_id}.md"'},
        )
    # PDF branch
    try:
        pdf_bytes = _markdown_to_pdf_bytes(markdown_text)
    except Exception as exc:
        logger.exception("knowledge export PDF generation failed for %s", doc_id)
        raise HTTPException(status_code=500, detail="PDF generation failed") from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="doc-{doc_id}.pdf"'},
    )
