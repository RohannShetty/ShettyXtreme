"""Idempotent Fyers adapter + pipeline bootstrap (lifespan AND post-OAuth-login).

Wires the F4 Fyers adapters (REST trading, market-data, HSM data socket,
JSON order socket) into the terminal: trading/data adapters on app.state,
live ticks bridged onto the EventBus for the watchlist projection and bar
builder, and order-socket updates forwarded to the ORDER_UPDATED topic
(Fyers has no postback webhooks — fills arrive over the order socket).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from fastapi import FastAPI

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.core.storage.time_series_store import TimeSeriesStore
from shettyxtreme.data.pipeline.bar_builder import BarBuilder
from shettyxtreme.integration.fyers.client import FyersHTTPClient
from shettyxtreme.integration.fyers.data_adapter import FyersDataAdapter
from shettyxtreme.integration.fyers.data_socket import FyersDataSocketWrapper
from shettyxtreme.integration.fyers.session import FyersSession
from shettyxtreme.integration.fyers.symbols import FyersSymbolResolver
from shettyxtreme.integration.fyers.trading_adapter import FyersTradingAdapter
from shettyxtreme.integration.fyers.ws_client import FyersOrderSocket
from shettyxtreme.terminal.api import postback_router
from shettyxtreme.terminal.api.instrument_init import init_instrument_master
from shettyxtreme.terminal.api.intelligence_router import prime_options_chain

logger = logging.getLogger(__name__)

# The wiring hook set by the lifespan; called by the OAuth callback after a
# successful consent exchange. Replaced in tests.
_init_terminal_adapters: Callable[[], Coroutine[Any, Any, bool]] | None = None


def wire_terminal_init(
    init_fn: Callable[[], Coroutine[Any, Any, bool]],
) -> None:
    """Register the async bootstrap the auth callback triggers post-login."""
    global _init_terminal_adapters
    _init_terminal_adapters = init_fn


async def run_terminal_init() -> bool:
    """Run the registered bootstrap (no-op when not wired). Returns success."""
    if _init_terminal_adapters is None:
        return False
    return await _init_terminal_adapters()


def _to_bus_tick(tick: Any) -> Any:
    """Convert a Fyers-adapter Tick to the EventBus Tick dataclass.

    F-CORE-001: ``core.interfaces.Tick`` and ``core.data_models.Tick`` are now
    the same class, so adapter ticks pass straight through — ``oi`` (and any
    future field) flows onto the bus untouched. The fallback constructor is
    kept only for foreign tick shapes and also forwards ``oi``.
    """
    from shettyxtreme.core.data_models import Tick as BusTick

    if isinstance(tick, BusTick):
        return tick
    return BusTick(
        symbol=tick.symbol,
        exchange=tick.exchange,
        ltp=tick.ltp,
        volume=tick.volume,
        timestamp=tick.timestamp,
        bid=tick.bid,
        ask=tick.ask,
        open=tick.open,
        high=tick.high,
        low=tick.low,
        close=tick.close,
        oi=getattr(tick, "oi", None),
    )


def _build_session_and_transport(
    store: CredentialStore,
) -> tuple[FyersSession, FyersHTTPClient] | None:
    """Rehydrate the Fyers session and REST transport from the credential store."""
    session = FyersSession.load(store)
    if session is None:
        return None
    client = FyersHTTPClient(app_id=session.app_id, access_token=session.access_token)
    return session, client


async def init_terminal_adapters(
    app: FastAPI,
    store: CredentialStore,
    symbol_map: dict[str, str],
) -> bool:
    """Idempotently initialize Fyers adapters + the market-data bridge.

    Safe to call repeatedly: skips entirely once a full success has been
    recorded (app.state.terminal_initialized). Raises nothing — failures are
    logged and False is returned (the health projection reports the degraded
    state). A partial failure leaves no marker, so the next call re-attempts
    the whole init, disconnecting any adapters orphaned by the failed run.
    """
    if getattr(app.state, "terminal_initialized", False):
        return True

    # Re-run: disconnect adapters/sockets orphaned by a previous partial
    # failure before constructing replacements.
    stale_trading = getattr(app.state, "trading_adapter", None)
    if stale_trading is not None:
        try:
            await stale_trading.disconnect()
        except Exception:
            logger.warning("Failed to disconnect stale trading adapter", exc_info=True)
        app.state.trading_adapter = None
        logger.info("Disconnected stale FyersTradingAdapter before re-init")

    stale_data = getattr(app.state, "data_adapter", None)
    if stale_data is not None:
        try:
            await stale_data.disconnect()
        except Exception:
            logger.warning("Failed to disconnect stale data adapter", exc_info=True)
        app.state.data_adapter = None
        logger.info("Disconnected stale FyersDataAdapter before re-init")

    built = _build_session_and_transport(store)
    if built is None:
        logger.warning("No Fyers access token — adapters not initialized")
        return False
    session, client = built

    ok = True
    try:
        master = init_instrument_master()
        symbol_resolver = FyersSymbolResolver(master)
        order_socket = FyersOrderSocket(
            app_id=session.app_id, access_token=session.access_token
        )
        data_socket = FyersDataSocketWrapper(
            app_id=session.app_id, access_token=session.access_token
        )
        trading_adapter = FyersTradingAdapter(
            session=session,
            client=client,
            symbol_resolver=symbol_resolver,
        )
        data_adapter = FyersDataAdapter(
            session=session,
            client=client,
            symbol_resolver=symbol_resolver,
            order_socket=order_socket,
            data_socket=data_socket,
        )
        app.state.fyers_session = session
        app.state.fyers_client = client
        app.state.instrument_master = master
        app.state.symbol_resolver = symbol_resolver
        app.state.fyers_order_socket = order_socket
        app.state.fyers_data_socket = data_socket
        app.state.trading_adapter = trading_adapter
        app.state.data_adapter = data_adapter
        logger.info(
            "Fyers adapters initialized (session client=%s)",
            session.access_token[-4:] if session.access_token else "none",
        )
    except Exception as exc:
        ok = False
        logger.error("Failed to initialize Fyers adapters: %s", exc)

    # Live market-data bridge + order-update bridge (best-effort).
    pipeline_started = False
    try:
        event_bus: EventBus | None = getattr(app.state, "event_bus", None)
        watchlist_proj = getattr(app.state, "watchlist_projection", None)
        watchlist_data = watchlist_proj.get() if watchlist_proj is not None else {}
        if not watchlist_data:
            logger.warning("Watchlist empty — market-data bridge not started")
        elif event_bus is None:
            ok = False
            logger.warning("Event bus missing — market-data bridge not started")
        else:
            data_adapter = app.state.data_adapter
            assert data_adapter is not None

            # Bar aggregation: the BarBuilder is broker-neutral and consumes
            # MARKET_DATA_TICK events, so start it before bridging ticks.
            ts_store = TimeSeriesStore()
            bar_builder = BarBuilder(event_bus=event_bus, ts_store=ts_store)
            await bar_builder.start()
            app.state.bar_builder = bar_builder

            async def _publish_market_tick(tick: Any) -> None:
                await event_bus.publish(Event(
                    topic=Topic.MARKET_DATA_TICK,
                    data=_to_bus_tick(tick),
                    source="fyers_data_adapter",
                ))

            symbols = list(watchlist_data.keys())
            subscribed = await data_adapter.subscribe_ticks(symbols, _publish_market_tick)
            if not subscribed:
                ok = False
                logger.warning(
                    "Fyers tick subscription failed for %d symbols", len(symbols)
                )
            else:
                pipeline_started = True
                logger.info(
                    "Fyers market-data bridge wired for %d watchlist symbols",
                    len(symbols),
                )

            # Order updates (replaces Dhan postback webhooks). Connect both
            # sockets best-effort: a missing data-socket SDK or an expired
            # token degrades to REST-only instead of failing the whole init.
            order_socket = getattr(app.state, "fyers_order_socket", None)
            if order_socket is not None:
                order_socket.on_message(postback_router.consume_order_message)

                # F-INT-004: surface socket transport errors / closes on the
                # SYSTEM_STATUS topic so fatal conditions are visible to the
                # app instead of being silent logger lines.
                async def _publish_socket_status(status: str, detail: Any = None) -> None:
                    data: dict[str, Any] = {"status": status}
                    if detail is not None:
                        data["error"] = str(detail)
                    await event_bus.publish(Event(
                        topic=Topic.SYSTEM_STATUS,
                        data=data,
                        source="fyers_order_socket",
                    ))

                async def _on_order_socket_error(exc: Any) -> None:
                    logger.error("Fyers order socket error: %s", exc)
                    await _publish_socket_status("data_socket_error", exc)

                async def _on_order_socket_close() -> None:
                    logger.warning("Fyers order socket closed")
                    await _publish_socket_status("data_socket_closed")

                order_socket.on_error(_on_order_socket_error)
                order_socket.on_close(_on_order_socket_close)

                try:
                    connected = await data_adapter.connect()
                    if connected:
                        await order_socket.subscribe(["orders", "trades"])
                        logger.info("Fyers order socket subscribed to orders/trades")
                    else:
                        logger.warning(
                            "Fyers sockets not fully connected — REST-only mode"
                        )
                except Exception:
                    logger.warning(
                        "Fyers socket connect failed — REST-only mode", exc_info=True
                    )
    except Exception as exc:
        ok = False
        logger.error("Failed to wire Fyers data bridge: %s", exc)

    # Only pin the marker when the market-data bridge actually started: an
    # empty-watchlist run stays cheap-to-retry, so a later re-init self-heals
    # once symbols exist.
    if ok and pipeline_started:
        app.state.terminal_initialized = True

    # Prime the options-chain cache (Wave 1 #12). The research options_posture
    # tool reads app.state.options_chain, which was only ever written by
    # GET /api/intelligence/options — so it showed [UNSOURCED] until that
    # endpoint had been hit once. Fetch NIFTY now that the data adapter
    # exists; failures degrade gracefully (cache left untouched, honest
    # [UNSOURCED] retained). Runs on every successful (re-)init, covering
    # both the lifespan startup and the post-OAuth-login bootstrap paths.
    if ok:
        try:
            await prime_options_chain(app)
        except Exception:
            logger.warning("options chain prime failed", exc_info=True)

    return ok
