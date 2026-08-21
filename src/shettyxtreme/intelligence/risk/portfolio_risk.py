"""Portfolio risk aggregator — computes all 4 risk heat map dimensions.

Pure, EventBus-agnostic module computing:
1. Sectoral exposure — group notional by sector
2. Greeks concentration — sum portfolio greeks with long/short breakdown
3. Max-loss scenario — ±5%/±10% spot shift stress test
4. Margin utilization — margin_used/available with breach state

Lives in intelligence/risk/ (imports core/ + options/ only — never integration/).
Instrument master lookups come in via dependency injection (Protocol).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# ── Protocols for dependency injection ──────────────────────────────────────


class InstrumentLookup(Protocol):
    """Protocol for looking up instrument metadata (strike/expiry/type/lot_size).

    Satisfied by integration/fyers/instrument_master.py's FyersInstrumentMaster
    and by test fakes. Passed into the aggregator — never imported directly.
    """

    def lookup(self, fyers_symbol: str) -> dict[str, Any] | None:
        """Look up one instrument by Fyers ticker. Returns row dict or None."""
        ...

    def search(
        self,
        internal_symbol: str,
        exchange: str | None = None,
        instrument_type: str | None = None,
        expiry: Any = None,
        strike: float | None = None,
        option_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search instruments by internal symbol with optional filters."""
        ...

    def get_lot_size(
        self,
        internal_symbol: str,
        exchange: str = "NSE",
        instrument_type: str = "INDEX",
    ) -> int | None:
        """Lot size for an internal symbol."""
        ...


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SectorExposure:
    """One sector's aggregated exposure."""
    sector: str
    notional: float
    pnl: float
    share_pct: float


@dataclass(frozen=True)
class GreeksBreakdown:
    """Long/short split for one greek."""
    long: float = 0.0
    short: float = 0.0
    net: float = 0.0


@dataclass(frozen=True)
class GreeksConcentration:
    """Portfolio-level greeks with long/short breakdown and lopsided flag."""
    delta: GreeksBreakdown
    gamma: GreeksBreakdown
    theta: GreeksBreakdown
    vega: GreeksBreakdown
    lopsided_warning: str | None = None  # e.g. "all theta, no vega"


@dataclass(frozen=True)
class ScenarioPnl:
    """P&L for one spot shift scenario."""
    shift_pct: float
    total_pnl: float
    per_position: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class StressResult:
    """Max-loss stress test across all scenarios."""
    scenarios: list[ScenarioPnl]
    worst_case_pnl: float = 0.0
    worst_case_shift: float = 0.0


@dataclass(frozen=True)
class MarginUtilization:
    """Margin utilization metric."""
    margin_used: float | None = None
    margin_available: float | None = None
    total: float | None = None
    utilization_pct: float | None = None
    breach: bool = False


@dataclass(frozen=True)
class HeatMapResult:
    """Full heat map output — all 4 dimensions."""
    sector_exposure: list[SectorExposure]
    greeks: GreeksConcentration
    stress: StressResult
    margin: MarginUtilization
    position_count: int = 0
    enriched_count: int = 0  # positions that resolved option metadata


# ── Enrichment helpers ─────────────────────────────────────────────────────


def _resolve_position_metadata(
    raw_position: dict[str, Any],
    instrument_lookup: InstrumentLookup | None,
) -> dict[str, Any]:
    """Resolve option metadata for a position from instrument master.

    Returns a dict with keys: strike, expiry, option_type, lot_size,
    instrument_type, underlying_spot, internal_symbol. Missing fields are
    None — never faked (honesty rule).
    """
    symbol = raw_position.get("symbol", "")
    result: dict[str, Any] = {
        "strike": None,
        "expiry": None,
        "option_type": None,
        "lot_size": None,
        "instrument_type": None,
        "underlying": None,
        "internal_symbol": None,
    }

    # Try to parse option identity from the Fyers symbol
    try:
        from shettyxtreme.integration.fyers.symbols import from_fyers
        parsed = from_fyers(symbol)
        result["instrument_type"] = parsed.get("instrument_type")
        result["strike"] = parsed.get("strike")
        result["option_type"] = parsed.get("option_type")
        result["expiry"] = parsed.get("expiry")
        result["underlying"] = parsed.get("underlying")
        result["internal_symbol"] = parsed.get("internal_symbol")
    except (ValueError, ImportError):
        pass

    # If instrument_lookup is available, get lot_size
    if instrument_lookup is not None:
        try:
            info = instrument_lookup.lookup(symbol)
            if info:
                if result["lot_size"] is None:
                    result["lot_size"] = info.get("lot_size")
                if result["instrument_type"] is None:
                    result["instrument_type"] = info.get("instrument_type")
                if result["strike"] is None:
                    result["strike"] = info.get("strike")
                if result["option_type"] is None:
                    result["option_type"] = info.get("option_type")
                if result["expiry"] is None:
                    result["expiry"] = info.get("expiry")
        except Exception:
            pass

    # Fallback lot_size from position data
    if result["lot_size"] is None:
        result["lot_size"] = raw_position.get("lot_size")

    return result


def _compute_position_stress_pnl(
    position: dict[str, Any],
    meta: dict[str, Any],
    spot: float,
    shift_pct: float,
    iv_map: dict[tuple[float, str], float],
) -> float:
    """Compute P&L for one position under a spot shift scenario.

    Option legs: repriced via Black-76 at shifted spot.
    Futures/equity legs: Δspot × net_quantity.
    Returns 0.0 when repricing is not possible (missing data).
    """
    from shettyxtreme.options.greeks import GreeksCalculator

    net_qty = position.get("net_quantity", 0)
    if net_qty == 0:
        return 0.0

    instrument_type = meta.get("instrument_type")
    strike = meta.get("strike")
    option_type = meta.get("option_type")

    shifted_spot = spot * (1.0 + shift_pct / 100.0)

    # Option legs: reprice at shifted spot
    if instrument_type == "OPTION" and strike and option_type:
        iv = iv_map.get((float(strike), str(option_type).upper()))
        if iv is None or iv <= 0:
            return 0.0
        # Get expiry for TTE
        expiry = meta.get("expiry")
        if expiry is None:
            return 0.0
        try:
            from datetime import datetime
            if hasattr(expiry, "year"):
                expiry_dt = datetime(expiry.year, expiry.month, expiry.day, 15, 30)
            else:
                # ISO string
                parts = str(expiry).split("-")
                expiry_dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 15, 30)
            now = datetime.now()
            tte = (expiry_dt - now).total_seconds() / (365.25 * 24 * 3600)
            tte = max(tte, 1 / 365)
        except (TypeError, ValueError, IndexError):
            return 0.0

        calc = GreeksCalculator(use_quantlib=False)
        opt = "CALL" if str(option_type).upper() == "CE" else "PUT"
        try:
            current_price = calc.calculate_option_price(
                spot=spot, strike=float(strike), tte=tte, iv=iv, option_type=opt,
            )
            shifted_price = calc.calculate_option_price(
                spot=shifted_spot, strike=float(strike), tte=tte, iv=iv, option_type=opt,
            )
            lot_size = meta.get("lot_size") or 1
            return float(net_qty) * (shifted_price - current_price) * float(lot_size)
        except Exception:
            return 0.0

    # Futures/equity legs: linear P&L
    if instrument_type in ("FUTURES", "EQUITY", "INDEX", None):
        buy_avg = position.get("buy_avg", 0.0)
        if buy_avg and buy_avg > 0:
            return float(net_qty) * (shifted_spot - spot)
        return 0.0

    return 0.0


# ── Main aggregator ────────────────────────────────────────────────────────


class PortfolioRiskAggregator:
    """Computes all 4 risk heat map dimensions from portfolio inputs.

    Pure and EventBus-agnostic — receives all data as arguments.
    Instrument master comes in via dependency injection (Protocol).
    """

    def __init__(
        self,
        sector_map: dict[str, str] | None = None,
        instrument_lookup: InstrumentLookup | None = None,
    ) -> None:
        from shettyxtreme.core.knowledge.sector_map import SYMBOL_SECTOR
        self._sector_map = sector_map if sector_map is not None else SYMBOL_SECTOR
        self._instrument_lookup = instrument_lookup

    def compute(
        self,
        positions: list[dict[str, Any]],
        spot_map: dict[str, float] | None = None,
        iv_map: dict[tuple[float, str], float] | None = None,
        margin: dict[str, Any] | None = None,
    ) -> HeatMapResult:
        """Compute all 4 heat map dimensions.

        Args:
            positions: Raw position dicts (from PositionProjection.get()).
            spot_map: symbol→spot price (from WatchlistProjection ticks).
            iv_map: (strike, option_type)→iv (from IV cache / primed chain).
            margin: {available, utilized, total} from trading_adapter.get_margin().

        Returns:
            HeatMapResult with all 4 dimensions. Missing data degrades to
            empty/None — never faked (honesty rule).
        """
        if spot_map is None:
            spot_map = {}
        if iv_map is None:
            iv_map = {}
        if margin is None:
            margin = {}

        # Enrichment pass
        enriched: list[dict[str, Any]] = []
        for pos in positions:
            meta = _resolve_position_metadata(pos, self._instrument_lookup)
            enriched.append({**pos, "_meta": meta})

        # Compute each dimension
        sector_exposure = self._compute_sector_exposure(enriched)
        greeks = self._compute_greeks_concentration(enriched, spot_map, iv_map)
        stress = self._compute_stress(enriched, spot_map, iv_map)
        margin_util = self._compute_margin_utilization(margin)

        enriched_count = sum(
            1 for e in enriched
            if e["_meta"].get("instrument_type") is not None
        )

        return HeatMapResult(
            sector_exposure=sector_exposure,
            greeks=greeks,
            stress=stress,
            margin=margin_util,
            position_count=len(positions),
            enriched_count=enriched_count,
        )

    def _compute_sector_exposure(
        self, enriched: list[dict[str, Any]],
    ) -> list[SectorExposure]:
        """Group notional exposure by sector."""
        sector_data: dict[str, dict[str, float]] = {}
        total_notional = 0.0

        for pos in enriched:
            symbol = pos.get("symbol", "")
            meta = pos.get("_meta", {})
            # Use underlying or internal_symbol from parsed metadata
            base_symbol = meta.get("underlying") or meta.get("internal_symbol")
            if not base_symbol:
                # Fallback: strip exchange prefix and option suffix
                base_symbol = symbol
                for prefix in ("NSE:", "NSE_FNO:", "BSE:"):
                    if base_symbol.startswith(prefix):
                        base_symbol = base_symbol[len(prefix):]
                # Strip trailing -EQ, -INDEX, etc.
                if "-" in base_symbol:
                    base_symbol = base_symbol.rsplit("-", 1)[0]
                # Strip option/future suffix (e.g. NIFTY24AUG24000CE -> NIFTY)
                # Try regex for option patterns
                import re
                m = re.match(r"^([A-Z]+?)(\d{2}[A-Z]{3}|\d{2}\d[A-Z]\d{2})(\d+)(CE|PE)$", base_symbol)
                if m:
                    base_symbol = m.group(1)
                m2 = re.match(r"^([A-Z]+?)(\d{2}[A-Z]{3}|\d{2}\d[A-Z]\d{2})FUT$", base_symbol)
                if m2:
                    base_symbol = m2.group(1)

            sector = self._sector_map.get(base_symbol.upper(), "Unknown")
            notional = abs(pos.get("net_quantity", 0) * pos.get("buy_avg", 0.0))
            pnl = pos.get("pnl", 0.0)

            if sector not in sector_data:
                sector_data[sector] = {"notional": 0.0, "pnl": 0.0}
            sector_data[sector]["notional"] += notional
            sector_data[sector]["pnl"] += pnl
            total_notional += notional

        result: list[SectorExposure] = []
        for sector, data in sorted(
            sector_data.items(), key=lambda x: x[1]["notional"], reverse=True,
        ):
            share = (data["notional"] / total_notional * 100.0) if total_notional > 0 else 0.0
            result.append(SectorExposure(
                sector=sector,
                notional=data["notional"],
                pnl=data["pnl"],
                share_pct=round(share, 2),
            ))
        return result

    def _compute_greeks_concentration(
        self,
        enriched: list[dict[str, Any]],
        spot_map: dict[str, float],
        iv_map: dict[tuple[float, str], float],
    ) -> GreeksConcentration:
        """Sum position greeks with long/short breakdown."""
        from shettyxtreme.options.greeks import GreeksCalculator

        calc = GreeksCalculator(use_quantlib=False)
        delta_long = delta_short = 0.0
        gamma_long = gamma_short = 0.0
        theta_long = theta_short = 0.0
        vega_long = vega_short = 0.0
        has_greeks = False

        for pos in enriched:
            meta = pos.get("_meta", {})
            instrument_type = meta.get("instrument_type")
            strike = meta.get("strike")
            option_type = meta.get("option_type")
            net_qty = pos.get("net_quantity", 0)
            lot_size = meta.get("lot_size") or 1

            if instrument_type != "OPTION" or strike is None or option_type is None:
                continue

            # Get spot for underlying
            underlying = meta.get("underlying", "")
            spot = spot_map.get(underlying) if underlying else None
            if spot is None or spot <= 0:
                continue

            # Get IV
            iv = iv_map.get((float(strike), str(option_type).upper()))
            if iv is None or iv <= 0:
                continue

            # Get TTE from expiry
            expiry = meta.get("expiry")
            if expiry is None:
                continue
            try:
                from datetime import datetime
                if hasattr(expiry, "year"):
                    expiry_dt = datetime(expiry.year, expiry.month, expiry.day, 15, 30)
                else:
                    parts = str(expiry).split("-")
                    expiry_dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 15, 30)
                now = datetime.now()
                tte = (expiry_dt - now).total_seconds() / (365.25 * 24 * 3600)
                tte = max(tte, 1 / 365)
            except (TypeError, ValueError, IndexError):
                continue

            opt = "CALL" if str(option_type).upper() == "CE" else "PUT"
            try:
                unit_greeks = calc.calculate_all(
                    spot=spot, strike=float(strike), tte=tte, iv=iv, option_type=opt,
                )
            except Exception:
                continue

            has_greeks = True
            scale = float(net_qty) * float(lot_size)
            d = scale * unit_greeks.get("delta", 0.0)
            g = scale * unit_greeks.get("gamma", 0.0)
            t = scale * unit_greeks.get("theta", 0.0)
            v = scale * unit_greeks.get("vega", 0.0)

            if d >= 0:
                delta_long += d
            else:
                delta_short += d
            if g >= 0:
                gamma_long += g
            else:
                gamma_short += g
            if t >= 0:
                theta_long += t
            else:
                theta_short += t
            if v >= 0:
                vega_long += v
            else:
                vega_short += v

        if not has_greeks:
            return GreeksConcentration(
                delta=GreeksBreakdown(),
                gamma=GreeksBreakdown(),
                theta=GreeksBreakdown(),
                vega=GreeksBreakdown(),
                lopsided_warning=None,
            )

        delta = GreeksBreakdown(long=delta_long, short=delta_short, net=delta_long + delta_short)
        gamma = GreeksBreakdown(long=gamma_long, short=gamma_short, net=gamma_long + gamma_short)
        theta = GreeksBreakdown(long=theta_long, short=theta_short, net=theta_long + theta_short)
        vega = GreeksBreakdown(long=vega_long, short=vega_short, net=vega_long + vega_short)

        # Detect lopsided profiles
        lopsided: str | None = None
        abs_theta = abs(theta.net)
        abs_vega = abs(vega.net)
        if abs_theta > 0 and abs_vega > 0:
            if abs_theta > 5 * abs_vega:
                lopsided = "all theta, no vega"
            elif abs_vega > 5 * abs_theta:
                lopsided = "all vega, no theta"
        elif abs_theta > 0 and abs_vega == 0:
            lopsided = "all theta, no vega"
        elif abs_vega > 0 and abs_theta == 0:
            lopsided = "all vega, no theta"

        return GreeksConcentration(
            delta=delta, gamma=gamma, theta=theta, vega=vega,
            lopsided_warning=lopsided,
        )

    def _compute_stress(
        self,
        enriched: list[dict[str, Any]],
        spot_map: dict[str, float],
        iv_map: dict[tuple[float, str], float],
    ) -> StressResult:
        """Compute max-loss stress test across ±5%/±10% spot shifts."""
        shifts = [-10.0, -5.0, 5.0, 10.0]
        scenarios: list[ScenarioPnl] = []

        for shift in shifts:
            total_pnl = 0.0
            per_pos: list[dict[str, Any]] = []
            for pos in enriched:
                meta = pos.get("_meta", {})
                underlying = meta.get("underlying", pos.get("symbol", ""))
                spot = spot_map.get(underlying) if underlying else None
                if spot is None or spot <= 0:
                    # Try index-level spot
                    instrument_type = meta.get("instrument_type")
                    if instrument_type in ("INDEX", "FUTURES", "OPTION"):
                        # Use first available spot as fallback
                        for s in spot_map.values():
                            if s > 0:
                                spot = s
                                break
                    if spot is None or spot <= 0:
                        continue

                pnl = _compute_position_stress_pnl(pos, meta, spot, shift, iv_map)
                total_pnl += pnl
                per_pos.append({
                    "symbol": pos.get("symbol", ""),
                    "pnl": round(pnl, 2),
                })

            scenarios.append(ScenarioPnl(
                shift_pct=shift,
                total_pnl=round(total_pnl, 2),
                per_position=per_pos,
            ))

        worst = min(scenarios, key=lambda s: s.total_pnl) if scenarios else None
        return StressResult(
            scenarios=scenarios,
            worst_case_pnl=worst.total_pnl if worst else 0.0,
            worst_case_shift=worst.shift_pct if worst else 0.0,
        )

    def _compute_margin_utilization(
        self, margin: dict[str, Any],
    ) -> MarginUtilization:
        """Compute margin utilization from broker margin data."""
        used = margin.get("utilized")
        available = margin.get("available")
        total = margin.get("total")

        # Parse from nested data if needed
        if used is None:
            used = margin.get("margin_used")
        if available is None:
            available = margin.get("margin_available")

        # Convert to float, None stays None
        try:
            used_f = float(used) if used is not None else None
        except (TypeError, ValueError):
            used_f = None
        try:
            avail_f = float(available) if available is not None else None
        except (TypeError, ValueError):
            avail_f = None
        try:
            total_f = float(total) if total is not None else None
        except (TypeError, ValueError):
            total_f = None

        # Compute utilization percentage
        util_pct: float | None = None
        breach = False
        if used_f is not None and avail_f is not None:
            denom = used_f + avail_f
            if denom > 0:
                util_pct = round(used_f / denom * 100.0, 2)
            breach = used_f > avail_f
        elif used_f is not None and total_f is not None and total_f > 0:
            util_pct = round(used_f / total_f * 100.0, 2)
            breach = used_f > total_f

        return MarginUtilization(
            margin_used=used_f,
            margin_available=avail_f,
            total=total_f,
            utilization_pct=util_pct,
            breach=breach,
        )
