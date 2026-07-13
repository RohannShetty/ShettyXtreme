"""Tests for VoterCorrelation."""
from __future__ import annotations

import pytest

from shettyxtreme.intelligence.signals.signal_engine import Vote
from shettyxtreme.intelligence.signals.voter_correlation import VoterCorrelation


def _v(name: str, direction: float) -> Vote:
    return Vote(direction=direction, confidence=0.5, weight=1.0, name=name)


def test_always_agree_correlation_one() -> None:
    vc = VoterCorrelation()
    votes = [
        [_v("a", 1.0), _v("b", 1.0)],
        [_v("a", 1.0), _v("b", 0.5)],
        [_v("a", -1.0), _v("b", -0.8)],
    ]
    matrix = vc.compute_correlation_matrix(votes)
    assert matrix[("a", "b")] == 1.0


def test_always_disagree_correlation_zero() -> None:
    vc = VoterCorrelation()
    votes = [
        [_v("a", 1.0), _v("b", -1.0)],
        [_v("a", -1.0), _v("b", 1.0)],
    ]
    matrix = vc.compute_correlation_matrix(votes)
    assert matrix[("a", "b")] == 0.0


def test_correlation_groups_contain_correlated_pair() -> None:
    vc = VoterCorrelation()
    votes = [
        [_v("a", 1.0), _v("b", 1.0), _v("c", -1.0)],
        [_v("a", 0.5), _v("b", 0.9), _v("c", -0.5)],
        [_v("a", 1.0), _v("b", 1.0), _v("c", -1.0)],
    ]
    vc.compute_correlation_matrix(votes)
    groups = vc.get_correlation_groups(threshold=0.7)
    names_in_same = any(
        ("a" in g and "b" in g) for g in groups
    )
    assert names_in_same


def test_block_cap_scales_group_total() -> None:
    vc = VoterCorrelation(block_cap=2.0)
    votes = [_v("a", 1.0), _v("b", 1.0), _v("c", 1.0)]
    caps = {"a": 2.0, "b": 2.0, "c": 2.0}
    out = vc.apply_block_caps(votes, caps)
    total = sum(v.weight for v in out if v.name in caps)
    assert total == pytest.approx(2.0)
    for v in out:
        if v.name in caps:
            assert v.weight == pytest.approx(2.0 / 3.0)


def test_block_cap_never_exceeds_cap() -> None:
    vc = VoterCorrelation(block_cap=1.5)
    votes = [_v("a", 1.0), _v("b", 1.0), _v("x", 1.0), _v("y", 1.0)]
    caps = {"a": 1.5, "b": 1.5}
    out = vc.apply_block_caps(votes, caps)
    group_total = sum(v.weight for v in out if v.name in caps)
    assert group_total <= 1.5 + 1e-9
    # uncapped voters unchanged
    for v in out:
        if v.name in ("x", "y"):
            assert v.weight == 1.0
