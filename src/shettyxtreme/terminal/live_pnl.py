"""Live P&L tracker (P4) — tick-driven mark-to-market for open positions.

PositionProjection feeds this tracker LTPs and position dicts; the tracker
owns the debounce state and the m2m/pnl math but no position state. Two
gates prevent tick storms from flooding the event loop or the WS socket:

  * time — at most one recompute per symbol per ``debounce_seconds``
  * noise — LTP moves below ``ltp_epsilon`` (relative) are ignored

The math mirrors the paper engine: long positions mark against ``buy_avg``,
shorts against ``sell_avg`` (falling back to ``buy_avg``). When an entry
price is missing the position is left untouched — a number that cannot be
computed honestly is never fabricated.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class LivePnlTracker:
    """Per-symbol LTP cache + debounced mark-to-market math."""

    def __init__(
        self,
        debounce_seconds: float = 1.0,
        ltp_epsilon: float = 0.01,
    ) -> None:
        self.debounce_seconds = debounce_seconds
        self.ltp_epsilon = ltp_epsilon
        self._ltp: dict[str, float] = {}
        self._last_recompute_ts: dict[str, float] = {}

    def note_tick(self, symbol: str, ltp: float) -> float | None:
        """Record an LTP; return the LTP when a recompute is warranted.

        Returns None when the tick is noise (sub-epsilon move) or arrives
        inside the debounce window — callers then skip recompute/broadcast.
        The LTP is cached either way so fresh fills can mark immediately.
        """
        prev = self._ltp.get(symbol)
        self._ltp[symbol] = ltp
        if prev is None:
            # First tick for this symbol — always mark, and record the
            # recompute time so a follow-up tick inside the window is gated.
            self._last_recompute_ts[symbol] = time.monotonic()
            return ltp
        if abs(ltp - prev) / max(prev, 1e-9) < self.ltp_epsilon:
            return None
        now = time.monotonic()
        if now - self._last_recompute_ts.get(symbol, -float("inf")) < self.debounce_seconds:
            return None
        self._last_recompute_ts[symbol] = now
        return ltp

    def last_ltp(self, symbol: str) -> float | None:
        """Most recently seen LTP for a symbol (None when never seen)."""
        return self._ltp.get(symbol)

    def apply_m2m(self, pos: dict[str, Any], ltp: float) -> bool:
        """Mark-to-market one position dict from an LTP.

        Long:  m2m = qty * (ltp - buy_avg)
        Short: m2m = |qty| * (entry - ltp), entry = sell_avg or buy_avg
        Flat:  m2m = 0 (realized pnl untouched)

        The unrealized swing is folded into ``pnl`` (realized P&L is
        preserved: pnl = old_pnl + (new_m2m - old_m2m)). Returns True when
        the position values changed, False when the entry price was missing
        (position left untouched).
        """
        qty = int(pos.get("net_quantity", 0) or 0)
        if qty == 0:
            pos["m2m"] = 0.0
            return True
        buy_avg = float(pos.get("buy_avg", 0.0) or 0.0)
        if qty > 0:
            if buy_avg <= 0:
                return False
            new_m2m = qty * (ltp - buy_avg)
        else:
            entry = float(pos.get("sell_avg", 0.0) or 0.0) or buy_avg
            if entry <= 0:
                return False
            new_m2m = abs(qty) * (entry - ltp)
        old_m2m = float(pos.get("m2m", 0.0) or 0.0)
        pos["m2m"] = round(new_m2m, 2)
        old_pnl = float(pos.get("pnl", 0.0) or 0.0)
        pos["pnl"] = round(old_pnl + (new_m2m - old_m2m), 2)
        return True
