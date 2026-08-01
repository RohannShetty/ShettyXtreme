
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
        "broker": "dhan",
        "data_provider": "openalgo",
        "log_level": "DEBUG",
        "dry_run": True,
        "dhan_client_id": "test_client",
        "openalgo_base_url": "http://test.openalgo:5000",
    }
    cfg_path = os.path.join(tmp_data_dir, "config.yaml")
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)
    from shettyxtreme.core.config import ConfigManager
    return ConfigManager(cfg_path)


@pytest.fixture
def clean_env():
    keys = [k for k in os.environ if k.startswith(("SHETTY_", "DHAN_", "OPENALGO_"))]
    stash = {k: os.environ.pop(k) for k in keys if k in os.environ}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k, v in stash.items():
        os.environ[k] = v
