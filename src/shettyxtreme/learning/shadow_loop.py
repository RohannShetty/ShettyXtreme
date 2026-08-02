"""Runtime learning loop — signal decisions, shadow voters, session outcomes.

Wires the standalone learning machinery into the live event flow (P4c):

    SIGNAL_V2 ──► record_signal_decision (learning.db)
              └─► run shadow voters ──► log_shadow_results (shadow.db)

Session end (lifespan teardown) evaluates the realized outcome derived from
the trade ledger's fills: shadow votes for the session's signals are compared
against that outcome and graduation is re-checked (still gated by the
>=20-session rule inside ShadowManager — this module only triggers the check).

Everything is event-driven; nothing here places orders (D10) and shadow
votes never enter the live conviction path. DB failures are logged and
never propagated into the event loop.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.execution.ledger import pair_fills
from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
    Vote,
)
from shettyxtreme.intelligence.signals.shadow_manager import ShadowManager
from shettyxtreme.intelligence.voters.shadow import (
    shadow_dpg_vote,
    shadow_orb_decay_vote,
    shadow_signal_drift_ev_vote,
    shadow_time_bucketed_oi_vote,
)
from shettyxtreme.learning.outcome_tracker import OutcomeLabel, OutcomeTracker

logger = logging.getLogger(__name__)

#: The four exported shadow voters, registered at startup (names match the
#: package __all__ so status endpoints surface stable identities).
SHADOW_VOTERS: list[tuple[str, object]] = [
    ("shadow_dpg_vote", shadow_dpg_vote),
    ("shadow_orb_decay", shadow_orb_decay_vote),
    ("shadow_signal_drift_ev", shadow_signal_drift_ev_vote),
    ("shadow_time_bucketed_oi", shadow_time_bucketed_oi_vote),
]

_LIVE_DIRECTION = {"UP": 1.0, "DOWN": -1.0, "NEUTRAL": 0.0}


def session_outcome_label(fills: list[dict]) -> OutcomeLabel | None:
    """Aggregate realized outcome for a session from its ledger fills.

    FIFO-pairs opposite-side fills per symbol (same semantics as the ledger's
    per-session summary) and labels the session WIN/LOSS by total realized
    PnL. Returns None when there are no completed pairs — a session that
    never traded has no outcome, and that must not be recorded as neutral.
    """
    pairs = pair_fills(fills or [])
    if not pairs:
        return None
    pnl = sum(float(p["pnl"]) for p in pairs)
    if pnl > 0:
        return OutcomeLabel.WIN
    if pnl < 0:
        return OutcomeLabel.LOSS
    return None


class ShadowLoop:
    """EventBus-bound learning loop: decisions -> shadows -> session outcomes."""

    def __init__(
        self,
        shadow_db_path: str,
        learning_db_path: str,
        session_id_provider=None,
        feature_provider=None,
        regime_provider=None,
    ) -> None:
        self._mgr = ShadowManager(db_path=shadow_db_path)
        self._tracker = OutcomeTracker(learning_db_path)
        self._session_id_provider = session_id_provider or (lambda: None)
        self._feature_provider = feature_provider or (lambda: None)
        self._regime_provider = regime_provider or (lambda: None)
        self._seq = 0
        self._signals_by_session: dict[str, dict[str, float]] = {}
        self._shadow_names: list[str] = []
        self._subscribed = False

    @property
    def shadow_names(self) -> list[str]:
        """Names of the shadow voters registered on the manager."""
        return list(self._shadow_names)

    def register(self) -> list[str]:
        """Register the exported shadow voters; returns their names."""
        self._shadow_names = []
        for name, fn in SHADOW_VOTERS:
            self._mgr.register_shadow(name, fn)
            self._shadow_names.append(name)
        logger.info("registered %d shadow voters: %s", len(self._shadow_names), self._shadow_names)
        return self.shadow_names

    def subscribe(self, bus: EventBus) -> None:
        if self._subscribed:
            return
        bus.subscribe(Topic.SIGNAL_V2, self._on_signal)
        self._subscribed = True

    def unsubscribe(self, bus: EventBus) -> None:
        if not self._subscribed:
            return
        bus.unsubscribe(Topic.SIGNAL_V2, self._on_signal)
        self._subscribed = False

    async def _on_signal(self, event: Event) -> None:
        """Record the decision and log shadow votes for one SIGNAL_V2."""
        data = event.data if isinstance(event.data, dict) else {}
        direction = data.get("direction")
        if direction not in _LIVE_DIRECTION:
            return
        session_id = self._session_id_provider()
        if not session_id:
            return
        signal_id = f"{session_id}:{self._seq}"
        self._seq += 1
        try:
            self._tracker.record_signal_decision(
                self._signal_from_event(data),
                {"kind": "signal", "session_id": session_id, "signal_id": signal_id},
            )
        except Exception:
            logger.exception("signal decision recording failed")
        try:
            features = dict(self._feature_provider() or {})
            regime = self._coerce_regime(self._regime_provider())
            votes = self._mgr.run_shadow(features, regime, {})
            self._mgr.log_shadow_results(
                signal_id,
                votes,
                session_date=datetime.now(UTC).date().isoformat(),
            )
        except Exception:
            logger.exception("shadow logging failed")
        self._signals_by_session.setdefault(session_id, {})[
            signal_id
        ] = _LIVE_DIRECTION[direction]

    def evaluate_session(
        self, session_id: str, outcome: OutcomeLabel | None
    ) -> None:
        """Compare the session's shadow votes against its realized outcome.

        Comparisons only happen when an outcome exists; graduation is always
        re-checked (ShadowManager gates it internally at >=20 sessions).
        """
        signals = self._signals_by_session.pop(session_id, {})
        if outcome is not None:
            for signal_id, live_direction in signals.items():
                try:
                    self._mgr.compare_shadow_vs_live(
                        signal_id, outcome, live_direction=live_direction
                    )
                except Exception:
                    logger.exception("shadow comparison failed for %s", signal_id)
        for name in self._shadow_names:
            try:
                self._mgr.graduate(name)
            except Exception:
                logger.exception("shadow graduation check failed for %s", name)

    def close(self) -> None:
        """Close both database connections (idempotent)."""
        self._mgr.close()
        try:
            self._tracker.close()
        except Exception:
            logger.exception("learning store close failed")

    def _signal_from_event(self, data: dict) -> Signal:
        try:
            conviction = float(data.get("conviction", 0.0))
        except (TypeError, ValueError):
            conviction = 0.0
        timestamp = data.get("timestamp")
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(UTC)
        voters: list[Vote] = []
        for v in data.get("voters", []) or []:
            if not isinstance(v, dict):
                continue
            try:
                voters.append(
                    Vote(
                        direction=float(v.get("direction", 0.0)),
                        confidence=float(v.get("confidence", 0.0)),
                        weight=float(v.get("weight", 1.0)),
                        name=str(v.get("name", "?")),
                    )
                )
            except (TypeError, ValueError):
                continue
        return Signal(
            direction=SignalDirection(str(data["direction"]).lower()),
            conviction=conviction,
            voters=voters,
            timestamp=timestamp,
        )

    @staticmethod
    def _coerce_regime(raw) -> Regime | None:
        """Regime from a Regime, dict, or string; None for anything unknown."""
        if isinstance(raw, Regime):
            return raw
        if isinstance(raw, dict):
            raw = raw.get("regime")
        if isinstance(raw, str):
            try:
                return Regime(raw)
            except ValueError:
                logger.warning("unknown regime value %r", raw)
        return None
