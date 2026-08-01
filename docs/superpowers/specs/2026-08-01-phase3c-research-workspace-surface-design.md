# Phase 3C — Research Workspace Full Surface: Design Spec

**Date:** 2026-08-01 · **Status:** DRAFT (user review) · **Repo:** D:\ShettyXtreme · **Branch:** phase3c from master (hygiene wave merged first)

## 1. Purpose

Complete the research workspace surface on the 3B core: read-only data tools the briefer can call mid-run (single-source registry + REST exposure), an in-process scheduler for periodic research passes, a richer terminal research panel with live WS updates, and brief scoring over the outcome stub — plus the `decided_at` surfacing deferred from 3B. Per D3 the LLM surface stays research-layer only; tools are read-only data access, no order tools exist.

## 2. Binding constraints (decisions pack + repo conventions)

- **D3:** agents never gate/place orders; `provider.py` remains the only LLM-touching module; tools are read-only (no write/order tool exists in the registry — absence beats instruction).
- **No-import rule (D1):** zero `import openalgo` / `from openalgo` in `src/`.
- **≤500 lines per file; zero new runtime dependencies** (stdlib + httpx + pydantic + existing only; NO `mcp` package — real MCP server deferred to Phase 4/D12).
- **Suite gate:** 612 passed / 0 failed / **0 skipped** → never shrinks, never skips.
- **Test runner (Windows):** `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` — never bare `pytest`.
- **Secrets:** `DEEPSEEK_API_KEY` env-only, read at call time.
- **Dirty file:** `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` — never stage/commit.
- **No test calls the real DeepSeek API.** Smoke script stays env-gated.

## 3. Design

### 3.1 Read-only tool registry (`research/tools.py`)

- `@dataclass(frozen=True) class ResearchTool:` `name`, `description`, `params_schema: dict` (JSON-schema-lite for function calling), `invoke(params: dict) -> str` (returns rendered text).
- `TOOLS: dict[str, ResearchTool]` — declarative (section-12 config-registry pattern, same shape as LENSES). Built-ins (v1):
  - `chain_snapshot(symbol)` — strike/spot/IV/volume digest for one NSE symbol.
  - `regime_snapshot()` — current regime, ADX, conviction D/P/G from the signal path.
  - `scanner_alerts()` — recent breakout/gap/alert list.
  - `options_posture()` — IV rank, PCR, OI buildup summary.
- **Data is injected, not imported:** `DataSource` protocol in `tools.py` (`chain_summary(symbol) -> str | None`, `regime_summary() -> str | None`, `scanner_summary() -> str | None`, `options_summary() -> str | None`). Tools call the source; `None` → `"[UNSOURCED] — no data"`. The terminal router wires a default source from `app.state` projections/scanner state where available (best-effort); tests inject synthetic sources. The `research/` package never imports `terminal/`.
- **Single-source rule:** a tool is defined once (name/description/schema/invoke) and serves both the briefer (function-calling) and the REST listing (`GET /api/research/tools` → definitions). Per-tool REST execution is deferred to the Phase-4 MCP surface.

### 3.2 Mid-run tool calling (provider v2 + orchestrator loop)

- `provider.py` changes (backward-compatible):
  - `ProviderResponse` dataclass: `content: str | None`, `tool_calls: list[ToolCall] | None`; `ToolCall`: `name: str`, `arguments: dict`.
  - `BriefProvider.generate` signature gains `tools: list[dict] | None = None` and `history: list[dict] | None = None`; returns `ProviderResponse` instead of `str`. `DeepSeekProvider`: sends `tools` and the assistant/tool message chain per the OpenAI-compatible function-calling contract; parses `choices[0].message.tool_calls` when present. `SimulatedProvider`: scriptable tool-call flows (`simulate_tool_calls: list[ToolCall] | None`, then content) + existing failure injection; **all existing 3B tests updated to the new return type** (this is a deliberate interface bump, spec'd, not a silent change).
- `orchestrator.py`: per lens, maintain `messages = [system, user(prompt)]`; loop:
  1. `resp = provider.generate(..., tools=tools, history=messages)`
  2. If `resp.tool_calls` and `tool_calls_used < MAX_TOOL_CALLS (3)`: append assistant message with tool_calls, execute each via the tool registry (unknown tool / exception → `"TOOL ERROR: ..."` result), append tool messages, continue.
  3. Else if content: `parse_brief_payload` (reject-retry-once as 3B) → persist → return.
  4. Budget exceeded without final content → lens error (`"tool call budget exceeded"`), never auto-advance.
  - `ResearchOrchestrator.run(lenses, sources, tools: Sequence[str] | None = None)` — `tools` selects the advertised toolset (default `[]` = 3B behavior); invalid tool name → `ValueError` (router 400s).
  - Token budget: `max_output_tokens` still caps each completion; `MAX_TOOL_CALLS` caps the loop.
- `POST /api/research/run` gains `tools: list[str] | None` (validated against `TOOLS`, 400 on unknown).

### 3.3 Scheduler (`research/scheduler.py`)

- `ResearchScheduler`: `__init__(orchestrator, interval_minutes: int = 60, lenses: list[str] | None = None, tools: list[str] | None = None)`; `start()` spawns an asyncio task; `stop()` cancels; each tick runs `orchestrator.run(lenses, tools=tools)` with a shared digest built from the wired sources; results land as `proposed` briefs; any failure is logged and the loop continues (never crashes the app); state: `next_run_at`, `last_run_at`, `last_result`.
- Config via env: `RESEARCH_SCHEDULE_ENABLED` (default off), `RESEARCH_SCHEDULE_INTERVAL_MINUTES`, `RESEARCH_SCHEDULE_LENSES` (comma list), `RESEARCH_SCHEDULE_TOOLS` (comma list). Wired in `app.py` lifespan only when enabled **and** `DEEPSEEK_API_KEY` present (else skipped with a log line — no key, no scheduler).
- `GET /api/research/scheduler` → `{enabled, interval_minutes, lenses, tools, next_run_at, last_run_at, last_result}` (last_result: `"ok" | "partial" | error string`).

### 3.4 Richer terminal panel + WS broadcast

- **Backend broadcast:** `research_router` gains `init_research(broadcast_fn: Callable[[dict], None])` (module-level, the `scanner_router.init_scanner_data` pattern); wired in `app.py` lifespan to `ws_manager.broadcast`. Events on topic `research`: `{"event": "new_brief", "data": <ResearchBriefResponse>}` (after every persisted insert — run endpoint and scheduler) and `{"event": "decision", "data": {"brief_id", "status"}}`. No new WS protocol — existing topic envelope.
- **Panel** (`terminal/web/src/components/ResearchPanel.svelte`, DESIGN.md tokens/design.css classes):
  - **Run bar:** lens checkboxes (3), tools multi-select (fetched from `GET /api/research/tools`), optional context textarea, Run button (disabled while a run is in flight; per-lens result chips: ok / error text).
  - **Brief list:** filter chips (All/Proposed/Approved/Rejected + lens filter), newest first; each row: lens badge, direction badge (+1/−1/0), confidence, thesis snippet, expiry/status; click to select.
  - **Detail view:** thesis, direction/confidence badges, rationale, evidence table (item/source/`[UNSOURCED]` flag), risks, validity + expiry, outcome, decided_at; decision card with Approve/Reject (disabled when decided or expired; 409 → refresh list).
- `lib/api.ts`: add `postBody<T>(path, body)` (existing `post` sends no body) + research response types. `lib/ws.ts`: handle `research` topic — `new_brief` prepends to the list (and selects it if nothing is selected), `decision` updates the row/status.
- `App.svelte`: mount `<ResearchPanel />` beside the existing panels per the current layout.

### 3.5 Scoring + decided_at (3B deferred minor)

- `ResearchBrief` gains `decided_at: str | None = None` (harness-owned, NOT in `MODEL_AUTHORED_FIELDS`); `store.decide` writes it into the payload (alongside the column); `ResearchBriefResponse` surfaces `decided_at`.
- `POST /api/research/briefs/{brief_id}/outcome` `{"outcome": "WIN" | "LOSS"}` → `store.set_outcome` (400 on bad value, 404 unknown, no restriction on decided-state — an outcome can be recorded for any brief that was decided; outcome on proposed briefs is rejected with 409 — you can't score what you haven't decided).
- `GET /api/research/scoring` → per lens: `{lens, total, decided, with_outcome, win_rate, avg_confidence}` computed from the store; empty DB → `[]` (200, never 500).

## 4. Data flow

```
POST /api/research/run {lenses, context, tools}
  → orchestrator.run → per lens:
      messages = [system, user(digest+brief-format prompt)]
      loop (≤3 tool calls):
        provider.generate(..., tools, history)
        tool_calls? → execute via TOOLS (injectable sources) → append tool messages
        else content → parse_brief_payload (reject-retry once) → store.insert
      → broadcast new_brief (WS topic research)
GET /api/research/tools         → TOOLS definitions (single source)
GET /api/research/briefs|/id    → store (as 3B) + decided_at
POST /{id}/approve|reject       → store.decide → broadcast decision
POST /{id}/outcome              → store.set_outcome
GET /api/research/scoring       → per-lens aggregates
ResearchScheduler (lifespan task) → orchestrator.run → proposed briefs → broadcast
```

## 5. Error handling

- Tool invocation failure inside a run: tool result `"TOOL ERROR: ..."` (model may recover); unknown tool name in `run` request → 400; budget exceeded → per-lens error entry (partial results preserved).
- Scheduler: tick failure logged, loop continues; scheduler endpoints never 500; no key → scheduler not started (log) and `GET /scheduler` returns `enabled: false`.
- Outcome endpoint: 400 invalid value, 404 unknown id, 409 outcome on undecided brief.
- Broadcast failure is caught and logged — never breaks the request.
- All other 3B error semantics unchanged (503 no-key, partial results, empty-on-missing-DB).

## 6. Testing

- Provider v2: tool-call parsing (DeepSeek format), `ProviderResponse` shape, SimulatedProvider tool scripts + failure injection; **all wave8 provider tests migrated to the new return type**.
- Orchestrator: no-tools path identical to 3B (existing tests migrated); tool path — model requests tool → executes → final JSON; tool error recovery; budget exceeded → lens error; invalid tool name ValueError; tools+retry interaction.
- Tools registry: declarative listing, invoke with synthetic DataSource, `[UNSOURCED]` fallback, schema shape.
- Scheduler: short-interval asyncio test (fake interval via constructor), tick persists briefs, failure doesn't kill the loop, start/stop idempotent.
- Endpoints: tools list; run with tools (SimulatedProvider); outcome 400/404/409; scoring aggregates + empty DB; scheduler status (enabled/disabled, no-key); decided_at present after approve; WS broadcast captured via injected broadcast_fn (record calls, no real WS).
- Svelte: `svelte-check` 0 errors; api.ts/ws.ts type-only additions.
- Full suite: 612 → ~650+ passing, **0 skipped**, 0 failed; grep gate zero; ≤500 lines/file.

## 7. Excluded / deferred

- Real MCP server + per-tool REST execution (Phase 4 knowledge layer, D12 single-source rule).
- Critic model pass (deferred until order intents exist to gate).
- Research panel polish beyond the spec'd regions; scheduled-run UI controls (env-config only).
- Live `/optionchain` fixture (separate OPEN QUESTION, needs live Dhan credentials).
- Phase 4 items (knowledge layer, analytics dashboards, multi-broker).

## 8. Delivery

- Branch `phase3c` from master (after hygiene wave merges); SDD with two parallel implementation waves (clean file ownership) → per-wave review (code-reviewer) → fix waves → final whole-branch review → ledger + handoff → merge decision + push presented.
- Docs to update at completion: roadmap §17 Phase 3 row (3C), CHANGELOG entry (v0.9.0), README feature list.
