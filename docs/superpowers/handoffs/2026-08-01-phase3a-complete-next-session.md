# ShettyXtreme — Session Handoff (2026-08-01): Phase 3A merged, next = 3B + Phase 4

> **For the next session:** read this first, then `docs/architecture/v2/ARCHITECTURE_V2.md` (decisions D1–D12) and `.superpowers/sdd/progress.md` (untracked, local ledger). All artifacts below are committed to `master` unless noted.

## 1. Where things stand

- **Repo:** D:\ShettyXtreme · **Branch:** `master` @ `19f3a69` (merge commit) — v0.7.1, suite **563 passed / 0 failed / 3 skipped** (verified on the merged result). Remote: github.com/RohannShetty/ShettyXtreme — **master NOT yet pushed for 3A** (origin/master is at `08d4032` v0.7.0).
- Phases 0, 1, 2, 3A: DONE. Remaining: **Phase 3B** (research workspace + AI research layer, D3) and **Phase 4** (maturity: knowledge layer, analytics, optional multi-broker).

## 2. What Phase 3A shipped (merged)

Session-gated shadow graduation (≥20 sessions, correctness = sign match AND outcome WIN — user decision), atomic `graduate()`, `CalibratedSizing` → hint quantity, correlation block caps + conviction D/P/G live on `Signal`, walkforward per-voter/per-regime breakdowns, `/api/learning/{calibration,shadows}`. Spec: `docs/superpowers/specs/2026-08-01-phase3a-advanced-intelligence-design.md`; plan: `docs/superpowers/plans/2026-08-01-phase3a-advanced-intelligence.md`.

## 3. Next-session todo list (in priority order)

1. **Push master to origin** (`git push origin master` — brings v0.7.1) — user's call, was not requested at merge time.
2. **Phase 3B — research workspace + AI research layer (D3).** FIRST ask the user for the **LLM-provider decision** (opencode's headroom proxy is NOT an LLM provider; needs a real provider/key or a provider-agnostic interface with a simulated briefer for tests — spec §12 pattern). Then: brainstorming → spec (`docs/superpowers/specs/`) → plan → SDD. Scope per `docs/architecture/v2/sections/12-ai-agentic-references.md`: 5-stage loop (research → gate → critic → approve → execute), read-only data MCPs only (no order tools), output-schema validation with reject-retry, token budgets, human approval cards, intent records, hard guardrails (D3: agents never gate/place orders).
3. **Registry→engine wiring** (deferred integration): graduated shadow voters are 3-arg `ShadowFn`s in a 1-arg-typed `VoterRegistry` that `SignalEngine` doesn't consume; needs an adapter + name-collision guard. This closes the Phase-2 "voter discovery" gap.
4. **Deferred minors from the ledger** (all non-blocking): rollback() in `graduate()` except; TestGraduation registry hygiene (snapshot/restore like the e2e file); atomicity failure-path test; legacy-DB migration test; N+1 in `graduation_status()`; WS broadcast omits D/P/G (when the UI gets a conviction panel); learning_router table-literal consolidation into `graduation_status()`.
5. **Live `/optionchain` fixture** (OPEN QUESTION in `intelligence_router.py` docstring): needs live Dhan credentials to record; align `strike`/`strike_price`/spot keys.
6. **Phase 4** (roadmap §17): knowledge layer (D12, human-gated, physically separated), analytics dashboards, optional multi-broker via `core/interfaces`.
7. **Real shadow activation**: automatic once ≥20 real OBSERVER sessions accumulate (machinery proven with synthetic sessions — no fake claims).

## 4. Bindings & conventions (recap)

- Decisions D1–D12 binding (ARCHITECTURE_V2.md): no `import openalgo` in src/; DESIGN.md token contract; DhanHQ-py 2.2.0; OBSERVER default, LIVE per-session confirmation; 806 = Data-API entitlement; D3 agents research-only.
- Test runner (Windows): `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-<phase> -p no:cacheprovider` — never bare `pytest`.
- Pre-existing dirty file `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` — never stage/commit (still dirty on master).
- SDD process: briefs + review packages under `C:\Users\rohan\AppData\Local\Temp\opencode\<phase>\`; review packages written manually (`git diff -U10 BASE HEAD` → file — skill helper paths contain literal backslashes on Windows).
- graphify rebuilds per commit (background); codegraph watcher live; ledger `.superpowers/sdd/progress.md` is untracked/local.
- Second Brain (O2B vault D:\RohanShettyObsidian): pinned context + milestone notes updated for Phase 3A.

## 5. Open questions for the user

1. Push master (v0.7.1) to GitHub?
2. LLM provider for 3B (or provider-agnostic + simulated briefer)?
3. Priorities for 3B vs the deferred minors vs Phase 4.
