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
        # No chain text renderer exists yet — honest best-effort.
        return None

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
