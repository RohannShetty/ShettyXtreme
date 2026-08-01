# BRIEF: D12 Knowledge-Layer Document-Store Backend

**Status:** Research brief · **Date:** 2026-08-02 · **Owner:** ShettyXtreme platform team
**Purpose:** Resolve wayfinder ticket `01-knowledge-docstore-backend` — which backend the Phase-4 `knowledge/` document store uses.
**Scope:** corpus = hundreds to low thousands of auto-ingested research briefs (JSON with brief_id/lens/as_of/status/decided_at/outcome/evidence); needs full-text search + tag/regime filtering + provenance joins; Python 3.11; D12 wall: `knowledge/` imports core ONLY, no LLM.
**Ticket:** `.scratch/phase4-knowledge-dashboards/issues/01-knowledge-docstore-backend.md`

---

## Decision

**Use `sqlite3` + FTS5 (stdlib, zero new runtime dependencies).** Verified working on this machine (see §1). The existing `ResearchStore` (`src/shettyxtreme/research/store.py`) already sets the sqlite append-only pattern the knowledge layer will extend — FTS5 layers full-text search on top of that proven shape instead of introducing a second store paradigm.

Fallback is **not needed**: FTS5 is compiled into the local Python's sqlite3.

## 1. FTS5 availability — empirical (this machine)

Checked `.venv\Scripts\python.exe` (Python 3.11.15, bundled sqlite **3.50.4**):

| Check | Result |
|---|---|
| `sqlite3.sqlite_version` | 3.50.4 |
| FTS5 in `pragma_compile_options` | ✓ present |
| Phrase match (`MATCH 'hello'`) | ✓ |
| Prefix query (`MATCH 'hel*'`) | ✓ |
| `tokenize='porter'` (stemming) | ✓ |
| `tokenize='trigram'` (substring/fuzzy) | ✓ |
| `content=''` (external-content table) | ✓ |
| `:memory:` FTS5 (testability) | ✓ |

FTS5 has shipped compiled-in by default in CPython's sqlite3 on all platforms for years; on Windows builds it is only absent when a distro compiles sqlite with `-DSQLITE_OMIT_FTS5` (rare). This venv confirms it.

## 2. Decision criteria

| Criterion | Why it matters for THIS use case |
|---|---|
| Search capability | phrase match, prefix, stemming for brief text (thesis/rationale/evidence) |
| Tag/regime filtering | lens, status, regime, symbols as structured filters joined with search |
| Provenance integrity | append-only decision records, referential links to `brief_id` (existing contract) |
| Dependencies | strong zero-new-runtime-deps preference (sqlite3, httpx, pydantic exist) |
| Windows | must work on the operator's Windows box (this one) |
| Testability | in-memory DB tests, no external services |
| Concurrency | single-operator, single-writer ingest; reads during ingest |

## 3. Comparison

| Option | Search | Tag filter | Provenance | Deps | Windows | Testability | Verdict |
|---|---|---|---|---|---|---|---|
| **sqlite3 + FTS5** | ✓ phrase, prefix, `bm25()` ranking, `snippet()`; porter/trigram tokenizers | ✓ columns + JOIN on MATCH (rowid) | ✓ append-only + FK to brief_id; WAL single-writer | **zero new** (stdlib) | ✓ verified | ✓ `:memory:` FTS5 works | **RECOMMENDED** |
| FTS5 + trigram/porter extras | ✓ adds substring + stemming | ✓ same | ✓ same | zero | ✓ verified | ✓ | Same as above — tokenizer choice, not a new backend |
| duckdb (already a dep: `duckdb>=1.5.4`, installed 1.5.4) | ⚠ FTS needs `INSTALL fts; LOAD fts` — runtime extension download, experimental status | ✓ struct/list filters | ✓ but no established append-only pattern in repo | already declared, but extension fetch = runtime/network dep | ✓ | ✓ | Capable but adds network-coupled experimental surface for search; keep it for analytics (TimeSeriesStore), not the doc store |
| tantivy (Rust) | ✓ superior relevance | ✗ none built-in — hand-roll | ✗ none built-in | heavy new dep (~MB wheel, Rust) | ✓ win_amd64 wheels, but heavy | ⚠ external index files | Overkill at hundreds–thousands docs; breaks zero-deps |
| whoosh | ✓ phrase/prefix (pure-python) | ✗ no metadata story | ✗ weaker atomicity | pure-python, but **last release 2016 (2.7.4), effectively unmaintained** | ✓ | ✓ | Dead-end maintenance risk; stale on 3.11 era |
| plain jsonl + in-memory index | ✗ hand-rolled substring/naive scoring; re-index on boot | ✗ manual | ✗ manual locking, no referential integrity | zero | ✓ | ✓ | Fine for toy scale only; the ticket explicitly wants real FTS quality |

## 4. Proposed shape (grounded in existing patterns)

Extend the `ResearchStore` pattern (`research/store.py` — append-only briefs table, payload as JSON TEXT, `json_extract(payload,'$.lens')` filtering) rather than replace it:

- `documents` table: `doc_id` PK, `brief_id` TEXT UNIQUE NOT NULL (provenance link), `payload` TEXT (JSON), `status`, `decided_at`, `outcome`, `as_of`, `ingested_at` — append-only semantics identical to ResearchStore.
- `documents_fts` FTS5 virtual table over searchable fields (thesis, rationale, evidence, regime, symbols) using `content='documents'` + `UPDATE`/`DELETE` triggers (or contentless if corpus grows), `tokenize='porter unicode61'`, `bm25()` ranking, `snippet()` for the activation UI.
- Tag/regime filtering: structured columns on `documents` (lens, regime, status, symbols as JSON or junction) joined with the FTS match on `rowid`; or FTS column filters (`MATCH 'thesis:vol AND regime:bull'`).
- `PRAGMA journal_mode=WAL` for concurrent read-while-ingest; single writer — matches the single-operator model.

## 5. Risks & mitigations

- **FTS index drift** (content updated without index sync) → `content=` external-content tables + triggers, or rebuild-on-ingest (cheap at this corpus size).
- **Tokenizer edge cases for financial text** (case, ticker-like tokens, Indian company names) → test the porter/unicode61 defaults on real brief payloads in wave tests; trigram tokenizer available if substring matching is required.
- **Bundled sqlite version drift across machines** → FTS5 is a stable, shipped feature; gate on `pragma_compile_options` check at import time (one line), error loudly if ever absent — fallback would be jsonl + naive index, but not needed here.
- **duckdb temptation** (already a dep) → its FTS extension is download-gated and experimental; keeping search on stdlib sqlite avoids runtime network coupling. duckdb stays for analytics.

## 6. Links

- Ticket: `.scratch/phase4-knowledge-dashboards/issues/01-knowledge-docstore-backend.md`
- Existing pattern: `src/shettyxtreme/research/store.py` (ResearchStore, append-only sqlite)
- D12 wall: `docs/architecture/v2/sections/05-system-boundaries.md`, `18-repo-codebase-strategy.md` (`knowledge/` → core ONLY)
