"""Decided-brief ingestion into the knowledge store (spec 4A §3.3).

`knowledge/` never imports `research/` (D12): callers hand us anything that
satisfies the `ResearchBriefLike` protocol, so the sync wiring can live in
the terminal layer without creating a dependency edge.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .schemas import KnowledgeDoc
from .store import DuplicateSourceError, KnowledgeStore
from .tagger import tag_document


class ResearchBriefLike(Protocol):
    """Structural contract for a decided research brief (spec 4A §3.3)."""

    brief_id: str
    lens: str
    as_of: str
    status: str
    thesis: str
    rationale: str
    decided_at: str | None
    outcome: str | None
    evidence: list[dict[str, Any]]


@dataclass
class IngestResult:
    """Counts from one ingest pass over decided briefs."""

    ingested: int = 0
    skipped_undecided: int = 0
    skipped_duplicate: int = 0


def ingest_decided_briefs(
    store: KnowledgeStore, briefs: Sequence[ResearchBriefLike]
) -> IngestResult:
    """Ingest decided briefs; returns per-category counts.

    Only briefs with status approved/rejected AND a decided_at are ingested.
    A duplicate source_ref is counted, never fatal (idempotent sync).
    """
    result = IngestResult()
    for brief in briefs:
        if brief.status not in ("approved", "rejected") or not brief.decided_at:
            result.skipped_undecided += 1
            continue
        evidence_parts = [
            f"{item.get('item', '')} {item.get('source', '')}"
            for item in (brief.evidence or [])
            if isinstance(item, dict)
        ]
        text = " ".join([brief.thesis, brief.rationale, *evidence_parts])
        doc = KnowledgeDoc(
            doc_id=f"brief-{brief.brief_id}",
            kind="research_brief",
            source_ref=brief.brief_id,
            payload={
                "thesis": brief.thesis,
                "rationale": brief.rationale,
                "lens": brief.lens,
                "as_of": brief.as_of,
                "status": brief.status,
                "decided_at": brief.decided_at,
                "outcome": brief.outcome,
                "evidence": brief.evidence or [],
            },
            tags=tag_document(text),
        )
        try:
            store.ingest(doc)
        except DuplicateSourceError:
            result.skipped_duplicate += 1
            continue
        result.ingested += 1
    return result
