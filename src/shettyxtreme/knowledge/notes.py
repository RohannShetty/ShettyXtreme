"""Operator-note ingestion into the knowledge store (knowledge v2).

D12: `knowledge/` imports core ONLY — notes are tagged heuristically and
stored as `proposed`; they become a research source only after the same
human activation gate as briefs. No LLM anywhere (D3).
"""
from __future__ import annotations

from uuid import uuid4

from .schemas import KnowledgeDoc
from .store import KnowledgeStore
from .tagger import tag_document


def ingest_note(
    store: KnowledgeStore,
    title: str,
    body: str,
    source_ref: str | None = None,
) -> KnowledgeDoc:
    """Tag and ingest an operator-written note; returns the stored doc."""
    ref = source_ref or f"note-{uuid4().hex[:12]}"
    text = f"{title} {body}".strip()
    doc = KnowledgeDoc(
        doc_id=ref,
        kind="operator_note",
        source_ref=ref,
        payload={"title": title, "body": body},
        tags=tag_document(text),
    )
    return store.ingest(doc)
