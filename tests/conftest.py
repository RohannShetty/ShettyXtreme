
"""Shared fixtures for ShettyXtreme integration tests."""
import os
import sys
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
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


class MockHttpResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            from httpx import HTTPStatusError
            raise HTTPStatusError(
                "HTTP error", request=MagicMock(), response=self,
            )


class MockAsyncClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self._closed = False

    async def get(self, url, **kwargs):
        return self.responses.get("get", MockHttpResponse({}, 200))

    async def post(self, url, **kwargs):
        return self.responses.get("post", MockHttpResponse({}, 200))

    async def aclose(self):
        self._closed = True

    def set_response(self, method, response):
        self.responses[method] = response


@pytest_asyncio.fixture
async def openalgo_adapter():
    from shettyxtreme.integration.openalgo import OpenAlgoAdapter
    adapter = OpenAlgoAdapter(
        base_url="http://mock.openalgo:5000",
        api_key="test-api-key",
    )
    mock_client = MockAsyncClient()
    adapter._client = mock_client
    adapter._ws_connected = True
    yield adapter
    if not mock_client._closed:
        await mock_client.aclose()


class MockDhanHQ:
    class HistoricalData:
        async def intraday_minute_data(self, **kwargs):
            return {"status": "success", "data": [{"time": "09:15", "open": 100}]}

        async def historical_daily_data(self, **kwargs):
            return {"status": "success", "data": [{"date": "2024-01-01", "close": 100}]}

        async def expired_options_data(self, **kwargs):
            return {"status": "success", "data": [{"strike": 50000}]}

    class OptionChain:
        async def get_option_chain(self, **kwargs):
            return {"status": "success", "data": [
                {"strike": 50000, "option_type": "CE", "ltp": 100}
            ]}

    class Portfolio:
        async def get_positions(self):
            return {"status": "success", "data": [
                {"symbol": "NIFTY", "exchange": "NSE", "quantity": 1}
            ]}

        async def get_holdings(self):
            return {"status": "success", "data": [
                {"symbol": "RELIANCE", "quantity": 10}
            ]}

        async def get_tradebook(self):
            return {"status": "success", "data": []}

    class Funds:
        async def get_fund_limits(self):
            return {"status": "success", "data": {"available": 50000}}

    class MarketFeed:
        async def ticker_data(self, securities):
            return {"status": "success", "data": securities}
        async def quote_data(self, securities):
            return {"status": "success", "data": securities}
        async def ohlc_data(self, securities):
            return {"status": "success", "data": securities}

    def __init__(self, **kwargs):
        self.client_id = kwargs.get("client_id", "")
        self.access_token = kwargs.get("access_token", "")
        self.historical_data = self.HistoricalData()
        self.option_chain = self.OptionChain()
        self.portfolio = self.Portfolio()
        self.funds = self.Funds()
        self.market_feed = self.MarketFeed()
        self.order = MagicMock()


class MockDhanHQModule:
    class dhanhq:
        DhanHQ = MockDhanHQ
    class marketfeed:
        class MarketFeed:
            def __init__(self, **kwargs):
                pass
            def run_forever(self):
                pass


@pytest.fixture
def dhan_adapter():
    from shettyxtreme.integration.dhan.dhan_adapter import DhanAdapter
    adapter = DhanAdapter(
        client_id="test_client",
        access_token="test_token",
        data_dir="/tmp/test_dhan_data",
    )
    mock_module = MockDhanHQModule()
    with patch.dict(
        "sys.modules",
        {"dhanhq": mock_module, "dhanhq.dhanhq": mock_module.dhanhq},
    ):
        adapter._dhanhq = None
        adapter._init_dhanhq()
        yield adapter


@pytest.fixture
def clean_env():
    keys = [k for k in os.environ if k.startswith(("SHETTY_", "DHAN_", "OPENALGO_"))]
    stash = {k: os.environ.pop(k) for k in keys if k in os.environ}
    for k in keys:
        os.environ.pop(k, None)
    yield
    for k, v in stash.items():
        os.environ[k] = v
