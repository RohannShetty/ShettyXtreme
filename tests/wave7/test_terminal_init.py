"""Tests for the idempotent Fyers adapter bootstrap (T1)."""
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
    app_id = "APP123"
    secret_id = "SECRET1"
    access_token = "tok_abc"
    token_expiry = "2099-01-01T00:00:00+00:00"
    client_id = "FY123"

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

    with patch("shettyxtreme.terminal.api.terminal_init._build_session_and_transport") as fake_build:
        result = await init_terminal_adapters(app, _FakeStore(), {})
        assert result is True
        fake_build.assert_not_called()

    app2 = FastAPI()
    app2.state.data_adapter = None
    app2.state.watchlist_projection = _FakeWatchlist(
        {"NIFTY": {"exchange": "NSE_FNO", "security_id": "NIFTY"}}
    )
    app2.state.event_bus = object()

    fake_trading_cls = MagicMock()
    fake_data_cls = MagicMock()
    fake_session = MagicMock()
    fake_session.app_id = "APP123"
    fake_session.access_token = "tok_abc"
    fake_client = MagicMock()
    fake_master = MagicMock()
    fake_resolver = MagicMock()
    fake_order_socket = MagicMock()
    fake_data_socket = MagicMock()

    async def _fake_subscribe_ticks(symbols, callback) -> bool:
        return True

    fake_data_cls.subscribe_ticks = AsyncMock(side_effect=_fake_subscribe_ticks)
    fake_data_cls.connect = AsyncMock(return_value=True)
    fake_order_socket.subscribe = AsyncMock(return_value=True)
    fake_bar_builder = MagicMock()
    fake_bar_builder.start = AsyncMock()

    with (
        patch("shettyxtreme.terminal.api.terminal_init._build_session_and_transport",
              return_value=(fake_session, fake_client)),
        patch("shettyxtreme.terminal.api.terminal_init.init_instrument_master",
              return_value=fake_master),
        patch("shettyxtreme.terminal.api.terminal_init.FyersSymbolResolver",
              return_value=fake_resolver),
        patch("shettyxtreme.terminal.api.terminal_init.FyersOrderSocket",
              return_value=fake_order_socket),
        patch("shettyxtreme.terminal.api.terminal_init.FyersDataSocketWrapper",
              return_value=fake_data_socket),
        patch("shettyxtreme.terminal.api.terminal_init.FyersTradingAdapter",
              return_value=fake_trading_cls),
        patch("shettyxtreme.terminal.api.terminal_init.FyersDataAdapter",
              return_value=fake_data_cls),
        patch("shettyxtreme.terminal.api.terminal_init.BarBuilder",
              return_value=fake_bar_builder),
        patch("shettyxtreme.terminal.api.terminal_init.TimeSeriesStore"),
    ):
        result = await init_terminal_adapters(app2, _FakeStore(), {"NIFTY": "NIFTY"})
        assert result is True
        fake_trading_cls.disconnect.assert_not_called()
        assert app2.state.trading_adapter is fake_trading_cls
        assert app2.state.data_adapter is fake_data_cls
        fake_bar_builder.start.assert_awaited_once()
        fake_data_cls.subscribe_ticks.assert_awaited_once()

        second = await init_terminal_adapters(app2, _FakeStore(), {"NIFTY": "NIFTY"})
        assert second is True
        assert getattr(app2.state, "terminal_initialized", False) is True


@pytest.mark.asyncio
async def test_init_partial_failure_does_not_raise_and_retries() -> None:
    app = FastAPI()
    app.state.watchlist_projection = _FakeWatchlist({})
    app.state.event_bus = object()

    fake_trading_cls = MagicMock()
    fake_trading_cls.disconnect = AsyncMock()

    with (
        patch("shettyxtreme.terminal.api.terminal_init._build_session_and_transport",
              side_effect=[None, None]),
    ):
        result = await init_terminal_adapters(app, _FakeStore(), {})
        assert result is False

        second = await init_terminal_adapters(app, _FakeStore(), {})
        assert second is False
        assert getattr(app.state, "terminal_initialized", False) is False


@pytest.mark.asyncio
async def test_init_empty_watchlist_succeeds_without_bridge() -> None:
    """Empty watchlist: returns True, no bridge started, marker NOT pinned —
    so a later re-init retries and self-heals once symbols exist."""
    app = FastAPI()
    app.state.watchlist_projection = _FakeWatchlist({})
    app.state.event_bus = object()

    fake_session = MagicMock()
    fake_session.app_id = "APP123"
    fake_session.access_token = "tok_abc"
    fake_client = MagicMock()

    fake_trading_cls = MagicMock()
    fake_data_cls = MagicMock()

    with (
        patch("shettyxtreme.terminal.api.terminal_init._build_session_and_transport",
              return_value=(fake_session, fake_client)),
        patch("shettyxtreme.terminal.api.terminal_init.init_instrument_master",
              return_value=MagicMock()),
        patch("shettyxtreme.terminal.api.terminal_init.FyersSymbolResolver"),
        patch("shettyxtreme.terminal.api.terminal_init.FyersOrderSocket"),
        patch("shettyxtreme.terminal.api.terminal_init.FyersDataSocketWrapper"),
        patch("shettyxtreme.terminal.api.terminal_init.FyersTradingAdapter",
              return_value=fake_trading_cls),
        patch("shettyxtreme.terminal.api.terminal_init.FyersDataAdapter",
              return_value=fake_data_cls),
    ):
        result = await init_terminal_adapters(app, _FakeStore(), {})
        assert result is True
        fake_data_cls.subscribe_ticks.assert_not_called()
        assert getattr(app.state, "ingestion_pipeline", None) is None
        assert getattr(app.state, "terminal_initialized", False) is False

        # Watchlist becomes non-empty later — the next re-init must start
        # the bridge and pin the marker (self-heal).
        app.state.watchlist_projection = _FakeWatchlist(
            {"NIFTY": {"exchange": "NSE_FNO", "security_id": "NIFTY"}}
        )
        fake_bar_builder = MagicMock()
        fake_bar_builder.start = AsyncMock()
        async def _sub(symbols, callback) -> bool:
            return True
        fake_data_cls.subscribe_ticks = AsyncMock(side_effect=_sub)

        with patch("shettyxtreme.terminal.api.terminal_init.BarBuilder",
                   return_value=fake_bar_builder), \
             patch("shettyxtreme.terminal.api.terminal_init.TimeSeriesStore"):
            second = await init_terminal_adapters(app, _FakeStore(), {"NIFTY": "NIFTY"})
        assert second is True
        fake_data_cls.subscribe_ticks.assert_awaited_once()
        assert getattr(app.state, "terminal_initialized", False) is True

        third = await init_terminal_adapters(app, _FakeStore(), {"NIFTY": "NIFTY"})
        assert third is True
        assert getattr(app.state, "terminal_initialized", False) is True


@pytest.mark.asyncio
async def test_init_event_bus_missing_returns_false() -> None:
    app = FastAPI()
    app.state.watchlist_projection = _FakeWatchlist(
        {"NIFTY": {"exchange": "NSE_FNO", "security_id": "NIFTY"}}
    )

    fake_session = MagicMock()
    fake_session.app_id = "APP123"
    fake_session.access_token = "tok_abc"
    fake_client = MagicMock()

    with (
        patch("shettyxtreme.terminal.api.terminal_init._build_session_and_transport",
              return_value=(fake_session, fake_client)),
        patch("shettyxtreme.terminal.api.terminal_init.init_instrument_master",
              return_value=MagicMock()),
        patch("shettyxtreme.terminal.api.terminal_init.FyersSymbolResolver"),
        patch("shettyxtreme.terminal.api.terminal_init.FyersOrderSocket"),
        patch("shettyxtreme.terminal.api.terminal_init.FyersDataSocketWrapper"),
        patch("shettyxtreme.terminal.api.terminal_init.FyersTradingAdapter",
              return_value=MagicMock()),
        patch("shettyxtreme.terminal.api.terminal_init.FyersDataAdapter",
              return_value=MagicMock()),
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
