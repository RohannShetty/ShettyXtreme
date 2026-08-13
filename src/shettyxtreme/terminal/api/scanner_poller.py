"""Tier-B scanner poller (Phase 3A.1).

8 of the 11 opportunity scanners are snapshot-driven: they never subscribe
to an event topic, so nothing ever called ``scan()`` on them. This module
owns the background loop that walks the cached chain snapshot
(``app.state.options_chain``, populated by ``prime_options_chain`` and the
v2 chain endpoint) every 15s and dispatches each Tier-B scanner against it.

Kept out of ``app.py`` so the composition root stays under the 1000-line
god-module guard and the loop is unit-testable in isolation.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI

from shettyxtreme.intelligence.scanners import TIER_B_SCANNER_TYPES
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType

logger = logging.getLogger(__name__)

_SCANNER_POLL_CADENCE_SECONDS = 15.0


def _scanner_poll_dte(app: FastAPI, symbol: str) -> int:
    """Best-effort days-to-expiry for a symbol (defaults to ~91d when unknown).

    Resolves the default expiry through the instrument master, then converts
    the time-to-expiry (years) to days. A large DTE keeps the DTE-gated
    scanners (iv_crush, max_pain_drift, theta_harvest) conservative — they
    simply won't fire — instead of fabricating a finding.
    """
    from shettyxtreme.integration.fyers.symbols import resolve_default_expiry
    from shettyxtreme.terminal.api.intelligence_router import _expiry_to_tte

    expiry: str | None = None
    master = getattr(app.state, "instrument_master", None)
    if master is not None:
        try:
            expiries = master.list_expiries(
                symbol.strip().upper(), exchange="NSE", instrument_type="OPTION"
            )
            if expiries:
                expiry = resolve_default_expiry(symbol.strip().upper(), expiries)
        except Exception:
            logger.debug("scanner poll: expiry resolution failed for %s", symbol, exc_info=True)
    tte = _expiry_to_tte(expiry)
    return max(int(round(tte * 365)), 1)


def _atm_iv(enriched: list[dict], spot: float) -> float:
    """IV of the CE contract nearest the spot price (0.0 when unavailable)."""
    if not enriched or spot <= 0:
        return 0.0
    best_iv = 0.0
    best_dist = float("inf")
    for c in enriched:
        try:
            strike = float(c.get("strike", 0) or 0)
            iv = float(c.get("iv", 0) or 0)
        except (TypeError, ValueError):
            continue
        if strike <= 0 or iv <= 0:
            continue
        if str(c.get("option_type", "")).upper() not in ("CE", "CALL"):
            continue
        dist = abs(strike - spot)
        if dist < best_dist:
            best_dist = dist
            best_iv = iv
    return best_iv


async def _safe_scanner_scan(scanner: BaseScanner | None, method: str, *args: object) -> None:
    """Call one scanner method, swallowing per-scanner failures."""
    if scanner is None:
        return
    fn = getattr(scanner, method, None)
    if fn is None:
        return
    try:
        await fn(*args)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "scanner poll: %s.%s failed", type(scanner).__name__, method
        )


async def _run_scanner_poll(app: FastAPI) -> None:
    """One poll pass: run all 8 Tier-B scanners against the cached chain.

    For every symbol in ``app.state.options_chain`` the chain is enriched
    once (greeks/IV) and dispatched to each Tier-B scanner with the data its
    ``scan()`` signature needs. A scanner absent from ``app.state.scanners``
    is skipped; per-scanner errors are logged and do not abort the pass.
    """
    scanners = getattr(app.state, "scanners", None) or []
    by_type: dict[str, BaseScanner] = {}
    for scanner in scanners:
        st = getattr(scanner, "scanner_type", None)
        if isinstance(st, ScannerType):
            type_value = st.value
        elif st is not None:
            type_value = str(st)
        else:
            type_value = "unknown"
        by_type[type_value] = scanner
    if not any(t in by_type for t in TIER_B_SCANNER_TYPES):
        return

    from shettyxtreme.terminal.api.intelligence_router import (
        _enrich_chain,
        _expiry_to_tte,
        _feed_options_calculators,
    )

    chain_cache = getattr(app.state, "options_chain", {}) or {}
    for symbol, entry in chain_cache.items():
        if isinstance(entry, dict):
            contracts = entry.get("contracts", [])
            raw_spot = entry.get("spot")
        else:
            contracts = entry
            raw_spot = None
        if not isinstance(contracts, list) or not contracts:
            continue
        try:
            spot = float(raw_spot) if raw_spot is not None else 0.0
        except (TypeError, ValueError):
            spot = 0.0
        dte = _scanner_poll_dte(app, symbol)
        expiry = ""  # not stored in the snapshot; resolved only for DTE
        try:
            _feed_options_calculators(app, contracts, symbol, expiry)
        except Exception:
            logger.debug("scanner poll: calculator feed failed for %s", symbol, exc_info=True)
        try:
            enriched = [
                c.model_dump() for c in _enrich_chain(contracts, spot or None, tte=_expiry_to_tte(None))
            ]
        except Exception:
            logger.debug("scanner poll: chain enrichment failed for %s", symbol, exc_info=True)
            enriched = []
        atm_iv = _atm_iv(enriched, spot)

        await _safe_scanner_scan(by_type.get("gamma_spike"), "scan_chain", symbol, enriched)
        await _safe_scanner_scan(by_type.get("iv_crush"), "scan", symbol, atm_iv, dte)
        await _safe_scanner_scan(by_type.get("iv_expansion"), "scan", symbol, atm_iv)
        await _safe_scanner_scan(by_type.get("pcr_extremes"), "scan", symbol)
        await _safe_scanner_scan(
            by_type.get("max_pain_drift"), "scan", symbol, spot, contracts, dte
        )
        await _safe_scanner_scan(
            by_type.get("theta_harvest"), "scan", symbol, spot, enriched, dte
        )
        # Calendar spread needs two expiries; the snapshot holds one chain per
        # symbol, so the weekly chain is scanned against an empty monthly set
        # (no-op without a second expiry — documented limitation).
        await _safe_scanner_scan(by_type.get("calendar_spread"), "scan", symbol, enriched, [])
        await _safe_scanner_scan(by_type.get("vertical_skew"), "scan", symbol, enriched)


async def _scanner_poll_loop(
    app: FastAPI, cadence: float = _SCANNER_POLL_CADENCE_SECONDS
) -> None:
    """Background loop: poll the chain snapshot and run Tier-B scanners."""
    while True:
        try:
            await _run_scanner_poll(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scanner poller iteration failed")
        await asyncio.sleep(cadence)
