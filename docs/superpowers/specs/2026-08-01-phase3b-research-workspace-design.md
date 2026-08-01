# Phase 3B — Research Workspace (AI Research Layer): Design Spec

**Date:** 2026-08-01 · **Status:** APPROVED (user) · **Repo:** D:\ShettyXtreme · **Branch:** to be created from master

## 1. Purpose

Deliver the research workspace's core: an LLM briefer harness (DeepSeek) that drafts schema-validated `ResearchBrief`s for the operator across three configurable lenses — OI/IV flow, directional momentum, tail-risk — with human approve/reject and an outcome-tracking stub. This is sub-project 3B of Phase 3; per D3 the LLM surface is research-layer only and never gates or places orders. 3C (read-only data tools/MCP, critic pass, terminal panel, scheduled runs) is a separate spec.

## 2. Binding constraints (from decisions pack + repo conventions)

- **D3:** agents never gate/place orders — no LLM output touches signal/gate/execution; absence beats instruction (no LLM surface outside `research/provider.py`).
- **No-import rule (D1):** zero `import openalgo` / `from openalgo` in `src/`.
- **≤500 lines per file; zero new runtime dependencies** (stdlib + existing packages only — httpx, pydantic already in pyproject; test helpers may use pytest).
- **Suite gate:** 563 passed / 0 failed → never shrinks.
- **Test runner (Windows):** `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` (never bare `pytest`).
- **Secrets:** `DEEPSEEK_API_KEY` from env vars only, read at call time; never committed, never in config files, never logged.
- **Dirty file:** `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` is pre-existing unstaged — never stage or commit it.
- **Section-12 doctrine:** output-schema validation with reject-retry-once-then-fail; failing worker surfaces partial results + error, never auto-advances; token budgets per briefer; untrusted-content doctrine (v1 digest has no untrusted input channel).
- **No test calls the real DeepSeek API.** A manual, env-gated smoke script covers real-provider runs.

## 3. Design

### 3.1 Architecture — thin deterministic harness

New package `src/shettyxtreme/research/` (currently empty), ~6 focused files:

| File | Responsibility |
|---|---|
| `provider.py` | `BriefProvider` protocol; `DeepSeekProvider` (httpx → `https://api.deepseek.com` OpenAI-compatible endpoint, non-thinking, `response_format: json_object`, configurable model/base_url/timeout; default model `deepseek-v4-flash`); `SimulatedProvider` (deterministic test double with failure injection: network error, invalid JSON, schema-violating JSON, scripted briefs) |
| `lenses.py` | Declarative lens registry: `oi_iv_flow`, `directional_momentum`, `tail_risk` — each a name, description, system prompt, brief prompt template (section 12 config-registry discovery) |
| `digest.py` | `ContextDigest` builder: composes an as-of snapshot from injectable data sources — regime state, last N signals with D/P/G, scanner alerts, options intel (IV rank/OI posture), calibration reliability. Every section tagged `[SOURCE: name]`; missing sources render `[UNSOURCED] — no data`; never fabricates |
| `briefs.py` | `ResearchBrief` pydantic contract (§3.3); validation helper used by the orchestrator |
| `orchestrator.py` | `ResearchOrchestrator.run(lenses, sources)` — per lens: digest → prompt → provider → JSON parse → pydantic validate (reject-retry once) → persist; `asyncio.gather` across lenses; per-lens failure → partial results + error entry, never 500/auto-advance; per-briefer `max_output_tokens` cap (default 2000) and per-call timeout (default 90 s) |
| `store.py` | sqlite `research.db` — `briefs` table (payload JSON + status/decision columns); decisions append-only; `decided_at` immutable; expiry computed at read time |

Plus `terminal/api/research_router.py` and response models in `terminal/api/models.py` (the 3A learning_router pattern).

### 3.2 Endpoints & data flow

| Endpoint | Behavior |
|---|---|
| `POST /api/research/run` `{lenses: [...]}` | Synchronous: `asyncio.gather` across requested lenses (omitted `lenses` = all); returns all briefs or partial results + per-lens error entries |
| `GET /api/research/lenses` | Available lenses with descriptions |
| `GET /api/research/briefs?status=&lens=` | List, filterable, newest first |
| `GET /api/research/briefs/{id}` | Single brief with full evidence |
| `POST /api/research/briefs/{id}/approve` · `/reject` | Immutable decision; second decision on same brief → 409 |

```
POST /run
  → orchestrator → per lens (asyncio.gather):
      digest.build(sources) ──→ prompt ──→ DeepSeekProvider (JSON mode)
        → pydantic validate ── retry once on failure ── fail
      → store.insert(brief) ──→ response
GET /briefs → store.list → status filter + expiry overlay
POST /{id}/approve|reject → store.decide (append-only) → 409 if already decided
```

**Lifecycle:** `proposed` → `approved` | `rejected`. `expired` is computed at read time (validity window, default 240 min); the stored status never mutates after a decision.

**Error handling:**
- Provider/network failure or validation failure after 1 retry → that lens returns `{lens, error, partial: null}`; other lenses still complete; never 500 on a failed briefer.
- `DEEPSEEK_API_KEY` unset → `POST /run` returns 503 with explicit message.
- Missing/corrupt DB → list/get return 200 with empty/neutral payload; run still persists nothing but returns per-lens errors.
- Invalid lens name in `POST /run` → 400 listing valid lenses.

### 3.3 ResearchBrief schema

```python
class ResearchBrief(BaseModel):
    brief_id: str            # uuid — harness-owned
    lens: str                # oi_iv_flow | directional_momentum | tail_risk — harness-owned
    as_of: str               # ISO timestamp (digest time; point-in-time discipline)
    instruments: list[str]   # NSE symbols examined (max 10)
    direction: int           # +1 | -1 | 0 — harness-validated from model output
    confidence: float        # 0.0–1.0
    thesis: str              # 1–2 sentence thesis (max 500 chars)
    rationale: str           # 300–1200 chars
    evidence: list[dict]     # [{item, source, unsourced: bool}] — max 10
    risks: list[str]         # max 5
    validity_window_minutes: int  # default 240
    status: Literal["proposed", "approved", "rejected"]  # never LLM-authored
    outcome: str | None      # None | "WIN" | "LOSS" — tracking stub
```

**Hard rules:** `brief_id`, `lens`, `as_of`, `status` are harness-owned (status always `proposed` at insert). Validation is strict: `additionalProperties: false`, enum/length caps enforced — injected instructions cannot survive the channel.

### 3.4 Guardrails

- `DEEPSEEK_API_KEY` env-only, read at call time; never written by the app.
- D3 wall structural: `provider.py` is the only LLM-touching module; nothing in `intelligence/`, `risk/`, `execution/` imports `research/`.
- Token budget per briefer (default 2000 output) + per-call timeout; failing worker surfaces partial + error, never auto-advances.
- Repo gates: no `import openalgo` in src/, ≤500 lines/file, dirty graphify-upgrade plan never staged.

## 4. Testing

- `SimulatedProvider` — scripted happy briefs, invalid JSON, schema-violating JSON, network error.
- Digest: synthetic regime/signals/scanners/options-intel sources; `[UNSOURCED]` marking when a source is absent.
- Lens registry: names/descriptions/prompt build.
- Store: insert/list/get/decide; decision immutability (second decide rejected); expiry overlay at read; missing DB → empty.
- Orchestrator: 3-lens happy path; one-lens-fails → partial + error; reject-retry-once then fail; token cap enforcement.
- Endpoints (TestClient + tmp DB): run/list/get/approve/reject/lenses; 409 double-decision; 503 no key; 400 unknown lens; 200 empty on missing DB.
- Full suite: 563 → ~580+ passing, 0 failures; grep gate zero; ≤500 lines.

## 5. Excluded / deferred (3C+)

- Read-only data tools / MCP exposure (single-source REST/WS/MCP rule).
- Critic / re-verification model pass.
- Terminal panel + WS broadcast (D/P/G-style visibility of briefs).
- Scheduled/periodic research runs.
- SignalThesis / intent drafting → approval-card execution flow (stays behind the D3 wall; execution service untouched).
- Briefer outcome scoring against realized outcomes — the `outcome` stub exists so 3C can close the loop.
- Live `/optionchain` fixture (separate OPEN QUESTION, needs live Dhan credentials).

## 6. Delivery

- New branch `phase3b-research-workspace` from master; SDD task-by-task (brief → implementer → task review → fix waves); final whole-branch review; ledger + handoff; merge decision presented to the user.
- Docs to update at completion: roadmap §17 Phase 3 row (3B), CHANGELOG entry, README feature list.
