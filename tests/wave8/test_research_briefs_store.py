"""Tests for the brief contract + store (spec §3.3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from shettyxtreme.research.briefs import BriefValidationError, ResearchBrief, parse_brief_payload
from shettyxtreme.research.store import AlreadyDecidedError, ResearchStore


def _valid_payload() -> str:
    return (
        '{"instruments": ["NIFTY"], "direction": 1, "confidence": 0.6, '
        '"thesis": "Strong OI buildup on the upside", '
        '"rationale": "' + "r" * 320 + '", '
        '"evidence": [{"item": "OI up 12%", "source": "oi_snapshot", "unsourced": false}], '
        '"risks": ["earnings event"]}'
    )


def test_parse_harness_owned_fields_overwritten() -> None:
    brief = parse_brief_payload(
        _valid_payload(), lens="oi_iv_flow", as_of="2026-08-01T10:00:00Z", brief_id="b1"
    )
    assert brief.brief_id == "b1"
    assert brief.lens == "oi_iv_flow"
    assert brief.status == "proposed"
    assert brief.outcome is None
    assert brief.direction == 1


def test_parse_rejects_unknown_fields() -> None:
    with pytest.raises(BriefValidationError, match="unknown fields"):
        parse_brief_payload(
            _valid_payload().replace('"risks"', '"status": "approved", "risks"'),
            lens="l", as_of="a", brief_id="b",
        )


def test_parse_rejects_non_json() -> None:
    with pytest.raises(BriefValidationError, match="invalid JSON"):
        parse_brief_payload("not json", lens="l", as_of="a", brief_id="b")


def test_parse_rejects_bad_direction() -> None:
    with pytest.raises(BriefValidationError, match="schema violation"):
        parse_brief_payload(
            _valid_payload().replace('"direction": 1', '"direction": 5'),
            lens="l", as_of="a", brief_id="b",
        )


def test_brief_model_direct_validation() -> None:
    with pytest.raises(ValidationError):
        ResearchBrief(
            brief_id="x", lens="l", as_of="a", direction=1, confidence=2.0,
            thesis="t", rationale="r" * 320,
        )


def test_store_crud_and_expiry(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    brief = parse_brief_payload(
        _valid_payload(), lens="oi_iv_flow", as_of=datetime.now(UTC).isoformat(), brief_id="b1"
    )
    store.insert(brief)
    assert store.get("b1") is not None
    assert store.get("nope") is None
    assert store.list()[0].brief_id == "b1"
    assert store.list(lens="oi_iv_flow")[0].brief_id == "b1"
    assert store.list(lens="tail_risk") == []
    old = parse_brief_payload(
        _valid_payload(),
        lens="oi_iv_flow",
        as_of=(datetime.now(UTC) - timedelta(hours=5)).isoformat(),
        brief_id="b2",
    )
    store.insert(old)
    assert store.get("b2").is_expired() is True
    store.close()


def test_store_decision_immutable(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    store.insert(parse_brief_payload(_valid_payload(), lens="l", as_of="2026-08-01T10:00:00Z", brief_id="b1"))
    decided = store.decide("b1", "approved")
    assert decided.status == "approved"
    with pytest.raises(AlreadyDecidedError):
        store.decide("b1", "rejected")
    with pytest.raises(KeyError):
        store.decide("missing", "approved")
    store.close()


def test_store_outcome_stub(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    store.insert(parse_brief_payload(_valid_payload(), lens="l", as_of="2026-08-01T10:00:00Z", brief_id="b1"))
    store.decide("b1", "approved")
    updated = store.set_outcome("b1", "WIN")
    assert updated.outcome == "WIN"
    store.close()


from uuid import uuid4

from shettyxtreme.research.briefs import MODEL_AUTHORED_FIELDS, ResearchBrief
from shettyxtreme.research.store import BriefNotDecidedError, ResearchStore


def _make_brief(lens: str, direction: int = 1, confidence: float = 0.6) -> ResearchBrief:
    return ResearchBrief(
        brief_id=str(uuid4()),
        lens=lens,
        as_of=datetime.now(UTC).isoformat(),
        direction=direction,
        confidence=confidence,
        thesis="Thesis",
        rationale="r" * 320,
        evidence=[],
        risks=[],
    )


def test_decided_at_not_model_authorable() -> None:
    assert "decided_at" not in MODEL_AUTHORED_FIELDS


def test_decided_at_surfaces_after_decision(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    decided = store.decide(brief.brief_id, "approved")
    assert decided.decided_at is not None
    assert store.get(brief.brief_id).decided_at is not None
    assert store.get(brief.brief_id).status == "approved"
    store.close()


def test_outcome_on_proposed_rejected(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    with pytest.raises(BriefNotDecidedError):
        store.set_outcome(brief.brief_id, "WIN")
    store.close()


def test_outcome_invalid_value(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    store.decide(brief.brief_id, "approved")
    with pytest.raises(ValueError, match="invalid outcome"):
        store.set_outcome(brief.brief_id, "DRAW")
    store.close()


def test_outcome_unknown_brief(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    with pytest.raises(KeyError):
        store.set_outcome("nope", "WIN")
    store.close()


def test_outcome_on_rejected_brief_allowed(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    store.decide(brief.brief_id, "rejected")
    updated = store.set_outcome(brief.brief_id, "LOSS")
    assert updated.outcome == "LOSS"
    store.close()


def test_scoring_aggregates(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    b1 = _make_brief("lens_a", direction=1, confidence=0.6)
    b2 = _make_brief("lens_a", direction=-1, confidence=0.8)
    b3 = _make_brief("lens_b", direction=0, confidence=0.5)
    store.insert(b1)
    store.insert(b2)
    store.insert(b3)
    store.decide(b1.brief_id, "approved")
    store.decide(b2.brief_id, "rejected")
    store.decide(b3.brief_id, "approved")
    store.set_outcome(b1.brief_id, "WIN")
    store.set_outcome(b2.brief_id, "LOSS")
    rows = {r["lens"]: r for r in store.scoring()}
    assert rows["lens_a"]["total"] == 2
    assert rows["lens_a"]["decided"] == 2
    assert rows["lens_a"]["with_outcome"] == 2
    assert rows["lens_a"]["win_rate"] == 0.5
    assert rows["lens_a"]["avg_confidence"] == 0.7
    assert rows["lens_b"]["total"] == 1
    assert rows["lens_b"]["with_outcome"] == 0
    assert rows["lens_b"]["win_rate"] == 0.0
    store.close()


def test_scoring_empty_db(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    assert store.scoring() == []
    store.close()


def test_regime_at_decision_not_model_authorable() -> None:
    assert "regime_at_decision" not in MODEL_AUTHORED_FIELDS


def test_decide_records_regime(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    decided = store.decide(brief.brief_id, "approved", regime="TRENDING_UP")
    assert decided.regime_at_decision == "TRENDING_UP"
    assert store.get(brief.brief_id).regime_at_decision == "TRENDING_UP"
    store.close()


def test_decide_without_regime_keeps_none(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    decided = store.decide(brief.brief_id, "approved")
    assert decided.regime_at_decision is None
    store.close()
