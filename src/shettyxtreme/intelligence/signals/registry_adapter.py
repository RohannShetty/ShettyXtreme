"""Adapter bridging 3-arg shadow voters into the 1-arg SignalEngine contract.

Graduated shadows are `ShadowFn`s — `Callable[[dict[str, float], Regime, dict], Vote]` —
but `SignalEngine.compute_signal` invokes voters with a single argument
(features). This module wraps such 3-arg callables in a thin adapter so the
engine can consume registry members without changing its 1-arg contract.

Design decisions (documented, tested in tests/wave6/test_registry_adapter.py):

1. Where do regime and options_context come from at call time?
   From the owning SignalEngine's live attributes (`engine.regime`,
   `engine.options_context`) at every invocation, NOT captured at sync time.
   Rationale: the regime/context may change between syncs; reading live state
   means a graduated shadow always votes under the engine's current view.
   Defaults when the engine attributes are None: `Regime.RANGE_BOUND` (the
   regime classifier's neutral fallback) and `{}`. The engine attributes
   themselves default to None so "unset" is distinguishable from "set".

 2. Which callables get wrapped? Only 3-arg ones.
   Arity is probed with `inspect.signature` (count of parameters excluding
   *args/**kwargs and keyword-only parameters), not a TypeError call-probe.
   Rationale: signature inspection is deterministic and side-effect free; a
   TypeError probe would actually invoke the callable, which may have side
   effects and cannot distinguish "wrong arity" from "raised TypeError
   internally". A callable that reports exactly 3 positional parameters is
   wrapped; anything else (including uninspectable callables, which are
   assumed to conform to the engine's 1-arg contract) is passed through
   unchanged.

3. Name collisions are resolved by `SignalEngine.sync_registry_members`
   (engine-registered voter wins; see its docstring).

4. Sync staleness: re-registering a different fn under an already-synced
   name (or unregistering an engine voter after a collision) is NOT
   re-wired by a later sync — `_synced_registry_names` only grows. This is
   deliberate: a shadow's identity is its registry name, and the engine
   contract treats registered names as stable for a session.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING

from shettyxtreme.intelligence.regime import Regime

if TYPE_CHECKING:
    from shettyxtreme.intelligence.signals.signal_engine import SignalEngine, Vote

DEFAULT_REGIME = Regime.RANGE_BOUND
DEFAULT_OPTIONS_CONTEXT: dict = {}


def is_shadow_fn(fn: Callable) -> bool:
    """True if `fn` declares exactly 3 positional parameters (ShadowFn-shaped)."""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) == 3


class ShadowAdapter:
    """Wrap a 3-arg ShadowFn as a 1-arg voter bound to a SignalEngine."""

    def __init__(self, fn: Callable, engine: SignalEngine) -> None:
        self._fn = fn
        self._engine = engine

    def __call__(self, features: dict[str, float]) -> Vote:
        regime = self._engine.regime if self._engine.regime is not None else DEFAULT_REGIME
        context = dict(
            self._engine.options_context
            if self._engine.options_context is not None
            else DEFAULT_OPTIONS_CONTEXT
        )
        return self._fn(features, regime, context)


def adapt_shadow_fn(fn: Callable, engine: SignalEngine) -> Callable:
    """Return `fn` unchanged if it fits the 1-arg contract, else a ShadowAdapter."""
    if is_shadow_fn(fn):
        return ShadowAdapter(fn, engine)
    return fn
