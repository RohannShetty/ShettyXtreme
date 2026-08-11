"""KillSwitchGate unit tests (Phase 6 Lane B — kill switch race fix).

Covers: atomic arm/disarm file writes (tempfile + os.replace, no residue),
the dual-layer is_armed (in-process asyncio.Event OR file), restart survival
(armed file honored at construction), cross-process file honor, empty-path
gate behavior, and the wire-entry accounting used to report placements that
crossed the wire during the arm window.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from shettyxtreme.execution.kill_switch import KillSwitchGate


# ── armed state, event + file layers ──────────────────────────────────────

def test_gate_starts_disarmed() -> None:
    gate = KillSwitchGate("")
    assert gate.is_armed() is False


def test_arm_sets_event_and_writes_file(tmp_path: Path) -> None:
    kill_file = tmp_path / "kill"
    gate = KillSwitchGate(kill_file)

    gate.arm()

    assert gate.is_armed() is True
    assert kill_file.exists()
    assert kill_file.read_text() == "armed\n"


def test_arm_then_disarm_clears_both_layers(tmp_path: Path) -> None:
    kill_file = tmp_path / "kill"
    gate = KillSwitchGate(kill_file)
    gate.arm()
    assert gate.is_armed() is True

    gate.disarm()

    assert gate.is_armed() is False
    assert not kill_file.exists()


def test_atomic_arm_leaves_no_temp_residue(tmp_path: Path) -> None:
    kill_file = tmp_path / "kill"
    gate = KillSwitchGate(kill_file)

    gate.arm()

    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".shetty_kill_switch.")]
    assert leftovers == []
    assert kill_file.exists()


def test_gate_honors_pre_existing_file_across_restart(tmp_path: Path) -> None:
    """A switch armed by a previous process blocks a fresh gate (restart
    survival — the file is the durable layer)."""
    kill_file = tmp_path / "kill"
    kill_file.touch()

    gate = KillSwitchGate(kill_file)

    assert gate.is_armed() is True


def test_is_armed_honors_file_recreated_externally(tmp_path: Path) -> None:
    """An event-disarmed gate still sees a file created by another process."""
    kill_file = tmp_path / "kill"
    gate = KillSwitchGate(kill_file)
    gate.arm()
    gate.disarm()
    assert gate.is_armed() is False

    kill_file.touch()  # another process arms it

    assert gate.is_armed() is True


def test_arm_then_disarm_does_not_require_file_to_exist() -> None:
    gate = KillSwitchGate("")
    gate.arm()
    assert gate.is_armed() is True
    gate.disarm()
    assert gate.is_armed() is False
    gate.disarm()  # no-op, no error


def test_disarm_without_path_is_noop() -> None:
    gate = KillSwitchGate("")
    gate.disarm()
    assert gate.is_armed() is False


# ── wire accounting / arm-window reporting ────────────────────────────────

def test_arm_report_counts_placements_in_flight() -> None:
    gate = KillSwitchGate("")
    gate.note_wire_entry()
    gate.note_wire_entry()

    gate.arm()

    report = gate.arm_report
    assert report["placements_in_flight"] == 2
    assert report["total_placements_at_arm"] == 2
    assert gate.placements_in_flight == 2


def test_wire_exit_decrements_in_flight() -> None:
    gate = KillSwitchGate("")
    gate.note_wire_entry()
    gate.note_wire_entry()
    gate.note_wire_exit()

    assert gate.placements_in_flight == 1

    gate.arm()
    assert gate.arm_report["placements_in_flight"] == 1


def test_arm_report_zero_when_no_placements() -> None:
    gate = KillSwitchGate("")
    gate.arm()
    assert gate.arm_report["placements_in_flight"] == 0
    assert gate.arm_report["total_placements_at_arm"] == 0
