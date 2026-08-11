
"""Shared fixtures for ShettyXtreme integration tests."""
import os
import sys
import tempfile
from pathlib import Path
from typing import Generator

import pytest
try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "duckdb: skip test when duckdb is not available")


@pytest.fixture(scope="session", autouse=True)
def _reset_execution_mode_to_observer() -> None:
    """Guard: never let a stale ~/.shettyxtreme_mode leak into the run.

    execution_router reads Path.home()/".shettyxtreme_mode" at import time to
    restore the last execution mode (`_current_mode = _load_mode()`); only
    OBSERVER/PAPER are restored, LIVE never auto-restores (D10). A stale value
    left by a manual session or a prior app run (e.g. "PAPER") silently makes
    the module start non-OBSERVER and changes the behavior of tests that assume
    the OBSERVER default.

    Two-pronged reset: (1) overwrite the persisted file once per session so any
    runtime read (including subprocesses / fresh imports) sees OBSERVER; (2)
    re-pin the already-imported module's `_current_mode` — test modules are
    imported during collection, before any fixture runs, so the file fix alone
    cannot undo a stale value captured at import time.
    """
    mode_file = Path.home() / ".shettyxtreme_mode"
    try:
        mode_file.write_text("OBSERVER")
    except Exception:
        pass
    try:
        from shettyxtreme.terminal.api import execution_router
        if execution_router._current_mode != "OBSERVER":
            execution_router._current_mode = "OBSERVER"
    except Exception:
        pass



_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


@pytest.fixture
def tmp_data_dir() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory(prefix="shetty_") as td:
        yield td


@pytest.fixture
def event_bus():
    from shettyxtreme.core.event_bus import EventBus
    return EventBus()


@pytest.fixture
def kv_store(tmp_data_dir: str):
    from shettyxtreme.core.storage import KVStore
    db_path = os.path.join(tmp_data_dir, "test_kv.db")
    store = KVStore(db_path)
    yield store
    store.close()


@pytest.fixture
def ts_store(tmp_data_dir: str):
    from shettyxtreme.core.storage.time_series_store import TimeSeriesStore
    db_path = os.path.join(tmp_data_dir, "test_ts.db")
    store = TimeSeriesStore(db_path)
    yield store
    store.close()


@pytest.fixture
def config_manager(tmp_data_dir: str):
    import yaml
    cfg = {
        "mode": "paper",
        "broker": "fyers",
        "log_level": "DEBUG",
        "dry_run": True,
        "fyers_app_id": "test_app",
    }
    cfg_path = os.path.join(tmp_data_dir, "config.yaml")
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)
    from shettyxtreme.core.config import ConfigManager
    return ConfigManager(cfg_path)


@pytest.fixture
def clean_env():
    keys = [k for k in os.environ if k.startswith(("SHETTY_", "FYERS_", "OPENALGO_"))]
    stash = {k: os.environ.pop(k) for k in keys if k in os.environ}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k, v in stash.items():
        os.environ[k] = v
