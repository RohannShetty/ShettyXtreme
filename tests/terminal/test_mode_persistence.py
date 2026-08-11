"""Tests for mode persistence in execution_router."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from shettyxtreme.terminal.api import execution_router


def _patch_mode_file(tmp_path: Path):
    """Return a monkeypatch that points _MODE_FILE at tmp_path."""
    mode_file = tmp_path / "mode.txt"

    import unittest.mock as mock

    return mock.patch.object(execution_router, "_MODE_FILE", mode_file), mode_file


@pytest.mark.asyncio
async def test_default_mode_observer(tmp_path: Path):
    patch, mode_file = _patch_mode_file(tmp_path)
    patch.start()
    try:
        if mode_file.exists():
            mode_file.unlink()
        assert execution_router._load_mode() == "OBSERVER"
    finally:
        patch.stop()


def test_live_mode_not_restored_across_sessions(tmp_path: Path) -> None:
    """LIVE is an explicit per-session action (D10): a saved LIVE mode
    must not auto-restore on the next load."""
    patch, mode_file = _patch_mode_file(tmp_path)
    with patch:
        if mode_file.exists():
            mode_file.unlink()
        execution_router._save_mode("LIVE")
        assert execution_router._load_mode() == "OBSERVER"


@pytest.mark.asyncio
async def test_load_missing_file(tmp_path: Path):
    patch, mode_file = _patch_mode_file(tmp_path)
    patch.start()
    try:
        if mode_file.exists():
            mode_file.unlink()
        assert execution_router._load_mode() == "OBSERVER"
    finally:
        patch.stop()


@pytest.mark.asyncio
async def test_save_persists(tmp_path: Path):
    patch, mode_file = _patch_mode_file(tmp_path)
    patch.start()
    try:
        execution_router._save_mode("PAPER")
        assert mode_file.exists()
        assert mode_file.read_text().strip() == "PAPER"
    finally:
        patch.stop()


def test_session_guard_leaves_mode_file_at_observer() -> None:
    """The session-scoped conftest guard must leave the persisted mode at
    OBSERVER so a stale LIVE/PAPER file can never leak into a test run.

    This is a permanent regression guard for the conftest autouse fixture: if
    the guard is removed, a stale ~/.shettyxtreme_mode resurfaces and tests
    that assume the OBSERVER default start failing again.
    """
    mode_file = Path.home() / ".shettyxtreme_mode"
    assert mode_file.exists(), "conftest guard did not create the mode file"
    assert mode_file.read_text().strip() == "OBSERVER"
    # The live module state must also be OBSERVER, not just the file.
    assert execution_router._current_mode == "OBSERVER"
