# Phase 4 Lane C — Intelligence Fixes (F-INTEL-007, F-INTEL-004) — Findings

**Date:** 2026-08-05
**Scope:** Phase 4 quick wins, Lane C — two intelligence fixes:
  1. **F-INTEL-007** — EMA NaN/None guard (`intelligence/features/indicators/ema.py`)
  2. **F-INTEL-004** — Honest `RegimeFilter` (`intelligence/risk/risk_engine.py`)
**Status:** Complete — full suite passes (1016 passed / 0 failed / 0 skipped), both fixes regression-tested (red→green verified)

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/intelligence/features/indicators/ema.py` | NaN/None LTP guard: bad ticks are skipped entirely — previous EMA returned (or None before the first valid tick), state untouched, stream resumes correctly |
| `src/shettyxtreme/intelligence/risk/risk_engine.py` | `RegimeFilter` is now an **honest stub**: `is_stub = True` class flag + `check()` returns a neutral ALLOW with an explicit `reason="stub: …"` marker instead of silently passing |
| `tests/intelligence/features/test_indicators.py` | Regression test `test_ema_skips_nan_and_none_ltp` |
| `tests/wave2/test_risk_engine.py` | Regression tests `TestRegimeFilter::test_regime_filter_is_honest_stub`, `TestRegimeFilter::test_regime_filter_does_not_block_engine_entry` |
| `docs/superpowers/plans/2026-08-05-phase4-lane-c-findings.md` | This report |

## Verification

- Full suite: `pytest tests/ -q --tb=short --basetemp=...\pytest-phase4 -p no:cacheprovider` → **1016 passed / 0 failed / 0 skipped** (baseline 1012 + 3 new regression tests; pre-existing conftest churn from the phase-3 working tree included)
- Red→green: both regression tests failed against the unpatched code (NaN returned `nan`; `None` LTP raised `TypeError`; `RegimeFilter.is_stub` did not exist) and pass after the fix
- `import openalgo` grep gate: zero matches in touched files (untouched rule, spot-checked)
- God-module guard: ema.py 38 lines, risk_engine.py 199 lines — both ≪ 1000

---

## 1. F-INTEL-007 — EMA NaN/None guard

### Symptom

`EMA.update()` assumed every `Tick.ltp` was a valid float:

```python
price = tick.ltp
self._count += 1
if self._count == 1:
    self._value = price          # ← NaN poisons the seed
    return self._value
self._value = price * self._k + self._value * (1 - self._k)  # ← None → TypeError
```

- A **NaN** first tick seeded `_value = NaN`, after which every subsequent EMA was NaN forever (silent corruption — the worst kind).
- A **None** LTP anywhere crashed with `TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'` (or contaminated the sum after the first tick).

### Fix

A single guard at the top of `update()` treats NaN/None ticks as **non-events**:

```python
if price is None or (isinstance(price, float) and math.isnan(price)):
    return self._value          # previous value, or None before first valid tick
```

- No `_count`/`_value` mutation on bad ticks → the EMA is a pure function of the *valid* tick stream; a bad tick can never advance `_count` (which would make the first valid tick mis-seed) nor corrupt the seed.
- **Behavior contract:** "return previous value or None" (the mission spec). After warm-up the feature engine keeps the previous EMA value in `features` (`feature_engine.py` line 61: `result is not None` → stored); before warm-up the feature stays absent. No downstream NaN propagation.
- The `# type: ignore[operator]` hack on the EMA line is replaced by an `assert self._value is not None` — mypy-clean narrowing with no behavioral cost.

### Regression test

`test_ema_skips_nan_and_none_ltp` covers: cold-start NaN/None → `None` + no state; warm-up normal; interleaved NaN/None → previous value returned, `value` unchanged; stream continues correctly (`30.0 → 22.5`). Red: `nan is None` assertion failure + TypeError; Green after fix.

---

## 2. F-INTEL-004 — Honest `RegimeFilter`

### Symptom

`RegimeFilter.check()` unconditionally returned `RiskDecision.allow(self.name)` — an **undocumented no-op** that pretended to "block entry if regime is incompatible with the signal direction" while never blocking anything.

### Decision: honest neutral stub (not fake-real)

The mission allowed either real regime logic **or** an honest neutral with an explicit stub flag. Real logic is currently impossible in the risk chain: **neither `Signal` nor `Portfolio` carries a regime**, and the `check(signal, portfolio)` protocol has no third input. Regime data exists only in the live pipeline — `RegimeClassifier` → `regime.changed` EventBus event → `RegimeBusBridge` → projection (`intelligence/regime/bus_bridge.py`, wired in `terminal/api/app.py`) — and never reaches the filter chain. Plumbing it in would mean a cross-layer signature change (new field on `Signal`/`Portfolio` or a provider on the protocol), which is a feature, not a quick win — and it would touch files outside Lane C ownership.

Any "real" logic derived from the signal alone (e.g. gating on `signal.direction`) would be **fabricated** regime data — exactly the kind of dishonest stub this task is meant to eliminate. So the fix is the second sanctioned option:

```python
class RegimeFilter:
    """… currently an HONEST STUB. …"""
    is_stub = True

    def check(self, signal, portfolio):
        return RiskDecision(
            allowed=True,
            reason="stub: no regime source in risk chain — neutral",
            filter_name=self.name,
        )
```

- **`is_stub = True`** is a public, programmatic marker — audit tooling can detect that no regime gating occurred without string-matching reasons.
- The **`reason`** now names the stub explicitly on every decision, so the audit trail is honest about what the filter did.
- The filter **stays in the default chain** (engine parity, uniform `RiskFilter` protocol, complete audit trail) — it is documented as a stub, not silently removed.
- `allowed_regimes` config remains (already present) so a future real implementation slots in without signature churn.

### Regression tests

- `test_regime_filter_is_honest_stub` — asserts `is_stub is True`, `allowed`, `filter_name == "regime"`, `"stub" in reason`. Red: `AttributeError: 'RegimeFilter' object has no attribute 'is_stub'`; Green after fix.
- `test_regime_filter_does_not_block_engine_entry` — asserts the default engine (which includes `RegimeFilter`) still ALLOWs entries, locking in the neutral behavior.

---

## Findings / notes for later phases

1. **Regime gating in the risk chain needs plumbing.** To make `RegimeFilter` real: add a regime source to the check path — either a `regime: Regime | None` field on `Signal` (filled by the pipeline's regime bridge, which already updates `signal_engine.regime`) or an optional `regime_provider: Callable[[], str | None]` injected into `RegimeFilter.__init__` with a neutral fallback when it returns `None`. The `allowed_regimes` whitelist is already in place. This is the natural follow-up feature (worth a spec).
2. **The "VOL-EXPAND" category in the mission text has no enum home.** `Regime` (regime_classifier.py) defines `trending_up / trending_down / range_bound / volatile / transition`; the mission's TREND/RANGE/VOL-EXPAND phrasing maps loosely onto those. If a real filter ships, `allowed_regimes` should be validated against `Regime` enum values to avoid drift.
3. **Feature-engine integration confirmed safe.** The guard's "return previous value" contract slots cleanly into `FeatureEngine.process_tick` (line 59–62): a bad tick leaves `features[name]` at the last valid EMA instead of dropping or NaN-poisoning it.

## Files touched

- `src/shettyxtreme/intelligence/features/indicators/ema.py` (owned)
- `src/shettyxtreme/intelligence/risk/risk_engine.py` (owned)
- `tests/intelligence/features/test_indicators.py` (regression)
- `tests/wave2/test_risk_engine.py` (regression)
- `docs/superpowers/plans/2026-08-05-phase4-lane-c-findings.md` (this report)

No other files were modified. Nothing committed.
