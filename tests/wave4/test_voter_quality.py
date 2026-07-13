"""Tests for the voter quality tracker."""
from __future__ import annotations

import os

import pytest

from shettyxtreme.learning.outcome_tracker import OutcomeLabel
from shettyxtreme.learning.voter_quality import VoterQualityTracker


def _tracker(tmp_data_dir: str) -> VoterQualityTracker:
    return VoterQualityTracker(os.path.join(tmp_data_dir, "vq.db"))


def _feed(
    tracker: VoterQualityTracker,
    name: str,
    signal_id: str,
    direction: float,
    confidence: float,
    outcome: OutcomeLabel,
) -> None:
    tracker.record_vote(name, direction, confidence, signal_id)
    tracker.record_outcome(name, signal_id, outcome)


def test_hit_rate_basic(tmp_data_dir: str) -> None:
    t = _tracker(tmp_data_dir)
    _feed(t, "v1", "s1", 1.0, 0.8, OutcomeLabel.WIN)
    _feed(t, "v1", "s2", 1.0, 0.8, OutcomeLabel.WIN)
    _feed(t, "v1", "s3", 1.0, 0.8, OutcomeLabel.LOSS)
    _feed(t, "v1", "s4", 1.0, 0.8, OutcomeLabel.NEUTRAL)
    assert t.get_hit_rate("v1") == pytest.approx(2 / 3)
    t.close()


def test_high_hit_rate_boosts_weight(tmp_data_dir: str) -> None:
    t = _tracker(tmp_data_dir)
    for i in range(10):
        _feed(t, "good", f"g{i}", 1.0, 0.8, OutcomeLabel.WIN)
    for i in range(4):
        _feed(t, "good", f"l{i}", 1.0, 0.8, OutcomeLabel.LOSS)
    weight = t.get_adjusted_weight("good", base_weight=1.0)
    assert weight > 1.0
    assert weight <= 2.0
    t.close()


def test_bad_voter_clamped(tmp_data_dir: str) -> None:
    t = _tracker(tmp_data_dir)
    for i in range(8):
        _feed(t, "bad", f"b{i}", 1.0, 0.8, OutcomeLabel.LOSS)
    for i in range(2):
        _feed(t, "bad", f"w{i}", 1.0, 0.8, OutcomeLabel.WIN)
    # hit_rate 0.2 < 0.3 -> hard clamp 0.1
    assert t.get_adjusted_weight("bad", base_weight=1.0) == pytest.approx(0.1)
    t.close()


def test_voter_report_counts(tmp_data_dir: str) -> None:
    t = _tracker(tmp_data_dir)
    _feed(t, "v1", "s1", 1.0, 0.8, OutcomeLabel.WIN)
    _feed(t, "v1", "s2", 1.0, 0.8, OutcomeLabel.WIN)
    _feed(t, "v1", "s3", 1.0, 0.8, OutcomeLabel.LOSS)
    reports = t.get_voter_report()
    assert len(reports) == 1
    r = reports[0]
    assert r.name == "v1"
    assert r.wins == 2
    assert r.losses == 1
    assert r.total_signals == 3
    assert r.hit_rate == pytest.approx(2 / 3)
    assert len(r.last_10_outcomes) == 3
    t.close()


def test_sliding_window(tmp_data_dir: str) -> None:
    t = _tracker(tmp_data_dir)
    for i in range(20):
        _feed(t, "win", f"w{i}", 1.0, 0.8, OutcomeLabel.WIN)
    for i in range(5):
        _feed(t, "win", f"l{i}", 1.0, 0.8, OutcomeLabel.LOSS)
    hr = t.get_hit_rate("win", window=20)
    assert hr == pytest.approx(15 / 20)
    t.close()


def test_record_outcome_without_vote_inserts(tmp_data_dir: str) -> None:
    t = _tracker(tmp_data_dir)
    t.record_outcome("orphan", "s1", OutcomeLabel.WIN)
    reports = t.get_voter_report()
    assert any(r.name == "orphan" for r in reports)
    t.close()
