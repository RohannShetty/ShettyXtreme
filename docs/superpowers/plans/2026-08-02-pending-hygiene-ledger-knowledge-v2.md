# Pending Work Implementation Plan (v0.11.0) — Hygiene + Trades Ledger + Knowledge v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clear the deferred-minor backlog (sqlite timeouts, test fixture hygiene, gitignore quirk, regime normalization, alert dedup, chain renderer), ship the trades-ledger recording track that unblocks net-EV scoring, and extend knowledge to operator notes + tag refinement.

**Architecture:** Three independent tracks (A hygiene, B ledger, C knowledge v2) — safe to run as parallel subagent waves with disjoint file ownership, coordinator commits. Track B follows the established store pattern (ResearchStore/SessionLog single-connection sqlite, `core/interfaces` untouched, recording via EventBus subscription — no router changes). Track C respects D12 (`knowledge/` imports core ONLY; notes are tagged heuristically, human-activated — no LLM).

**Tech Stack:** Python 3.11, sqlite3 stdlib (FTS5 where used), FastAPI, Svelte 5, pytest-asyncio, plain-SVG scorecard (zero charting deps).

## Global Constraints

- Test runner (exact): `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase5 -p no:cacheprovider` — distinct basetemps per parallel agent.
- Suite gate: never shrinks, 0 skipped, currently 703/0/0; grep gate zero `import openalgo|from openalgo` in src/; no new file > 500 lines.
- D12: `knowledge/` imports core ONLY; D3: LLM only in `research/provider.py`; sqlite stdlib only for stores.
- `svelte-check` 0 errors before build; bundle in `terminal/static/` is committed.
- Never stage: `AGENTS.md`, `.opencode/opencode.json`, `docs/superpowers/plans/2026-07-31-graphify-upgrade.md`. Subagents never commit.
- DESIGN.md tokens binding: price-up red `#f6525c`, price-down green `#2ebd85`; JetBrains Mono numerals.
- Out of scope (already decided): multi-broker, backtest depth, critic pass (waits for order intents), live `/optionchain` fixture (needs live creds).

---

## Task 0: Phase-4 surface smoke (manual, no code)

- [ ] **Step 1:** Run the full suite to confirm the 703/0/0 baseline.
- [ ] **Step 2:** `& .\.venv\Scripts\python.exe run.py --mode OBSERVER`; populate `data/research.db` with 2–3 decided briefs (real `DEEPSEEK_API_KEY` run + approve, or sqlite INSERT into `briefs` with valid JSON payloads).
- [ ] **Step 3:** In the terminal verify KnowledgePanel sync/activate/search against `data/research.db` and AnalyticsPanel scorecard/sessions render. Check `server.err` for noise.
- [ ] **Step 4:** Record findings; commit nothing (smoke only).

---

## Track A — Hygiene

### Task 1: sqlite timeouts on all store connects

**Files:**
- Modify: `src/shettyxtreme/research/store.py:45`, `src/shettyxtreme/knowledge/store.py` (`__init__` connect), `src/shettyxtreme/learning/sessions.py:29`, `src/shettyxtreme/execution/execution_engine.py` (`_init_db` connect)
- Test: Create `tests/wave8/test_store_timeouts.py`

**Interfaces:** No signatures change; stores keep accepting `db_path: str`.

- [ ] **Step 1: Write the failing test**

```python
import sqlite3

import pytest

from shettyxtreme.knowledge.store import KnowledgeStore
from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.research.store import ResearchStore


@pytest.mark.parametrize("cls", [ResearchStore, KnowledgeStore, SessionLog])
def test_connect_uses_timeout(cls, tmp_path, monkeypatch):
    real = sqlite3.connect
    captured: dict[str, dict] = {}

    def spy(db_path, *args, **kwargs):
        captured[str(db_path)] = kwargs
        return real(db_path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy)
    store = cls(str(tmp_path / "store.db"))
    store.close()
    assert captured, "connect was not called"
    assert captured[str(tmp_path / "store.db")].get("timeout") == 5.0
```

- [ ] **Step 2:** Run `pytest tests/wave8/test_store_timeouts.py -v` — Expected: FAIL (no `timeout` kwarg; captured kwarg is `{}`).
- [ ] **Step 3:** Change each `sqlite3.connect(db_path)` to `sqlite3.connect(db_path, timeout=5.0)` (4 sites). No comments.
- [ ] **Step 4:** Run the test — PASS. Then full suite — still 703/0/0.
- [ ] **Step 5: Commit** `git add -A; git commit -m "fix: sqlite connect timeout=5 on all stores (deferred minor)"`

### Task 2: research-router global fixture hygiene

**Files:**
- Modify: `tests/wave8/test_research_api.py`

**Interfaces:** None — test-only.

- [ ] **Step 1: Add module import-state capture + autouse restore fixture** (after the `client` fixture):

```python
_IMPORT_STATE = (rr.RESEARCH_DB_PATH, rr._ORCHESTRATOR)


@pytest_asyncio.fixture(autouse=True)
async def _restore_research_globals():
    yield
    rr.RESEARCH_DB_PATH, rr._ORCHESTRATOR = _IMPORT_STATE
    rr.init_research(broadcast_fn=None, scheduler=None)
```

- [ ] **Step 2: Add the order-last assertion test** at the end of the file (runs after all mutating tests):

```python
@pytest.mark.asyncio
async def test_module_globals_restored() -> None:
    assert (rr.RESEARCH_DB_PATH, rr._ORCHESTRATOR) == _IMPORT_STATE
```

- [ ] **Step 3:** Run `pytest tests/wave8/test_research_api.py -v` — all PASS including the new test. Run full suite.
- [ ] **Step 4: Commit** `git add -A; git commit -m "test: research api module-global snapshot/restore fixture (deferred minor)"`

### Task 3: `.gitignore` `_*.py` quirk — un-ignore `__init__.py`

**Files:**
- Modify: `.gitignore` (after line 59 `_*.py`)

- [ ] **Step 1: Verify the bug** — Run `git check-ignore -v src/shettyxtreme/knowledge/__init__.py`; Expected: matched by `_*.py` (exit 0).
- [ ] **Step 2: Add the negation line** immediately after `_*.py`:

```
!**/__init__.py
```

- [ ] **Step 3: Verify** — `git check-ignore -v src/shettyxtreme/knowledge/__init__.py` now exits 1 (not ignored); confirm `_*.py` still matches a scaffolding file (`git check-ignore -v _scaffold.py` exits 0).
- [ ] **Step 4: Commit** `git add .gitignore; git commit -m "fix: un-ignore __init__.py (gitignore _*.py quirk)"`

### Task 4: regime normalization at decide time

**Files:**
- Modify: `src/shettyxtreme/terminal/api/research_router.py` (`_current_regime` at line 233)
- Test: `tests/wave8/test_research_api.py`

**Interfaces:** New helper `_normalize_regime(value: object) -> str | None` — later tasks/scorecard rely on `regime_at_decision` being lowercase enum values.

- [ ] **Step 1: Write the failing tests**

```python
from shettyxtreme.terminal.api.research_router import _normalize_regime


def test_normalize_regime_maps_names_and_values() -> None:
    assert _normalize_regime("TRENDING_UP") == "trending_up"
    assert _normalize_regime("trending_up") == "trending_up"
    assert _normalize_regime("VOLATILE") == "volatile"
    assert _normalize_regime("nonsense") is None
    assert _normalize_regime(None) is None
    assert _normalize_regime("") is None
```

Integration test (append to `test_research_api.py`):

```python
@pytest.mark.asyncio
async def test_regime_normalized_at_decision(client, orchestrator, monkeypatch) -> None:
    monkeypatch.setattr(rr, "_current_regime", lambda request: "TRENDING_UP")
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    fetched = (await client.get(f"/api/research/briefs/{brief['brief_id']}")).json()
    assert fetched["regime_at_decision"] == "trending_up"
```

- [ ] **Step 2:** Run `pytest tests/wave8/test_research_api.py -v` — Expected: FAIL (regime stored as `TRENDING_UP`, `_normalize_regime` missing).
- [ ] **Step 3: Implement** in `research_router.py`:

```python
_KNOWN_REGIMES = {"trending_up", "trending_down", "range_bound", "volatile", "transition"}


def _normalize_regime(value: object) -> str | None:
    """Lowercase enum value for regime strings; None for anything unknown."""
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text in _KNOWN_REGIMES else None
```

and change `_current_regime`'s return to `return _normalize_regime(value)`.

- [ ] **Step 4:** Run the tests — PASS. Full suite still green.
- [ ] **Step 5: Commit** `git add -A; git commit -m "fix: normalize regime_at_decision to lowercase enum values (deferred minor)"`

### Task 5: alert duplicate suppression

**Files:**
- Modify: `src/shettyxtreme/terminal/projections.py` (`AlertProjection`)
- Test: `tests/terminal/test_projections.py`

**Interfaces:** `AlertProjection.get()` and the `alert` WS broadcast contract unchanged (unique alerts still emit).

- [ ] **Step 1: Write the failing test** (append):

```python
from datetime import timedelta
from shettyxtreme.core.event_bus.event_bus import Event, Topic


@pytest.mark.asyncio
async def test_duplicate_alert_suppressed_within_window(mock_broadcast) -> None:
    proj = AlertProjection()
    ev = Event(topic=Topic.RISK_ALERT, data={"alert_type": "gap", "severity": "HIGH", "message": "same"}, timestamp=datetime.now(UTC))
    await proj.on_alert(ev)
    await proj.on_alert(ev)
    assert len(proj.get()) == 1
    later = Event(topic=Topic.RISK_ALERT, data={"alert_type": "gap", "severity": "HIGH", "message": "same"}, timestamp=datetime.now(UTC) + timedelta(seconds=60))
    await proj.on_alert(later)
    assert len(proj.get()) == 2
```

(Add `from datetime import timedelta` to the file's imports if absent.)

- [ ] **Step 2:** Run `pytest tests/terminal/test_projections.py -v` — Expected: FAIL (queue has 2).
- [ ] **Step 3: Implement** — in `AlertProjection.__init__` add `self._last_key: tuple[str, str] | None = None` and `self._last_ts: datetime | None = None`; add module constant `_DEDUP_WINDOW_SECONDS = 30.0`; at the top of `on_alert`:

```python
d = event.data
key = (str(d.get("alert_type", "system")), str(d.get("message", "")))
now = event.timestamp
if key == self._last_key and self._last_ts is not None and (now - self._last_ts).total_seconds() < _DEDUP_WINDOW_SECONDS:
    return
self._last_key, self._last_ts = key, now
```

- [ ] **Step 4:** Run the file's tests — PASS (existing `test_alert_broadcast_on_alert` still holds: single alert broadcasts once). Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "fix: suppress duplicate scanner alerts within 30s window (deferred minor)"`

### Task 6: research `chain_summary` renderer from watchlist

**Files:**
- Modify: `src/shettyxtreme/terminal/api/research_source.py` (`chain_summary`, line 19)
- Test: Create `tests/wave8/test_research_source.py`

**Interfaces:** `ProjectionDataSource.chain_summary(symbol: str) -> str | None`; `options_summary` intentionally stays `None` → `[UNSOURCED]` (no runtime options-posture source exists — honest per spec).

- [ ] **Step 1: Write the failing test**

```python
from types import SimpleNamespace

from shettyxtreme.terminal.api.research_source import ProjectionDataSource
from shettyxtreme.terminal.projections import WatchlistProjection


def test_chain_summary_renders_watchlist_row() -> None:
    proj = WatchlistProjection()
    row = proj.add("NIFTY")
    row["ltp"] = 24750.0
    row["change_pct"] = 0.35
    ds = ProjectionDataSource(SimpleNamespace(watchlist_projection=proj))
    assert ds.chain_summary("NIFTY") == "NIFTY ltp=24750.0 change=+0.35%"


def test_chain_summary_unsourced_when_missing() -> None:
    ds = ProjectionDataSource(SimpleNamespace(watchlist_projection=WatchlistProjection()))
    assert ds.chain_summary("NIFTY") is None
```

- [ ] **Step 2:** Run `pytest tests/wave8/test_research_source.py -v` — Expected: FAIL (returns None).
- [ ] **Step 3: Implement** — replace the `chain_summary` body:

```python
def chain_summary(self, symbol: str) -> str | None:
    proj = getattr(self._state, "watchlist_projection", None)
    if proj is None:
        return None
    try:
        watch = proj.get() or {}
    except Exception:
        return None
    key = str(symbol).upper()
    info = watch.get(key) or next(
        (v for k, v in watch.items() if str(k).upper() == key), None
    )
    if not info:
        return None
    ltp = info.get("ltp")
    if ltp is None:
        return None
    chg = info.get("change_pct")
    chg_txt = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "n/a"
    return f"{key} ltp={ltp} change={chg_txt}"
```

- [ ] **Step 4:** Run tests — PASS. Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat: research chain_snapshot renders watchlist LTP (Phase-4 renderer)"`

---

## Track B — Trades ledger + net-EV

### Task 7: `TradeLedger` store

**Files:**
- Create: `src/shettyxtreme/execution/ledger.py`
- Test: Create `tests/execution/test_trade_ledger.py`

**Interfaces produced (used by Tasks 8–10):**
- `TradeLedger(db_path: str)` — methods `record_fill(fill: dict) -> dict` (idempotent on `order_id`+`source`), `list(session_id: str | None = None, symbol: str | None = None, limit: int = 200) -> list[dict]`, `per_session_summary() -> list[dict]` (`session_id/fills/gross_notional/realized_pnl`), `close()`.
- Module function `pair_fills(fills: list[dict]) -> list[dict]` — FIFO opposite-side pairing per symbol; each pair `{"symbol", "entry_fill", "exit_fill", "quantity", "pnl"}`.

- [ ] **Step 1: Write the failing tests**

```python
import sqlite3
from datetime import UTC, datetime

import pytest

from shettyxtreme.execution.ledger import TradeLedger, pair_fills


def _fill(order_id="O1", source="paper", side="BUY", symbol="NIFTY", qty=75, price=150.0, session="S1"):
    return {
        "fill_id": f"{order_id}:{source}",
        "order_id": order_id,
        "session_id": session,
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "price": price,
        "product": None,
        "source": source,
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def test_record_and_list(tmp_path) -> None:
    store = TradeLedger(str(tmp_path / "l.db"))
    store.record_fill(_fill())
    rows = store.list()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "NIFTY"
    store.record_fill(_fill())  # same order_id+source -> dedup
    assert len(store.list()) == 1
    assert len(store.list(session_id="OTHER")) == 0


def test_per_session_summary_pairing(tmp_path) -> None:
    store = TradeLedger(str(tmp_path / "l.db"))
    store.record_fill(_fill(order_id="O1", side="BUY", price=100.0))
    store.record_fill(_fill(order_id="O2", side="SELL", price=110.0))
    store.record_fill(_fill(order_id="O3", side="BUY", price=200.0))  # unpaired
    summary = store.per_session_summary()
    assert len(summary) == 1
    assert summary[0]["fills"] == 3
    assert summary[0]["realized_pnl"] == 750.0  # (110-100)*75
    assert summary[0]["gross_notional"] == 100.0 * 75 + 110.0 * 75 + 200.0 * 75


def test_pair_fills_long_and_short() -> None:
    fills = [
        _fill(order_id="A", side="SELL", price=200.0, qty=75),
        _fill(order_id="B", side="BUY", price=190.0, qty=75),
    ]
    pairs = pair_fills(fills)
    assert len(pairs) == 1
    assert pairs[0]["pnl"] == 750.0  # short: (entry 200 - exit 190) * 75
```

- [ ] **Step 2:** Run `pytest tests/execution/test_trade_ledger.py -v` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement `src/shettyxtreme/execution/ledger.py`**

```python
"""Trade fill ledger — sqlite recording of order fills (ticket 06).

Mirrors the ResearchStore pattern: single connection, commit per op.
Fills are idempotent on (order_id, source). Realized PnL uses FIFO
pairing of opposite-side fills per symbol (see pair_fills).
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
    fill_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    session_id TEXT,
    symbol TEXT,
    side TEXT,
    quantity INTEGER,
    price REAL,
    product TEXT,
    source TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fills_session ON fills(session_id);
CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
"""


def pair_fills(fills: list[dict]) -> list[dict]:
    """FIFO-pair opposite-side fills per symbol; returns pairs with pnl.

    Long (BUY then SELL): pnl = (exit_price - entry_price) * qty.
    Short (SELL then BUY): pnl = (entry_price - exit_price) * qty.
    Unpaired remainder stays open — no pair emitted.
    """
    pairs: list[dict] = []
    by_symbol: dict[str, list[dict]] = {}
    for fill in sorted(fills, key=lambda f: str(f.get("recorded_at", ""))):
        by_symbol.setdefault(str(fill.get("symbol") or "?"), []).append(fill)
    for group in by_symbol.values():
        queue: list[dict] = []
        for fill in group:
            side = str(fill.get("side", "")).upper()
            if side == "BUY":
                queue.append(fill)
            elif side == "SELL" and queue:
                entry = queue.pop(0)
                qty = min(int(entry["quantity"]), int(fill["quantity"]))
                pnl = (float(fill["price"]) - float(entry["price"])) * qty
                pairs.append(
                    {"symbol": fill.get("symbol"), "entry_fill": entry,
                     "exit_fill": fill, "quantity": qty, "pnl": round(pnl, 4)}
                )
    return pairs


class TradeLedger:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def record_fill(self, fill: dict) -> dict:
        self._conn.execute(
            "INSERT OR IGNORE INTO fills (fill_id, order_id, session_id, symbol, side, "
            "quantity, price, product, source, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fill["fill_id"], fill.get("order_id"), fill.get("session_id"),
                fill.get("symbol"), fill.get("side"), fill.get("quantity"),
                fill.get("price"), fill.get("product"), fill.get("source", "event"),
                fill.get("recorded_at") or datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM fills WHERE fill_id = ?", (fill["fill_id"],)
        ).fetchone()
        return self._row(row)

    @staticmethod
    def _row(row) -> dict:
        return {
            "fill_id": row[0], "order_id": row[1], "session_id": row[2],
            "symbol": row[3], "side": row[4], "quantity": row[5],
            "price": row[6], "product": row[7], "source": row[8], "recorded_at": row[9],
        }

    def list(self, session_id: str | None = None, symbol: str | None = None, limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM fills"
        clauses, params = [], []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        return [self._row(r) for r in self._conn.execute(sql, params).fetchall()]

    def _fills_for(self, session_id: str | None) -> list[dict]:
        if session_id is None:
            return self.list(limit=100000)
        return self.list(session_id=session_id, limit=100000)

    def per_session_summary(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT session_id, COUNT(*), COALESCE(SUM(quantity * price), 0) "
            "FROM fills GROUP BY session_id"
        ).fetchall()
        out = []
        for session_id, count, notional in rows:
            pnl = sum(p["pnl"] for p in pair_fills(self._fills_for(session_id)))
            out.append({
                "session_id": session_id, "fills": int(count),
                "gross_notional": round(float(notional), 4), "realized_pnl": round(pnl, 4),
            })
        return out

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4:** Run tests — PASS. Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(ledger): TradeLedger sqlite store + FIFO fill pairing (ticket 06)"`

### Task 8: `LedgerRecorder` — EventBus subscription

**Files:**
- Create: `src/shettyxtreme/execution/ledger_recorder.py`
- Test: `tests/execution/test_trade_ledger.py` (append)

**Interfaces:** `LedgerRecorder(ledger: TradeLedger, session_id_provider: Callable[[], str | None] | None = None)` with `subscribe(bus: EventBus)`; subscribes `Topic.ORDER_FILLED` (paper fills: `order_id/symbol/side/quantity/price` — full) and `Topic.ORDER_UPDATED` (postbacks: `order_id/status/filled_quantity/average_price` — partial, symbol/side None).

- [ ] **Step 1: Write the failing tests**

```python
from shettyxtreme.core.event_bus.event_bus import Event, Topic
from shettyxtreme.execution.ledger_recorder import LedgerRecorder


@pytest.mark.asyncio
async def test_recorder_captures_paper_fill(tmp_path) -> None:
    ledger = TradeLedger(str(tmp_path / "l.db"))
    rec = LedgerRecorder(ledger, lambda: "S1")
    await rec.on_order_filled(Event(topic=Topic.ORDER_FILLED, data={
        "order_id": "O1", "symbol": "NIFTY", "side": "BUY",
        "quantity": 75, "price": 150.0,
    }, source="paper_trading"))
    rows = ledger.list()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "S1"
    assert rows[0]["source"] == "paper"


@pytest.mark.asyncio
async def test_recorder_ignores_non_fill_postback(tmp_path) -> None:
    ledger = TradeLedger(str(tmp_path / "l.db"))
    rec = LedgerRecorder(ledger)
    await rec.on_order_updated(Event(topic=Topic.ORDER_UPDATED, data={
        "order_id": "O1", "status": "REJECTED", "filled_quantity": 0,
    }, source="postback"))
    assert ledger.list() == []


@pytest.mark.asyncio
async def test_recorder_captures_postback_fill_with_nulls(tmp_path) -> None:
    ledger = TradeLedger(str(tmp_path / "l.db"))
    rec = LedgerRecorder(ledger)
    await rec.on_order_updated(Event(topic=Topic.ORDER_UPDATED, data={
        "order_id": "O1", "status": "FILLED", "filled_quantity": 75, "average_price": 149.5,
    }, source="postback"))
    rows = ledger.list()
    assert len(rows) == 1
    assert rows[0]["symbol"] is None and rows[0]["side"] is None
    assert rows[0]["quantity"] == 75 and rows[0]["price"] == 149.5
```

- [ ] **Step 2:** Run — Expected: FAIL (module missing).
- [ ] **Step 3: Implement `src/shettyxtreme/execution/ledger_recorder.py`**

```python
"""EventBus -> TradeLedger recorder (ticket 06).

Paper fills arrive as ORDER_FILLED (full order details); Dhan postbacks
arrive as ORDER_UPDATED (order_id/status/filled_quantity/average_price —
symbol/side unknowable at this surface, recorded as NULL). Idempotent
via the ledger's (order_id, source) key.
"""
from __future__ import annotations

from collections.abc import Callable

from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.execution.ledger import TradeLedger

_FILLED_STATUSES = {"FILLED", "TRADED", "COMPLETE"}


class LedgerRecorder:
    def __init__(
        self,
        ledger: TradeLedger,
        session_id_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self._ledger = ledger
        self._session_id = session_id_provider or (lambda: None)

    async def on_order_filled(self, event: Event) -> None:
        d = event.data
        self._ledger.record_fill({
            "fill_id": f"{d.get('order_id')}:paper",
            "order_id": d.get("order_id"),
            "session_id": self._session_id(),
            "symbol": d.get("symbol"),
            "side": d.get("side"),
            "quantity": d.get("quantity"),
            "price": d.get("price"),
            "product": d.get("product"),
            "source": "paper",
            "recorded_at": event.timestamp.isoformat(),
        })

    async def on_order_updated(self, event: Event) -> None:
        d = event.data
        status = str(d.get("status", "")).upper()
        qty = d.get("filled_quantity") or 0
        if status not in _FILLED_STATUSES or not qty:
            return
        self._ledger.record_fill({
            "fill_id": f"{d.get('order_id')}:postback",
            "order_id": d.get("order_id"),
            "session_id": self._session_id(),
            "symbol": None,
            "side": None,
            "quantity": int(qty),
            "price": d.get("average_price"),
            "product": None,
            "source": "postback",
            "recorded_at": event.timestamp.isoformat(),
        })

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.ORDER_FILLED, self.on_order_filled)
        bus.subscribe(Topic.ORDER_UPDATED, self.on_order_updated)
```

- [ ] **Step 4:** Run tests — PASS. Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(ledger): LedgerRecorder subscribes ORDER_FILLED + ORDER_UPDATED"`

### Task 9: lifespan wiring + `/api/analytics/ledger`

**Files:**
- Modify: `src/shettyxtreme/terminal/api/app.py` (lifespan: ledger init after `session_log` block ~line 196; close next to `knowledge_store.close()` ~line 289)
- Modify: `src/shettyxtreme/terminal/api/analytics_models.py`
- Modify: `src/shettyxtreme/terminal/api/analytics_router.py`
- Test: `tests/wave9/test_analytics_api.py`, `tests/wave9/test_lifespan_wiring.py`

**Interfaces:** `app.state.trade_ledger` (TradeLedger), `app.state.current_session_id` (str | None); `GET /api/analytics/ledger?session_id=&symbol=&limit=` → `LedgerResponse{fills, sessions}`; `LEDGER_DB_PATH = "data/ledger.db"` module constant on the router.

- [ ] **Step 1: Write the failing tests** — append to `tests/wave9/test_analytics_api.py` (read the file first; reuse its client fixture pattern):

```python
from shettyxtreme.execution.ledger import TradeLedger
from shettyxtreme.terminal.api import analytics_router as ar


@pytest.mark.asyncio
async def test_ledger_empty_and_populated(client, tmp_path, monkeypatch) -> None:
    db = str(tmp_path / "ledger.db")
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", db)
    resp = await client.get("/api/analytics/ledger")
    assert resp.status_code == 200
    assert resp.json()["fills"] == []
    store = TradeLedger(db)
    store.record_fill({"fill_id": "O1:paper", "order_id": "O1", "session_id": "S1",
                       "symbol": "NIFTY", "side": "BUY", "quantity": 75,
                       "price": 100.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T10:00:00Z"})
    store.record_fill({"fill_id": "O2:paper", "order_id": "O2", "session_id": "S1",
                       "symbol": "NIFTY", "side": "SELL", "quantity": 75,
                       "price": 110.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T11:00:00Z"})
    store.close()
    resp2 = await client.get("/api/analytics/ledger")
    body = resp2.json()
    assert len(body["fills"]) == 2
    assert body["sessions"][0]["session_id"] == "S1"
    assert body["sessions"][0]["realized_pnl"] == 750.0
```

Lifespan wiring test — extend `tests/wave9/test_lifespan_wiring.py`: after the app state assertions, add:

```python
assert hasattr(app.state, "trade_ledger")
assert getattr(app.state, "current_session_id", None) is not None
```

- [ ] **Step 2:** Run `pytest tests/wave9/test_analytics_api.py tests/wave9/test_lifespan_wiring.py -v` — Expected: FAIL (no endpoint / no state attrs).
- [ ] **Step 3: Implement** — models in `analytics_models.py`:

```python
class LedgerFillResponse(BaseModel):
    fill_id: str
    order_id: str | None = None
    session_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    quantity: int | None = None
    price: float | None = None
    product: str | None = None
    source: str
    recorded_at: str


class LedgerSessionResponse(BaseModel):
    session_id: str
    fills: int = 0
    gross_notional: float = 0.0
    realized_pnl: float = 0.0


class LedgerResponse(BaseModel):
    fills: list[LedgerFillResponse] = []
    sessions: list[LedgerSessionResponse] = []
```

Endpoint in `analytics_router.py`:

```python
LEDGER_DB_PATH = "data/ledger.db"


@router.get("/ledger", response_model=LedgerResponse)
async def ledger(
    session_id: str | None = None,
    symbol: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> LedgerResponse:
    """Trade fills + per-session aggregates; missing DB -> empty payload."""
    try:
        store = TradeLedger(LEDGER_DB_PATH)
    except Exception as exc:
        logger.warning("Ledger unavailable: %s", exc)
        return LedgerResponse()
    try:
        return LedgerResponse(
            fills=[LedgerFillResponse(**f) for f in store.list(session_id=session_id, symbol=symbol, limit=limit)],
            sessions=[LedgerSessionResponse(**s) for s in store.per_session_summary()],
        )
    except Exception as exc:
        logger.warning("Ledger read failed: %s", exc)
        return LedgerResponse()
    finally:
        store.close()
```

Lifespan wiring in `app.py` (imports + block after `app.state.session_log = session_log`):

```python
from shettyxtreme.execution.ledger import TradeLedger
from shettyxtreme.execution.ledger_recorder import LedgerRecorder
...
    trade_ledger = TradeLedger("data/ledger.db")
    app.state.trade_ledger = trade_ledger
    app.state.current_session_id = _session_id
    _ledger_recorder = LedgerRecorder(
        trade_ledger, lambda: getattr(app.state, "current_session_id", None)
    )
    _ledger_recorder.subscribe(_event_bus)
```

Shutdown: add `trade_ledger.close()` beside `knowledge_store.close()`.

- [ ] **Step 4:** Run tests — PASS. Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(ledger): lifespan wiring + GET /api/analytics/ledger"`

### Task 10: scorecard net-EV + cost metrics

**Files:**
- Modify: `src/shettyxtreme/terminal/api/analytics_router.py` (`scorecard()`)
- Test: `tests/wave9/test_analytics_api.py`

**Interfaces:** Two new scorecard metrics: `fills` (count, unit "fills") and `net_ev_per_session` (float, `available:false` until a session has closed pairs). Cost constant `_COST_PER_FILL = 25.0` (brokerage 20 + slippage 5 — matches `strategy_hints.py` defaults). The AnalyticsPanel renders metrics generically (bool-guard fix in 4B) — no frontend change needed.

- [ ] **Step 1: Write the failing test** (append; reuse the Task 9 populated-ledger pattern):

```python
@pytest.mark.asyncio
async def test_scorecard_net_ev_metrics(client, tmp_path, monkeypatch) -> None:
    db = str(tmp_path / "ledger.db")
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", db)
    store = TradeLedger(db)
    store.record_fill({"fill_id": "O1:paper", "order_id": "O1", "session_id": "S1",
                       "symbol": "NIFTY", "side": "BUY", "quantity": 75,
                       "price": 100.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T10:00:00Z"})
    store.record_fill({"fill_id": "O2:paper", "order_id": "O2", "session_id": "S1",
                       "symbol": "NIFTY", "side": "SELL", "quantity": 75,
                       "price": 110.0, "product": None, "source": "paper",
                       "recorded_at": "2026-08-02T11:00:00Z"})
    store.close()
    resp = await client.get("/api/analytics/scorecard")
    metrics = {m["key"]: m for m in resp.json()["metrics"]}
    assert metrics["fills"]["value"] == 2
    assert metrics["fills"]["available"] is True
    assert metrics["net_ev_per_session"]["available"] is True
    assert metrics["net_ev_per_session"]["value"] == 750.0 - 2 * 25.0


@pytest.mark.asyncio
async def test_scorecard_net_ev_unavailable_empty(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", str(tmp_path / "empty_ledger.db"))
    resp = await client.get("/api/analytics/scorecard")
    metrics = {m["key"]: m for m in resp.json()["metrics"]}
    assert metrics["fills"]["available"] is False
    assert metrics["net_ev_per_session"]["available"] is False
```

- [ ] **Step 2:** Run — Expected: FAIL (metrics missing).
- [ ] **Step 3: Implement** — add `_COST_PER_FILL = 25.0` constant; in `scorecard()` after the `avg_confidence` metric append block:

```python
    fills_total = 0
    net_ev: float | None = None
    try:
        lstore = TradeLedger(LEDGER_DB_PATH)
        try:
            session_rows = lstore.per_session_summary()
            fills_total = sum(s["fills"] for s in session_rows)
            closed = [s for s in session_rows if s["realized_pnl"] != 0.0]
            if closed:
                net_ev = round(
                    sum(s["realized_pnl"] for s in closed) - fills_total * _COST_PER_FILL,
                    4,
                )
        finally:
            lstore.close()
    except Exception as exc:
        logger.warning("Ledger stats unavailable: %s", exc)
    metrics.append(
        _metric(
            "fills",
            "Fills recorded",
            fills_total,
            fills_total > 0,
            note=None if fills_total > 0 else "Recorded automatically from order fills (paper + postback).",
            unit="fills",
        )
    )
    metrics.append(
        _metric(
            "net_ev_per_session",
            "Net EV per session",
            net_ev,
            net_ev is not None,
            note=None
            if net_ev is not None
            else "Needs closed fill pairs (entry+exit) in the ledger.",
        )
    )
```

- [ ] **Step 4:** Run tests — PASS. Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(analytics): fills + net-EV-per-session scorecard metrics (ticket 06)"`

---

## Track C — Knowledge v2

### Task 11: operator-note ingest (`knowledge/notes.py`)

**Files:**
- Create: `src/shettyxtreme/knowledge/notes.py`
- Test: Create `tests/wave9/test_knowledge_notes.py`

**Interfaces produced:** `ingest_note(store: KnowledgeStore, title: str, body: str, source_ref: str | None = None) -> KnowledgeDoc` — kind `operator_note`, status `proposed` (same human-activation gate as briefs), tags via `tag_document(title + " " + body)`. D12: imports only `core/` + the knowledge package.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from shettyxtreme.knowledge.notes import ingest_note
from shettyxtreme.knowledge.store import DuplicateSourceError, KnowledgeStore


def test_ingest_note_tags_and_defaults_proposed(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    doc = ingest_note(
        store, "NIFTY breakout",
        "NIFTY trending up with elevated iv near resistance", source_ref="note-1",
    )
    assert doc.kind == "operator_note"
    assert doc.status == "proposed"
    tags = {t["tag"] for t in doc.tags}
    assert "NIFTY" in tags
    assert "trending_up" in tags
    assert "ELEVATED_IV" in tags
    got = store.get("note-1")
    assert got is not None and got.payload["title"] == "NIFTY breakout"


def test_ingest_note_generates_source_ref(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    doc = ingest_note(store, "T", "body text")
    assert doc.doc_id.startswith("note-")


def test_ingest_note_duplicate_ref_raises(tmp_path) -> None:
    store = KnowledgeStore(str(tmp_path / "k.db"))
    ingest_note(store, "T", "b", source_ref="dup")
    with pytest.raises(DuplicateSourceError):
        ingest_note(store, "T2", "b2", source_ref="dup")
```

- [ ] **Step 2:** Run — Expected: FAIL (module missing).
- [ ] **Step 3: Implement `src/shettyxtreme/knowledge/notes.py`**

```python
"""Operator-note ingestion into the knowledge store (knowledge v2).

D12: `knowledge/` imports core ONLY — notes are tagged heuristically and
stored as `proposed`; they become a research source only after the same
human activation gate as briefs. No LLM anywhere (D3).
"""
from __future__ import annotations

from uuid import uuid4

from .schemas import KnowledgeDoc
from .store import KnowledgeStore
from .tagger import tag_document


def ingest_note(
    store: KnowledgeStore,
    title: str,
    body: str,
    source_ref: str | None = None,
) -> KnowledgeDoc:
    """Tag and ingest an operator-written note; returns the stored doc."""
    ref = source_ref or f"note-{uuid4().hex[:12]}"
    text = f"{title} {body}".strip()
    doc = KnowledgeDoc(
        doc_id=ref,
        kind="operator_note",
        source_ref=ref,
        payload={"title": title, "body": body},
        tags=tag_document(text),
    )
    return store.ingest(doc)
```

- [ ] **Step 4:** Run tests — PASS (verify `KnowledgeDoc` accepts these kwargs and default `status` is `proposed`; if the schema requires `status` explicitly, pass `status="proposed"`). Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(knowledge): operator-note ingest (knowledge v2)"`

### Task 12: `/api/knowledge/notes` endpoint

**Files:**
- Modify: `src/shettyxtreme/terminal/api/knowledge_models.py`, `src/shettyxtreme/terminal/api/knowledge_router.py`
- Test: `tests/wave9/test_knowledge_api.py`

**Interfaces:** `KnowledgeNoteRequest{title: str (1..200), body: str (0..5000)}`; `POST /api/knowledge/notes` → `KnowledgeDocResponse` (200; 422 for empty title; 500 degrade on store failure, mirroring `activate`).

- [ ] **Step 1: Write the failing tests** (read `tests/wave9/test_knowledge_api.py` first; reuse its client fixture; isolate DB per test):

```python
@pytest.mark.asyncio
async def test_create_note_ingests_proposed(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(kr, "_STORE", None)
    resp = await client.post("/api/knowledge/notes", json={
        "title": "NIFTY setup", "body": "NIFTY trending up, elevated iv",
    })
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["kind"] == "operator_note"
    assert doc["status"] == "proposed"
    tags = {t["tag"] for t in doc["tags"]}
    assert "NIFTY" in tags and "trending_up" in tags


@pytest.mark.asyncio
async def test_create_note_empty_title_422(client) -> None:
    resp = await client.post("/api/knowledge/notes", json={"title": "", "body": "x"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_note_activate_flow(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(kr, "_STORE", None)
    created = (await client.post("/api/knowledge/notes", json={
        "title": "T", "body": "range bound NIFTY",
    })).json()
    activated = await client.post(f"/api/knowledge/docs/{created['doc_id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "activated"
```

(`kr` = the imported knowledge_router module; `monkeypatch.setattr(kr, "_STORE", None)` forces the router's `_store()` to open the test-path DB if `_store()` uses a default path — check `knowledge_router._store()` behavior and patch `_STORE` to a `KnowledgeStore(tmp_path)` directly if needed.)

- [ ] **Step 2:** Run — Expected: FAIL (endpoint missing → 404/405).
- [ ] **Step 3: Implement** — model in `knowledge_models.py`:

```python
from pydantic import BaseModel, Field


class KnowledgeNoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=0, max_length=5000)
```

Endpoint in `knowledge_router.py` (import `ingest_note`):

```python
@router.post("/notes", response_model=KnowledgeDocResponse)
async def create_note(req: KnowledgeNoteRequest) -> KnowledgeDocResponse:
    """Ingest an operator note (proposed; activate to make it a research source)."""
    try:
        doc = ingest_note(_store(), req.title, req.body)
    except Exception as exc:
        logger.warning("Knowledge note failed: %s", exc)
        raise HTTPException(status_code=500, detail="note ingest failed") from exc
    return _doc_response(doc)
```

- [ ] **Step 4:** Run tests — PASS. Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(knowledge): POST /api/knowledge/notes (operator notes)"`

### Task 13: tag refinement — symbol aliases + deterministic order

**Files:**
- Modify: `src/shettyxtreme/core/knowledge/lexicons.py`, `src/shettyxtreme/knowledge/tagger.py`
- Test: `tests/wave9/test_knowledge_lexicons.py`, `tests/wave9/test_knowledge_tagger.py`

**Interfaces:** `SYMBOL_ALIASES: dict[str, str]` in lexicons; `normalize_symbol` maps aliases to canonical symbols; `tag_document` returns tags sorted by `(kind, tag)`.

- [ ] **Step 1: Write the failing tests**

```python
# test_knowledge_lexicons.py
from shettyxtreme.core.knowledge.lexicons import normalize_symbol


def test_normalize_symbol_alias_maps_to_canonical() -> None:
    assert normalize_symbol("BNF") == "BANKNIFTY"
    assert normalize_symbol("BANK") == "BANKNIFTY"
    assert normalize_symbol("MIDCAP") == "MIDCPNIFTY"
    assert normalize_symbol("NIFTY") == "NIFTY"
    assert normalize_symbol("BANKNIFTY") == "BANKNIFTY"
```

```python
# test_knowledge_tagger.py
from shettyxtreme.knowledge.tagger import tag_document


def test_tag_document_uses_aliases() -> None:
    tags = tag_document("BNF trending up with tail risk")
    keys = {(t["tag"], t["kind"]) for t in tags}
    assert ("BANKNIFTY", "symbol") in keys


def test_tag_document_sorted_deterministic() -> None:
    a = tag_document("NIFTY expiry event risk, NIFTY trending up")
    b = tag_document("NIFTY expiry event risk, NIFTY trending up")
    assert a == b
    kinds = [t["kind"] for t in a]
    assert kinds == sorted(kinds)
```

- [ ] **Step 2:** Run — Expected: FAIL (no alias, unstable order).
- [ ] **Step 3: Implement** — in `lexicons.py` add after `NSE_SYMBOLS`:

```python
# Common colloquial tokens -> canonical symbols (disambiguation at tag time).
SYMBOL_ALIASES: dict[str, str] = {
    "BANK": "BANKNIFTY",
    "BNF": "BANKNIFTY",
    "FIN": "FINNIFTY",
    "MIDCAP": "MIDCPNIFTY",
    "NIFTYNEXT50": "NIFTYNXT50",
}
```

and in `normalize_symbol`, after the prefix strip and before the stopword check:

```python
candidate = SYMBOL_ALIASES.get(candidate, candidate)
```

In `tagger.py`, change the final return to sorted:

```python
return sorted(
    [{"tag": tag, "kind": kind} for (tag, kind) in tags],
    key=lambda t: (t["kind"], t["tag"]),
)[:_MAX_TAGS]
```

- [ ] **Step 4:** Run both test files — PASS. Full suite.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(knowledge): symbol aliases + deterministic tag order (tag refinement)"`

### Task 14: KnowledgePanel note composer

**Files:**
- Modify: `src/shettyxtreme/terminal/web/src/components/KnowledgePanel.svelte`
- Modify: `src/shettyxtreme/terminal/web/src/lib/api.ts` (add `KnowledgeNoteRequest` interface)

**Interfaces:** `postBody<T>(url, body)` from `../lib/api` (verify its exact signature in `api.ts` first — Step 1).

- [ ] **Step 1:** Read `src/shettyxtreme/terminal/web/src/lib/api.ts` to confirm the `postBody` signature; adjust the snippet if named differently.
- [ ] **Step 2: Implement the script additions** (after `syncResult`):

```ts
let noteTitle = "";
let noteBody = "";
let saving = false;

async function saveNote(): Promise<void> {
  if (saving || !noteTitle.trim()) return;
  saving = true;
  error = "";
  try {
    await postBody<KnowledgeDoc>("/api/knowledge/notes", {
      title: noteTitle.trim(),
      body: noteBody,
    });
    noteTitle = "";
    noteBody = "";
    await loadStatus();
    await search();
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  } finally {
    saving = false;
  }
}
```

and the markup between the controls row and `{#if syncResult}`:

```svelte
<div class="note-box">
  <input class="query mono" type="text" placeholder="Note title…" bind:value={noteTitle} />
  <textarea class="note-body mono" rows="2" placeholder="Note body — symbols/regimes auto-tagged…" bind:value={noteBody}></textarea>
  <button class="run-btn" on:click={saveNote} disabled={saving || !noteTitle.trim()}>
    {saving ? "Saving…" : "Save note"}
  </button>
</div>
```

plus a `.note-box` style (flex column, gap 6px, padding 8px 10px, `border-bottom: 1px solid var(--hairline)`) and `.note-body { background: var(--surface); border: 1px solid var(--hairline); border-radius: 4px; color: var(--body); font-size: 11px; padding: 4px 6px; resize: vertical; }` — DESIGN.md tokens only.

- [ ] **Step 3:** `npm run check` — 0 errors (expect the existing 2 a11y warnings, repo baseline).
- [ ] **Step 4:** `npm run build` — bundle regenerated; run `git status` and confirm `terminal/static/` artifacts changed.
- [ ] **Step 5: Commit** `git add -A; git commit -m "feat(web): KnowledgePanel operator-note composer (knowledge v2)"`

---

## Track D — Docs + release

### Task 15: CHANGELOG, roadmap, version bump (user gate)

**Files:**
- Modify: `CHANGELOG.md`, `docs/architecture/v2/sections/17-delivery-roadmap.md`, `README.md`
- Version drift files (user approved bump to 0.11.0): `src/shettyxtreme/__init__.py`, `src/shettyxtreme/terminal/api/app.py`, `pyproject.toml`, `src/shettyxtreme/terminal/web/package.json`

- [ ] **Step 1:** Update `17-delivery-roadmap.md` — change row 1 `Blueprint + design contract | **CURRENT**` to `**DONE (2026-08-01)**`.
- [ ] **Step 2:** Add CHANGELOG `## [2026-08-02] — v0.11.0` entry summarizing the three tracks (final suite count; grep gate; note the ledger's `available:false`-until-data scorecard semantics and the postback partial-fill NULLs).
- [ ] **Step 3:** README roadmap: add a line under the Phase 4 row noting post-Phase-4 work (trades ledger, knowledge v2).
- [ ] **Step 4:** Version bump to 0.11.0 in the 4 code files listed above (CHANGELOG already gets the 0.11.0 header).
- [ ] **Step 5: Commit** `git add -A; git commit -m "docs: v0.11.0 changelog + roadmap Phase 1 status fix + version bump"`

---

## Gates (after every task AND at the end)

1. Full suite: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase5 -p no:cacheprovider` — must not shrink below 703, 0 skipped.
2. Grep gate: `rg -c "import openalgo|from openalgo" src/shettyxtreme/` → zero matches.
3. Line gate: no new file > 500 lines (ledger.py is ~110, notes.py ~40 — fine).
4. `svelte-check` 0 errors (Track C task 14).
5. D12 check: `knowledge/` imports only `core` + sibling modules (`rg "^from shettyxtreme" src/shettyxtreme/knowledge/` shows only `core` + knowledge).
6. Code review via code-reviewer subagent after each track, before merge.

## Execution order

- Wave 1 (parallel, disjoint ownership): Track A subagent (Tasks 1–6) ∥ Track B subagent (Tasks 7–10) ∥ Track C subagent (Tasks 11–14). Each runs its own pytest basetemp; coordinator reviews + commits.
- Wave 2: Task 15 (docs/release) + full-suite gate + final code review.
- Task 0 (smoke) can run any time before release.

## Self-review notes

- **Spec coverage:** all deferred minors from the Phase-4 handoff §4/§5 are mapped to tasks; ticket 06 (ledger/net-EV) → Tasks 7–10; knowledge v2 (operator-notes, tag refinement) → Tasks 11–14; roadmap stale marker → Task 15. **Already-resolved items excluded** (verified in code): 806 ent-chip exists in Header.svelte:92, `_fetch_chain_with_spot` is live (only the old `_fetch_chain` died), `strike_price` alias handled in strategy_hints.py:154, polyline-vs-step is a documented deliberate deviation.
- **Placeholder scan:** every code step contains real test/implementation code.
- **Type consistency:** `TradeLedger.record_fill` accepts the dicts built by `LedgerRecorder` (same keys); `per_session_summary`/`pair_fills` shapes match the router/scorecard consumers; `LedgerResponse`/`LedgerSessionResponse` names consistent across Task 9–10.
- **Deferred deliberately:** net-EV stays `available:false` until paired fills exist (honesty convention — never fabricate); postback fills record NULL symbol/side (documented).
