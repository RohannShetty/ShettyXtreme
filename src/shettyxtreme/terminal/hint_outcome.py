"""Hint outcome recording helpers (3A.2) — win/loss scoring on position close.

Moved out of projections.py (god-module guard) and called by
PositionProjection when a position update closes a position. The hint store
only accepts the first outcome per hint, so repeated close events never
double-count.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def maybe_record_hint_outcome(
    hint_store: Any,
    raw: dict[str, Any],
    pos: dict[str, Any],
) -> None:
    """Record the outcome for a matching hint when this position closes.

    A position counts as closed when the event says so explicitly
    (status CLOSED) or its quantity/net_quantity has flattened to zero.
    The outcome is ``win`` when the actual PnL is positive, else
    ``loss``. Recording is best-effort and idempotent. Requires a hint
    store attached via ``set_hint_store``; otherwise this is a no-op.
    """
    if hint_store is None:
        return
    if not is_closed(raw):
        return
    symbol = str(pos.get("symbol", ""))
    if not symbol:
        return
    pnl = close_pnl(raw, pos)
    outcome = "win" if pnl > 0 else "loss"
    for direction in closing_directions(raw, pos):
        try:
            hint_id = hint_store.find_hint(symbol, direction)
        except Exception:
            logger.debug(
                "hint lookup failed for %s/%s", symbol, direction, exc_info=True,
            )
            continue
        if hint_id is None:
            continue
        try:
            hint_store.record_outcome(hint_id, outcome, pnl)
        except Exception:
            logger.debug(
                "hint outcome recording failed for %s", symbol, exc_info=True,
            )
        return  # first matching hint wins


def is_closed(raw: dict[str, Any]) -> bool:
    """True when the event explicitly reports a closed/flat position."""
    if str(raw.get("status", "")).upper() == "CLOSED":
        return True
    if raw.get("net_quantity") is not None and int(raw.get("net_quantity", 0)) == 0:
        return True
    if raw.get("quantity") is not None and int(raw.get("quantity", 0)) == 0:
        return True
    return False


def closing_directions(raw: dict[str, Any], pos: dict[str, Any]) -> list[str]:
    """Candidate hint directions for a closing position.

    A closing fill's side is the *opposite* of the position's side
    (SELL closes a long → bullish hint; BUY closes a short → bearish
    hint). Falls back to the net-quantity sign, then to both
    directions when the event carries no directional signal.
    """
    side = str(raw.get("side", "")).upper()
    candidates: list[str] = []
    if side == "SELL":
        candidates.append("bullish")  # closing a long
    elif side == "BUY":
        candidates.append("bearish")  # closing a short
    net = int(pos.get("net_quantity", 0) or 0)
    if net > 0:
        candidates.append("bullish")
    elif net < 0:
        candidates.append("bearish")
    if not candidates:
        candidates = ["bullish", "bearish"]
    return list(dict.fromkeys(candidates))


def close_pnl(raw: dict[str, Any], pos: dict[str, Any]) -> float:
    """Actual PnL from the close event; 0.0 when absent/junk."""
    pnl = raw.get("pnl", pos.get("pnl"))
    try:
        return float(pnl or 0.0)
    except (TypeError, ValueError):
        return 0.0
