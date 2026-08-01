# ShettyXtreme — Session Handoff (2026-08-01): Phase 3C shipped + pushed, Phase 4 next

> **For the next session:** read this first. Ledger: `.superpowers/sdd/progress.md` (local, untracked). Full decision + commit map for 3B/3C: `docs/superpowers/handoffs/2026-08-01-session-record-complete.md` and this file.

## 1. Where things stand

- **Repo:** D:\ShettyXtreme · **master** @ `bbb5577`, **pushed to origin** (v0.9.0 — hygiene wave + Phase 3C shipped together). Suite **655 passed / 0 failed / 0 skipped** (verified on merged result; the 3 recurring skips stay dead — 0 skipped is a permanent gate).
- **Branch `phase3c`:** merged (no-ff `bbb5577`) and deleted. Working tree carries only the never-stage files (`AGENTS.md`, `.opencode/opencode.json`, `docs/superpowers/plans/2026-07-31-graphify-upgrade.md`, untracked `.gitattributes`).
- **Versions:** bumped to 0.9.0 in all four drift locations (`__init__.py`, `app.py`, `pyproject.toml`, `package.json`).

## 2. What Phase 3C shipped (spec `docs/superpowers/specs/2026-08-01-phase3c-research-workspace-surface-design.md`, plan `docs/superpowers/plans/2026-08-01-phase3c-research-workspace-surface.md`)

- **Tool registry** (`research/tools.py`): 4 read-only tools + `DataSource` protocol + `set_data_source`/`run_tool`; `GET /api/research/tools` (single source for REST + function calling).
- **Provider v2** (`research/provider.py`): `ProviderResponse {content, tool_calls}`, `generate(tools=, history=)`, DeepSeek `_parse_tool_calls`, `SimulatedProvider.simulate_tool_calls`; all wave8 provider tests migrated (deliberate interface bump).
- **Tool loop** (`research/orchestrator.py`): `MAX_TOOL_CALLS=3` per lens, budget exceeded → lens error, `TOOL ERROR:` recovery, retry rebuilds fresh messages (`messages` rebuilt per attempt — review fix), `on_brief` callback; no-tools path byte-identical to 3B.
- **Scheduler** (`research/scheduler.py`): env-config (`RESEARCH_SCHEDULE_*`), default off, key-gated start in lifespan, never-crash ticks, `interval_minutes <= 0` rejected (review fix), `GET /api/research/scheduler`.
- **Scoring + decided_at**: `decided_at` on `ResearchBrief` (not model-authorable) + responses; `POST /briefs/{id}/outcome` (400 invalid / 404 unknown / 409 undecided); `GET /api/research/scoring` per-lens aggregates.
- **Router + wiring**: `init_research(broadcast_fn, scheduler)`, `build_orchestrator()`, `/run` tools validation (400), decision broadcast; `ProjectionDataSource` (`research_source.py`) wired in lifespan; broadcast = `asyncio.create_task(ws_manager.broadcast("research", data))`.
- **Frontend**: `ResearchPanel.svelte` (450 lines) + `ResearchBriefDetail.svelte` (176) — run bar (lens checkboxes bind:group + tool multi-select), filterable list, detail with evidence/[UNSOURCED]/approve-reject; `api.ts` `postBody` + types; WS topic `research` via existing `onMessage` registry (ws.ts unchanged); bundle committed.

## 3. Gates (all verified)

- Full suite **655/0/0**; grep zero `import openalgo`; new files ≤500 lines; svelte-check 0 errors (2 a11y warnings — repo baseline); review: 3 IMPORTANT + 2 MINOR fixed, 4 MINOR deferred (below).

## 4. Deferred minors (recorded in ledger — pick up in Phase 4 hygiene)

1. Two sqlite connections to `data/research.db` (scheduler tick vs manual run) can contend → per-lens `persist failed`, never crash; add `sqlite3.connect(timeout=...)` later.
2. `tests/wave8/test_research_api.py`: module-global discipline is manual (`rr.RESEARCH_DB_PATH`/`_ORCHESTRATOR`/`init_research`) — add autouse snapshot/restore fixture (pattern: `_reset_source` in test_research_tools.py).
3. Filter "chips" implemented as `<select>` dropdowns (spec said chips) — functional, cosmetic.
4. `ProjectionDataSource.chain_summary`/`options_summary` → `[UNSOURCED]` until Phase-4 renderers exist (by design). WS `decision` handler stamps client-side `decided_at` (approximates server time until refresh).

## 5. Live smoke results (real DeepSeek key — user-provided, env-only, never stored)

- `scripts/research_smoke.py`: **EXIT=0** — all 3 lenses produced schema-valid briefs; `thinking: {"type":"disabled"}` accepted; JSON mode reliable.
- `/api/research/run` with `tools: ["regime_snapshot","scanner_alerts"]` through uvicorn: valid brief, no 400/500; scheduler status endpoint live.
- **Real function-calling contract verified:** DeepSeek returned `tool_calls` → parsed `chain_snapshot(NIFTY)` correctly.
- **Finding (documented, not a bug):** DeepSeek `response_format: json_object` 400s unless the prompt contains the word "json" — all lens prompts satisfy this; ad-hoc prompts must too.

## 6. Next session todo list (in order)

1. **Phase 4 chart** — wayfinder map on the local-markdown tracker (set up via setup-matt-pocock-skills first: `.scratch/` convention). Destination: knowledge flow end-to-end (D12: doc store + tagger + heuristic extractor, human-gated activation) + analytics dashboards + optional multi-broker/backtest depth. Brainstorm → decision tickets → research subagents in parallel.
2. **Optionally pick up deferred minors** (§4) as a hygiene wave or fold into Phase 4.
3. **Live `/optionchain` fixture** — still open; needs live Dhan credentials (Dhan error 806 = Data-API entitlement, surface don't paper over).
4. Keep the 0-skipped + ≤500-line + grep gates on every change.

## 7. Conventions (unchanged)

- Test runner: `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` with `PYTHONPATH=""` — never bare `pytest`.
- D1–D12 binding; D3: `research/provider.py` is the only LLM-touching module; no LLM output in signal/gate/execution; tools read-only.
- Dirty file `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` — never stage/commit.
- SDD: ledger local/untracked; graphify background rebuilds per commit; codegraph watcher live.
- O2B vault: pinned context + milestone notes updated this session.
