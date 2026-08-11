"""Shared in-process kill gate with atomic file persistence.

Phase 6 Lane B (kill switch race): the file-based kill switch
(~/.shetty_kill_switch) is the durable, cross-process source of truth that
survives restarts, but a check-then-act against the file is TOCTOU-prone —
arming between the gate check and the broker await cannot stop an in-flight
placement. This gate adds an in-process asyncio.Event that the mode router
and the execution router share:

  * arm()/disarm() update BOTH layers: the file is written/removed atomically
    (tempfile + os.replace) and the event is set/cleared, so an arm lands
    instantly in-process without a filesystem round-trip.
  * is_armed() consults either layer (event OR file) so a file armed by
    another process is still honored (and an event armed by the API is
    honored even if the file write is momentarily raced).
  * the mode router double-checks the gate immediately before dispatching to
    the broker (after any pre-await), shrinking the race window to the single
    final call — the inherent TOCTOU of any check-before-act.
  * wire-entry/exit accounting lets arming report how many placements crossed
    the wire during the arm window ("placed just before kill") — honesty-first
    reporting (recon §5.3).
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_ARM_MARKER = "armed\n"


class KillSwitchGate:
    """asyncio.Event-based kill gate with atomic file persistence.

    The path may be empty (no file layer) — used by tests and by the API when
    the switch path has been reset; the event layer still works.
    """

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        raw = str(path) if path else ""
        self._path: Path | None = Path(raw) if raw else None
        # asyncio.Event has no initial-state constructor; mirror the file so a
        # switch armed by a previous process is honored across restarts.
        self._armed = asyncio.Event()
        self._in_flight = 0
        self._total_wire_entries = 0
        self._arm_in_flight: int | None = None
        self._arm_total_entries: int | None = None
        if self._path is not None and self._path.exists():
            self._armed.set()

    @property
    def path(self) -> str:
        return str(self._path) if self._path is not None else ""

    # ------------------------------------------------------------------
    # Armed state (either layer)
    # ------------------------------------------------------------------
    def is_armed(self) -> bool:
        """True when either layer is armed (in-process event OR file)."""
        if self._armed.is_set():
            return True
        return self._path is not None and self._path.exists()

    def arm(self) -> None:
        """Arm both layers: atomic file write, then set the in-process event.

        The file is written first so is_armed() (event OR file) can never
        observe a gap where the gate appears open.
        """
        self._write_file()
        self._armed.set()
        self._arm_in_flight = self._in_flight
        self._arm_total_entries = self._total_wire_entries

    def disarm(self) -> None:
        """Disarm both layers: clear the event, then remove the file."""
        self._armed.clear()
        self._remove_file()

    # ------------------------------------------------------------------
    # Wire accounting (honest arm-window reporting)
    # ------------------------------------------------------------------
    @property
    def placements_in_flight(self) -> int:
        """Placements currently dispatched to the wire (not yet returned)."""
        return self._in_flight

    def note_wire_entry(self) -> None:
        """Record a placement passing the final gate and reaching the wire."""
        self._in_flight += 1
        self._total_wire_entries += 1

    def note_wire_exit(self) -> None:
        """Record a placement returning from the wire."""
        self._in_flight -= 1

    @property
    def arm_report(self) -> dict:
        """Snapshot taken at the most recent arm().

        placements_in_flight: how many placements were already dispatched to
            the wire when the switch was armed — the "crossed the wire in the
            arm window" population.
        total_placements_at_arm: cumulative wire entries up to arm time.
        """
        return {
            "placements_in_flight": self._arm_in_flight or 0,
            "total_placements_at_arm": self._arm_total_entries or 0,
        }

    # ------------------------------------------------------------------
    # File layer
    # ------------------------------------------------------------------
    def _write_file(self) -> None:
        """Atomic write via tempfile + os.replace (recon §5.3)."""
        if self._path is None:
            return
        fd, tmp = tempfile.mkstemp(prefix=".shetty_kill_switch.", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(_ARM_MARKER)
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _remove_file(self) -> None:
        if self._path is None:
            return
        self._path.unlink(missing_ok=True)
