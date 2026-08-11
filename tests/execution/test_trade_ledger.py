import logging
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
    # Legacy NULL-symbol rows stay in the count/notional but are never paired:
    # the summary pairs only rows WHERE symbol IS NOT NULL, so they can never
    # phantom-pair cross-symbol fills (the pair_fills regression test covers
    # the ERROR log when NULL-symbol fills reach pairing directly).
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


def test_pair_fills_requeues_partial_remainders() -> None:
    """F-KNOW-005: a partial close leaves the entry remainder queued.

    The 30-qty SELL only closes part of the 75-qty BUY; the remaining 45 must
    pair against the next SELL instead of being silently dropped.
    """
    fills = [
        _fill(order_id="A", side="BUY", price=100.0, qty=75),
        _fill(order_id="B", side="SELL", price=110.0, qty=30),
        _fill(order_id="C", side="SELL", price=112.0, qty=45),
    ]
    pairs = pair_fills(fills)
    assert len(pairs) == 2
    assert pairs[0]["quantity"] == 30
    assert pairs[0]["pnl"] == (110.0 - 100.0) * 30
    assert pairs[1]["quantity"] == 45
    assert pairs[1]["pnl"] == (112.0 - 100.0) * 45
    # The remainder came from the SAME entry fill (A), FIFO-preserved.
    assert pairs[1]["entry_fill"]["order_id"] == "A"


def test_pair_fills_remainder_carries_to_next_opposite() -> None:
    """F-KNOW-005: an oversized close re-queues its own remainder short.

    The 100-qty SELL closes the 75-qty BUY and leaves a 25-qty short that the
    next BUY must close — under the old code the 25-qty remainder vanished.
    """
    fills = [
        _fill(order_id="A", side="BUY", price=100.0, qty=75),
        _fill(order_id="B", side="SELL", price=110.0, qty=100),
        _fill(order_id="C", side="BUY", price=108.0, qty=25),
    ]
    pairs = pair_fills(fills)
    assert len(pairs) == 2
    assert pairs[0]["quantity"] == 75
    assert pairs[0]["pnl"] == (110.0 - 100.0) * 75
    assert pairs[1]["quantity"] == 25
    assert pairs[1]["pnl"] == round((110.0 - 108.0) * 25, 4)  # short close: entry - exit
    assert pairs[1]["entry_fill"]["order_id"] == "B"


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
async def test_recorder_resolves_symbol_for_postback_fill(tmp_path) -> None:
    ledger = TradeLedger(str(tmp_path / "l.db"))
    rec = LedgerRecorder(ledger)
    # Original paper fill creates the order-id with a known symbol...
    await rec.on_order_filled(Event(topic=Topic.ORDER_FILLED, data={
        "order_id": "O1", "symbol": "NIFTY", "side": "BUY",
        "quantity": 75, "price": 150.0,
    }, source="paper_trading"))
    # ...then the Dhan postback for the same order-id resolves to NIFTY.
    await rec.on_order_updated(Event(topic=Topic.ORDER_UPDATED, data={
        "order_id": "O1", "status": "FILLED", "filled_quantity": 75, "average_price": 149.5,
    }, source="postback"))
    rows = ledger.list()
    assert len(rows) == 2
    postback = next(r for r in rows if r["source"] == "postback")
    assert postback["symbol"] == "NIFTY"  # resolved, never NULL
    assert postback["side"] is None
    assert postback["quantity"] == 75 and postback["price"] == 149.5


@pytest.mark.asyncio
async def test_recorder_skips_postback_for_unknown_order(tmp_path, caplog) -> None:
    ledger = TradeLedger(str(tmp_path / "l.db"))
    rec = LedgerRecorder(ledger)
    with caplog.at_level(logging.WARNING, logger="shettyxtreme.execution.ledger_recorder"):
        await rec.on_order_updated(Event(topic=Topic.ORDER_UPDATED, data={
            "order_id": "UNKNOWN", "status": "FILLED", "filled_quantity": 75,
            "average_price": 149.5,
        }, source="postback"))
    assert ledger.list() == []  # unresolvable postback is not recorded
    assert any("postback fill skipped" in r.message for r in caplog.records)


def test_pair_fills_never_phantom_pairs_cross_symbol_same_order(tmp_path, caplog) -> None:
    """Regression: F-KNOW-001 — same order-id, conflicting symbols must not pair.

    Simulates the old bug: a NULL-symbol postback (symbol never resolved)
    sitting next to the original paper fill for the same order-id. Under the
    old "?" catch-all these bucketed together and phantom-paired; now the
    NULL-symbol fill is dropped with an ERROR and no pair is emitted.
    """
    store = TradeLedger(str(tmp_path / "l.db"))
    store.record_fill(_fill(order_id="O1", source="paper", symbol="NIFTY",
                            side="BUY", price=100.0))
    store.record_fill(_fill(order_id="O1", source="postback", symbol=None,
                            side="SELL", price=110.0))  # legacy unresolved postback
    fills = store.list()
    with caplog.at_level(logging.ERROR, logger="shettyxtreme.execution.ledger"):
        pairs = pair_fills(fills)
    assert pairs == []  # NIFTY buy stays open; unresolved postback excluded
    assert any("NULL-symbol" in r.message for r in caplog.records)

    # Distinct resolved symbols never cross-pair either.
    other = TradeLedger(str(tmp_path / "other.db"))
    other.record_fill(_fill(order_id="O9", source="paper", symbol="NIFTY",
                            side="BUY", price=100.0))
    other.record_fill(_fill(order_id="O9", source="postback", symbol="BANKNIFTY",
                            side="SELL", price=110.0))
    assert pair_fills(other.list()) == []
