"""Registry adapter — graduated 3-arg shadows consumable by SignalEngine.

Covers:
  - a 3-arg shadow fn in the global registry is consumed by a SignalEngine
    with regime/options_context set, and its Vote lands in compute_signal
    output;
  - 1-arg voters pass through unchanged (byte-compatible engine behavior);
  - collision: engine-registered voter wins, registry member skipped with a
    warning (no silent override);
  - adapter with default (None) regime/context uses documented defaults
    (Regime.RANGE_BOUND, {});
  - empty registry -> behavior identical to today;
  - global-registry hygiene: full snapshot/restore per test.
"""
from __future__ import annotations

import logging

import pytest
from unittest.mock import MagicMock

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import (
    SignalEngine, SignalDirection, Vote, get_registry,
)


def _make_engine(**kwargs) -> SignalEngine:
    mock_fe = MagicMock()
    mock_fe.features = {"adx": 30.0, "ltp": 100.0}
    return SignalEngine(feature_engine=mock_fe, **kwargs)


def _shadow(name: str, received: list, direction: float = 1.0):
    def vote(features: dict[str, float], regime: Regime, options_context: dict) -> Vote:
        received.append((features, regime, options_context))
        return Vote(direction=direction, confidence=0.8, weight=1.0, name=name)

    return vote


@pytest.fixture(autouse=True)
def _pristine_registry():
    """Snapshot and fully clear the global registry; restore after the test.

    Deterministic sync tests: import-time voters (e.g. @voter-decorated
    modules) must not bleed into compute_signal here, and nothing added
    during a test may leak out.
    """
    reg = get_registry()
    before: dict[str, tuple[object, float]] = {}
    for name in reg.names():
        fn = reg.get(name)
        if fn is not None:
            before[name] = (fn, reg.get_weight(name))
    for name in list(reg.names()):
        reg._voters.pop(name, None)
        reg._weights.pop(name, None)
    yield
    for name in list(reg.names()):
        reg._voters.pop(name, None)
        reg._weights.pop(name, None)
    for name, (fn, weight) in before.items():
        reg.register(name, fn, weight=weight)


def test_shadow_consumed_with_regime_and_options() -> None:
    received: list = []
    get_registry().register("shadow_alpha", _shadow("shadow_alpha", received))
    engine = _make_engine(
        regime=Regime.TRENDING_UP, options_context={"symbol": "NIFTY"}
    )
    engine.sync_registry_members()
    signal = engine.compute_signal()
    names = [v.name for v in signal.voters]
    assert "shadow_alpha" in names
    assert received == [
        ({"adx": 30.0, "ltp": 100.0}, Regime.TRENDING_UP, {"symbol": "NIFTY"})
    ]


def test_registry_weight_applied_to_engine_vote() -> None:
    get_registry().register(
        "shadow_w", _shadow("shadow_w", []), weight=0.5
    )
    engine = _make_engine(regime=Regime.RANGE_BOUND)
    engine.sync_registry_members()
    signal = engine.compute_signal()
    assert engine.voter_weights["shadow_w"] == 0.5
    assert signal.voters[0].weight == 0.5


def test_one_arg_voter_passes_through_unchanged() -> None:
    def one_arg(features: dict[str, float]) -> Vote:
        return Vote(direction=-1.0, confidence=0.7, weight=1.0, name="flat")

    get_registry().register("flat", one_arg)
    engine = _make_engine()
    engine.sync_registry_members()
    assert engine.voters["flat"] is one_arg  # not wrapped in an adapter
    signal = engine.compute_signal()
    assert signal.direction == SignalDirection.DOWN
    assert any(v.name == "flat" for v in signal.voters)


def test_collision_engine_voter_wins(caplog) -> None:
    received: list = []
    get_registry().register("collide", _shadow("collide_shadow", received))
    engine = _make_engine(regime=Regime.VOLATILE)

    def engine_voter(features: dict[str, float]) -> Vote:
        return Vote(direction=1.0, confidence=0.9, weight=1.0, name="collide")

    engine.register_voter("collide", engine_voter)
    with caplog.at_level(logging.WARNING, logger="shettyxtreme.intelligence.signals.signal_engine"):
        engine.sync_registry_members()
    assert engine.voters["collide"] is engine_voter
    assert received == []  # shadow never invoked
    signal = engine.compute_signal()
    assert all(v.name != "collide_shadow" for v in signal.voters)
    assert any("collide" in r.message for r in caplog.records)


def test_adapter_defaults_when_engine_attrs_none() -> None:
    received: list = []
    get_registry().register("shadow_defaults", _shadow("shadow_defaults", received))
    engine = _make_engine()  # regime=None, options_context=None
    engine.sync_registry_members()
    engine.compute_signal()
    assert received == [
        ({"adx": 30.0, "ltp": 100.0}, Regime.RANGE_BOUND, {})
    ]


def test_consume_registry_constructor_param() -> None:
    get_registry().register("shadow_ctor", _shadow("shadow_ctor", []))
    engine = _make_engine(regime=Regime.TRENDING_DOWN, consume_registry=True)
    signal = engine.compute_signal()
    assert any(v.name == "shadow_ctor" for v in signal.voters)


def test_sync_is_idempotent_without_warnings(caplog) -> None:
    get_registry().register("shadow_alpha", _shadow("shadow_alpha", []))
    engine = _make_engine(regime=Regime.RANGE_BOUND)
    engine.sync_registry_members()
    engine.sync_registry_members()
    assert engine.voters["shadow_alpha"] is not None
    with caplog.at_level(logging.WARNING, logger="shettyxtreme.intelligence.signals.signal_engine"):
        engine.sync_registry_members()
    assert not caplog.records


def test_no_registry_members_behavior_identical_to_today() -> None:
    engine = _make_engine()  # fixture guarantees empty global registry
    engine.sync_registry_members()
    signal = engine.compute_signal()
    assert signal.direction == SignalDirection.NEUTRAL
    assert signal.conviction == 0.0
    assert signal.voters == []
