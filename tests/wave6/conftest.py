"""Shared fixtures for wave 6 tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Yield a temporary directory for SQLite paths."""
    d = tmp_path / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d
