"""Knowledge schema tests (spec 4A §3.2)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from shettyxtreme.knowledge.schemas import KnowledgeDoc, SearchHit


def test_knowledge_doc_defaults() -> None:
    doc = KnowledgeDoc(doc_id="d1", kind="research_brief", source_ref="b1", payload={})
    assert doc.status == "proposed"
    assert doc.created_at is None
    assert doc.activated_at is None
    assert doc.tags == []


def test_knowledge_doc_round_trip() -> None:
    doc = KnowledgeDoc(
        doc_id="d1",
        kind="research_brief",
        source_ref="b1",
        payload={"thesis": "NIFTY trending"},
        status="activated",
        created_at="t0",
        activated_at="t1",
        tags=[{"tag": "NIFTY", "kind": "symbol"}],
    )
    dumped = doc.model_dump()
    assert dumped["payload"]["thesis"] == "NIFTY trending"
    assert dumped["tags"][0]["tag"] == "NIFTY"


def test_search_hit_construction() -> None:
    hit = SearchHit(
        doc_id="d1",
        kind="research_brief",
        source_ref="b1",
        status="activated",
        title="NIFTY trending",
        snippet="…NIFTY [trending]…",
        tags=[{"tag": "NIFTY", "kind": "symbol"}],
        bm25_score=-3.2,
    )
    assert hit.bm25_score == -3.2
    assert hit.snippet.startswith("…NIFTY")


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        KnowledgeDoc(doc_id="d1", kind="k", source_ref="s", payload={}, nope=1)
    with pytest.raises(ValidationError):
        SearchHit(
            doc_id="d1", kind="k", source_ref="s", status="x",
            title="t", snippet="s", bm25_score=1.0, bogus=2,
        )
