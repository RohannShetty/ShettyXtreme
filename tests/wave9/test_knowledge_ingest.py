"""Ingest tests (spec 4A §3.3, §6)."""
from __future__ import annotations

from dataclasses import dataclass, field

from shettyxtreme.knowledge.ingest import ingest_decided_briefs
from shettyxtreme.knowledge.store import KnowledgeStore


@dataclass
class FakeBrief:
    brief_id: str
    lens: str
    as_of: str
    status: str
    thesis: str
    rationale: str = "r" * 320
    decided_at: str | None = None
    outcome: str | None = None
    evidence: list[dict] = field(default_factory=list)


def test_only_decided_ingested(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    briefs = [
        FakeBrief(brief_id="a", lens="oi_iv_flow", as_of="t", status="approved", thesis="NIFTY trending", decided_at="t1"),
        FakeBrief(brief_id="b", lens="tail_risk", as_of="t", status="proposed", thesis="BANKNIFTY"),
    ]
    res = ingest_decided_briefs(store, briefs)
    assert res.ingested == 1 and res.skipped_undecided == 1 and res.skipped_duplicate == 0
    assert store.counts()["docs"] == 1
    store.close()


def test_rejected_with_decided_at_ingested(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    b = FakeBrief(brief_id="c", lens="directional_momentum", as_of="t", status="rejected", thesis="X", decided_at="t2")
    res = ingest_decided_briefs(store, [b])
    assert res.ingested == 1
    doc = store.list_docs()[0]
    assert doc.source_ref == "c" and doc.kind == "research_brief"
    store.close()


def test_duplicates_counted_not_fatal(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    b = FakeBrief(brief_id="d", lens="l", as_of="t", status="approved", thesis="NIFTY", decided_at="t3")
    ingest_decided_briefs(store, [b])
    res = ingest_decided_briefs(store, [b])
    assert res.ingested == 0 and res.skipped_duplicate == 1
    store.close()


def test_tags_and_body_populated(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    b = FakeBrief(brief_id="e", lens="oi_iv_flow", as_of="t", status="approved", thesis="NIFTY trending with elevated IV", decided_at="t4", evidence=[{"item": "x", "source": "y", "unsourced": False}])
    ingest_decided_briefs(store, [b])
    doc = store.list_docs()[0]
    kinds = {t["kind"] for t in doc.tags}
    assert kinds == {"symbol", "regime", "risk"}
    assert len(store.search("elevated")) == 1  # body includes evidence + rationale
    store.close()
