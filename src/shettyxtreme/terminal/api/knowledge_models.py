"""Response models for the knowledge API (Phase 4A)."""
from __future__ import annotations

from pydantic import BaseModel


class KnowledgeTagResponse(BaseModel):
    tag: str
    kind: str


class KnowledgeDocResponse(BaseModel):
    doc_id: str
    kind: str
    source_ref: str
    payload: dict
    status: str
    created_at: str | None = None
    activated_at: str | None = None
    tags: list[KnowledgeTagResponse] = []


class KnowledgeListResponse(BaseModel):
    docs: list[KnowledgeDocResponse] = []


class KnowledgeSearchHitResponse(BaseModel):
    doc_id: str
    kind: str
    source_ref: str
    status: str
    title: str
    snippet: str
    tags: list[KnowledgeTagResponse] = []
    bm25_score: float = 0.0


class KnowledgeSearchResponse(BaseModel):
    hits: list[KnowledgeSearchHitResponse] = []


class KnowledgeSyncResponse(BaseModel):
    ingested: int = 0
    skipped_undecided: int = 0
    skipped_duplicate: int = 0
    error: str | None = None


class KnowledgeStatusResponse(BaseModel):
    docs: int = 0
    proposed: int = 0
    activated: int = 0
    tags: int = 0
