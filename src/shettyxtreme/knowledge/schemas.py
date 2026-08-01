"""Knowledge layer schemas (spec 4A §3.2).

`KnowledgeDoc` mirrors one `docs` row plus its tags; `SearchHit` carries the
FTS ranking projection returned by `KnowledgeStore.search`. Both are strict:
unknown fields are rejected, mirroring the ResearchBrief channel contract.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDoc(BaseModel):
    """One document in the knowledge store (proposed -> activated)."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    kind: str
    source_ref: str
    payload: dict = Field(default_factory=dict)
    status: str = "proposed"
    created_at: str | None = None
    activated_at: str | None = None
    tags: list[dict] = Field(default_factory=list)


class SearchHit(BaseModel):
    """One FTS5 search result with a snippet and bm25 score."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    kind: str
    source_ref: str
    status: str
    title: str
    snippet: str
    tags: list[dict] = Field(default_factory=list)
    bm25_score: float
