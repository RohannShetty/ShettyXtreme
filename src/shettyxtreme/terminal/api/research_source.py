"""Default research DataSource — renders live app.state into tool text.

Best-effort per spec §3.1: summaries are composed from whatever live
state exists; anything unavailable renders None (the tool layer turns
that into [UNSOURCED]). research/ never imports terminal/ — this module
implements the DataSource protocol, not the other way around.
"""
from __future__ import annotations

from typing import Any


class ProjectionDataSource:
    """DataSource backed by the running app's projections."""

    def __init__(self, app_state: Any) -> None:
        self._state = app_state

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

    def regime_summary(self) -> str | None:
        proj = getattr(self._state, "intelligence_projection", None)
        if proj is None:
            return None
        try:
            regime = proj.get_regime() or {}
            signal = proj.get_signal() or {}
        except Exception:
            return None
        return (
            f"regime={regime.get('regime', 'unknown')} "
            f"adx={regime.get('adx', 'n/a')} "
            f"conviction={signal.get('conviction', 0.0)} "
            f"D={signal.get('D', 0.0)} P={signal.get('P', 0.0)} "
            f"G={signal.get('G', 0.0)}"
        )

    def scanner_summary(self) -> str | None:
        proj = getattr(self._state, "alert_projection", None)
        if proj is None:
            return None
        try:
            alerts = proj.get() or []
        except Exception:
            return None
        if not alerts:
            return None
        lines = [f"- {a.get('severity')} {a.get('message')}" for a in alerts[:10]]
        return "\n".join(lines)

    def options_summary(self) -> str | None:
        # No options-posture renderer exists yet — honest best-effort.
        return None

    def knowledge_summary(self, query: str) -> str | None:
        """Top activated knowledge docs for a query (best-effort)."""
        store = getattr(self._state, "knowledge_store", None)
        if store is None:
            return None
        try:
            hits = store.search(query, status="activated", limit=5)
        except Exception:
            return None
        if not hits:
            return None
        lines = []
        for h in hits:
            tags = ",".join(t["tag"] for t in h.tags[:4]) or "untagged"
            lines.append(f"- {h.title} [{tags}] ({h.source_ref})")
        return "\n".join(lines)
