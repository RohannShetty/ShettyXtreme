"""Scanner engine — 11 opportunity scanner types.

Exports:
  - ``SCANNER_REGISTRY``: list of ``(ScannerType, class)`` tuples for wiring.
  - All scanner classes for direct import.
  - Legacy scanners (GapScanner, PriceBreakoutScanner) preserved for back-compat.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.core.event_bus import EventBus

from .base_scanner import BaseScanner, ScannerType
from .breakout_scanner import PriceBreakoutScanner
from .calendar_spread_scanner import CalendarSpreadScanner
from .gap_fill_scanner import GapFillScanner
from .gap_scanner import GapScanner
from .gamma_spike_scanner import GammaSpikeScanner
from .iv_crush_scanner import IVCrushScanner
from .iv_expansion_scanner import IVExpansionScanner
from .max_pain_drift_scanner import MaxPainDriftScanner
from .oi_buildup_scanner import OIBuildupScanner
from .pcr_extremes_scanner import PCRExtremesScanner
from .theta_harvest_scanner import ThetaHarvestScanner
from .vertical_skew_scanner import VerticalSkewScanner
from .volume_anomaly_scanner import VolumeAnomalyScanner

# ── Scanner registry (type → class) ────────────────────────────────────────
# Tier A: event-driven (subscribe MARKET_DATA_BAR)
# Tier B: snapshot-driven (called by chain poller)
SCANNER_REGISTRY: list[tuple[ScannerType, type[BaseScanner]]] = [
    # Tier A — event-driven
    (ScannerType.GAP_FILL, GapFillScanner),
    (ScannerType.VOLUME_ANOMALY, VolumeAnomalyScanner),
    (ScannerType.OI_BUILDUP, OIBuildupScanner),
    # Tier B — snapshot-driven (chain poller calls scan())
    (ScannerType.GAMMA_SPIKE, GammaSpikeScanner),
    (ScannerType.IV_CRUSH, IVCrushScanner),
    (ScannerType.IV_EXPANSION, IVExpansionScanner),
    (ScannerType.PCR_EXTREMES, PCRExtremesScanner),
    (ScannerType.MAX_PAIN_DRIFT, MaxPainDriftScanner),
    (ScannerType.THETA_HARVEST, ThetaHarvestScanner),
    (ScannerType.CALENDAR_SPREAD, CalendarSpreadScanner),
    (ScannerType.VERTICAL_SKEW, VerticalSkewScanner),
]

# All 11 scanner type values for validation
ALL_SCANNER_TYPES: list[str] = [st.value for st in ScannerType]


def instantiate_scanners(
    event_bus: EventBus,
    **shared_kwargs: Any,
) -> list[BaseScanner]:
    """Instantiate all registered scanners with the given event_bus.

    Args:
        event_bus: The EventBus instance.
        **shared_kwargs: Extra kwargs passed to every scanner constructor
            (e.g. ``oi_tracker=..., iv_rank_calculator=...``).

    Returns:
        List of instantiated scanner objects.
    """
    scanners: list[BaseScanner] = []
    for _st, cls in SCANNER_REGISTRY:
        try:
            scanners.append(cls(event_bus=event_bus, **shared_kwargs))
        except TypeError:
            # Some scanners may not accept all shared_kwargs — retry with
            # only event_bus.
            scanners.append(cls(event_bus=event_bus))
    return scanners


__all__ = [
    "BaseScanner",
    "ScannerType",
    "SCANNER_REGISTRY",
    "ALL_SCANNER_TYPES",
    "instantiate_scanners",
    "PriceBreakoutScanner",
    "GapScanner",
    "GapFillScanner",
    "VolumeAnomalyScanner",
    "OIBuildupScanner",
    "GammaSpikeScanner",
    "IVCrushScanner",
    "IVExpansionScanner",
    "PCRExtremesScanner",
    "MaxPainDriftScanner",
    "ThetaHarvestScanner",
    "CalendarSpreadScanner",
    "VerticalSkewScanner",
]
