"""Instrument-master bootstrap for the terminal lifespan."""
from __future__ import annotations

import logging

from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster

logger = logging.getLogger(__name__)


def init_instrument_master(
    db_path: str = "data/fyers_instruments.db",
) -> FyersInstrumentMaster | None:
    """Create the FyersInstrumentMaster backed by the local SQLite mirror.

    Refreshes the public master files on first run so internal-symbol ->
    Fyers-ticker resolution works for the watchlist add path and the
    round-trip gate. The master JSON is a public download, so this works
    even when only an access token exists.
    """
    try:
        master = FyersInstrumentMaster(db_path=db_path)
        if master.count_instruments() == 0:
            counts = master.refresh()
            logger.info("Fyers instrument master populated: %s", counts)
        return master
    except Exception as exc:
        logger.error("Instrument master unavailable: %s", exc)
        return None
