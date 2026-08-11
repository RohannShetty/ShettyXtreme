"""ModeRoutingExecutor cancel/modify routing tests (F-CORE-005).

Covers: cancel_order routes by mode (LIVE -> live adapter, PAPER/OBSERVER ->
paper engine), LIVE cancel gates (session validity + kill switch + missing
adapter), modify_order LIVE gates, modify_order rejected outside LIVE.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from shettyxtreme.core.data_models import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
)
from shettyxtreme.execution.kill_switch import KillSwitchGate
from shettyxtreme.execution.mode_router import ModeRoutingExecutor
from shettyxtreme.execution.paper_trading import PaperTradingEngine


class _SessionExpiredAdapter:
    """Fake live adapter with is_session_valid -> False.

    The router probes the *class* and calls the method with the instance, so
    this mirrors the real adapter's plain instance method (not a classmethod).
    """

    def is_session_valid(self) -> bool:
        return False

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def modify_order(self, order_id: str, order: OrderRequest) -> OrderResult:
        return OrderResult(order_id=order_id, status=OrderStatus.OPEN, message="ok")


def _make_router(
    mode: str = "PAPER",
    live: object | None = None,
    kill: bool = False,
    paper: PaperTradingEngine | None = None,
) -> ModeRoutingExecutor:
    return ModeRoutingExecutor(
        paper_engine=paper if paper is not None else PaperTradingEngine(),
        mode_provider=lambda: mode,
        kill_switch_provider=lambda: kill,
        live_provider=lambda: live,
    )


def _order() -> OrderRequest:
    return OrderRequest(
        symbol="NIFTY",
        exchange="NFO",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=75,
        price=100.0,
    )


# ── cancel_order: routing by mode ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancel_live_routes_to_live_not_paper() -> None:
    live = AsyncMock()
    live.cancel_order = AsyncMock(return_value=True)
    paper = PaperTradingEngine()
    paper.cancel_order = AsyncMock(return_value=True)
    router = _make_router(mode="LIVE", live=live, paper=paper)

    result = await router.cancel_order("LIVE-1")

    assert result is True
    live.cancel_order.assert_awaited_once_with("LIVE-1")
    paper.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_paper_routes_to_paper_not_live() -> None:
    live = AsyncMock()
    live.cancel_order = AsyncMock(return_value=True)
    paper = PaperTradingEngine()
    paper.cancel_order = AsyncMock(return_value=True)
    router = _make_router(mode="PAPER", live=live, paper=paper)

    result = await router.cancel_order("PAPER-1")

    assert result is True
    paper.cancel_order.assert_awaited_once_with("PAPER-1")
    live.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_observer_routes_to_paper() -> None:
    paper = PaperTradingEngine()
    paper.cancel_order = AsyncMock(return_value=True)
    router = _make_router(mode="OBSERVER", paper=paper)

    result = await router.cancel_order("OBS-1")

    assert result is True
    paper.cancel_order.assert_awaited_once_with("OBS-1")


@pytest.mark.asyncio
async def test_cancel_live_missing_adapter_rejected() -> None:
    router = _make_router(mode="LIVE", live=None)

    result = await router.cancel_order("LIVE-1")

    assert result is False


@pytest.mark.asyncio
async def test_cancel_live_session_invalid_blocked() -> None:
    live = _SessionExpiredAdapter()
    router = _make_router(mode="LIVE", live=live)

    result = await router.cancel_order("LIVE-1")

    assert result is False


@pytest.mark.asyncio
async def test_cancel_live_kill_switch_blocks() -> None:
    live = AsyncMock()
    live.cancel_order = AsyncMock(return_value=True)
    router = _make_router(mode="LIVE", live=live, kill=True)

    result = await router.cancel_order("LIVE-1")

    assert result is False
    live.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_paper_missing_engine_returns_false() -> None:
    router = _make_router(mode="PAPER", paper=None)

    result = await router.cancel_order("PAPER-1")

    assert result is False


@pytest.mark.asyncio
async def test_cancel_unknown_mode_returns_false() -> None:
    router = _make_router(mode="WEIRD")

    result = await router.cancel_order("X-1")

    assert result is False


# ── modify_order: LIVE gates ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_modify_live_routes_to_adapter() -> None:
    live = AsyncMock()
    live.modify_order = AsyncMock(
        return_value=OrderResult(order_id="LIVE-1", status=OrderStatus.OPEN, message="ok")
    )
    router = _make_router(mode="LIVE", live=live)

    result = await router.modify_order("LIVE-1", _order())

    assert result.status == OrderStatus.OPEN
    live.modify_order.assert_awaited_once_with("LIVE-1", _order())


@pytest.mark.asyncio
async def test_modify_live_missing_adapter_rejected() -> None:
    router = _make_router(mode="LIVE", live=None)

    result = await router.modify_order("LIVE-1", _order())

    assert result.status == OrderStatus.REJECTED
    assert "not initialized" in result.message


@pytest.mark.asyncio
async def test_modify_live_session_invalid_blocked() -> None:
    live = _SessionExpiredAdapter()
    router = _make_router(mode="LIVE", live=live)

    result = await router.modify_order("LIVE-1", _order())

    assert result.status == OrderStatus.REJECTED
    assert "token expired" in result.message


@pytest.mark.asyncio
async def test_modify_live_kill_switch_blocks() -> None:
    live = AsyncMock()
    live.modify_order = AsyncMock(
        return_value=OrderResult(order_id="LIVE-1", status=OrderStatus.OPEN, message="ok")
    )
    router = _make_router(mode="LIVE", live=live, kill=True)

    result = await router.modify_order("LIVE-1", _order())

    assert result.status == OrderStatus.REJECTED
    assert "kill switch" in result.message
    live.modify_order.assert_not_awaited()


# ── modify_order: rejected outside LIVE ────────────────────────────────────

@pytest.mark.asyncio
async def test_modify_observer_rejected() -> None:
    router = _make_router(mode="OBSERVER")

    result = await router.modify_order("OBS-1", _order())

    assert result.status == OrderStatus.REJECTED
    assert "OBSERVER" in result.message


@pytest.mark.asyncio
async def test_modify_paper_rejected() -> None:
    router = _make_router(mode="PAPER")

    result = await router.modify_order("PAPER-1", _order())

    assert result.status == OrderStatus.REJECTED


@pytest.mark.asyncio
async def test_modify_unknown_mode_rejected() -> None:
    router = _make_router(mode="WEIRD")

    result = await router.modify_order("X-1", _order())

    assert result.status == OrderStatus.REJECTED
    assert "unknown execution mode" in result.message


# ── place_order: LIVE session gate on unknown expiry (F-INT-009) ───────────

@pytest.mark.asyncio
async def test_live_place_blocked_when_session_expiry_unknown() -> None:
    """F-INT-009 regression: unknown token expiry gates LIVE placement.

    Fyers does not publish a token TTL, so a session without a recorded
    expiry cannot be proven live. The session-validity gate must treat it as
    expired and force re-auth instead of waving the order through to the
    broker — this is what makes the LIVE gate honest. Uses the real
    FyersTradingAdapter so the gate is exercised end-to-end, not via a fake.
    """
    from shettyxtreme.integration.fyers.session import FyersSession
    from shettyxtreme.integration.fyers.trading_adapter import FyersTradingAdapter

    session = FyersSession(app_id="APP", secret_id="SEC", access_token="TOK")
    assert session.token_expiry is None
    live = FyersTradingAdapter(
        session=session, client=AsyncMock(), symbol_resolver=None
    )
    router = _make_router(mode="LIVE", live=live)

    result = await router.place_order(_order())

    assert result.status == OrderStatus.REJECTED
    assert "re-auth" in result.message


# ── Kill-switch TOCTOU race regression (Phase 6 Lane B) ──────────────────

def _async_ok(order_id: str = "L-1") -> OrderResult:
    return OrderResult(order_id=order_id, status=OrderStatus.OPEN, message="ok")


@pytest.mark.asyncio
async def test_live_place_double_check_blocks_arm_between_checks() -> None:
    """The final gate re-consults the kill state immediately before the wire.

    Simulates an arm that lands between the entry check and the broker await
    (the TOCTOU window the Phase 6 fix shrinks): the provider flips armed on
    its second call, so the first gate passes and the pre-wire double-check
    must reject — the order never reaches the broker.
    """
    calls = {"n": 0}

    def flip_provider() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    live = AsyncMock()
    live.place_order = AsyncMock(return_value=_async_ok())
    router = _make_router(
        mode="LIVE", live=live, kill=False, paper=PaperTradingEngine()
    )
    router._kill_provider = flip_provider

    result = await router.place_order(_order())

    assert result.status == OrderStatus.REJECTED
    assert "kill switch" in result.message
    live.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_place_gate_armed_blocks_wire_even_when_provider_passes() -> None:
    """The shared asyncio gate is authoritative on its own: armed gate blocks
    the broker call even if the legacy provider reports disarmed."""
    gate = KillSwitchGate("")
    gate.arm()
    live = AsyncMock()
    live.place_order = AsyncMock(return_value=_async_ok())
    router = _make_router(mode="LIVE", live=live, kill=False)
    router._kill_gate = gate

    result = await router.place_order(_order())

    assert result.status == OrderStatus.REJECTED
    assert "kill switch" in result.message
    live.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_in_flight_placement_surfaces_in_arm_report() -> None:
    """Mock concurrent arm + place_order: a placement already dispatched to
    the wire when the operator arms is honestly reported as having crossed
    the wire during the arm window (inherent TOCTOU, surfaced not hidden)."""
    gate = KillSwitchGate("")
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_place(order: OrderRequest) -> OrderResult:
        started.set()
        await proceed.wait()
        return _async_ok()

    live = AsyncMock()
    live.place_order = slow_place
    router = _make_router(mode="LIVE", live=live, kill=False)
    router._kill_gate = gate

    task = asyncio.create_task(router.place_order(_order()))
    await started.wait()  # placement has crossed into the wire
    assert gate.placements_in_flight == 1

    gate.arm()  # operator arms while the placement is in flight
    assert gate.arm_report["placements_in_flight"] == 1

    proceed.set()
    result = await task

    assert result.status == OrderStatus.OPEN
    assert gate.placements_in_flight == 0


@pytest.mark.asyncio
async def test_placements_starting_after_arm_never_reach_wire() -> None:
    """A placement arriving after the gate is armed is rejected before the
    broker await — no wire entry is recorded."""
    gate = KillSwitchGate("")
    gate.arm()
    live = AsyncMock()
    live.place_order = AsyncMock(return_value=_async_ok())
    router = _make_router(mode="LIVE", live=live, kill=False)
    router._kill_gate = gate

    result = await router.place_order(_order())

    assert result.status == OrderStatus.REJECTED
    live.place_order.assert_not_awaited()
    assert gate.placements_in_flight == 0


@pytest.mark.asyncio
async def test_paper_place_double_check_blocks_arm_between_checks() -> None:
    """The paper path gets the same pre-wire double-check (kill blocks all
    modes)."""
    calls = {"n": 0}

    def flip_provider() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    paper = PaperTradingEngine()
    paper.place_order = AsyncMock(return_value=_async_ok())
    router = _make_router(mode="PAPER", kill=False, paper=paper)
    router._kill_provider = flip_provider

    result = await router.place_order(_order())

    assert result.status == OrderStatus.REJECTED
    assert "kill switch" in result.message
    paper.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_modify_live_double_check_blocks_arm_between_checks() -> None:
    """Live modify gets the same pre-wire double-check."""
    calls = {"n": 0}

    def flip_provider() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    live = AsyncMock()
    live.modify_order = AsyncMock(return_value=_async_ok("LIVE-1"))
    router = _make_router(mode="LIVE", live=live, kill=False)
    router._kill_provider = flip_provider

    result = await router.modify_order("LIVE-1", _order())

    assert result.status == OrderStatus.REJECTED
    assert "kill switch" in result.message
    live.modify_order.assert_not_awaited()
