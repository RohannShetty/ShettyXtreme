"""Knowledge store tests (spec 4A §3.2, §6)."""
from __future__ import annotations

import pytest

from shettyxtreme.knowledge.schemas import KnowledgeDoc
from shettyxtreme.knowledge.store import DuplicateSourceError, KnowledgeStore


def _doc(doc_id: str, source_ref: str = "b1", body_text: str = "NIFTY trending up with elevated IV crowding") -> KnowledgeDoc:
    return KnowledgeDoc(
        doc_id=doc_id,
        kind="research_brief",
        source_ref=source_ref,
        payload={"thesis": body_text, "lens": "oi_iv_flow"},
        tags=[{"tag": "NIFTY", "kind": "symbol"}, {"tag": "TRENDING_UP", "kind": "regime"}],
    )


def test_schema_created_and_empty(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    assert store.list_docs() == []
    assert store.search("nifty") == []
    assert store.counts() == {"docs": 0, "proposed": 0, "activated": 0, "tags": 0}
    store.close()


def test_ingest_and_get(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    doc = _doc("d1")
    store.ingest(doc)
    got = store.get("d1")
    assert got is not None and got.source_ref == "b1" and got.status == "proposed"
    assert got.created_at is not None
    store.close()


def test_ingest_duplicate_source_ref(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1"))
    with pytest.raises(DuplicateSourceError):
        store.ingest(_doc("d2", "b1"))
    store.ingest(_doc("d2", "b1"), replace=True)  # replace wins
    assert store.get("d1") is None
    assert store.get("d2") is not None
    store.close()


def test_search_ranking_and_snippet(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1", "NIFTY trending up with elevated IV crowding"))
    store.ingest(_doc("d2", "b2", "BANKNIFTY range bound, no momentum"))
    hits = store.search("trending")
    assert len(hits) == 1
    assert hits[0].doc_id == "d1"
    assert "trending" in hits[0].snippet.lower()
    store.close()


def test_search_tag_and_status_filters(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1"))
    store.ingest(_doc("d2", "b2", "BANKNIFTY range bound"))
    assert len(store.search("nifty", tags=["NIFTY"])) == 1
    store.activate("d1")
    assert len(store.search("nifty", status="proposed")) == 0
    assert len(store.search("nifty", status="activated")) == 1
    assert len(store.search("nope", tags=["NOPE_TAG"])) == 0
    store.close()


def test_fts_stays_in_sync_on_replace(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1", "NIFTY trending"))
    store.ingest(_doc("d1", "b1", "BANKNIFTY range bound"), replace=True)
    assert len(store.search("trending")) == 0
    assert len(store.search("banknifty")) == 1
    store.close()


def test_activate_idempotent_and_unknown(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1"))
    act = store.activate("d1")
    assert act.status == "activated" and act.activated_at is not None
    assert store.activate("d1").status == "activated"  # idempotent
    with pytest.raises(KeyError):
        store.activate("nope")
    store.close()


def test_counts(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1"))
    store.ingest(_doc("d2", "b2", "BANKNIFTY range bound"))
    store.activate("d1")
    assert store.counts() == {"docs": 2, "proposed": 1, "activated": 1, "tags": 4}
    store.close()


def test_last_sync_meta(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    assert store.get_last_sync() is None
    store.set_last_sync("2026-08-05T10:00:00+00:00")
    assert store.get_last_sync() == "2026-08-05T10:00:00+00:00"
    store.set_last_sync("2026-08-05T11:00:00+00:00")  # overwrite, not append
    assert store.get_last_sync() == "2026-08-05T11:00:00+00:00"
    store.close()


def test_list_status_filter_and_limit(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    for i in range(5):
        store.ingest(_doc(f"d{i}", f"b{i}"))
    assert len(store.list_docs(limit=2)) == 2
    store.activate("d0")
    assert all(d.status == "activated" for d in store.list_docs(status="activated"))
    store.close()
