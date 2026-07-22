"""Open Interest tracker and alert generator.

Monitors OI changes by subscribing to EventBus option chain data.
Detects unusual OI build-up, OI decline, and computes put/call OI ratio.
Stores OI snapshots in-memory for comparison across time periods.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shettyxtreme.core.event_bus import Event, EventBus, Topic


@dataclass
class OISnapshot:
    """A snapshot of open interest for a specific option contract."""

    symbol: str
    expiry: str
    strike: float
    option_type: str  # "CE" or "PE"
    oi: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
        else:
            self._oi_data.clear()
            self._previous_oi.clear()

    @property
    def tracked_symbols(self) -> list[str]:
        """Return list of symbols being tracked."""
        return list(self._oi_data.keys())

    async def _on_market_data(self, event: Event) -> None:
        """Handle MARKET_DATA_BAR events from EventBus.

        Args:
            event: The event containing option chain data.
        """
        data = event.data
        if isinstance(data, dict):
            symbol = data.get("symbol", "")
            expiry = data.get("expiry", "")
            contracts = data.get("contracts", [])
            if symbol and expiry and contracts:
                self.update_from_chain(symbol, expiry, contracts)
