"""Outcome tracking — record signal decisions, execution attempts, and outcomes.

Stores decisions in a SQLite database so results can be analyzed later by the
learning loop. Designed to be additive: does not import anything from
intelligence/ or execution/.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from shettyxtreme.core.data_models.orders import Order
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
    Vote,
)


class OutcomeLabel(Enum):
    """Outcome of a signal decision."""

    WIN = "win"
    LOSS = "loss"
    NEUTRAL = "neutral"
    EXPIRED = "expired"
    UNREALIZED = "unrealized"


@dataclass
class SignalDecision:
    """A recorded signal decision and its lifecycle metadata."""

    id: str
    signal: Signal
    timestamp: datetime
    strategy_hint: dict | None = None
    execution_attempts: list = None  # type: ignore[assignment]
    outcome: OutcomeLabel | None = None


def _serialize_signal(signal: Signal) -> str:
    """Serialize a Signal to a JSON string."""
    data = asdict(signal)
    data["direction"] = signal.direction.value
    return json.dumps(data, default=str)


def _deserialize_signal(raw: str) -> Signal:
    """Reconstruct a Signal from a JSON string."""
    data = json.loads(raw)
    dir_val = data["direction"]
    if isinstance(dir_val, str) and dir_val.startswith("SignalDirection."):
        dir_val = dir_val.split(".", 1)[1].lower()
    data["direction"] = SignalDirection(dir_val)
    voters = []
    for v in data.get("voters", []):
        voters.append(
            Vote(
                direction=float(v["direction"]),
                confidence=float(v["confidence"]),
                weight=float(v["weight"]),
                name=str(v["name"]),
            )
        )
    data["voters"] = voters
    ts = data.get("timestamp")
    data["timestamp"] = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
    return Signal(**data)


class OutcomeTracker:
    """Persist signal decisions, execution attempts, and outcomes."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_decisions (
                id TEXT PRIMARY KEY,
                signal_json TEXT,
                timestamp TEXT,
                strategy_hint TEXT,
                outcome TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_attempts (
                id TEXT PRIMARY KEY,
                decision_id TEXT,
                order_json TEXT
            )
            """
        )
        self._conn.commit()

    def record_signal_decision(
        self, signal: Signal, strategy_hint: dict | None = None
    ) -> str:
        """Store a new signal decision. Returns the decision id."""
        decision_id = uuid4().hex
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO signal_decisions "
            "(id, signal_json, timestamp, strategy_hint, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                decision_id,
                _serialize_signal(signal),
                signal.timestamp.isoformat(),
                json.dumps(strategy_hint, default=str)
                if strategy_hint is not None
                else None,
                None,
            ),
        )
        self._conn.commit()
        return decision_id

    def record_execution_attempt(self, decision_id: str, order: Order) -> str:
        """Record an execution attempt for a decision. Returns attempt id."""
        attempt_id = uuid4().hex
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO execution_attempts (id, decision_id, order_json) "
            "VALUES (?, ?, ?)",
            (attempt_id, decision_id, json.dumps(asdict(order), default=str)),
        )
        self._conn.commit()
        return attempt_id

    def record_outcome(self, decision_id: str, outcome: OutcomeLabel) -> None:
        """Record the outcome for a decision.

        Raises ValueError if an outcome was already recorded for this decision.
        """
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT outcome FROM signal_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown decision_id: {decision_id}")
        if row["outcome"] is not None:
            raise ValueError(
                f"Outcome already recorded for decision {decision_id}: "
                f"{row['outcome']}"
            )
        cur.execute(
            "UPDATE signal_decisions SET outcome = ? WHERE id = ?",
            (outcome.value, decision_id),
        )
        self._conn.commit()

    def get_decision(self, decision_id: str) -> SignalDecision | None:
        """Return the SignalDecision for an id, or None."""
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT * FROM signal_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_decision(row)

    def get_decisions_by_date(self, day: date) -> list[SignalDecision]:
        """Return all decisions whose timestamp falls on the given date."""
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT * FROM signal_decisions WHERE DATE(timestamp) = ? "
            "ORDER BY timestamp",
            (day.isoformat(),),
        ).fetchall()
        return [self._row_to_decision(r) for r in rows]

    def _row_to_decision(self, row: sqlite3.Row) -> SignalDecision:
        attempts = self._attempts_for(row["id"])
        hint = (
            json.loads(row["strategy_hint"])
            if row["strategy_hint"] is not None
            else None
        )
        outcome = (
            OutcomeLabel(row["outcome"]) if row["outcome"] is not None else None
        )
        return SignalDecision(
            id=row["id"],
            signal=_deserialize_signal(row["signal_json"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            strategy_hint=hint,
            execution_attempts=attempts,
            outcome=outcome,
        )

    def _attempts_for(self, decision_id: str) -> list:
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT order_json FROM execution_attempts WHERE decision_id = ?",
            (decision_id,),
        ).fetchall()
        return [json.loads(r["order_json"]) for r in rows]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
