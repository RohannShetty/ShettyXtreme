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
    updated = store.set_outcome("b1", "WIN")
    assert updated.outcome == "WIN"
    store.close()
