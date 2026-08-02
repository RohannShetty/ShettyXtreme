import pytest

from shettyxtreme.knowledge.notes import ingest_note
from shettyxtreme.knowledge.store import DuplicateSourceError, KnowledgeStore


def test_ingest_note_tags_and_defaults_proposed(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    doc = ingest_note(
        store, "NIFTY breakout",
        "NIFTY trending up with elevated iv near resistance", source_ref="note-1",
    )
    assert doc.kind == "operator_note"
    assert doc.status == "proposed"
    tags = {t["tag"] for t in doc.tags}
    assert "NIFTY" in tags
    assert "trending_up" in tags
    assert "ELEVATED_IV" in tags
    got = store.get("note-1")
    assert got is not None and got.payload["title"] == "NIFTY breakout"


def test_ingest_note_generates_source_ref(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    doc = ingest_note(store, "T", "body text")
    assert doc.doc_id.startswith("note-")


def test_ingest_note_duplicate_ref_raises(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    ingest_note(store, "T", "b", source_ref="dup")
    with pytest.raises(DuplicateSourceError):
        ingest_note(store, "T2", "b2", source_ref="dup")
