"""Idempotent Dhan adapter + pipeline bootstrap (lifespan AND post-OAuth-login)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

from fastapi import FastAPI

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.core.storage.time_series_store import TimeSeriesStore
from shettyxtreme.data.ingestion import IngestionPipeline
from shettyxtreme.integration.dhan.data_adapter import DhanDataAdapter
from shettyxtreme.integration.dhan.trading_adapter import DhanTradingAdapter
from shettyxtreme.terminal.api.instrument_init import init_instrument_master

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


async def init_terminal_adapters(
    app: FastAPI,
    store: CredentialStore,
    symbol_map: dict[str, str],
) -> bool:
    """Idempotently initialize Dhan adapters + ingestion pipelines.

    Safe to call repeatedly: skips entirely once a full success has been
    recorded (app.state.terminal_initialized). Raises nothing — failures are
    logged and False is returned (the health projection reports the degraded
    state). A partial failure leaves no marker, so the next call re-attempts
    the whole init, disconnecting any adapters orphaned by the failed run.
    """
    if getattr(app.state, "terminal_initialized", False):
        return True

    # Re-run: disconnect adapters/pipelines orphaned by a previous partial
    # failure before constructing replacements.
    stale_trading = getattr(app.state, "trading_adapter", None)
    if stale_trading is not None:
        try:
            await stale_trading.disconnect()
        except Exception:
            logger.warning("Failed to disconnect stale trading adapter", exc_info=True)
        app.state.trading_adapter = None
        logger.info("Disconnected stale DhanTradingAdapter before re-init")

    stale_pipeline = getattr(app.state, "ingestion_pipeline", None)
    if stale_pipeline is not None:
        try:
            await stale_pipeline.stop()
        except Exception:
            logger.warning("Failed to stop stale ingestion pipeline", exc_info=True)
        app.state.ingestion_pipeline = None
        logger.info("Stopped stale IngestionPipeline before re-init")

    ok = True
    try:
        trading_adapter = DhanTradingAdapter(
            client_id=store.client_id,
            access_token=store.access_token,
        )
        app.state.trading_adapter = trading_adapter
        logger.info("DhanTradingAdapter initialized")
    except Exception as exc:
        ok = False
        logger.error("Failed to initialize DhanTradingAdapter: %s", exc)

    try:
        data_adapter = DhanDataAdapter(
            client_id=store.client_id,
            access_token=store.access_token,
            data_access_token=store.data_access_token,
        )
        app.state.data_adapter = data_adapter
        logger.info("DhanDataAdapter initialized")
        data_adapter.set_symbol_map(symbol_map)

        # Instrument master: symbol <-> security ID resolution for the
        # watchlist add path.
        app.state.instrument_master = init_instrument_master(data_adapter)

        watchlist_proj = getattr(app.state, "watchlist_projection", None)
        event_bus = getattr(app.state, "event_bus", None)
        watchlist_data = watchlist_proj.get() if watchlist_proj is not None else {}
        if not watchlist_data:
            logger.warning("Watchlist empty — pipeline not started")
        elif event_bus is None:
            ok = False
            logger.warning("Event bus missing — pipeline not started")
        else:
            # Group watchlist symbols by exchange for correct MarketFeed
            # subscription; feed subscribes by security ID, the projection is
            # keyed by display name (watchlist rows show NIFTY, not 13).
            exchange_groups: dict[str, list[str]] = {}
            for sym, info in watchlist_data.items():
                exch = info.get("exchange", "NSE_FNO")
                feed_segment = {"NSE_FNO": "NSE_FNO", "NSE": "NSE_EQ", "BSE": "BSE_EQ"}.get(exch, exch)
                feed_symbol = info.get("security_id") or sym
                exchange_groups.setdefault(feed_segment, []).append(feed_symbol)

            ts_store = TimeSeriesStore()
            # Start one pipeline per exchange segment
            for feed_segment, symbols in exchange_groups.items():
                pipeline_exchange = {"NSE_FNO": "NFO", "NSE_EQ": "NSE", "BSE_EQ": "BSE"}.get(feed_segment, "NSE")
                pipeline = IngestionPipeline(
                    event_bus=event_bus,
                    ts_store=ts_store,
                    dhan_client_id=store.client_id,
                    dhan_access_token=store.access_token,
                    exchange=pipeline_exchange,
                    symbol_map=symbol_map,
                )
                app.state.ingestion_pipeline = pipeline
                await pipeline.start(symbols)
                logger.info(
                    "IngestionPipeline started for %s with symbols: %s",
                    feed_segment,
                    symbols,
                )
    except Exception as exc:
        ok = False
        logger.error("Failed to initialize DhanDataAdapter or IngestionPipeline: %s", exc)

    if ok:
        app.state.terminal_initialized = True

    return ok
