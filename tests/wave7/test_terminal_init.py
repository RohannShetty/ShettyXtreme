"""Tests for the idempotent Dhan adapter + pipeline bootstrap (T1)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

import shettyxtreme.terminal.api.terminal_init as terminal_init
from shettyxtreme.terminal.api.terminal_init import (
    init_terminal_adapters,
    run_terminal_init,
    wire_terminal_init,
)


class _FakeStore:
    client_id = "DHAN123"
    access_token = "tok_abc"
    data_access_token = "data_tok_abc"

    def is_token_valid(self) -> bool:
        return True


class _FakeWatchlist:
    def __init__(self, rows: dict) -> None:
        self._rows = rows

    def get(self) -> dict:
        return self._rows


@pytest.fixture(autouse=True)
def _reset_hook() -> None:
    terminal_init._init_terminal_adapters = None
    yield
    terminal_init._init_terminal_adapters = None


@pytest.mark.asyncio
async def test_init_terminal_adapters_idempotent() -> None:
    app = FastAPI()
    app.state.data_adapter = object()
    app.state.terminal_initialized = True

    with patch("shettyxtreme.terminal.api.terminal_init.DhanDataAdapter") as fake_da:
        result = await init_terminal_adapters(app, _FakeStore(), {})
        assert result is True
        fake_da.assert_not_called()

    app2 = FastAPI()
    app2.state.data_adapter = None
    app2.state.watchlist_projection = _FakeWatchlist(
        {"NIFTY": {"exchange": "NSE_FNO", "security_id": "13"}}
    )
    app2.state.event_bus = object()

    fake_ing = MagicMock()
    fake_ing.start = AsyncMock()
    fake_pipeline_cls = MagicMock(return_value=fake_ing)
    fake_trading_cls = MagicMock()
    fake_data_cls = MagicMock()
    fake_ts_cls = MagicMock()

    with (
        patch("shettyxtreme.terminal.api.terminal_init.DhanTradingAdapter", fake_trading_cls),
        patch("shettyxtreme.terminal.api.terminal_init.DhanDataAdapter", fake_data_cls),
        patch("shettyxtreme.terminal.api.terminal_init.IngestionPipeline", fake_pipeline_cls),
        patch("shettyxtreme.terminal.api.terminal_init.TimeSeriesStore", fake_ts_cls),
        patch("shettyxtreme.terminal.api.terminal_init.init_instrument_master", return_value=None),
    ):
        result = await init_terminal_adapters(app2, _FakeStore(), {"13": "NIFTY"})
        assert result is True
        fake_trading_cls.assert_called_once_with(
            client_id="DHAN123", access_token="tok_abc"
        )
        fake_data_cls.assert_called_once_with(
            client_id="DHAN123",
            access_token="tok_abc",
            data_access_token="data_tok_abc",
        )
        fake_ts_cls.assert_called_once()
        fake_ing.start.assert_awaited_once_with(["13"])
        assert app2.state.trading_adapter is fake_trading_cls.return_value
        assert app2.state.data_adapter is fake_data_cls.return_value
        assert app2.state.ingestion_pipeline is fake_ing

        second = await init_terminal_adapters(app2, _FakeStore(), {"13": "NIFTY"})
        assert second is True
        fake_trading_cls.assert_called_once()
        fake_data_cls.assert_called_once()
        fake_ing.start.assert_awaited_once()
        assert getattr(app2.state, "terminal_initialized", False) is True


@pytest.mark.asyncio
async def test_init_partial_failure_does_not_raise_and_retries() -> None:
    app = FastAPI()
    app.state.watchlist_projection = _FakeWatchlist({})
    app.state.event_bus = object()

    fake_trading_cls = MagicMock()
    fake_trading_cls.return_value.disconnect = AsyncMock()
    fake_data_cls = MagicMock(side_effect=RuntimeError("data init boom"))

    with (
        patch("shettyxtreme.terminal.api.terminal_init.DhanTradingAdapter", fake_trading_cls),
        patch("shettyxtreme.terminal.api.terminal_init.DhanDataAdapter", fake_data_cls),
    ):
        result = await init_terminal_adapters(app, _FakeStore(), {})
        assert result is False

        second = await init_terminal_adapters(app, _FakeStore(), {})
        assert second is False
        assert fake_trading_cls.call_count == 2
        assert fake_data_cls.call_count == 2
        fake_trading_cls.return_value.disconnect.assert_awaited_once()
        assert getattr(app.state, "terminal_initialized", False) is False


@pytest.mark.asyncio
async def test_init_empty_watchlist_succeeds_without_pipeline() -> None:
    """Empty watchlist: returns True, no pipeline, marker NOT pinned — so a
    later re-init retries and self-heals once symbols exist."""
    app = FastAPI()
    app.state.watchlist_projection = _FakeWatchlist({})
    app.state.event_bus = object()

    fake_trading_cls = MagicMock()
    fake_trading_cls.return_value.disconnect = AsyncMock()
    fake_data_cls = MagicMock()
    fake_pipeline_cls = MagicMock()
    fake_pipeline_cls.return_value.start = AsyncMock()

    with (
        patch("shettyxtreme.terminal.api.terminal_init.DhanTradingAdapter", fake_trading_cls),
        patch("shettyxtreme.terminal.api.terminal_init.DhanDataAdapter", fake_data_cls),
        patch("shettyxtreme.terminal.api.terminal_init.IngestionPipeline", fake_pipeline_cls),
        patch("shettyxtreme.terminal.api.terminal_init.init_instrument_master", return_value=None),
    ):
        result = await init_terminal_adapters(app, _FakeStore(), {})
        assert result is True
        fake_pipeline_cls.assert_not_called()
        fake_data_cls.return_value.set_symbol_map.assert_called_once()
        assert getattr(app.state, "ingestion_pipeline", None) is None
        assert getattr(app.state, "terminal_initialized", False) is False

        # Watchlist becomes non-empty later — the next re-init must start
        # pipelines and pin the marker (self-heal).
        app.state.watchlist_projection = _FakeWatchlist(
            {"NIFTY": {"exchange": "NSE_FNO", "security_id": "13"}}
        )
        second = await init_terminal_adapters(app, _FakeStore(), {})
        assert second is True
        assert fake_pipeline_cls.call_count == 1
        fake_pipeline_cls.return_value.start.assert_awaited_once()
        assert getattr(app.state, "terminal_initialized", False) is True

        third = await init_terminal_adapters(app, _FakeStore(), {})
        assert third is True
        assert fake_trading_cls.call_count == 2  # marker pinned — no re-build
        assert fake_data_cls.call_count == 2


@pytest.mark.asyncio
async def test_init_event_bus_missing_returns_false() -> None:
    app = FastAPI()
    app.state.watchlist_projection = _FakeWatchlist(
        {"NIFTY": {"exchange": "NSE_FNO", "security_id": "13"}}
    )

    fake_trading_cls = MagicMock()
    fake_data_cls = MagicMock()

    with (
        patch("shettyxtreme.terminal.api.terminal_init.DhanTradingAdapter", fake_trading_cls),
        patch("shettyxtreme.terminal.api.terminal_init.DhanDataAdapter", fake_data_cls),
        patch("shettyxtreme.terminal.api.terminal_init.IngestionPipeline", MagicMock()),
        patch("shettyxtreme.terminal.api.terminal_init.init_instrument_master", return_value=None),
    ):
        result = await init_terminal_adapters(app, _FakeStore(), {})
        assert result is False
        assert getattr(app.state, "terminal_initialized", False) is False


@pytest.mark.asyncio
async def test_wire_and_run_terminal_init() -> None:
    async def _fake() -> bool:
        return True

    wire_terminal_init(_fake)
    assert await run_terminal_init() is True

    terminal_init._init_terminal_adapters = None
    assert await run_terminal_init() is False
