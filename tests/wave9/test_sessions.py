"""SessionLog tests (spec 4B §4.1)."""
from __future__ import annotations

from shettyxtreme.learning.sessions import SessionLog


def test_start_end_cycle(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    sid = log.start("OBSERVER")
    assert log.counts() == {"total": 1, "open": 1, "live": 0, "observer": 1}
    log.end(sid)
    assert log.counts()["open"] == 0
    rows = log.list()
    assert len(rows) == 1
    assert rows[0]["mode"] == "OBSERVER"
    assert rows[0]["ended_at"] is not None
    log.close()


def test_end_unknown_noop(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    log.end("nope")  # must not raise
    assert log.counts()["total"] == 0
    log.close()


def test_modes_counted(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    log.start("OBSERVER")
    log.start("LIVE")
    log.start("OBSERVER")
    assert log.counts() == {"total": 3, "open": 3, "live": 1, "observer": 2}
    log.close()


def test_limit(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    for i in range(5):
        log.start("OBSERVER")
    assert len(log.list(limit=2)) == 2
    log.close()
