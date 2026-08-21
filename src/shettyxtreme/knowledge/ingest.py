"""Decided-brief and agent-signal ingestion into the knowledge store.

`knowledge/` never imports `research/` (D12): callers hand us anything that
satisfies the `ResearchBriefLike` protocol, so the sync wiring can live in
the terminal layer without creating a dependency edge.

P2-3.5: added `ingest_agent_signals` for `kind="agent_signal"` ingestion
of proposed agent signals into the knowledge store (mirroring the
`research_brief` sync but at `proposed` status, keeping the human
activation gate). `KnowledgeDoc.kind` is free-form — no schema change needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .schemas import KnowledgeDoc
from .store import DuplicateSourceError, KnowledgeStore
from .tagger import tag_document


class ResearchBriefLike(Protocol):
    """Structural contract for a decided research brief (spec 4A §3.3)."""

    @property
    def brief_id(self) -> str: ...
    @property
    def lens(self) -> str: ...
    @property
    def as_of(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def thesis(self) -> str: ...
    @property
    def rationale(self) -> str: ...
    @property
    def decided_at(self) -> str | None: ...
    @property
    def outcome(self) -> str | None: ...
    @property
    def evidence(self) -> list[dict[str, Any]]: ...


class AgentSignalLike(Protocol):
    """Structural contract for a proposed agent signal (P2-3.5)."""

    brief_id: str
    lens: str
    as_of: str
    status: str
    thesis: str
    rationale: str
    instruments: list[str]
    direction: int
    confidence: float
    evidence: list[dict[str, Any]]
    risks: list[str]


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


def ingest_agent_signals(
    store: KnowledgeStore, signals: Sequence[AgentSignalLike]
) -> IngestResult:
    """Ingest proposed agent signals into the knowledge store.

    Agent signals are ingested at `proposed` status (the human activation
    gate is preserved). A duplicate source_ref is counted, never fatal.

    This mirrors `ingest_decided_briefs` but for `kind="agent_signal"` —
    proposed signals from deterministic analysts that the operator can
    activate to become research sources.
    """
    result = IngestResult()
    for signal in signals:
        if signal.status != "proposed":
            result.skipped_undecided += 1
            continue
        evidence_parts = [
            f"{item.get('item', '')} {item.get('source', '')}"
            for item in (signal.evidence or [])
            if isinstance(item, dict)
        ]
        text = " ".join([signal.thesis, signal.rationale, *evidence_parts])
        doc = KnowledgeDoc(
            doc_id=f"signal-{signal.brief_id}",
            kind="agent_signal",
            source_ref=signal.brief_id,
            payload={
                "thesis": signal.thesis,
                "rationale": signal.rationale,
                "lens": signal.lens,
                "as_of": signal.as_of,
                "status": signal.status,
                "instruments": signal.instruments,
                "direction": signal.direction,
                "confidence": signal.confidence,
                "evidence": signal.evidence or [],
                "risks": signal.risks or [],
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
