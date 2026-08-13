"""Scanner engine — 11 opportunity scanner types.

Exports:
  - ``SCANNER_REGISTRY``: list of ``(ScannerType, class)`` tuples for wiring.
  - ``SCANNER_THRESHOLD_SPECS``: configurable threshold params per scanner
    type (Phase 3A.1) — name → (module, attr) for module-constant-backed
    params, or name → (None, None) for constructor-kwarg-backed params.
  - ``TIER_B_SCANNER_TYPES``: snapshot-driven scanners run by the chain poller.
  - All scanner classes for direct import.
  - Legacy scanners (GapScanner, PriceBreakoutScanner) preserved for back-compat.
"""
from __future__ import annotations

from typing import Any

from shettyxtreme.core.event_bus import EventBus

from . import (
    calendar_spread_scanner,
    gap_fill_scanner,
    gamma_spike_scanner,
    iv_crush_scanner,
    iv_expansion_scanner,
    max_pain_drift_scanner,
    theta_harvest_scanner,
    vertical_skew_scanner,
    volume_anomaly_scanner,
)
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

#: Snapshot-driven scanners — the chain poller runs ``scan()`` on these.
TIER_B_SCANNER_TYPES: frozenset[str] = frozenset({
    ScannerType.GAMMA_SPIKE.value,
    ScannerType.IV_CRUSH.value,
    ScannerType.IV_EXPANSION.value,
    ScannerType.PCR_EXTREMES.value,
    ScannerType.MAX_PAIN_DRIFT.value,
    ScannerType.THETA_HARVEST.value,
    ScannerType.CALENDAR_SPREAD.value,
    ScannerType.VERTICAL_SKEW.value,
})

# ── Configurable thresholds (Phase 3A.1) ────────────────────────────────────
# scanner_type value → public param name → (target_kind, target, default)
#   target_kind "module": target = (module, attribute) — the scanner reads the
#       module constant at scan time, so we reset + override the module global.
#   target_kind "kwarg":  target = constructor keyword — flows through
#       ``instantiate_scanners`` kwargs (BaseScanner stores extras in _params).
SCANNER_THRESHOLD_SPECS: dict[str, dict[str, tuple[str, Any, Any]]] = {
    ScannerType.GAMMA_SPIKE.value: {
        "gamma_spike_multiplier": ("module", (gamma_spike_scanner, "_GAMMA_SPIKE_MULTIPLIER"), 2.0),
        "min_observations": ("module", (gamma_spike_scanner, "_MIN_OBSERVATIONS"), 2),
    },
    ScannerType.IV_CRUSH.value: {
        "iv_rank_threshold": ("module", (iv_crush_scanner, "_IV_RANK_THRESHOLD"), 80.0),
        "dte_threshold": ("module", (iv_crush_scanner, "_DTE_THRESHOLD"), 2),
    },
    ScannerType.IV_EXPANSION.value: {
        "iv_rank_low": ("module", (iv_expansion_scanner, "_IV_RANK_LOW"), 20.0),
        "vix_1d_return_threshold": ("module", (iv_expansion_scanner, "_VIX_1D_RETURN_THRESHOLD"), 10.0),
    },
    ScannerType.PCR_EXTREMES.value: {
        "pcr_low": ("kwarg", "pcr_low", 0.5),
        "pcr_high": ("kwarg", "pcr_high", 1.5),
    },
    ScannerType.MAX_PAIN_DRIFT.value: {
        "drift_threshold": ("module", (max_pain_drift_scanner, "_DRIFT_THRESHOLD"), 2.0),
        "dte_threshold": ("module", (max_pain_drift_scanner, "_DTE_THRESHOLD"), 3),
    },
    ScannerType.THETA_HARVEST.value: {
        "theta_vega_ratio": ("module", (theta_harvest_scanner, "_THETA_VEGA_RATIO"), 3.0),
        "dte_threshold": ("module", (theta_harvest_scanner, "_DTE_THRESHOLD"), 10),
    },
    ScannerType.CALENDAR_SPREAD.value: {
        "iv_diff_threshold": ("module", (calendar_spread_scanner, "_IV_DIFF_THRESHOLD"), 15.0),
    },
    ScannerType.VERTICAL_SKEW.value: {
        "skew_threshold": ("module", (vertical_skew_scanner, "_SKEW_THRESHOLD"), 5.0),
    },
    ScannerType.GAP_FILL.value: {
        "gap_threshold": ("module", (gap_fill_scanner, "_GAP_THRESHOLD"), 1.0),
    },
    ScannerType.VOLUME_ANOMALY.value: {
        "volume_multiplier": ("module", (volume_anomaly_scanner, "_VOLUME_MULTIPLIER"), 3.0),
        "price_change_epsilon": ("module", (volume_anomaly_scanner, "_PRICE_CHANGE_EPSILON"), 0.5),
    },
    ScannerType.OI_BUILDUP.value: {
        "oi_change_threshold": ("kwarg", "threshold", 20.0),
    },
}


def _reset_threshold_defaults() -> None:
    """Restore every threshold-bearing module constant to its default.

    Called at the start of ``instantiate_scanners`` so repeated wiring is
    deterministic (operator overrides apply only for the current call).
    """
    for _specs in SCANNER_THRESHOLD_SPECS.values():
        for _kind, _target, _default in _specs.values():
            if _kind == "module":
                _mod, _attr = _target
                setattr(_mod, _attr, _default)


def _apply_thresholds(thresholds: dict[str, dict[str, Any]] | None) -> None:
    """Apply operator thresholds: module-constant overrides + kwarg mapping.

    ``thresholds`` maps scanner_type value → public param name → value.
    Unknown scanner types / params are ignored (the settings router validates
    against ``SCANNER_THRESHOLD_SPECS`` upstream; core stays permissive).
    """
    if not thresholds:
        return
    for scanner_type, params in thresholds.items():
        specs = SCANNER_THRESHOLD_SPECS.get(scanner_type)
        if not specs or not isinstance(params, dict):
            continue
        for param_name, value in params.items():
            spec = specs.get(param_name)
            if spec is None:
                continue
            kind, target, _default = spec
            if kind == "module":
                mod, attr = target
                setattr(mod, attr, value)


def instantiate_scanners(
    event_bus: EventBus,
    thresholds: dict[str, dict[str, Any]] | None = None,
    **shared_kwargs: Any,
) -> list[BaseScanner]:
    """Instantiate all registered scanners with the given event_bus.

    Args:
        event_bus: The EventBus instance.
        thresholds: Optional per-scanner threshold overrides, mapping
            scanner_type value → param name → value. Keys must match
            ``SCANNER_THRESHOLD_SPECS`` (module constants are overridden in
            place; constructor-kwarg params are passed through).
        **shared_kwargs: Extra kwargs passed to every scanner constructor
            (e.g. ``oi_tracker=..., iv_rank_calculator=...``).

    Returns:
        List of instantiated scanner objects.
    """
    _reset_threshold_defaults()
    _apply_thresholds(thresholds)
    scanners: list[BaseScanner] = []
    for _st, cls in SCANNER_REGISTRY:
        kwargs: dict[str, Any] = dict(shared_kwargs)
        if thresholds:
            type_thresholds = thresholds.get(_st.value)
            if type_thresholds:
                for param_name, value in type_thresholds.items():
                    spec = SCANNER_THRESHOLD_SPECS.get(_st.value, {}).get(param_name)
                    if spec is not None and spec[0] == "kwarg":
                        kwargs[spec[1]] = value
        try:
            scanners.append(cls(event_bus=event_bus, **kwargs))
        except TypeError:
            # Some scanners may not accept all shared_kwargs — retry with
            # only event_bus.
            scanners.append(cls(event_bus=event_bus))
    return scanners


__all__ = [
    "BaseScanner",
    "ScannerType",
    "SCANNER_REGISTRY",
    "SCANNER_THRESHOLD_SPECS",
    "TIER_B_SCANNER_TYPES",
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
