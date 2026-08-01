# Phase 4 — Knowledge Layer + Analytics Dashboards: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 4 v1: D12 knowledge layer (FTS5 store + heuristic tagger + human-gated activation wired to a `knowledge_search` research tool) and analytics dashboards (calibration SVG chart + scorecard cards + regime bars) with a recording track (SessionLog + `regime_at_decision`).

**Architecture:** Two parallel tracks. Track 4A: `knowledge/` package (imports core ONLY — D12) + `core/knowledge/lexicons.py` + `terminal/api/knowledge_router.py` + `KnowledgePanel.svelte`. Track 4B: `learning/sessions.py` + `regime_at_decision` on decide + `terminal/api/analytics_router.py` + `AnalyticsPanel.svelte`. Shared: `app.py` lifespan wiring, `models` additions live in NEW files (`knowledge_models.py`, `analytics_models.py`) so waves stay disjoint.

**Tech Stack:** Python 3.11, sqlite3 + FTS5 (stdlib — verified 3.50.4), pydantic v2, FastAPI, Svelte 5 (plain SVG/CSS charts, zero new deps anywhere).

## Global Constraints

- **D12:** `knowledge/` imports core ONLY — never research/intelligence/execution/terminal. Lexicons in `core/knowledge/` (pure data).
- **D3:** no LLM in knowledge/ or analytics; tagger is heuristic; `knowledge_search` is read-only.
- **Zero new runtime deps** (stdlib + httpx + pydantic + existing only).
- **Gates:** full suite never shrinks, **0 skipped** (655 baseline → ~715+); grep gate zero; ≤500 lines/file; `svelte-check` 0 errors.
- **Test runner:** `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest <file(s)> -q --basetemp=... -p no:cacheprovider` — distinct basetemp per subagent; never bare `pytest`.
- **New tests in `tests/wave9/`** (plus additive edits to `tests/wave8/test_research_briefs_store.py` and `tests/wave8/test_research_tools.py` — coordinator-owned).
- **Commit protocol:** subagents NEVER commit; coordinator stages/commits per task on branch `phase4`.
- **Never stage:** `AGENTS.md`, `.opencode/opencode.json`, `docs/superpowers/plans/2026-07-31-graphify-upgrade.md`.

## File Structure

| File | Responsibility | Task | Wave |
|---|---|---|---|
| `core/knowledge/__init__.py`, `core/knowledge/lexicons.py` | NSE_SYMBOLS, REGIME_TERMS, RISK_THEMES, normalize_symbol, stopwords | 1 | W1-SA-K1 |
| `knowledge/__init__.py` | namespace pkg | 1 | W1-SA-K1 |
| `knowledge/schemas.py` | KnowledgeDoc, SearchHit, IngestResult? (IngestResult in ingest.py) | 2 | W1-SA-K1 |
| `knowledge/store.py` | KnowledgeStore (FTS5, tags, ingest/search/list/activate/counts) | 3 | W1-SA-K1 |
| `knowledge/tagger.py` | tag_document | 4 | W1-SA-K1 |
| `knowledge/ingest.py` | ingest_decided_briefs (ResearchBriefLike protocol) | 5 | W1-SA-K1 |
| `learning/sessions.py` | SessionLog | 6 | W1-SA-A1 |
| `research/briefs.py` + `research/store.py` | regime_at_decision field + decide(regime=) | 7 | W1-SA-A1 |
| `terminal/web/src/lib/api.ts` | knowledge + analytics types | 8 | W1-SA-F1 |
| `terminal/web/src/components/KnowledgePanel.svelte` | search/list/detail/activate/sync + WS | 9 | W1-SA-F1 |
| `terminal/web/src/components/AnalyticsPanel.svelte` | scorecard cards + SVG calibration + regime bars | 10 | W1-SA-F1 |
| `terminal/web/src/App.svelte` | mount both panels | 11 | W1-SA-F1 |
| `terminal/api/knowledge_models.py` + `knowledge_router.py` | /api/knowledge/* | 12 | W2 (coordinator) |
| `terminal/api/analytics_models.py` + `analytics_router.py` | /api/analytics/* | 13 | W2 |
| `research/tools.py` (+ DataSource), `research_source.py` | knowledge_search tool + knowledge_summary | 14 | W2 |
| `research_router.py` (decide regime), `app.py` (wiring) | recording + store/session wiring | 15 | W2 |
| `tests/wave9/*` API/integration tests | router tests | 16 | W2 |
| Docs: CHANGELOG v0.10.0, roadmap §17, README, handoff | finish | 17 | W3 |

## Execution Protocol

- **Wave 1 (parallel, disjoint):** SA-K1 = Tasks 1–5 (knowledge package); SA-A1 = Tasks 6–7 (recording); SA-F1 = Tasks 8–11 (frontend).
- **Wave 2 (coordinator, sequential, TDD):** Tasks 12–16 — routers, tool wiring, app lifespan, tests. Note: `test_research_tools.py::test_tools_registry_shape` asserts the exact 4-tool list — Task 14 updates it to 5.
- **Wave 3:** code-review (code-reviewer) → fix waves → final whole-branch review → gates → docs → merge + push (v0.10.0).

---

## Track 4A — Knowledge layer

### Task 1: Core lexicons (`core/knowledge/lexicons.py`)

**Files:** Create `core/knowledge/__init__.py` (empty), `core/knowledge/lexicons.py`; Test `tests/wave9/test_knowledge_lexicons.py`.

**Interfaces:** Produces `NSE_SYMBOLS: set[str]`, `REGIME_TERMS: dict[str, str]`, `RISK_THEMES: dict[str, str]`, `SYMBOL_STOPWORDS: set[str]`, `normalize_symbol(token: str) -> str | None`.

- [ ] **Step 1: Write failing tests**

```python
"""Lexicon tests (spec 4A §3.1, §6)."""
from __future__ import annotations

import pytest

from shettyxtreme.core.knowledge.lexicons import (
    NSE_SYMBOLS,
    REGIME_TERMS,
    RISK_THEMES,
    SYMBOL_STOPWORDS,
    normalize_symbol,
)


def test_normalize_symbol() -> None:
    assert normalize_symbol("nifty") == "NIFTY"
    assert normalize_symbol("NSE:NIFTY") == "NIFTY"
    assert normalize_symbol("NSE_FNO:BANKNIFTY") == "BANKNIFTY"
    assert normalize_symbol("it") is None  # stopword
    assert normalize_symbol("the") is None
    assert normalize_symbol("  ") is None


def test_lexicons_are_curated() -> None:
    assert "NIFTY" in NSE_SYMBOLS and "BANKNIFTY" in NSE_SYMBOLS
    assert REGIME_TERMS["trending"] == "TRENDING_UP"
    assert REGIME_TERMS["ranging"] == "RANGE_BOUND"
    assert RISK_THEMES["elevated iv"] == "ELEVATED_IV"
    assert RISK_THEMES["crowding"] == "CROWDING"
    assert "IT" in SYMBOL_STOPWORDS


def test_lexicon_values_normalized() -> None:
    # every regime value matches the canonical enum (lowercase values)
    from shettyxtreme.intelligence.regime.regime_classifier import Regime

    for v in set(REGIME_TERMS.values()):
        assert v in {r.value for r in Regime}
```

- [ ] **Step 2: Run to verify FAIL** (`tests/wave9/test_knowledge_lexicons.py` — module not found)
- [ ] **Step 3: Implement** `core/knowledge/lexicons.py`:
  - `NSE_SYMBOLS` — seed from `configs/default_watchlist.yaml` indices (read at import? NO — pure data: hardcode the curated set from that file: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50 + any equities listed there — hardcoded, no config import in core).
  - `REGIME_TERMS`: `trending→trending_up, trending up→trending_up, uptrend→trending_up, bullish→trending_up, bull→trending_up, falling→trending_down, downtrend→trending_down, bearish→trending_down, bear→trending_down, ranging→range_bound, range bound→range_bound, sideways→range_bound, flat→range_bound` (values = lowercase `intelligence.regime.regime_classifier.Regime` enum values).
  - `RISK_THEMES`: `crowding→CROWDING, crowded→CROWDING, elevated iv→ELEVATED_IV, high iv→ELEVATED_IV, iv rank→ELEVATED_IV, tail risk→TAIL_RISK, tail-risk→TAIL_RISK, overbought→OVERBOUGHT, oversold→OVERSOLD, gap risk→GAP_RISK, gap up→GAP_RISK, gap down→GAP_RISK, event risk→EVENT_RISK, binary event→EVENT_RISK, resistance→RESISTANCE, support→SUPPORT, expiry→EXPIRY`.
  - `SYMBOL_STOPWORDS`: `{"IT", "ON", "IN", "AT", "TO", "OF", "THE", "A", "AN", "AND", "OR", "FOR", "WITH", "AS", "BY", "IS", "BE", "ARE", "WAS", "WERE"}`.
  - `normalize_symbol(token)`: strip `NSE:`, `NSE_FNO:`, `BSE:` prefixes (case-insensitive) → uppercase → return if in NSE_SYMBOLS and not in SYMBOL_STOPWORDS else None.
- [ ] **Step 4: Verify PASS** (both tests; `Regime` enum import is read-only, fine — knowledge lexicons may not import intelligence, but the TEST may)
- [ ] **Step 5: Report** (coordinator commits): `git commit -m "feat(4a): core knowledge lexicons (symbols, regimes, risk themes)"`

### Task 2: Knowledge schemas (`knowledge/schemas.py`)

**Files:** Create `knowledge/__init__.py` (empty), `knowledge/schemas.py`; Test `tests/wave9/test_knowledge_schemas.py`.

**Interfaces:** Produces `KnowledgeDoc` (pydantic): `doc_id, kind, source_ref, payload: dict, status: str = "proposed", created_at: str | None = None, activated_at: str | None = None, tags: list[dict] = []`; `SearchHit`: `doc_id, kind, source_ref, status, title, snippet, tags: list[dict], bm25_score: float`.

- [ ] **Step 1: Failing tests** — round-trip defaults: `KnowledgeDoc(doc_id="d1", kind="research_brief", source_ref="b1", payload={})` → status "proposed"; `SearchHit` construction; unknown field rejected (pydantic strictness like ResearchBrief — `model_config = ConfigDict(extra="forbid")`).
- [ ] **Step 2: FAIL** → **Step 3: Implement** (pydantic BaseModel, `extra="forbid"`, field defaults per spec) → **Step 4: PASS** → **Step 5: Report** (commit: `feat(4a): knowledge schemas`)

### Task 3: Knowledge store (`knowledge/store.py`) — FTS5

**Files:** Create `knowledge/store.py`; Test `tests/wave9/test_knowledge_store.py`.

**Interfaces:** Consumes `KnowledgeDoc`, `SearchHit` (Task 2). Produces `KnowledgeStore(db_path)`, `DuplicateSourceError(Exception)`, methods per spec §3.2: `ingest(doc, replace=False)`, `search(query, *, status=None, tags=None, limit=20) -> list[SearchHit]`, `list_docs(status=None, limit=100)`, `get(doc_id)`, `activate(doc_id)` (idempotent), `counts()`, `close()`.

- [ ] **Step 1: Failing tests** (spec §6 — the full list):

```python
"""Knowledge store tests (spec 4A §3.2, §6)."""
from __future__ import annotations

import pytest

from shettyxtreme.knowledge.schemas import KnowledgeDoc
from shettyxtreme.knowledge.store import DuplicateSourceError, KnowledgeStore


def _doc(doc_id: str, source_ref: str = "b1", body_text: str = "NIFTY trending up with elevated IV crowding") -> KnowledgeDoc:
    return KnowledgeDoc(
        doc_id=doc_id,
        kind="research_brief",
        source_ref=source_ref,
        payload={"thesis": body_text, "lens": "oi_iv_flow"},
        tags=[{"tag": "NIFTY", "kind": "symbol"}, {"tag": "TRENDING_UP", "kind": "regime"}],
    )


def test_schema_created_and_empty(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    assert store.list_docs() == []
    assert store.search("nifty") == []
    assert store.counts() == {"docs": 0, "proposed": 0, "activated": 0, "tags": 0}
    store.close()


def test_ingest_and_get(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    doc = _doc("d1")
    store.ingest(doc)
    got = store.get("d1")
    assert got is not None and got.source_ref == "b1" and got.status == "proposed"
    assert got.created_at is not None
    store.close()


def test_ingest_duplicate_source_ref(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1"))
    with pytest.raises(DuplicateSourceError):
        store.ingest(_doc("d2", "b1"))
    store.ingest(_doc("d2", "b1"), replace=True)  # replace wins
    assert store.get("d1") is None
    assert store.get("d2") is not None
    store.close()


def test_search_ranking_and_snippet(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1", "NIFTY trending up with elevated IV crowding"))
    store.ingest(_doc("d2", "b2", "BANKNIFTY range bound, no momentum"))
    hits = store.search("trending")
    assert len(hits) == 1
    assert hits[0].doc_id == "d1"
    assert "trending" in hits[0].snippet.lower()
    store.close()


def test_search_tag_and_status_filters(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1"))
    store.ingest(_doc("d2", "b2", "BANKNIFTY range bound"))
    assert len(store.search("nifty", tags=["NIFTY"])) == 1
    store.activate("d1")
    assert len(store.search("nifty", status="proposed")) == 0
    assert len(store.search("nifty", status="activated")) == 1
    assert len(store.search("nope", tags=["NOPE_TAG"])) == 0
    store.close()


def test_fts_stays_in_sync_on_replace(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1", "b1", "NIFTY trending"))
    store.ingest(_doc("d1", "b1", "BANKNIFTY range bound"), replace=True)
    assert len(store.search("trending")) == 0
    assert len(store.search("banknifty")) == 1
    store.close()


def test_activate_idempotent_and_unknown(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1"))
    act = store.activate("d1")
    assert act.status == "activated" and act.activated_at is not None
    assert store.activate("d1").status == "activated"  # idempotent
    with pytest.raises(KeyError):
        store.activate("nope")
    store.close()


def test_counts(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    store.ingest(_doc("d1"))
    store.ingest(_doc("d2", "b2", "BANKNIFTY range bound"))
    store.activate("d1")
    assert store.counts() == {"docs": 2, "proposed": 1, "activated": 1, "tags": 4}
    store.close()


def test_list_status_filter_and_limit(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    for i in range(5):
        store.ingest(_doc(f"d{i}", f"b{i}"))
    assert len(store.list_docs(limit=2)) == 2
    store.activate("d0")
    assert all(d.status == "activated" for d in store.list_docs(status="activated"))
    store.close()
```

- [ ] **Step 2: FAIL** → **Step 3: Implement** (spec §3.2):
  - Schema: `docs(doc_id PK, kind, source_ref UNIQUE, payload, status, created_at, activated_at)`; `tags(doc_id, tag, kind, PK(doc_id, tag, kind))`; `docs_fts` external-content FTS5 (`content='docs', content_rowid='rowid'`, columns `title, body`) + AFTER INSERT/UPDATE/DELETE triggers (`'delete'` on insert for replace, insert/update/delete of `docs_fts`).
  - Row storage: `title` = `payload.thesis` (trunc 200), `body` = thesis + rationale + evidence items; store `title/body` INSIDE payload? No — FTS content comes from payload; triggers need the columns → add REAL columns `title TEXT, body TEXT` on `docs` alongside payload (FTS content-table columns must be real columns). Payload keeps the full model dump; title/body are the searchable projection. `ingest` writes both.
  - `search`: `SELECT d.rowid, d.doc_id, ..., bm25(docs_fts) AS score, snippet(docs_fts, 1, '[', ']', '…', 12) AS snip FROM docs_fts JOIN docs d ON d.rowid = docs_fts.rowid WHERE docs_fts MATCH ? [AND d.status = ?] [AND d.doc_id IN (SELECT doc_id FROM tags WHERE tag = ?)] ORDER BY score LIMIT ?` — build MATCH from the user query via `'"' + query.replace('"', '""') + '"'` quoting; empty/whitespace query → `[]`.
  - `activate`: UPDATE status/activated_at; unknown → KeyError; already activated → return as-is (idempotent).
  - Degradation: all read paths never raise on empty store.
- [ ] **Step 4: PASS** → **Step 5: Report** (commit: `feat(4a): knowledge store — sqlite FTS5, tags, idempotent ingest, activate`)

### Task 4: Tagger (`knowledge/tagger.py`)

**Files:** Create `knowledge/tagger.py`; Test `tests/wave9/test_knowledge_tagger.py`.

**Interfaces:** Consumes lexicons (Task 1). Produces `tag_document(text: str) -> list[dict]` (`{"tag", "kind"}` entries; dedup; cap 50; multi-word phrases first).

- [ ] **Step 1: Failing tests:**

```python
"""Tagger tests (spec 4A §3.4)."""
from __future__ import annotations

from shettyxtreme.knowledge.tagger import tag_document


def test_symbols_extracted() -> None:
    tags = tag_document("NIFTY broke out while BANKNIFTY lagged")
    syms = {t["tag"] for t in tags if t["kind"] == "symbol"}
    assert syms == {"NIFTY", "BANKNIFTY"}


def test_stopwords_not_symbols() -> None:
    tags = tag_document("The IT sector was ON fire")
    syms = {t["tag"] for t in tags if t["kind"] == "symbol"}
    assert syms == set()


def test_regime_phrases() -> None:
    tags = tag_document("market is trending up with sideways pressure")
    regimes = {t["tag"] for t in tags if t["kind"] == "regime"}
    assert regimes == {"trending_up", "range_bound"}


def test_risk_themes() -> None:
    tags = tag_document("elevated IV and crowding near resistance")
    risks = {t["tag"] for t in tags if t["kind"] == "risk"}
    assert risks == {"ELEVATED_IV", "CROWDING", "RESISTANCE"}


def test_dedup_and_cap() -> None:
    tags = tag_document("NIFTY NIFTY NIFTY " + " ".join([f"X{i}" for i in range(100)]))
    syms = [t for t in tags if t["kind"] == "symbol"]
    assert len([t for t in syms if t["tag"] == "NIFTY"]) == 1
    assert len(tags) <= 50
```

- [ ] **Step 2: FAIL** → **Step 3: Implement** (spec §3.4): lowercase copy for regime/risk phrase matching (longest phrase first: sort REGIME_TERMS/RISK_THEMES keys by word count desc); symbols via regex `\b[A-Za-z:]{2,}\b` tokenize → uppercase → `normalize_symbol`; dedup dict; cap 50.
- [ ] **Step 4: PASS** → **Step 5: Report** (commit: `feat(4a): heuristic tagger (symbols, regimes, risk themes)`)

### Task 5: Ingest contract (`knowledge/ingest.py`)

**Files:** Create `knowledge/ingest.py`; Test `tests/wave9/test_knowledge_ingest.py`.

**Interfaces:** Consumes `KnowledgeStore`, `tag_document`. Produces `ResearchBriefLike` Protocol, `IngestResult(ingested, skipped_undecided, skipped_duplicate)` dataclass, `ingest_decided_briefs(store, briefs) -> IngestResult`.

- [ ] **Step 1: Failing tests** (use a plain fake brief class implementing the protocol fields — proves knowledge/ never imports research/):

```python
"""Ingest tests (spec 4A §3.3, §6)."""
from __future__ import annotations

from dataclasses import dataclass, field

from shettyxtreme.knowledge.ingest import ingest_decided_briefs
from shettyxtreme.knowledge.store import KnowledgeStore


@dataclass
class FakeBrief:
    brief_id: str
    lens: str
    as_of: str
    status: str
    thesis: str
    rationale: str = "r" * 320
    decided_at: str | None = None
    outcome: str | None = None
    evidence: list[dict] = field(default_factory=list)


def test_only_decided_ingested(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    briefs = [
        FakeBrief(brief_id="a", lens="oi_iv_flow", as_of="t", status="approved", thesis="NIFTY trending", decided_at="t1"),
        FakeBrief(brief_id="b", lens="tail_risk", as_of="t", status="proposed", thesis="BANKNIFTY"),
    ]
    res = ingest_decided_briefs(store, briefs)
    assert res.ingested == 1 and res.skipped_undecided == 1 and res.skipped_duplicate == 0
    assert store.counts()["docs"] == 1
    store.close()


def test_rejected_with_decided_at_ingested(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    b = FakeBrief(brief_id="c", lens="directional_momentum", as_of="t", status="rejected", thesis="X", decided_at="t2")
    res = ingest_decided_briefs(store, [b])
    assert res.ingested == 1
    doc = store.list_docs()[0]
    assert doc.source_ref == "c" and doc.kind == "research_brief"
    store.close()


def test_duplicates_counted_not_fatal(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    b = FakeBrief(brief_id="d", lens="l", as_of="t", status="approved", thesis="NIFTY", decided_at="t3")
    ingest_decided_briefs(store, [b])
    res = ingest_decided_briefs(store, [b])
    assert res.ingested == 0 and res.skipped_duplicate == 1
    store.close()


def test_tags_and_body_populated(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    b = FakeBrief(brief_id="e", lens="oi_iv_flow", as_of="t", status="approved", thesis="NIFTY trending with elevated IV", decided_at="t4", evidence=[{"item": "x", "source": "y", "unsourced": False}])
    ingest_decided_briefs(store, [b])
    doc = store.list_docs()[0]
    kinds = {t["kind"] for t in doc.tags}
    assert kinds == {"symbol", "regime", "risk"}
    assert len(store.search("elevated")) == 1  # body includes evidence + rationale
    store.close()
```

- [ ] **Step 2: FAIL** → **Step 3: Implement** (spec §3.3): protocol; skip unless `status in {"approved","rejected"} and decided_at`; `tag_document(thesis + " " + rationale + evidence items)`; DuplicateSourceError → skipped_duplicate; doc_id = `f"brief-{brief_id}"`.
- [ ] **Step 4: PASS** → **Step 5: Report** (commit: `feat(4a): decided-brief ingest contract (protocol-decoupled)`)

---

## Track 4B — Recording track

### Task 6: SessionLog (`learning/sessions.py`)

**Files:** Create `learning/sessions.py`; Test `tests/wave9/test_sessions.py`.

**Interfaces:** Produces `SessionLog(db_path)`: `start(mode: str) -> str`, `end(session_id: str) -> None` (no-op unknown), `list(limit=100) -> list[dict]`, `counts() -> dict` (`{total, open, live, observer}`), `close()`.

- [ ] **Step 1: Failing tests:**

```python
"""SessionLog tests (spec 4B §4.1)."""
from __future__ import annotations

from shettyxtreme.learning.sessions import SessionLog


def test_start_end_cycle(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    sid = log.start("OBSERVER")
    assert log.counts() == {"total": 1, "open": 1, "live": 0, "observer": 1}
    log.end(sid)
    assert log.counts()["open"] == 0
    rows = log.list()
    assert len(rows) == 1
    assert rows[0]["mode"] == "OBSERVER"
    assert rows[0]["ended_at"] is not None
    log.close()


def test_end_unknown_noop(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    log.end("nope")  # must not raise
    assert log.counts()["total"] == 0
    log.close()


def test_modes_counted(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    log.start("OBSERVER")
    log.start("LIVE")
    log.start("OBSERVER")
    assert log.counts() == {"total": 3, "open": 3, "live": 1, "observer": 2}
    log.close()


def test_limit(tmp_path) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    for i in range(5):
        log.start("OBSERVER")
    assert len(log.list(limit=2)) == 2
    log.close()
```

- [ ] **Step 2: FAIL** → **Step 3: Implement** (spec §4.1): sqlite `sessions(session_id PK, started_at, ended_at, mode)`; session_id = uuid4 str; single connection + commit per op (ResearchStore pattern); `list` newest first (`ORDER BY started_at DESC`).
- [ ] **Step 4: PASS** → **Step 5: Report** (commit: `feat(4b): SessionLog store`)

### Task 7: regime_at_decision (`research/briefs.py` + `research/store.py`)

**Files:** Modify `research/briefs.py`, `research/store.py`; Test `tests/wave8/test_research_briefs_store.py` (additive — use the existing `_make_brief` helper there).

**Interfaces:** Consumes existing. Produces `ResearchBrief.regime_at_decision: str | None = None` (NOT in MODEL_AUTHORED_FIELDS — like decided_at); `store.decide(brief_id, decision, regime: str | None = None)` writes it into payload.

- [ ] **Step 1: Failing tests** (append to `tests/wave8/test_research_briefs_store.py`):

```python
def test_regime_at_decision_not_model_authorable() -> None:
    assert "regime_at_decision" not in MODEL_AUTHORED_FIELDS


def test_decide_records_regime(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    decided = store.decide(brief.brief_id, "approved", regime="TRENDING_UP")
    assert decided.regime_at_decision == "TRENDING_UP"
    assert store.get(brief.brief_id).regime_at_decision == "TRENDING_UP"
    store.close()


def test_decide_without_regime_keeps_none(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    decided = store.decide(brief.brief_id, "approved")
    assert decided.regime_at_decision is None
    store.close()
```

- [ ] **Step 2: FAIL** → **Step 3: Implement**: field on ResearchBrief (after `decided_at`); `decide(..., regime=None)` → `payload["regime_at_decision"] = regime` next to `decided_at`.
- [ ] **Step 4: PASS** → **Step 5: Report** (commit: `feat(4b): regime_at_decision recorded at decide time`)

---

## Track frontend (both panels)

### Task 8: api.ts types

**Files:** Modify `src/shettyxtreme/terminal/web/src/lib/api.ts` (append).

**Interfaces:** Produces types: `KnowledgeTag {tag, kind}`, `KnowledgeDoc {doc_id, kind, source_ref, payload, status, created_at, activated_at, tags}`, `KnowledgeSearchHit {doc_id, kind, source_ref, status, title, snippet, tags, bm25_score}`, `KnowledgeSearchResponse {hits}`, `KnowledgeListResponse {docs}`, `KnowledgeStatusResponse {docs, proposed, activated, tags}`, `KnowledgeSyncResponse {ingested, skipped_undecided, skipped_duplicate}`, `CalibrationPoint {conviction_bin, actual_win_rate, sample_size, confidence_interval}`, `ScorecardMetric {key, label, value, unit, available, note}`, `RegimeRow {regime, decided, with_outcome, win_rate}`, `ScorecardResponse {reliable_calibration, metrics, by_regime, calibration}`, `SessionsResponse {sessions, counts}`.

- [ ] **Step 1: Write** → **Step 2: `npm run check` 0 errors** → **Step 3: Report** (commit: `feat(4): frontend api types for knowledge + analytics`)

### Task 9: KnowledgePanel.svelte

**Files:** Create `src/shettyxtreme/terminal/web/src/components/KnowledgePanel.svelte` (≤500 lines).

**Interfaces:** Consumes api.ts types + `get`/`post`; `onMessage` (WS topic `knowledge`). Produces: search box (debounced Enter/Search button), results list (title, tag badges, snippet, source_ref, status), select → detail (thesis, rationale, tags, evidence refs from payload, activated_at), Activate button (disabled when activated/unknown), Sync button (shows `ingested/skipped` counts), empty state. WS `activated` event updates row status.

- [ ] **Step 1: Write component** (ResearchPanel patterns: `.panel`, `.panel-head`, `.tag`, `.mono`, DESIGN.md tokens) → **Step 2: `npm run check` 0 errors** → **Step 3: Report** (commit: `feat(4a): KnowledgePanel — search, review, activate, sync`)

### Task 10: AnalyticsPanel.svelte

**Files:** Create `src/shettyxtreme/terminal/web/src/components/AnalyticsPanel.svelte` (≤500 lines).

**Interfaces:** Consumes `get` + analytics types. Produces: scorecard metric cards (label/value/`available:false` dashed-empty-state + `note` title attr), calibration SVG step chart (points: x = bin midpoint %, y = win rate; CI whiskers; diagonal reference; `reliable` badge; empty → message), by-regime CSS bars (width % = win_rate, counts), refresh button.

- [ ] **Step 1: Write component** — the SVG math (no lib):

```ts
function chart(points: CalibrationPoint[]): string {
  // viewBox 0 0 320 120; x = 20 + (mid * 280) where mid = (lo+hi)/2 (conviction 0..1)
  // y = 104 - (win_rate * 96); reference diagonal from (20,104) to (300,8)
  const W = 320, H = 120, PX = 20, PY = 8, CW = 280, CH = 96;
  const x = (m: number) => PX + m * CW;
  const y = (r: number) => H - PY - r * CH;
  const pts = points.map((p, i) => `${x((p.conviction_bin[0] + p.conviction_bin[1]) / 2)},${y(p.actual_win_rate)}`).join(" ");
  const whisk = points.map((p) => {
    const mx = (p.conviction_bin[0] + p.conviction_bin[1]) / 2;
    return `<line x1="${x(mx)}" y1="${y(p.confidence_interval[1])}" x2="${x(mx)}" y2="${y(p.confidence_interval[0])}" stroke="var(--hairline-strong)" stroke-width="1"/>`;
  }).join("");
  const dots = points.map((p) => {
    const mx = (p.conviction_bin[0] + p.conviction_bin[1]) / 2;
    return `<circle cx="${x(mx)}" cy="${y(p.actual_win_rate)}" r="${Math.max(2, Math.min(6, Math.sqrt(p.sample_size)))}" fill="var(--accent)"/>`;
  }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="calibration curve">
    <line x1="${PX}" y1="${H - PY}" x2="${W - PX}" y2="${PY}" stroke="var(--hairline)" stroke-dasharray="3 3"/>
    ${whisk}${dots}<polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
  </svg>`;
}
```

  (XSS-safe: numbers only interpolated — no raw text into SVG.) → **Step 2: `npm run check` 0 errors** → **Step 3: Report** (commit: `feat(4b): AnalyticsPanel — scorecard cards + SVG calibration + regime bars`)

### Task 11: App.svelte mount

**Files:** Modify `src/shettyxtreme/terminal/web/src/App.svelte`.

- [ ] **Step 1: Edit** — import `KnowledgePanel` + `AnalyticsPanel`; mount `<KnowledgePanel />` in `.right-col` after `<ResearchPanel />`; mount `<AnalyticsPanel />` in `.center` after `<HintsPanel />` → **Step 2: `npm run check` 0 errors** → **Step 3: Report** (commit: `feat(4): mount Knowledge + Analytics panels`)

---

## Wave 2 — Coordinator integration (TDD, sequential)

### Task 12: Knowledge API (`knowledge_models.py` + `knowledge_router.py`)

**Files:** Create `terminal/api/knowledge_models.py`, `terminal/api/knowledge_router.py`; Test `tests/wave9/test_knowledge_api.py`.

- [ ] **Step 1: Failing tests** (ASGITransport AsyncClient pattern from `test_research_api.py`; fixture overrides `kr._STORE` with tmp-path store; also test `init_knowledge(broadcast_fn)` broadcast capture):

```python
"""Knowledge API tests (spec 4A §3.6, §6)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.knowledge_router as kr
from shettyxtreme.knowledge.schemas import KnowledgeDoc
from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def kstore(tmp_path) -> KnowledgeStore:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    kr._STORE = store
    return store


@pytest.mark.asyncio
async def test_status_empty(client: AsyncClient, kstore) -> None:
    resp = await client.get("/api/knowledge/status")
    assert resp.status_code == 200
    assert resp.json() == {"docs": 0, "proposed": 0, "activated": 0, "tags": 0}


@pytest.mark.asyncio
async def test_sync_and_search(client: AsyncClient, kstore, tmp_path) -> None:
    # seed the research store with one decided brief (real ResearchStore)
    from shettyxtreme.research.briefs import ResearchBrief
    from shettyxtreme.research.store import ResearchStore

    rstore = ResearchStore(str(tmp_path / "research.db"))
    kr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    brief = ResearchBrief(
        brief_id="b1", lens="oi_iv_flow", as_of="t", direction=1, confidence=0.6,
        thesis="NIFTY trending up", rationale="r" * 320, evidence=[], risks=[],
    )
    rstore.insert(brief)
    rstore.decide("b1", "approved")
    rstore.close()

    resp = await client.post("/api/knowledge/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingested"] == 1 and body["skipped_undecided"] == 0

    resp2 = await client.get("/api/knowledge/search", params={"q": "trending"})
    assert resp2.status_code == 200
    hits = resp2.json()["hits"]
    assert len(hits) == 1 and hits[0]["source_ref"] == "b1"


@pytest.mark.asyncio
async def test_activate_flow(client: AsyncClient, kstore) -> None:
    kstore.ingest(KnowledgeDoc(doc_id="d1", kind="research_brief", source_ref="b1", payload={"thesis": "x"}))
    resp = await client.post("/api/knowledge/docs/d1/activate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "activated"
    resp2 = await client.post("/api/knowledge/docs/nope/activate")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_sync_missing_research_db(client: AsyncClient, kstore, tmp_path) -> None:
    kr.RESEARCH_DB_PATH = str(tmp_path / "missing.db")
    resp = await client.post("/api/knowledge/sync")
    assert resp.status_code == 200  # degraded, never 500
    assert resp.json()["ingested"] == 0


@pytest.mark.asyncio
async def test_broadcast_on_activate(client: AsyncClient, kstore) -> None:
    events: list[dict] = []
    kr.init_knowledge(broadcast_fn=events.append)
    kstore.ingest(KnowledgeDoc(doc_id="d1", kind="research_brief", source_ref="b1", payload={"thesis": "x"}))
    await client.post("/api/knowledge/docs/d1/activate")
    assert any(e["event"] == "activated" for e in events)
    kr.init_knowledge(broadcast_fn=None)
```

- [ ] **Step 2: FAIL** → **Step 3: Implement** — models per spec §3.6; router: module globals `_STORE: KnowledgeStore | None`, `_broadcast_fn`, `init_knowledge(store=None, broadcast_fn=None)`, `RESEARCH_DB_PATH = "data/research.db"`; endpoints per spec (search with empty q → `[]`; sync opens ResearchStore — catch Exception → 200 zeros + `error` field... spec says `{ingested: 0, ..., error: "..."}` — add `error: str | None = None` to KnowledgeSyncResponse); activate broadcasts `{"event": "activated", "data": <model_dump>}`. `_store()` helper: `if _STORE is None: _STORE = KnowledgeStore("data/knowledge.db")`.
- [ ] **Step 4: PASS** → **Step 5: Commit** (`feat(4a): knowledge API — search, docs, status, sync, activate + broadcast`)

### Task 13: Analytics API (`analytics_models.py` + `analytics_router.py`)

**Files:** Create `terminal/api/analytics_models.py`, `terminal/api/analytics_router.py`; Test `tests/wave9/test_analytics_api.py`.

- [ ] **Step 1: Failing tests:**

```python
"""Analytics API tests (spec 4B §4.3, §6)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.analytics_router as ar
from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_scorecard_empty(client: AsyncClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "missing.db"))
    resp = await client.get("/api/analytics/scorecard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metrics"] != []
    assert all(m["available"] is False for m in body["metrics"])
    assert body["by_regime"] == []
    assert body["calibration"] == []


@pytest.mark.asyncio
async def test_scorecard_with_data(client: AsyncClient, tmp_path, monkeypatch) -> None:
    from shettyxtreme.research.briefs import ResearchBrief
    from shettyxtreme.research.store import ResearchStore

    rstore = ResearchStore(str(tmp_path / "research.db"))
    for i, (status, outcome, regime) in enumerate(
        [("approved", "WIN", "TRENDING_UP"), ("approved", "LOSS", "TRENDING_UP"), ("rejected", None, "RANGE_BOUND")]
    ):
        b = ResearchBrief(
            brief_id=f"b{i}", lens="oi_iv_flow", as_of="t", direction=1, confidence=0.6,
            thesis="t", rationale="r" * 320, evidence=[], risks=[],
        )
        rstore.insert(b)
        rstore.decide(b.brief_id, status, regime=regime)
        if outcome:
            rstore.set_outcome(b.brief_id, outcome)
    rstore.close()

    log = SessionLog(str(tmp_path / "s.db"))
    sid = log.start("OBSERVER")
    log.end(sid)
    log.close()

    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "research.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "s.db"))
    resp = await client.get("/api/analytics/scorecard")
    assert resp.status_code == 200
    body = resp.json()
    by_key = {m["key"]: m for m in body["metrics"]}
    assert by_key["sessions_total"]["value"] == 1
    assert by_key["decisions"]["value"] == 3
    assert by_key["win_rate"]["value"] == 0.5
    rows = {r["regime"]: r for r in body["by_regime"]}
    assert rows["TRENDING_UP"]["win_rate"] == 0.5
    assert rows["RANGE_BOUND"]["with_outcome"] == 0


@pytest.mark.asyncio
async def test_sessions_endpoint(client: AsyncClient, tmp_path, monkeypatch) -> None:
    log = SessionLog(str(tmp_path / "s.db"))
    log.start("LIVE")
    log.close()
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "s.db"))
    resp = await client.get("/api/analytics/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["sessions"]) == 1
    assert body["counts"]["live"] == 1
```

- [ ] **Step 2: FAIL** → **Step 3: Implement** — models per spec §4.3; router: module constants `RESEARCH_DB_PATH = "data/research.db"`, `SESSIONS_DB_PATH = "data/sessions.db"`, `LEARNING_DB_PATH = "data/learning.db"`; `_fit_calibration` imported from `learning_router` (same package); scorecard assembly: sessions counts (SessionLog), research aggregates (ResearchStore: decisions = status != proposed; with_outcome = outcome in WIN/LOSS; win_rate; avg_confidence over decided; by_regime GROUP BY regime_at_decision — read payloads like `scoring()` does); each metric carries `available` (bool) + `note`. All DB opens wrapped — failures → `available: false` metrics (never 500).
- [ ] **Step 4: PASS** → **Step 5: Commit** (`feat(4b): analytics API — scorecard + sessions`)

### Task 14: knowledge_search tool wiring

**Files:** Modify `research/tools.py` (DataSource protocol + tool), `terminal/api/research_source.py` (knowledge_summary), `tests/wave8/test_research_tools.py` (registry shape update), `tests/wave8/test_research_api.py` (tools listing now 5).

- [ ] **Step 1: Failing tests** — append to `tests/wave8/test_research_tools.py`:

```python
def test_knowledge_search_tool_registered() -> None:
    assert "knowledge_search" in TOOLS
    ks = TOOLS["knowledge_search"]
    assert ks.params_schema["required"] == ["query"]


def test_knowledge_search_with_source() -> None:
    class KSource(FakeSource):
        def knowledge_summary(self, query: str) -> str | None:
            return f"hits for {query}"

    set_data_source(KSource())
    out = run_tool("knowledge_search", {"query": "nifty"})
    assert out == "hits for nifty"


def test_knowledge_search_unsourced() -> None:
    set_data_source(None)
    assert run_tool("knowledge_search", {"query": "nifty"}) == UNSOURCED
```

  Update `test_tools_registry_shape` name list → `["chain_snapshot", "regime_snapshot", "scanner_alerts", "options_posture", "knowledge_search"]` and the tools-listing test in `test_research_api.py` set → include `knowledge_search`.
- [ ] **Step 2: FAIL** → **Step 3: Implement** — `DataSource` gains `knowledge_summary(self, query: str) -> str | None: ...`; tool def `knowledge_search` (description "Search activated knowledge documents."); `_knowledge_invoke(params)` → `query = params.get("query")`; missing → `"TOOL ERROR: missing required parameter 'query'"`; `_source.knowledge_summary(str(query))` or UNSOURCED. `ProjectionDataSource.knowledge_summary`: `store = getattr(self._state, "knowledge_store", None)`; None → None; `store.search(query, status="activated", limit=5)` → join `f"- {h.title} [{h.tags...}] ({h.source_ref})"` lines or None; wrap in try/except → None.
- [ ] **Step 4: PASS** → **Step 5: Commit** (`feat(4a): knowledge_search research tool + DataSource method`)

### Task 15: app.py + research_router wiring

**Files:** Modify `terminal/api/app.py`, `terminal/api/research_router.py`; Test `tests/wave9/test_lifespan_wiring.py` (import smoke + unit-level asserts — no full lifespan run).

- [ ] **Step 1: Failing tests:**

```python
"""Phase 4 lifespan wiring tests (spec 4A §3.6, 4B §4.1)."""
from __future__ import annotations

from shettyxtreme.terminal.api import app as app_module


def test_knowledge_router_importable() -> None:
    from shettyxtreme.terminal.api.knowledge_router import router

    assert router.prefix == "/api/knowledge"


def test_analytics_router_importable() -> None:
    from shettyxtreme.terminal.api.analytics_router import router

    assert router.prefix == "/api/analytics"


def test_app_imports_clean() -> None:
    assert app_module.app is not None
```

- [ ] **Step 2: FAIL/red-import** → **Step 3: Implement** — `app.py`: imports (`init_knowledge`, `knowledge_router`, `analytics_router`, `SessionLog`); in lifespan after research wiring: create `knowledge_store = KnowledgeStore("data/knowledge.db")`, `app.state.knowledge_store = knowledge_store`, `init_knowledge(store=knowledge_store, broadcast_fn=_research_broadcast)` (reuse the research broadcast wrapper — or a knowledge-specific one; spec: same pattern, new wrapper `_knowledge_broadcast`); `session_log = SessionLog("data/sessions.db")`, `app.state.session_log = session_log`; `_session_id = session_log.start(mode)` where `mode = getattr(app.state, "mode", "OBSERVER")`; teardown: `session_log.end(_session_id)`, `knowledge_store.close()`. Include routers: `app.include_router(knowledge_router)`, `app.include_router(analytics_router)`. `research_router._decide`: accept `request: Request`, read `proj = request.app.state.intelligence_projection` → `regime = proj.get_regime().get("regime")` → `store.decide(brief_id, decision, regime=regime)`; endpoints `approve`/`reject` pass `request`. (Existing tests call the endpoints via AsyncClient — request available; `_decide` signature change is internal.)
- [ ] **Step 4: PASS** → **Step 5: Commit** (`feat(4): lifespan wiring — knowledge store, session log, regime-at-decision`)

### Task 16: Wave-2 gate + full suite

- [ ] **Step 1: Full suite** — `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=... -p no:cacheprovider` → all pass, **0 skipped** (~715+).
- [ ] **Step 2: Gates** — grep zero; ≤500 lines; `npm run check` 0 errors; `npm run build` (commit bundle).
- [ ] **Step 3: Commit** (`build(4): committed frontend bundle`)

---

## Wave 3 — Review + finish (Task 17)

- [ ] **Step 1: Code review** — code-reviewer subagent on `master...phase4` (specs 4A/4B as contract); fix IMPORTANTs; re-review; final whole-branch review.
- [ ] **Step 2: Docs** — CHANGELOG v0.10.0 (Phase 4: knowledge layer + analytics + recording; suite count); roadmap §17 Phase 4 row → DONE; README roadmap row; version bump all four files → 0.10.0.
- [ ] **Step 3: Merge + push decision presented** (v0.10.0); handoff `docs/superpowers/handoffs/2026-08-01-phase4-complete-next-session.md`; ledger + O2B pinned update.

## Self-review notes

- D12 integrity: knowledge/ imports only core + stdlib + pydantic (subagent gate: `rg "import shettyxtreme" knowledge/` must show only core).
- FTS external-content tables REQUIRE real `title`/`body` columns on `docs` — spec'd in Task 3.
- `test_research_tools.py` registry-shape + `test_research_api.py` tools-listing tests change in Task 14 (5 tools now) — owned by coordinator.
- Regime enum values taken from `intelligence.regime.models.Regime` (TRENDING_UP/TRENDING_DOWN/RANGE_BOUND/NEUTRAL) — lexicon maps to those strings; test imports the enum to lock it.
- No test touches the real DeepSeek API (tool loop is SimulatedProvider-only in tests).
