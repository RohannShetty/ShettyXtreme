"""Mode-aware order executor — routes placement per execution mode (D10).

The ModeRoutingExecutor implements core.interfaces.order_executor.OrderExecutor
and decides the placement target at call time:

    OBSERVER  -> never places (proposals only, human approval never auto-routes)
    PAPER     -> PaperTradingEngine (simulated fills, in-memory book)
    LIVE      -> FyersTradingAdapter.place_order (real broker, human-gated)

Safety (binding, D10):
  - an armed kill switch blocks ALL placement, every mode
  - OBSERVER never places, no exceptions
  - LIVE requires the live adapter to be initialized (provider returns None
    otherwise) and the mode gate is enforced at the mode-switch endpoint
    (confirm=true, server-side) — this router is the second line of defense

Mode and kill-switch state are read lazily via callables so runtime changes
(mode switches, kill-switch toggles) take effect on the next placement call.

Kill-switch TOCTOU hardening (Phase 6 Lane B): a shared asyncio.Event-based
KillSwitchGate is consulted twice — once at entry and again immediately
before the broker await (after any pre-await) — so an arm that lands while
this coroutine was suspended cannot slip an order onto the wire. Wire
entries are accounted on the gate so arming can report placements that
crossed the wire during the arm window.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from shettyxtreme.core.data_models import OrderRequest, OrderResult, OrderStatus
from shettyxtreme.execution.kill_switch import KillSwitchGate
from shettyxtreme.execution.paper_trading import PaperTradingEngine

logger = logging.getLogger(__name__)


class ModeRoutingExecutor:
    """Routes OrderExecutor.place_order to the engine matching the current mode."""

    def __init__(
        self,
        paper_engine: PaperTradingEngine | None,
        mode_provider: Callable[[], str],
        kill_switch_provider: Callable[[], bool],
        live_provider: Callable[[], object] | None = None,
        kill_gate: KillSwitchGate | None = None,
    ) -> None:
        self._paper = paper_engine
        self._mode_provider = mode_provider
        self._kill_provider = kill_switch_provider
        self._live_provider = live_provider
        # Shared asyncio.Event gate (Phase 6 Lane B): armed instantly
        # in-process and re-checked immediately before the broker await.
        self._kill_gate = kill_gate

    # ------------------------------------------------------------------
    # OrderExecutor protocol
    # ------------------------------------------------------------------
    def _kill_armed(self) -> bool:
        """Armed via either layer: the legacy provider callable or the shared
        asyncio gate. The gate is authoritative when wired (production); the
        provider stays for backward compat with existing callers/tests."""
        if self._kill_provider():
            return True
        return self._kill_gate is not None and self._kill_gate.is_armed()

    def _gate(self) -> KillSwitchGate | None:
        """The shared gate for wire accounting, or None (no accounting)."""
        return self._kill_gate

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """Route one order to the engine for the current mode (D10)."""
        if self._kill_armed():
            return self._reject(
                "kill switch armed - placement blocked (all modes)"
            )
        mode = str(self._mode_provider() or "OBSERVER").upper()
        if mode == "OBSERVER":
            return self._reject(
                "OBSERVER mode never places orders - switch to PAPER or LIVE"
            )
        if mode == "PAPER":
            if self._paper is None:
                return self._reject("paper engine not initialized")
            return await self._place_paper(order)
        if mode == "LIVE":
            live = self._live_provider() if self._live_provider else None
            if live is None:
                return self._reject(
                    "live trading adapter not initialized - cannot place"
                )
            # Session-validity gate (D10 / mission §9 Q5): the broker token
            # (Fyers daily tokens, no silent refresh) must be live before any
            # real order reaches the wire. The class is probed (not the
            # instance) so mocks / adapters without the method default to
            # True (backward compat with the Protocol addition).
            is_session_valid = getattr(type(live), "is_session_valid", None)
            if callable(is_session_valid) and not is_session_valid(live):
                return self._reject("token expired — re-auth required")
            return await self._dispatch_live(live, order)
        return self._reject(f"unknown execution mode: {mode}")

    async def _dispatch_live(self, live: object, order: OrderRequest) -> OrderResult:
        """Final kill gate — immediately before the wire, after any pre-await.

        The kill switch can be armed while this coroutine was suspended (a
        concurrent HTTP arm request, or a future pre-wire await): re-check
        here so an order that passed the first gate cannot reach the broker
        once armed. The residual window is the single final call — the
        inherent TOCTOU of any check-before-act (recon §5.3). Wire entry/exit
        are accounted on the shared gate so arming can report placements that
        crossed the wire during the arm window.
        """
        if self._kill_armed():
            return self._reject(
                "kill switch armed - placement blocked (all modes)"
            )
        gate = self._gate()
        if gate is not None:
            gate.note_wire_entry()
        try:
            result = await live.place_order(order)
        finally:
            if gate is not None:
                gate.note_wire_exit()
        if gate is not None and gate.is_armed():
            logger.warning(
                "order %s crossed the wire during the kill-switch arm window",
                order.symbol,
            )
        return result

    async def modify_order(self, order_id: str, order: OrderRequest) -> OrderResult:
        """Modify an order on the engine for the current mode (D10).

        Real orders can only be modified in LIVE mode. OBSERVER/PAPER are
        rejected outright; LIVE requires the adapter, a valid session, and a
        disarmed kill switch — same gates as placement.
        """
        mode = str(self._mode_provider() or "OBSERVER").upper()
        if mode == "OBSERVER":
            return self._reject(
                "OBSERVER mode never modifies orders - switch to PAPER or LIVE"
            )
        if mode == "PAPER":
            return self._reject(
                "PAPER mode cannot modify orders - switch to LIVE"
            )
        if mode == "LIVE":
            if self._kill_armed():
                return self._reject(
                    "kill switch armed - modify blocked (all modes)"
                )
            live = self._live_provider() if self._live_provider else None
            if live is None:
                return self._reject(
                    "live trading adapter not initialized - cannot modify"
                )
            # Session-validity gate, same class-probe as place_order so mocks
            # without the method default to valid (backward compat).
            is_session_valid = getattr(type(live), "is_session_valid", None)
            if callable(is_session_valid) and not is_session_valid(live):
                return self._reject("token expired — re-auth required")
            # Final gate, same as placement: an arm that landed during any
            # pre-wire await must block the real order change (Phase 6 Lane B).
            if self._kill_armed():
                return self._reject(
                    "kill switch armed - modify blocked (all modes)"
                )
            return await live.modify_order(order_id, order)
        return self._reject(f"unknown execution mode: {mode}")

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order on the engine for the current mode (D10).

        Route by mode exactly like placement: LIVE cancels go to the live
        adapter (gated on session validity + kill switch), PAPER/OBSERVER
        cancels go to the paper engine. Previously the paper engine was
        checked first, so LIVE cancels never reached the broker (F-CORE-005).
        """
        mode = str(self._mode_provider() or "OBSERVER").upper()
        if mode == "LIVE":
            if self._kill_armed():
                logger.warning("cancel blocked: kill switch armed")
                return False
            live = self._live_provider() if self._live_provider else None
            if live is None:
                logger.warning(
                    "cancel blocked: live trading adapter not initialized"
                )
                return False
            is_session_valid = getattr(type(live), "is_session_valid", None)
            if callable(is_session_valid) and not is_session_valid(live):
                logger.warning("cancel blocked: token expired — re-auth required")
                return False
            return await live.cancel_order(order_id)
        if mode in ("PAPER", "OBSERVER"):
            if self._paper is None:
                logger.warning("cancel blocked: paper engine not initialized")
                return False
            return await self._paper.cancel_order(order_id)
        logger.warning("cancel blocked: unknown execution mode: %s", mode)
        return False

    async def get_order_status(self, order_id: str) -> OrderResult:
        live = self._live_provider() if self._live_provider else None
        if live is not None:
            return await live.get_order_status(order_id)
        return self._reject("no placement target initialized")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _place_paper(self, order: OrderRequest) -> OrderResult:
        """Bridge the placement request -> PaperTradingEngine.place_order."""
        # Final gate before the (simulated) paper placement — same double-check
        # as the live wire so an arm that landed mid-flow blocks every mode.
        if self._kill_armed():
            return self._reject(
                "kill switch armed - placement blocked (all modes)"
            )
        assert self._paper is not None
        result = await self._paper.place_order(
            symbol=order.symbol,
            exchange=order.exchange,
            side=self._enum_value(order.side),
            order_type=self._enum_value(order.order_type),
            quantity=order.quantity,
            price=order.price or 0.0,
            trigger_price=order.trigger_price,
            tag=order.tag,
        )
        status = OrderStatus[str(result.status).upper()] if result.status in OrderStatus._member_names_ else OrderStatus.REJECTED
        return OrderResult(
            order_id=result.order_id,
            status=status,
            message=result.message,
            filled_quantity=result.filled_quantity,
            average_price=result.average_price,
            rejected_reason=result.message if status == OrderStatus.REJECTED else None,
        )

    @staticmethod
    def _enum_value(value: object) -> str:
        if value is None:
            return ""
        return value.value if hasattr(value, "value") else str(value)

    @staticmethod
    def _reject(reason: str) -> OrderResult:
        logger.warning("placement blocked: %s", reason)
        return OrderResult(
            order_id="",
            status=OrderStatus.REJECTED,
            message=reason,
            rejected_reason=reason,
        )
