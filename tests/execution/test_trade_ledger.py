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


def test_per_session_summary_ignores_nullsymbol_fills_for_pairing(tmp_path) -> None:
    store = TradeLedger(str(tmp_path / "l.db"))
    store.record_fill(_fill(order_id="O1", side="BUY", price=100.0, symbol=None))
    store.record_fill(_fill(order_id="O2", side="SELL", price=110.0, symbol=None))
    store.record_fill(_fill(order_id="O3", side="BUY", price=200.0))
    summary = store.per_session_summary()
    assert len(summary) == 1
    assert summary[0]["fills"] == 3
    assert summary[0]["realized_pnl"] == 0.0  # NULL-symbol fills never pair
    assert summary[0]["gross_notional"] == 100.0 * 75 + 110.0 * 75 + 200.0 * 75


def test_pair_fills_long_and_short() -> None:
    fills = [
        _fill(order_id="A", side="SELL", price=200.0, qty=75),
        _fill(order_id="B", side="BUY", price=190.0, qty=75),
    ]
    pairs = pair_fills(fills)
    assert len(pairs) == 1
    assert pairs[0]["pnl"] == 750.0  # short: (entry 200 - exit 190) * 75


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
