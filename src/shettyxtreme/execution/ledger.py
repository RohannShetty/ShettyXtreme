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
        longs: list[dict] = []
        shorts: list[dict] = []
        for fill in group:
            side = str(fill.get("side", "")).upper()
            if side == "BUY":
                if shorts:
                    entry = shorts.pop(0)
                    qty = min(int(entry["quantity"]), int(fill["quantity"]))
                    pnl = (float(entry["price"]) - float(fill["price"])) * qty
                    pairs.append(
                        {"symbol": fill.get("symbol"), "entry_fill": entry,
                         "exit_fill": fill, "quantity": qty, "pnl": round(pnl, 4)}
                    )
                else:
                    longs.append(fill)
            elif side == "SELL":
                if longs:
                    entry = longs.pop(0)
                    qty = min(int(entry["quantity"]), int(fill["quantity"]))
                    pnl = (float(fill["price"]) - float(entry["price"])) * qty
                    pairs.append(
                        {"symbol": fill.get("symbol"), "entry_fill": entry,
                         "exit_fill": fill, "quantity": qty, "pnl": round(pnl, 4)}
                    )
                else:
                    shorts.append(fill)
    return pairs


class TradeLedger:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.executescript(_SCHEMA)
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
