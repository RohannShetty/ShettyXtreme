"""Instrument-master bootstrap for the terminal lifespan."""
from __future__ import annotations

import logging

from shettyxtreme.integration.dhan.data_adapter import DhanDataAdapter
from shettyxtreme.integration.instrument_master import InstrumentMaster

logger = logging.getLogger(__name__)


def init_instrument_master(
    data_adapter: DhanDataAdapter,
    db_path: str = "data/instruments.db",
) -> InstrumentMaster | None:
    """Create the InstrumentMaster backed by the data adapter's Dhan client.

    Fetches the security list on first run so symbol <-> security ID
    resolution works for the watchlist add path. The security CSV is a
    public download, so this works even when only a data token exists.
    """
    try:
        master = InstrumentMaster(
            db_path=db_path,
            dhan_client=data_adapter.dhan_client,
        )
        if master.count_instruments() == 0:
            fetched = master.fetch_security_list()
            logger.info("Instrument master populated: %d instruments", fetched)
        return master
    except Exception as exc:
        logger.error("Instrument master unavailable: %s", exc)
        return None
