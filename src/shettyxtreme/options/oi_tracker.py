"""Open Interest tracker and alert generator.

Monitors OI changes by subscribing to EventBus option chain data.
Detects unusual OI build-up, OI decline, and computes put/call OI ratio.
Stores OI snapshots in-memory for comparison across time periods.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic


@dataclass
class OISnapshot:
    """A snapshot of open interest for a specific option contract."""

    symbol: str
    expiry: str
    strike: float
    option_type: str  # "CE" or "PE"
    oi: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OIAlert:
    """Alert generated when unusual OI activity is detected."""

    symbol: str
    expiry: str
    strike: float
    option_type: str
    oi_change_percent: float
    current_oi: int
    previous_oi: int
    significance: str  # "HIGH", "MEDIUM", "LOW"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class OITracker:
    """Monitor open interest changes and generate alerts.

    Subscribes to EventBus for option chain data and tracks OI changes
    across expiries and strikes. Detects unusual OI activity.

    Usage:
        tracker = OITracker(event_bus)
        alerts = tracker.check_alerts()  # Returns list of OIAlert
    """

    # Thresholds for unusual activity
    HIGH_CHANGE_THRESHOLD = 100.0  # 100% change = HIGH significance
    MEDIUM_CHANGE_THRESHOLD = 50.0  # 50% change = MEDIUM significance
    LOW_CHANGE_THRESHOLD = 25.0  # 25% change = LOW significance

    def __init__(self, event_bus: EventBus | None = None) -> None:
        """Initialise the OI tracker.

        Args:
            event_bus: Optional EventBus to subscribe to for option chain data.
        """
        self._oi_data: dict[str, dict[str, dict[tuple[float, str], int]]] = (
            defaultdict(lambda: defaultdict(dict))
        )
        # Structure: {symbol: {expiry: {(strike, option_type): oi}}}
        self._previous_oi: dict[str, dict[str, dict[tuple[float, str], int]]] = (
            defaultdict(lambda: defaultdict(dict))
        )
        self._snapshots: list[OISnapshot] = []
        self._alerts: list[OIAlert] = []
        #: Symbol-level OI observations derived from MARKET_DATA_BAR bars
        #: (bars carry aggregate per-symbol OI, not per-contract chains).
        self._symbol_oi: dict[str, list[int]] = defaultdict(list)

        if event_bus is not None:
            event_bus.subscribe(Topic.MARKET_DATA_BAR, self._on_market_data)

    def update_from_chain(
        self,
        symbol: str,
        expiry: str,
        contracts: list[dict[str, Any]],
    ) -> list[OIAlert]:
        """Update OI data from an option chain and check for alerts.

        Args:
            symbol: Underlying symbol.
            expiry: Expiry date string.
            contracts: List of contract dicts with 'strike', 'option_type', 'oi' keys.

        Returns:
            List of OIAlert objects for any unusual activity detected.
        """
        alerts: list[OIAlert] = []

        for contract in contracts:
            strike = float(contract.get("strike", 0))
            option_type = str(contract.get("option_type", "")).upper()
            oi = int(contract.get("oi", 0))

            # Only track CE/PE
            if option_type not in ("CE", "PE"):
                continue

            key = (strike, option_type)

            # Get previous OI
            prev_oi = self._oi_data[symbol][expiry].get(key, 0)

            # Store current OI as previous before updating
            self._previous_oi[symbol][expiry][key] = prev_oi
            self._oi_data[symbol][expiry][key] = oi

            # Store snapshot
            self._snapshots.append(
                OISnapshot(
                    symbol=symbol,
                    expiry=expiry,
                    strike=strike,
                    option_type=option_type,
                    oi=oi,
                )
            )

            # Detect changes
            if prev_oi > 0:
                change_pct = ((oi - prev_oi) / prev_oi) * 100.0
                alert = self._check_alert_level(
                    symbol, expiry, strike, option_type,
                    change_pct, oi, prev_oi,
                )
                if alert:
                    alerts.append(alert)
                    self._alerts.append(alert)

        return alerts

    def _check_alert_level(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        option_type: str,
        change_pct: float,
        current_oi: int,
        previous_oi: int,
    ) -> OIAlert | None:
        """Check if OI change warrants an alert."""
        abs_change = abs(change_pct)
        if abs_change >= self.HIGH_CHANGE_THRESHOLD:
            significance = "HIGH"
        elif abs_change >= self.MEDIUM_CHANGE_THRESHOLD:
            significance = "MEDIUM"
        elif abs_change >= self.LOW_CHANGE_THRESHOLD:
            significance = "LOW"
        else:
            return None

        return OIAlert(
            symbol=symbol,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            oi_change_percent=round(change_pct, 2),
            current_oi=current_oi,
            previous_oi=previous_oi,
            significance=significance,
        )

    def get_pcr(self, symbol: str, expiry: str | None = None) -> float:
        """Compute put/call OI ratio for a symbol.

        Args:
            symbol: Underlying symbol.
            expiry: Optional expiry filter. If None, uses all expiries.

        Returns:
            Put/Call OI ratio as a float.
        """
        total_call_oi = 0
        total_put_oi = 0
        if symbol not in self._oi_data:
            return 0.0
        expiries = [expiry] if expiry else list(self._oi_data[symbol].keys())

        for exp in expiries:
            for (strike, opt_type), oi in self._oi_data[symbol][exp].items():
                if opt_type == "CE":
                    total_call_oi += oi
                elif opt_type == "PE":
                    total_put_oi += oi

        if total_call_oi == 0:
            return 0.0
        return round(total_put_oi / total_call_oi, 4)

    def get_oi(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        option_type: str,
    ) -> int:
        """Get current OI for a specific contract.

        Args:
            symbol: Underlying symbol.
            expiry: Expiry date string.
            strike: Strike price.
            option_type: 'CE' or 'PE'.

        Returns:
            Current OI value, or 0 if not tracked.
        """
        return self._oi_data.get(symbol, {}).get(expiry, {}).get(
            (strike, option_type.upper()), 0
        )

    def get_oi_change(
        self,
        symbol: str,
        expiry: str,
        strike: float,
        option_type: str,
    ) -> float:
        """Get OI change percentage for a specific contract.

        Args:
            symbol: Underlying symbol.
            expiry: Expiry date string.
            strike: Strike price.
            option_type: 'CE' or 'PE'.

        Returns:
            OI change percentage, or 0.0 if not tracked.
        """
        key = (strike, option_type.upper())
        current = self._oi_data.get(symbol, {}).get(expiry, {}).get(key, 0)
        previous = self._previous_oi.get(symbol, {}).get(expiry, {}).get(key, 0)
        if previous == 0:
            return 0.0
        return round(((current - previous) / previous) * 100.0, 2)

    def get_alerts(self, min_significance: str = "LOW") -> list[OIAlert]:
        """Get all alerts filtered by minimum significance level.

        Args:
            min_significance: Minimum significance level ('LOW', 'MEDIUM', 'HIGH').

        Returns:
            List of OIAlert objects.
        """
        levels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        min_level = levels.get(min_significance, 0)
        return [
            a for a in self._alerts
            if levels.get(a.significance, 0) >= min_level
        ]

    def clear_alerts(self) -> None:
        """Clear all stored alerts."""
        self._alerts.clear()

    def clear_oi_data(self, symbol: str | None = None) -> None:
        """Clear OI data for one or all symbols.

        Args:
            symbol: If provided, clears data only for this symbol.
                    If None, clears all data.
        """
        if symbol:
            self._oi_data.pop(symbol, None)
            self._previous_oi.pop(symbol, None)
            self._symbol_oi.pop(symbol, None)
        else:
            self._oi_data.clear()
            self._previous_oi.clear()
            self._symbol_oi.clear()

    @property
    def tracked_symbols(self) -> list[str]:
        """Return list of symbols being tracked."""
        return list(self._oi_data.keys())

    def record_symbol_oi(self, symbol: str, oi: Any) -> None:
        """Record a symbol-level OI observation carried by a bar event.

        F-KNOW-004: MARKET_DATA_BAR events carry a ``Bar`` (OHLCV aggregate
        with an optional per-symbol ``oi`` field), NOT an option chain. Bars
        have no expiry/strike/option_type, so they cannot feed the per-contract
        ``update_from_chain`` path — their aggregate OI is recorded here so OI
        direction changes remain observable even without a full chain.

        Args:
            symbol: Underlying symbol.
            oi: Open interest value (int-able).
        """
        try:
            self._symbol_oi[symbol].append(int(oi))
        except (TypeError, ValueError):
            return

    def get_symbol_oi(self, symbol: str) -> list[int]:
        """Return recorded symbol-level OI observations (oldest first).

        Args:
            symbol: Underlying symbol.

        Returns:
            List of OI values observed from bar events, empty if none.
        """
        return list(self._symbol_oi.get(symbol, []))

    def get_pcr_history(self, symbol: str = "NIFTY", days: int = 30) -> list[dict[str, Any]]:
        """Return a per-poll put/call OI ratio time series.

        Phase 3A.3: exposes the per-contract snapshot list as a PCR history
        for the PCR chart. Contracts from the same chain poll are bucketed by
        their timestamp truncated to the second (one poll lands within a
        single second), summed per option side, and the PCR is computed per
        bucket, oldest first.

        Args:
            symbol: Underlying symbol to compute PCR for.
            days: How many days of history to return (default 30). Clamped
                to >= 1.

        Returns:
            Chronological list of ``{timestamp, pcr, total_call_oi,
            total_put_oi}`` dicts; empty when no snapshots exist for the
            symbol within the window.
        """
        if not self._snapshots:
            return []
        cutoff = datetime.now(UTC) - timedelta(days=max(1, days))
        buckets: dict[datetime, list[int]] = {}
        for snap in self._snapshots:
            if snap.symbol != symbol or snap.timestamp < cutoff:
                continue
            bucket_ts = snap.timestamp.replace(microsecond=0)
            counts = buckets.setdefault(bucket_ts, [0, 0])
            if snap.option_type == "CE":
                counts[0] += snap.oi
            elif snap.option_type == "PE":
                counts[1] += snap.oi

        result: list[dict[str, Any]] = []
        for ts in sorted(buckets):
            total_call_oi, total_put_oi = buckets[ts]
            pcr = round(total_put_oi / total_call_oi, 4) if total_call_oi > 0 else 0.0
            result.append({
                "timestamp": ts.isoformat(),
                "pcr": pcr,
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
            })
        return result

    async def _on_market_data(self, event: Event) -> None:
        """Handle MARKET_DATA_BAR events from EventBus.

        F-KNOW-004: the bus's MARKET_DATA_BAR topic carries ``Bar`` objects
        (``core.data_models.Bar``), not the ``{symbol, expiry, contracts}``
        option-chain dict this handler originally assumed. Accept the real
        payloads:

        - ``Bar`` (or bar-shaped dict ``{symbol, oi, ...}``) → record the
          symbol-level OI via :meth:`record_symbol_oi` (a bar carries no
          per-contract chain).
        - option-chain dict ``{symbol, expiry, contracts}`` → feed
          :meth:`update_from_chain` (kept for publishers that emit chains).

        Args:
            event: The event containing bar or option chain data.
        """
        data = event.data
        if isinstance(data, Bar):
            if data.oi is not None:
                self.record_symbol_oi(data.symbol, data.oi)
            return
        if not isinstance(data, dict):
            return
        contracts = data.get("contracts")
        if contracts:
            symbol = data.get("symbol", "")
            expiry = data.get("expiry", "")
            if symbol and expiry:
                self.update_from_chain(symbol, expiry, contracts)
            return
        # Bar-shaped dict payload: {symbol, oi, ...}
        symbol = data.get("symbol", "")
        oi = data.get("oi")
        if symbol and oi is not None:
            self.record_symbol_oi(symbol, oi)
