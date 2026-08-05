"""Instrument-master bootstrap for the terminal lifespan."""
from __future__ import annotations

import logging

from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster

logger = logging.getLogger(__name__)


def init_instrument_master(
    db_path: str = "data/fyers_instruments.db",
    max_age_hours: float = 24.0,
) -> FyersInstrumentMaster | None:
    """Create the FyersInstrumentMaster backed by the local SQLite mirror.

    Refreshes the public master files on first run AND whenever the local
    mirror is older than ``max_age_hours`` (F-INT-008: the master is
    refreshed every trading day, so a populated-but-stale database misses new
    expiries and changed lot sizes). The master JSON is a public download, so
    this works even when only an access token exists.
    """
    try:
        master = FyersInstrumentMaster(db_path=db_path, max_age_hours=max_age_hours)
        counts = master.ensure_fresh(max_age_hours=max_age_hours)
        if counts is not None:
            logger.info("Fyers instrument master refreshed: %s", counts)
        return master
    except Exception as exc:
        logger.error("Instrument master unavailable: %s", exc)
        return None
