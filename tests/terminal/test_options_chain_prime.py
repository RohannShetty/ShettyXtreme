"""Tests for startup options-chain priming (Wave 1 #12).

The research ``options_posture`` tool reads ``app.state.options_chain``,
which was previously only ever populated as a side-effect of
``GET /api/intelligence/options`` — so it showed ``[UNSOURCED]`` until that
endpoint had been hit once. ``prime_options_chain`` closes that gap by
fetching the NIFTY chain once the data adapter exists (called from the
terminal bootstrap). These tests pin the graceful-degradation contract:
any failure leaves the cache untouched and never raises.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from shettyxtreme.terminal.api.intelligence_router import (
    DataEntitlementError,
    _fetch_chain_with_spot,
    prime_options_chain,
)
from shettyxtreme.terminal.api.research_source import ProjectionDataSource


class _FakeAdapter:
    """Adapter double whose get_option_chain result is injectable."""

    def __init__(self, result: dict | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    async def get_option_chain(self, underlying: str, expiry: str, strike_count: int = 50) -> dict:
        if self._error is not None:
            raise self._error
        return self._result or {}


def _state(adapter: object | None = None, existing: dict | None = None) -> SimpleNamespace:
    """app.state double shaped like FastAPI: ``app.state.data_adapter`` etc."""
    ns = SimpleNamespace(data_adapter=adapter)
    if existing is not None:
        ns.options_chain = existing
    return SimpleNamespace(state=ns)


def _ok_chain() -> dict:
    return {
        "s": "ok",
        "underlying_ltp": 24750.0,
        "option_chain": [
            {"strike": 24500, "option_type": "CE", "oi": 50000, "iv": 15.0},
            {"strike": 24600, "option_type": "CE", "oi": 70000, "iv": 15.5},
            {"strike": 24500, "option_type": "PE", "oi": 60000, "iv": 16.0},
        ],
    }


@pytest.mark.asyncio
async def test_prime_populates_chain_cache() -> None:
    app = _state(adapter=_FakeAdapter(_ok_chain()))
    await prime_options_chain(app)
    cache = app.state.options_chain
    assert "NIFTY" in cache
    assert cache["NIFTY"]["spot"] == 24750.0
    assert len(cache["NIFTY"]["contracts"]) == 3


@pytest.mark.asyncio
async def test_prime_preserves_other_symbols_in_cache() -> None:
    existing = {"BANKNIFTY": {"spot": 55000.0, "contracts": []}}
    app = _state(adapter=_FakeAdapter(_ok_chain()), existing=existing)
    await prime_options_chain(app)
    assert "BANKNIFTY" in app.state.options_chain
    assert app.state.options_chain["BANKNIFTY"]["spot"] == 55000.0


@pytest.mark.asyncio
async def test_prime_no_adapter_leaves_cache_untouched() -> None:
    existing = {"NIFTY": {"spot": 1.0, "contracts": []}}
    app = _state(adapter=None, existing=existing)
    await prime_options_chain(app)
    assert app.state.options_chain == existing


@pytest.mark.asyncio
async def test_prime_entitlement_error_leaves_cache_untouched() -> None:
    existing = {"NIFTY": {"spot": 1.0, "contracts": []}}
    app = _state(
        adapter=_FakeAdapter({"entitlement": True, "s": "error"}),
        existing=existing,
    )
    await prime_options_chain(app)  # must not raise
    assert app.state.options_chain == existing


@pytest.mark.asyncio
async def test_prime_network_error_leaves_cache_untouched() -> None:
    existing = {"NIFTY": {"spot": 1.0, "contracts": []}}
    app = _state(
        adapter=_FakeAdapter(error=RuntimeError("socket closed")),
        existing=existing,
    )
    await prime_options_chain(app)  # must not raise
    assert app.state.options_chain == existing


@pytest.mark.asyncio
async def test_prime_empty_chain_leaves_cache_untouched() -> None:
    existing = {"NIFTY": {"spot": 1.0, "contracts": []}}
    app = _state(adapter=_FakeAdapter({"s": "ok", "option_chain": []}), existing=existing)
    await prime_options_chain(app)
    assert app.state.options_chain == existing


@pytest.mark.asyncio
async def test_primed_cache_feeds_options_summary() -> None:
    """End-to-end: after priming, options_posture renders real data, not [UNSOURCED]."""
    app = _state(adapter=_FakeAdapter(_ok_chain()))
    await prime_options_chain(app)
    out = ProjectionDataSource(app.state).options_summary()
    assert out is not None
    assert "NIFTY options" in out
    assert "pcr=" in out
    assert "iv=" in out


@pytest.mark.asyncio
async def test_failed_prime_keeps_options_summary_unsourced() -> None:
    """Entitlement failure degrades to [UNSOURCED] (honest no-data state)."""
    app = _state(adapter=_FakeAdapter({"entitlement": True, "s": "error"}))
    await prime_options_chain(app)
    out = ProjectionDataSource(app.state).options_summary()
    assert out is None


@pytest.mark.asyncio
async def test_prime_calls_adapter_with_nifty_defaults() -> None:
    adapter = _FakeAdapter(_ok_chain())
    get_option_chain = AsyncMock(wraps=adapter.get_option_chain)
    adapter.get_option_chain = get_option_chain  # type: ignore[method-assign]
    app = _state(adapter=adapter)
    await prime_options_chain(app)
    get_option_chain.assert_awaited_once()
    kwargs = get_option_chain.call_args.kwargs
    assert kwargs["underlying"] == "NIFTY"
    assert kwargs["strike_count"] == 50


class _FakeAdapterForFetch:
    """Adapter double for _fetch_chain_with_spot tests."""

    def __init__(self, result: dict | None = None) -> None:
        self._result = result or {}

    async def get_option_chain(self, underlying: str, expiry: str, strike_count: int = 50) -> dict:
        return self._result


class TestFetchChainWithSpot:
    """P0-1.1: _fetch_chain_with_spot must surface errors, not swallow them."""

    @pytest.mark.asyncio
    async def test_entitlement_code_minus_373_raises_data_entitlement(self) -> None:
        """Fyers code -373 → DataEntitlementError."""
        adapter = _FakeAdapterForFetch({"s": "error", "code": -373, "message": "no entitlement"})
        with pytest.raises(DataEntitlementError):
            await _fetch_chain_with_spot(adapter, "NIFTY", None)

    @pytest.mark.asyncio
    async def test_entitlement_flag_raises_data_entitlement(self) -> None:
        """Legacy entitlement flag → DataEntitlementError."""
        adapter = _FakeAdapterForFetch({"entitlement": True, "s": "error"})
        with pytest.raises(DataEntitlementError):
            await _fetch_chain_with_spot(adapter, "NIFTY", None)

    @pytest.mark.asyncio
    async def test_generic_error_raises_503(self) -> None:
        """Non-ok response with arbitrary code → HTTPException 503."""
        adapter = _FakeAdapterForFetch({"s": "error", "code": -300, "message": "some error"})
        with pytest.raises(HTTPException) as exc_info:
            await _fetch_chain_with_spot(adapter, "NIFTY", None)
        assert exc_info.value.status_code == 503
        assert "code -300" in exc_info.value.detail
        assert "some error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_error_without_code_or_message_raises_503(self) -> None:
        """Non-ok response with no code/message → HTTPException 503 with repr."""
        adapter = _FakeAdapterForFetch({"s": "error"})
        with pytest.raises(HTTPException) as exc_info:
            await _fetch_chain_with_spot(adapter, "NIFTY", None)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_ok_response_returns_chain_and_spot(self) -> None:
        """Legitimate ok response → returns (chain, spot)."""
        adapter = _FakeAdapterForFetch({
            "s": "ok",
            "option_chain": [{"strike": 24500, "option_type": "CE"}],
            "underlying_ltp": 24750.0,
        })
        chain, spot = await _fetch_chain_with_spot(adapter, "NIFTY", None)
        assert len(chain) == 1
        assert spot == 24750.0

    @pytest.mark.asyncio
    async def test_ok_empty_chain_returns_empty_list(self) -> None:
        """Ok with empty option_chain → returns ([], None) (legitimate empty)."""
        adapter = _FakeAdapterForFetch({"s": "ok", "option_chain": []})
        chain, spot = await _fetch_chain_with_spot(adapter, "NIFTY", None)
        assert chain == []
        assert spot is None
