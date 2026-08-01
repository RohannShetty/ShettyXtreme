# Phase 4A — Knowledge Layer (D12): Design Spec

**Date:** 2026-08-01 · **Status:** APPROVED (wayfinder tickets 01–04) · **Branch:** phase4 from master · **Map:** `.scratch/phase4-knowledge-dashboards/map.md`

## 1. Purpose

Ship the D12 knowledge layer v1: an FTS5-backed document store for decided research briefs, a heuristic tagger (symbols + regimes + risk themes), and a human-gated activation flow where an activated document becomes a research tool source (`knowledge_search`). Physically separated: `knowledge/` imports core ONLY; no LLM inside; the LLM surface stays `research/provider.py` (D3).

## 2. Binding constraints

- **D12:** `knowledge/` imports core ONLY — never `research/`, `intelligence/`, `execution/`, `terminal/`. Lexicons therefore live in `core/knowledge/` (pure data, no external imports).
- **D3:** no LLM output in the knowledge path; the tagger is heuristic; `knowledge_search` is a read-only research tool (absence of write tools).
- **Zero new runtime deps** — sqlite3 FTS5 (verified compiled in: sqlite 3.50.4). Findings: `docs/references/BRIEF-knowledge-docstore.md`.
- ≤500 lines/file; suite never shrinks, **0 skipped**; grep gate zero; test runner `.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` with `PYTHONPATH=""`.
- New tests live in `tests/wave9/`.
- Never stage `AGENTS.md`, `.opencode/opencode.json`, `docs/superpowers/plans/2026-07-31-graphify-upgrade.md`.

## 3. Design

### 3.1 Core lexicons (`core/knowledge/lexicons.py`)

- `NSE_SYMBOLS: set[str]` — curated NSE instrument symbols (from `configs/default_watchlist.yaml` seed + common F&O names: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50, plus equity symbols listed there).
- `REGIME_TERMS: dict[str, str]` — canonical regime keyword → normalized regime tag (`{"trending": "TRENDING_UP", "trending up": "TRENDING_UP", "range": "RANGE_BOUND", "ranging": "RANGE_BOUND", "falling": "TRENDING_DOWN", "downtrend": "TRENDING_DOWN", "bearish": "TRENDING_DOWN", "bullish": "TRENDING_UP", ...}`).
- `RISK_THEMES: dict[str, str]` — risk lexicon keyword → normalized risk tag (`{"crowding": "CROWDING", "elevated iv": "ELEVATED_IV", "iv rank": "ELEVATED_IV", "tail risk": "TAIL_RISK", "overbought": "OVERBOUGHT", "gap": "GAP_RISK", "event": "EVENT_RISK", ...}`).
- Pure data + one helper `normalize_symbol(token) -> str | None` (uppercase, strip exchange suffix like `NSE:`, `NSE_FNO:`).

### 3.2 Knowledge store (`knowledge/store.py`)

- `KnowledgeStore(db_path: str)` — sqlite + FTS5, extends the ResearchStore append-only pattern:
  - `docs` table: `doc_id TEXT PK, kind TEXT, source_ref TEXT, payload TEXT NOT NULL, status TEXT DEFAULT 'proposed' ('proposed'|'activated'), created_at TEXT, activated_at TEXT`.
  - `tags` table: `(doc_id TEXT, tag TEXT, kind TEXT)` — kind in `symbol|regime|risk`; PK `(doc_id, tag, kind)`.
  - FTS5 virtual table `docs_fts` (content=`docs`, content_rowid, `title, body`) + triggers to keep it in sync (insert/update/delete) — external-content FTS per the brief.
  - `source_ref` UNIQUE → idempotent ingest by brief_id.
- Methods:
  - `ingest(doc: KnowledgeDoc) -> KnowledgeDoc` — insert doc + tags + FTS (raises `DuplicateSourceError` on existing source_ref unless `replace=True`).
  - `search(query: str, *, status: str | None = None, tags: list[str] | None = None, limit: int = 20) -> list[SearchHit]` — FTS5 `bm25` ranking + `snippet()`; status/tag filtering via SQL joins on docs/tags.
  - `list_docs(status: str | None = None, limit: int = 100) -> list[KnowledgeDoc]`.
  - `get(doc_id) -> KnowledgeDoc | None`.
  - `activate(doc_id: str) -> KnowledgeDoc` — proposed → activated (idempotent; `AlreadyActivatedError` on repeat? NO — idempotent: activating an activated doc returns it unchanged; activating unknown → KeyError).
  - `counts() -> dict` — `{docs, proposed, activated, tags}` for status endpoint.
  - `close()`.
- `KnowledgeDoc` pydantic model (in `knowledge/schemas.py`): `doc_id, kind, source_ref, payload: dict, status, created_at, activated_at, tags: list[dict] = []` — mirror of the row + tags for responses.
- `SearchHit` pydantic: `doc_id, kind, source_ref, status, title, snippet, tags, bm25_score`.
- All reads degrade: empty store → `[]`/`None`, never raise.

### 3.3 Ingest contract (`knowledge/ingest.py`)

- `def ingest_decided_briefs(store: KnowledgeStore, briefs: Sequence[ResearchBriefLike]) -> IngestResult` — pure function; `knowledge/` imports the protocol, NOT `research/`:
  - `ResearchBriefLike` Protocol: `brief_id: str`, `lens: str`, `as_of: str`, `status: str`, `decided_at: str | None`, `outcome: str | None`, `thesis: str`, `rationale: str`, `evidence: list[dict]`.
  - Ingest only briefs with `status in ("approved", "rejected")` AND `decided_at` — skipped others (counted).
  - Doc kind = `research_brief`; source_ref = `brief_id`; title = thesis (truncated 200); body = thesis + rationale + evidence items/sources; tags = tagger output (3.4); idempotent (existing source_ref skipped, counted).
  - `IngestResult` dataclass: `ingested, skipped_undecided, skipped_duplicate`.
- Wiring (terminal layer, NOT knowledge/): a `sync` endpoint reads `ResearchStore(RESEARCH_DB_PATH)` and passes decided briefs in — the only place research and knowledge meet.

### 3.4 Tagger (`knowledge/tagger.py`)

- `def tag_document(text: str) -> list[dict]` → `[{"tag": <normalized>, "kind": "symbol"|"regime"|"risk"}]`:
  - symbols: tokenize on non-alphanumerics, uppercase, `normalize_symbol` against `NSE_SYMBOLS`; disambiguation: only tokens length ≥ 2; skip common words ("IT" etc. — curated stopwords in core lexicons).
  - regimes: lowercase keyword lookup against `REGIME_TERMS` (multi-word phrases checked first).
  - risks: lowercase keyword lookup against `RISK_THEMES`.
  - Dedup per (tag, kind); cap 50 tags.
- Unit-tested lexicon behavior (no ML).

### 3.5 Research tool wiring (`research/tools.py` + terminal)

- `DataSource` protocol gains `knowledge_summary(query: str) -> str | None`.
- New tool `knowledge_search(query)` — `params_schema: {"query": {"type": "string"}}` required; invoke calls `_source.knowledge_summary(query)`; missing source / None → `[UNSOURCED] — no data`.
- `ProjectionDataSource` (terminal) implements `knowledge_summary`: read `app.state.knowledge_store` (activated docs only, top 5, `doc_id: title [tags]`), else None. knowledge/ never imported by research/; terminal does the join.
- `GET /api/research/tools` automatically lists the new tool (single-source registry).

### 3.6 API (`terminal/api/knowledge_router.py` + `knowledge_models.py`)

Models in NEW `terminal/api/knowledge_models.py` (keeps `models.py` untouched → disjoint waves):
- `KnowledgeDocResponse` (doc fields + tags), `KnowledgeListResponse {docs}`, `SearchHitResponse`, `KnowledgeSearchResponse {hits}`, `KnowledgeSyncResponse {ingested, skipped_undecided, skipped_duplicate}`, `KnowledgeStatusResponse {docs, proposed, activated, tags}`.

Endpoints (`/api/knowledge`, tag `knowledge`, module-global store via `init_knowledge(store)` — scanner_router pattern):
- `GET /api/knowledge/search?q&status&tags&limit` → hits (empty q → 422? No: empty q → 200 with `[]`).
- `GET /api/knowledge/docs?status&limit` → list.
- `GET /api/knowledge/status` → counts.
- `POST /api/knowledge/sync` → pulls decided briefs from the research store into knowledge (400 if research DB missing? No — 200 with skipped counts; DB failure → 200 with zeros + `error` field? Keep spec: research store open failure → 200 `{ingested: 0, ..., error: "research store unavailable"}`).
- `POST /api/knowledge/docs/{doc_id}/activate` → activate (404 unknown; 200 idempotent; 409 if... no — idempotent per 3.2 → always 200 when found).
- WS broadcast on activate: event `{"event": "activated", "data": <KnowledgeDocResponse>}` on topic `knowledge` via the same `init_research`-style `init_knowledge(broadcast_fn)`.
- Store instance created in `app.py` lifespan (`KnowledgeStore("data/knowledge.db")`) → `init_knowledge(store, broadcast_fn)`; teardown `store.close()`.

### 3.7 Panel (`terminal/web/src/components/KnowledgePanel.svelte`)

- Search box + results (title, tags badges, snippet, source_ref, status, activated_at) + click-to-select detail (full thesis/rationale, provenance, tags, evidence refs) + **Activate** button (disabled when activated) + **Sync** button (top-right, POST /api/knowledge/sync, shows result counts).
- WS topic `knowledge` (`activated` event updates the row).
- DESIGN.md tokens; `.mono` numerals; mounted in the right column under ResearchPanel (App.svelte).
- api.ts: knowledge types + `get`/`post`/`postBody` reuse.

## 4. Data flow

```
lifespan: KnowledgeStore("data/knowledge.db") → init_knowledge(store, broadcast)
POST /api/knowledge/sync → ResearchStore.read decided briefs → ingest_decided_briefs(store, briefs)
POST /api/knowledge/docs/{id}/activate → store.activate → broadcast activated
GET /api/knowledge/search?q&status&tags → FTS5 bm25 + snippet + tag joins
research run with tools=[...knowledge_search] → provider tool_calls → run_tool("knowledge_search") → DataSource.knowledge_summary (terminal) → activated docs
```

## 5. Error handling

- Ingest: duplicate source_ref skipped (counted), never fails the sync; corrupt payload row → skipped (counted in a `skipped_errors` counter? keep simple: skipped_duplicate covers it; corrupt JSON → skipped_duplicate).
- Search with unknown tag value → 200 `[]` (never 500).
- Store file missing → store auto-creates schema (ResearchStore pattern).
- Broadcast failure caught + logged (existing pattern).
- Activate unknown → 404; activate idempotent → 200.

## 6. Testing

- Lexicons: symbol normalization, regime/risk phrase matching, stopword disambiguation.
- Store: schema creation, ingest + duplicate idempotency, search ranking + snippet, tag filtering, status filtering, activate idempotency + unknown KeyError, counts, empty-store degradation.
- FTS triggers: doc insert/update/delete keeps FTS in sync (update payload → search reflects it).
- Ingest: only decided+decided_at briefs; duplicate counting; protocol decoupling (test with a fake brief class — no research/ import).
- API: search/docs/status/sync/activate happy + error paths; sync counts; broadcast captured via injected fn; 404s; empty DB.
- Tool: `knowledge_search` invoke with fake DataSource; `[UNSOURCED]` fallback; tool listed in `/api/research/tools`.
- Frontend: `svelte-check` 0 errors.
- Full suite: 655 → ~700+, **0 skipped**.

## 7. Excluded / deferred

- Operator-notes ingest folder (v2; ticket 02 recorded).
- Tag refinement/ML extractor; knowledge graph links (D12 "knowledge linker" — later).
- Knowledge → digest auto-merge into every research run (only the `knowledge_search` tool path; ticket 04 recorded).
- Deeper activation semantics (promote tag to live surface) — v2.

## 8. Delivery

Branch `phase4` from master; SDD waves (knowledge layer package / frontend in parallel; router + app wiring in a coordinator integration pass; per-wave review; final whole-branch review); gates as §2; docs (CHANGELOG v0.10.0, roadmap §17 Phase 4 row, README); merge + push decision presented.
