# P2-3.4 — Backtesting Engine (IAF adapter) — Findings

**Date:** 2026-08-12
**Task:** Vendor `investing-algorithm-framework` (IAF) + build an adapter behind an ACL
**Scope:** `learning/` (walkforward), `integration/`, `vendor/`, `docs/decisions/ADR-009`
**Status:** Findings only — algorithm for the fix, no code written

---

## Executive summary

ShettyXtreme's only backtest is a **point-in-time, non-event-driven evaluator**
(`learning/walkforward.py`) — it is a library with **no runtime caller, no bar
loop, no position-sizing rules, no cooldown rules, no slippage, and only
Sharpe + max-drawdown metrics**. There is no strategy-comparison surface and no
backtest engine.

**IAF is not vendored, not referenced, and not planned anywhere in the repo.**
`vendor/` holds only `openalgo/`; `integration/` has no `external/` package;
grep for `iaf|IAF|investing-algorithm` returns **zero matches**; ADR-009 does
**not exist** (ADRs 001–008 only). Upstream (verified 2026-08-12): IAF =
`coding-kitties/investing-algorithm-framework`, **Apache-2.0**, pip package
`investing-algorithm-framework`, v8 stable / v9.0.0a2 alpha (OBTF storage +
dual vector/event engines). Every capability the task wants — event-driven
backtest, `PositionSize`/`ScalingRule`, `StopLossRule` (trailing), `CooldownRule`,
Sharpe/Sortino/Calmar/drawdown — exists in IAF. The unwanted parts (CCXT live
integration, AWS Lambda/Azure deploy, Finterion marketplace) are separable.

**Key tension to resolve in the spec (not here):** the roadmap has "backtest
depth" **DECIDED-DEFER** since Phase 4 (last re-confirmed 2026-08-06, trigger =
"strategy-comparison surface"). IAF's `BacktestReport` is precisely that
comparison surface — so this task **re-opens a recorded deferral** and needs the
roadmap row + a new ADR-009, not just an adapter.

---

## 1. Current backtesting architecture (what exists)

### 1.1 The only "backtest": `learning/walkforward.py` (205 lines)

`WalkforwardEvaluator` / `WalkforwardResult` — the self-described
"honest option-premium backtest":

- **Input is not bars.** It consumes `list[SignalDecision]` + two dicts
  (`entry_prices`, `exit_prices` keyed by decision id) supplied by the caller.
  There is **no time loop, no bar-by-bar execution, no fill simulation**.
- **Exit policy is a static simulation** (`_simulate_exit`, lines 62–89):
  TP1/TP2/TP3 premium targets (`tp1=0.30, tp2=0.60, tp3=1.00`), a trailing-stop
  line computed **from entry** (`tsl_atr_multiplier=1.5`), and EOD exit at
  `15:15`. It is not a live stop engine — no stop ratcheting, no partial exits.
- **Costs** subtracted via `intelligence/risk/cost_model.py: compute_cost`
  (India-correct: STT + exchange + stamp etc.), fixed `lot_size` (default 65;
  hardcoded `LOT_SIZE` flagged separately in P0-1.5 findings).
- **Metrics:** `total_return`, `win_rate`, `avg_win`, `avg_loss`,
  `sharpe_ratio` (per-trade mean/std, **not annualized**), `max_drawdown`
  (sum-based), `per_voter`, `per_regime`.
- **No runtime caller.** Grep shows `WalkforwardEvaluator` referenced only from
  `learning/__init__.py` and `tests/wave4/test_walkforward.py`. Results are
  never persisted (corroborated by `2026-08-05-phase6w3-item7-findings.md`
  analytics-data-inventory: "No runtime caller; results never persisted").
- **Missing vs. task requirements:** event-driven realism, position sizing
  rules, scaling/pyramiding, cooldown after stop-out, Sortino/Calmar, slippage.

### 1.2 Supporting learning-loop modules (`src/shettyxtreme/learning/`)

| Module | What it does | Reuse value |
|---|---|---|
| `outcome_tracker.py` | SQLite persistence of decisions/execution attempts/outcomes | **Reuse** — replay/validation source |
| `voter_quality.py` | Per-voter hit rate + adjusted weights | Keep (live loop, unchanged) |
| `calibration.py` | Conviction→win-probability curve (Wilson CI) | **Reuse** — sizing input |
| `sizing.py` | `CalibratedSizing` — scale qty by calibrated win rate | **Reuse** — feeds `PositionSize` |
| `mfe_mae.py` | In-memory MFE/MAE per signal | Keep or replace (IAF has its own) |
| `analytics.py` | Regime stats, voter contribution, cost, perf summary | Keep for live loop |
| `shadow_loop.py` | EventBus wiring: decisions→shadows→session outcomes | Keep — unrelated to backtest |
| `sessions.py` | SessionLog SQLite | Keep |

### 1.3 Adjacent pieces

- **Pre-trade risk, not backtesting:** `intelligence/risk/risk_engine.py`
  (`LossLimitFilter`, `MarginFilter`, `MaxPositionFilter`, `RegimeFilter`) +
  `cost_model.py` (`compute_cost`, `adjust_ev`, `check_marginal`).
- **Dead optional dependency:** `pyproject.toml:45`
  `backtest = ["vectorbt>=0.3"]` — declared but **never used in `src/`**
  (grep: only docs mention vectorbt). IAF supersedes this.
- **Roadmap context:** feature map §08 "Backtest depth (vectorbt strategy
  library) | Phase 4 | Valuable"; architecture §06 table row
  "Backtest | Historical | Simulated | — | Evaluation (walkforward,
  calibration)"; §14 principle "the backtest path is the live path"
  (honest-by-construction, from BRIEF-ai-hedge-fund §2); §04 India-first
  session boundaries (a bar spanning 15:30→09:15 is a gap artifact) and the
  mandate to persist live-captured data into DuckDB TS from day one.
- **Deferral record:** `.scratch/phase4-knowledge-dashboards/issues/08-backtest-depth-scope.md`
  + `2026-08-05-phase7w4-decided-defer.md` — "Walkforward stays; no comparison
  surface in `src/`". **Trigger:** strategy-comparison surface becomes a
  concrete requirement. IAF `BacktestReport` satisfies that trigger.

## 2. IAF integration status (vendored? adapter exists?)

**Nothing exists.** Verified by grep + glob:

- `vendor/` → only `openalgo/` (ADR-002: AGPL-3.0, private use, byte-idempotent
  resync via `scripts/sync_vendor.py`, `FILES.yaml`/`ORIGIN.md` manifest pattern).
- `grep -ri "iaf\|investing-algorithm"` → **0 matches** in the whole repo.
- `integration/` → `fyers/` (live) + `order_validator.py` + `instrument_master.py`;
  `integration/__init__.py` is a one-line comment. **No `integration/external/`
  package exists.**
- `docs/references/STATUS.md` reference registry → no IAF; no BRIEF file.
- No plan/spec/handoff mentions IAF; no ADR; no git branch (`master` +
  `fix/terminal-data-pipeline` only). The task id `P2-3.4` itself is not
  recorded anywhere in the repo (external tracker).

### 2.1 Upstream facts (verified 2026-08-12, web)

- **Repo:** `coding-kitties/investing-algorithm-framework` (~1.6k stars,
  1,859 commits). **License: Apache-2.0** (permissive — unlike openalgo's AGPL).
- **PyPI:** `investing-algorithm-framework`; **v8 stable**; v9.0.0 alpha
  (a2) is current head with **breaking API + persisted-data (OBTF) changes** —
  pin v8 for adoption, treat v9 as future.
- **Package:** `investing_algorithm_framework` with `TradingStrategy`,
  `PositionSize`, `ScalingRule`, `StopLossRule`, `TakeProfitRule`,
  `CooldownRule`, `TradingCost`, `BacktestReport`, `BacktestStore`, `iaf` CLI.
- **Engines:** Polars-powered **vector** backtest (`run_vector_backtests`) and
  **event-driven** backtest (`run_backtest`) — "bar-by-bar realism with order
  fills", same `TradingStrategy` code path for backtest/paper/live.
- **Metrics:** 30+ — CAGR, Sharpe, Sortino, Calmar, VaR/CVaR, Max DD,
  recovery, win rate, profit factor.
- **Live/deploy surface (to exclude):** built-in **CCXT** integration,
  AWS Lambda / Azure Functions deployment, Finterion marketplace plugin,
  paper/live trading with portfolio persistence.

## 3. What to use from IAF vs what NOT to use

### ✅ Use (all verified present upstream)

| Need (task) | IAF facility | Maps to / replaces |
|---|---|---|
| Event-driven backtesting (bar-by-bar realism) | `app.run_backtest` event engine, pluggable slippage/fill models | replaces walkforward's static `_simulate_exit` |
| Vector screening (bonus, matches roadmap's "vectorbt-style" intent) | `app.run_vector_backtests` (Polars) | supersedes the dead `vectorbt` optional dep |
| Position sizing rules | `PositionSize` (fixed or `percentage_of_portfolio`) | replaces fixed-lot math; driven by `CalibratedSizing` |
| Scaling rules | `ScalingRule` (`scale_in_percentage`, `max_entries`, `cooldown_in_bars`) | **new capability** — nothing equivalent in src/ |
| Stop-loss engine with trailing stops | `StopLossRule` (fixed/trailing, partial `sell_percentage`) + `TakeProfitRule` | ports walkforward TP1-3/TSL policy as declarative rules |
| Cooldown rules (prevent re-entry after stop-out) | `CooldownRule` (per-symbol/portfolio-wide, side-aware `trigger`/`blocks`/`bars`) | **new capability** — nothing equivalent in src/ |
| Backtest evaluation | Sharpe, Sortino, Calmar, drawdown, VaR/CVaR, recovery, profit factor | upgrades walkforward's Sharpe+max_dd |
| Comparison surface (the deferred trigger!) | `BacktestReport` self-contained HTML dashboard | the "strategy comparison surface" roadmap §17 was waiting for |
| Data + execution seams | custom data-provider and `OrderExecutor` protocols | Fyers/duckdb historical data in; live path stays ours |

### ❌ NOT use

- **CCXT integration** — FR-002/ADR-008: Fyers is primary; crypto venues
  irrelevant. Must be excluded at dependency/vendor boundary.
- **Cloud deployment** (AWS Lambda / Azure Functions) — out of scope
  (private-use, ADR-003).
- **IAF's live/paper trading path** — conflicts with D10 OBSERVER-first and
  our own `integration/fyers/` + `execution/` stack. Only the backtest engines
  + risk rules + metrics are wanted.
- **Finterion marketplace plugin** — monetization out of scope.
- **OBTF storage layer / `iaf` CLI / `BacktestStore`** — optional, defer for
  v1 (our results should not adopt IAF's persistence model until needed).

## 4. ADR-009 — does not exist (new work)

`docs/decisions/` holds ADR-001…008 only. ARCHITECTURE_V2's ADR index lists
001–008; `.projectos/decisions/INDEX.jsonl` has ADR-001 + ADR-008. **ADR-009 is
greenfield** and must record the IAF integration boundary:

- What we take (event engine + vector engine, PositionSize/ScalingRule/
  StopLossRule/TakeProfitRule/CooldownRule/TradingCost, metrics, BacktestReport)
  vs what we exclude (ccxt, cloud deploy, Finterion, live/paper path, OBTF v1).
- **Dependency admission per §05 external-deps table** ("new deps require an
  ADR") — IAF becomes a tracked row.
- **Vendoring vs pip decision** (see §6): Apache-2.0 makes a plain pip dep
  legal, but IAF's install pulls ccxt etc.; vendoring (ADR-002 precedent)
  gives byte-idempotent sync + exclusion control. Either way, FR-004 ACL holds.
- **Where the ACL lives**: `integration/external/` + a `core/interfaces`
  Protocol (FR-003/FR-005), so nothing above integration imports IAF.
- **Grep gate to add:** `grep -r "import investing_algorithm_framework" src/`
  must be zero outside the adapter (mirrors the openalgo standalone rule).

## 5. Existing code that can be reused

1. **Exit-policy parameters** — `walkforward.py:42-51` (`tp1/tp2/tp3`,
   `tsl_atr_multiplier`, `tsl_stop_fraction`, `eod_time=15:15`): the exact
   numbers to declare as IAF `TakeProfitRule`/`StopLossRule` + EOD exit.
2. **`intelligence/risk/cost_model.py: compute_cost`** — India-correct cost
   model → becomes `TradingCost` rules (fees/slippage) so backtest costs match
   live-cost expectations.
3. **`learning/sizing.py: CalibratedSizing`** + **`calibration.py:
   CalibrationCurve`** — conviction-calibrated multiplier → drives
   `PositionSize` percentages.
4. **`learning/outcome_tracker.py` + `shadow_loop.py`** — recorded decisions
   and outcomes are the replay/validation corpus for backtests.
5. **`learning/mfe_mae.py: MfeMaeCalculator`** — realized MFE/MAE for
   target/stop tuning (keep in-house or let IAF's equivalents supersede — spec
   decision).
6. **`integration/fyers/` data adapters + DuckDB TS capture mandate** (§04) —
   historical premium/underlying bars for India session-correct data.
7. **Vendoring infra** — `scripts/sync_vendor.py` + `vendor/openalgo/`
   (`FILES.yaml`, `ORIGIN.md`) as the manifest template if we vendor.
8. **`tests/wave4/test_walkforward.py`** — port the TP/SL/EOD expectations as
   baseline acceptance for the IAF-backed engine.

## 6. Proposed fix approach (algorithm, not code)

1. **Re-open the deferral (gate first).** Update
   `.scratch/.../issues/08-backtest-depth-scope.md`, roadmap §17 Phase-4 row,
   and `2026-08-05-phase7w4-decided-defer.md` — the comparison-surface trigger
   is now met by IAF `BacktestReport`. Without this, the work contradicts a
   recorded decision.
2. **ADR-009 first** (§4) — integration boundary, dependency admission,
   vendoring-vs-pip stance, exclusion list, grep gate.
3. **Dependency mechanism:** (a) *vendored* via `scripts/sync_vendor.py`
   (openalgo precedent, strips ccxt/cloud/Finterion at source, byte-idempotent)
   **or** (b) pip dep with `--no-deps` + import-blocked stray modules. Vendoring
   is the more precedent-consistent choice given the ccxt coupling; pin v8
   (v9 alpha has breaking OBTF changes). **Decision belongs to the user in the
   spec phase.**
4. **ACL + adapter:** add a `BacktestEngine`-style Protocol to `core/interfaces/`
   (FR-005); implement `integration/external/iaf_adapter.py` translating
   ShettyXtreme signal/decision inputs → `TradingStrategy`, mapping our cost
   model to `TradingCost`, sizing to `PositionSize`, TP/SL policy to
   `TakeProfitRule`/`StopLossRule`, and adding `CooldownRule`s. src/ above
   integration never imports IAF (FR-004).
5. **Data:** historical bars from `integration/fyers/` + DuckDB TS, India
   session-aware (FR-001); keep "backtest path = live path" honesty (§14).
6. **Landing surface:** first consumer is the walkforward replacement —
   `learning/` exposes a `run_backtest` API over the adapter; results feed
   `BacktestReport` for the comparison dashboard. OutcomeTracker/analytics/
   shadow_loop stay as-is.
7. **Housekeeping:** drop the dead `vectorbt` optional dep (`pyproject.toml:45`)
   in the same change; add IAF import grep gate; version-bump all 5 drifted
   files per AGENTS.md.
8. **Docs ritual:** spec → plan → handoff in `docs/superpowers/` (superpowers
   convention; this is multi-file, cross-layer work — not a tiny-fix).

### Gates (from AGENTS.md)

- Full suite green (1012 baseline, exact pytest invocation with `--basetemp`).
- `grep -r "import investing_algorithm_framework" src/` → zero outside the
  adapter (and outside `vendor/` if vendored).
- `grep -r "import ccxt" src/ vendor/` → zero.
- No file > 1000 lines; `core/` stays external-free.

## 7. Open questions for the spec phase

1. **Vendor (sync_vendor) vs pip `--no-deps`?** (ADR-009 must answer; openalgo
   precedent favors vendoring, Apache-2.0 makes pip viable)
2. **IAF version pin:** v8 stable vs v9.0.0a2 alpha (breaking OBTF/API)?
3. **Scope of v1:** event engine + rules + metrics + report only, or also
   vector sweeps and multi-window robustness?
4. **Reuse boundaries:** keep in-house MFE/MAE + calibration curve, or
   let IAF's supersede them?
5. **Data source for history:** Fyers REST history now, or DuckDB TS replay
   once the capture mandate (§04) is wired?
