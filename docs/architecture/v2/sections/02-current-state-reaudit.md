# Section 02 — Current-State Reaudit

A restatement of the verified v1 delivery state (from the Phase-1 decisions pack — no re-exploration of `src/` was performed; the pack's inventory is binding) as the baseline v2 rewrites against. Per D5, v1 is archived at `docs/architecture/v1/` and v2 is a full rewrite at `docs/architecture/v2/`. This section answers: what did v1 actually deliver, what is right and must survive, what is wrong and must be corrected, and what breaks today.

## 1. What v1 delivered

Phase 3 of the v1 program was completed. Ship state, verified at pack-writing time (2026-08-01):

- **Version:** v0.7.0 (post-Phase-2); **527 tests passing**, 0 known failures (was ~495 / 4 — see §3 for the resolved set).
- **Entry point:** `run.py` — opens browser, starts uvicorn on 127.0.0.1:8000; CLI flags `--mode OBSERVER|PAPER|LIVE` (D10: OBSERVER default, LIVE needs typed confirmation), `--no-browser`, `--port` (Phase 2).
- **Config:** `configs/default.yaml` — broker dhan, dry_run true, mode observer.
- **Storage:** `data/shetty_kv.db` (sqlite KV) + `data/shetty_ts.db` (duckdb time-series).

Module inventory (verified):

| Module | Contents |
|---|---|
| `core/` | Domain models, event bus (Topic/Event), interface Protocols, config, storage (sqlite KV + duckdb TS) |
| `auth/` | Fernet CredentialStore, DhanOAuthHelper consent flow, TokenHealthMonitor, CredentialValidator |
| `integration/dhan/` | DhanTradingAdapter, DhanDataAdapter (incl. `get_option_chain`), SessionHealth, instrument_master, order_validator |
| `intelligence/` | feature_engine (O(1)/tick), regime_classifier, signal_engine + voters (breadth, micro, options_flow, orb, iv_rank) + shadow voters, risk_engine + cost_model, scanners |
| `execution/` | ExecutionEngine (semi-auto approve), PaperTradingEngine, PositionManager (TP/TSL/EOD) |
| `learning/` | OutcomeTracker, VoterQualityTracker, MfeMaeCalculator, WalkforwardEvaluator, CalibrationCurve, AnalyticsEngine |
| `options/` | greeks, iv_rank, oi_tracker, quantlib_pricer, strategy_analyzer |
| `terminal/` | FastAPI + static HTML dashboard/setup/settings; routers: watchlist, intelligence, execution, scanner, health, auth, postback, settings; WS echo |
| `observability/` | — (module present) |

## 2. What is right (v2 keeps these)

| Keeper | Why it survives |
|---|---|
| Event bus (Topic/Event) + interface Protocols | The modular-monolith seam v2 is built around ([Section 06 — Proposed Architecture](06-proposed-architecture.md)); core stability depends on it |
| Adapter split: trading vs data, SessionHealth, order_validator | Correct shape for D8's single-primary + data-fallback model; only details need fixing (see §4) |
| Intelligence stack: feature_engine O(1)/tick, regime_classifier, signal_engine + voters + shadow voters | The deterministic heart of the product — [Section 09 — ShettyBot Evolution](09-shettybot-evolution.md) preserves its DNA |
| risk_engine + cost_model | Already cost-aware; foundation for the cost-aware EV discipline in [Section 14 — Data-Decision Intelligence](14-data-decision-intelligence.md) |
| Learning loop (OutcomeTracker → VoterQualityTracker → WalkforwardEvaluator → CalibrationCurve → AnalyticsEngine) | v1's differentiator; survives intact as the `learning/` pillar |
| Options module (greeks, iv_rank, oi_tracker, quantlib_pricer, strategy_analyzer) | The options-first pipeline core per D6; the 2 501 stubs in it get implemented in Phase 2 |
| Fernet CredentialStore + consent flow | Secrets handling is sound; TokenHealthMonitor needs the real refresh path (see §4) |
| Storage split (sqlite KV for state, duckdb TS for time series) | Right choice; no change |
| Config defaults (dry_run true, mode observer) | Correct default posture — matches D10's intent; only the mode-file mechanism is wrong |
| FastAPI terminal scaffold + router separation | Terminal layer survives, frontend is replaced with Svelte per D9 |

## 3. The 4 known test failures — ALL RESOLVED (Phase 2, 2026-08-01)

The Phase-2 exit gate fixed every row below (suite: 527 passed / 0 failed):

| Test | Cause | Resolution (commit) |
|---|---|---|
| `test_get_options` | `get_option_chain` was a 501 stub | Implemented per D6 — chain + pure-Python greeks enrichment (`intelligence_router.py`); kills the 501 |
| `test_get_strategy_hint` | strategy-hint endpoint was a 501 stub | Implemented per D6 — `intelligence/hints/strategy_hints.py` (strike EV selection), wired to the hints panel (D4/design) |
| `test_execution_mode_default` | Mode file was env-dependent; default not asserted as OBSERVER | D10: OBSERVER is the runtime default; LIVE is an explicit per-session action with confirmation; test made deterministic |
| `test_matches_builtin_black76` | quantlib pricing mismatch vs reference | Relative 1% tolerance with the QuantLib calendar-convention delta documented (env-pinned, no silent skip) |

## 4. Landmines — ALL CLEARED (Phase 2, 2026-08-01)

| Landmine | Resolution |
|---|---|
| `intelligence/hints/__init__.py` dead import | Implemented `strategy_hints.py` (StrategyHints/StrategyHint) |
| `intelligence/conviction/__init__.py` dead import | Implemented `conviction_engine.py` (D/P/G per §14) |
| `VoterRegistry` pass-stub | Real registry (register/names/count/get, `@voter` decorator, `get_registry()`); shadow-voter activation remains Phase 3 |
| Stale conftest fixtures | Removed (`openalgo_adapter`, `dhan_adapter` imported nonexistent modules) |
| Empty dirs | Removed `execution/lifecycle/`, `execution/position_tracker/`, `tests/risk/`, `tests/integration/` |
| `core/errors/__init__.py` empty | Deleted (zero importers; no dead code in v2) |

## 5. Corrected facts: v1 said wrong, v2 says true

Binding per the pack (§33-38). These are the v1 stances that must never reappear in v2 docs or code:

| # | v1 (wrong) | v2 (truth) | Source |
|---|---|---|---|
| 1 | Dhan 806 = credential mixing / token problem | 806 = **Data-API subscription entitlement error** ("Subscribe to Data APIs to continue"); feed disconnect packet code at index 4 of `<BHBIH`, first byte 50 | `BRIEF-dhanhq-upstream.md` §3 |
| 2 | Feed request codes 2 (ticker) / 8 (full) | v2 feed codes are **15 (Ticker) / 17 (Quote) / 21 (Full)**; 19 (Depth) is v1-only; unsubscribe = code+1; disconnect = RequestCode 12; our `DhanDataAdapter` has a **latent bug** passing 2/8 | `BRIEF-dhanhq-upstream.md` §3 |
| 3 | Loose `dhanhq>=0.1.0` pin | Pin **`>=2.2.0,<2.3.0`**; 2.3.0rc1 is additive (conditional orders, global stocks, P&L exit); auth/feed/historical byte-identical to 2.2.0; only breaking change is unused `place_forever` | `BRIEF-dhanhq-upstream.md` §1 |
| 4 | OpenAlgo local copy is a sync source | Only mirror **v2.0.1.7** (`references/upstream/openalgo`) syncs to `vendor/`; local `D:\OpenAlgo` v2.0.1.4 is **contaminated** (personal strategy scripts) | `BRIEF-openalgo-upstream.md` §1 + D1 |
| 5 | (implicit) v1 relied on OpenAlgo as runtime dependency | **D1: standalone + vendoring** — no server, no `import openalgo` in `src/`; vendored code is adaptation source only | pack D1 |
| 6 | Stale adapter docstring "41=OHLC, 51=depth" | Those codes don't exist in the SDK; fix alongside the request-code bug | `BRIEF-dhanhq-upstream.md` §3 |
| 7 | `SessionHealth._init_context` rebuilds with the same stored token | A true refresh must call `DhanLogin.renew_token`/`generate_token` to mint a NEW token; feed-side 807 must trigger the same renewal path | `BRIEF-dhanhq-upstream.md` §8 |
| 8 | Mode default implementation is env-dependent | **OBSERVER is the runtime default; LIVE is an explicit per-session user action with confirmation** | pack D10 |

## 6. Where this leaves v2

The v1 architecture core — event bus, protocols, module seams, storage split, deterministic intelligence, learning loop — is sound and is the substrate v2 grows on. The corrections above are surgical (D8 credential model, D10 mode default, request codes, pinning, vendoring discipline), not structural. The 501 stubs are the two features that make the product options-first (per D6), and the landmines are housekeeping that Phase 2 (per [Section 17 — Delivery Roadmap](17-delivery-roadmap.md)) clears while the Svelte terminal lands (D9). The full rewrite scope is framed in [Section 06 — Proposed Architecture](06-proposed-architecture.md); per-module disposition (retain/refactor/deprecate) in [Section 09 — ShettyBot Evolution](09-shettybot-evolution.md).
