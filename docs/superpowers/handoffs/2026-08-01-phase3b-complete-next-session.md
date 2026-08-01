# ShettyXtreme — Session Handoff (2026-08-01): Phase 3B complete, next = merge decision + 3C

> **For the next session:** read this first, then `.superpowers/sdd/progress.md` (untracked, local ledger). All artifacts below are committed to branch `phase3b-research-workspace`; master NOT yet merged/pushed for 3B.

## 1. Where things stand

- **Repo:** D:\ShettyXtreme · **Branch:** `phase3b-research-workspace` @ `8fe8d1a` (7 commits above master `feb301d`). Suite **599 passed / 0 failed / 3 skipped** (was 563). Final review: **READY TO MERGE (YES)**.
- **LLM provider decision made:** DeepSeek (`api.deepseek.com`, OpenAI-compatible, model `deepseek-v4-flash`). Key: `DEEPSEEK_API_KEY` env-only, read at call time, never committed. User provided the key in chat — **must set it as an env var to use** (I never wrote it to disk).

## 2. What Phase 3B shipped (per spec `docs/superpowers/specs/2026-08-01-phase3b-research-workspace-design.md`, plan `docs/superpowers/plans/2026-08-01-phase3b-research-workspace.md`)

- **`research/` package**: `provider.py` (BriefProvider protocol + DeepSeekProvider via httpx, JSON-output mode, non-thinking + SimulatedProvider with deterministic failure injection — the ONLY LLM-touching module, D3 wall), `lenses.py` (3 declarative lenses: oi_iv_flow, directional_momentum, tail_risk), `digest.py` (ContextDigest with [SOURCE]/[UNSOURCED] provenance), `briefs.py` (strict ResearchBrief schema — unknown-field rejection, harness-owned fields unspoofable), `orchestrator.py` (asyncio.gather, reject-retry-once-then-fail, token caps, partial results), `store.py` (sqlite, append-only decisions, expiry at read, outcome stub).
- **`/api/research/*`**: `run` (lenses + optional context), `lenses`, `briefs` (list/get), `approve`/`reject` (409 double-decision). 503 without key, 400 unknown lens, never 500 on failed briefers/missing DBs.
- **`scripts/research_smoke.py`**: env-gated manual run (exit 2 without key; tests never call the real API).
- Docs: CHANGELOG v0.8.0, roadmap §17 Phase 3 row, README roadmap.

## 3. Next-session todo list (in priority order)

1. **Merge decision for 3B** (pending user) — branch `phase3b-research-workspace` → master; then **push master** (origin is 14+ commits behind: v0.7.1 + v0.8.0) — user's call.
2. **Smoke run with the real key** — user sets `DEEPSEEK_API_KEY` env var, then `& .\.venv\Scripts\python.exe scripts\research_smoke.py`. Watch for: `thinking: {"type": "disabled"}` acceptance (if 400, drop the field — thinking defaults ON), JSON mode reliability, brief quality per lens.
3. **3C (research workspace full surface)**: read-only data tools/MCP (single-source REST/WS/MCP per section 12), critic model pass, terminal panel + WS broadcast, scheduled runs, briefer outcome scoring (store stub exists). Spec'd via brainstorming → spec → plan when started.
4. **Registry→engine wiring** (from 3A ledger, still open): 3-arg ShadowFn vs 1-arg VoterRegistry adapter + name-collision guard.
5. **Deferred minors (3B ledger)**: `ResearchBriefResponse` mirrors `ResearchBrief` (schema duplication — revisit in 3C); `decided_at` never surfaced in responses.
6. **Deferred minors (3A ledger, unchanged)**: rollback() in graduate except, TestGraduation registry hygiene, atomicity failure-path test, legacy-DB migration test, N+1 in graduation_status(), WS D/P/G broadcast, learning_router table-literal consolidation.
7. **Live `/optionchain` fixture** — open question, needs live Dhan credentials.
8. **Phase 4** (roadmap §17): knowledge layer (D12), analytics dashboards, optional multi-broker.

## 4. Bindings & conventions (recap)

- Decisions D1–D12 binding (ARCHITECTURE_V2.md); D3: agents research-only — `provider.py` is the only LLM-touching module.
- Test runner (Windows): `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-<phase> -p no:cacheprovider` — never bare `pytest` (basetemp required: pytest-current PermissionError quirk).
- Pre-existing dirty file `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` — never stage/commit (still dirty on the branch; verified unstaged).
- SDD: ledger `.superpowers/sdd/progress.md` untracked/local; graphify rebuilds per commit (background).
- Second Brain (O2B vault D:\RohanShettyObsidian): pinned context updated for Phase 3B post-merge.

## 5. Open questions for the user

1. Merge 3B to master? (Final review: READY — YES)
2. Push master (v0.7.1 + v0.8.0) to GitHub?
3. Set `DEEPSEEK_API_KEY` and run the smoke script now?
4. Priorities: 3C research surface vs registry→engine wiring vs Phase 4.
