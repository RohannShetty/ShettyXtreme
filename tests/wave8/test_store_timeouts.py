import sqlite3

import pytest

from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.research.store import ResearchStore


@pytest.mark.parametrize("cls", [ResearchStore, KnowledgeStore, SessionLog])
def test_connect_uses_timeout(cls, tmp_path, monkeypatch):
    real = sqlite3.connect
    captured: dict[str, dict] = {}

    def spy(db_path, *args, **kwargs):
        captured[str(db_path)] = kwargs
        return real(db_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    store = cls(str(tmp_path / "store.db"))
    store.close()
    assert captured, "connect was not called"
    assert captured[str(tmp_path / "store.db")].get("timeout") == 5.0
