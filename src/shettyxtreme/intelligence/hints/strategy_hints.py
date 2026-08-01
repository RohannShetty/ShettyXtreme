"""Strategy hint generation — regime + signal + chain → trade structure.

Blueprint §14 stage 4: turn the aggregate signal (D/P/G) and the option
chain into a concrete strategy suggestion with an EV line item.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shettyxtreme.intelligence.options.options_intel import (
    compute_signal_drift_ev,
    select_strike_by_ev,
)
from shettyxtreme.learning.sizing import CalibratedSizing
from shettyxtreme.options.strategy_analyzer import StrategyAnalyzer

_CONVICTION_GATE: float = 0.25
_PARTICIPATION_GATE: float = 0.5
_DEFAULT_DTE: int = 7


def _safe_float(value: Any, default: float) -> float:
    """Coerce to float; fall back to the default on junk (never 500s)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class StrategyHint:
    direction: str  # bullish / bearish / neutral
    strategy: str
    strike: float | None = None
    premium: float | None = None
    ev_after_cost: float = 0.0
    rationale: str = ""
    quantity: int | None = None


class StrategyHints:
    """Generate a strategy hint from the signal and (optional) chain."""

    def __init__(
        self,
        signal: dict[str, Any],
        chain: list[dict[str, Any]] | None = None,
        current_price: float | None = None,
        slippage_per_lot: float = 5.0,
        brokerage_per_lot: float = 20.0,
        days_to_expiry: int = _DEFAULT_DTE,
        sizing: CalibratedSizing | None = None,
        base_quantity: int = 75,
    ) -> None:
        self._signal = signal
        self._chain = chain or []
        self._current_price = current_price
        self._slippage = slippage_per_lot
        self._brokerage = brokerage_per_lot
        self._dte = days_to_expiry
        self._sizing = sizing
        self._base_quantity = base_quantity

    def generate(self) -> StrategyHint:
        direction = str(self._signal.get("direction", "NEUTRAL")).upper()
        conviction = float(self._signal.get("conviction", 0.0))
        participation = float(self._signal.get("P", 1.0))

        if direction == "NEUTRAL":
            return StrategyHint(
                direction="neutral",
                strategy="stand_aside",
                rationale=(
                    "Signal is NEUTRAL — no directional edge to pay premium for. "
                    "Stand aside until participation or conviction returns."
                ),
            )
        if conviction < _CONVICTION_GATE:
            return StrategyHint(
                direction="neutral",
                strategy="stand_aside",
                rationale=(
                    f"Signal is {direction} but conviction {conviction:.2f} is below "
                    f"the {_CONVICTION_GATE:.2f} gate — insufficient edge for a structure."
                ),
            )
        if participation < _PARTICIPATION_GATE:
            return StrategyHint(
                direction="neutral",
                strategy="stand_aside",
                rationale=(
                    f"Participation {participation:.0%} is too low — data-starved "
                    "voters make the signal unreliable."
                ),
            )

        bullish = direction == "UP"
        hint_dir = "bullish" if bullish else "bearish"
        option_type = "CE" if bullish else "PE"
        strategy_name = StrategyAnalyzer.display_name("long_call" if bullish else "long_put")

        quantity: int | None = None
        if self._sizing is not None and self._sizing.active:
            quantity = self._sizing.adjust(self._base_quantity, conviction)

        selected = self._select_strike(option_type, conviction, bullish)
        if selected is None:
            return StrategyHint(
                direction=hint_dir,
                strategy=strategy_name,
                quantity=quantity,
                rationale=(
                    f"{hint_dir.capitalize()} signal with conviction {conviction:.2f}; "
                    f"no strike in the chain offers positive EV after costs "
                    f"(slippage {self._slippage:.0f} + brokerage {self._brokerage:.0f} per lot)."
                ),
            )
        return StrategyHint(
            direction=hint_dir,
            strategy=strategy_name,
            strike=selected["strike"],
            premium=selected["premium"],
            ev_after_cost=selected["ev"],
            quantity=quantity,
            rationale=(
                f"{hint_dir.capitalize()} conviction {conviction:.2f} "
                f"(participation {participation:.0%}); best strike {selected['strike']:.0f} "
                f"{option_type} @ premium {selected['premium']:.2f} with EV "
                f"{selected['ev']:.2f} after slippage + brokerage."
            ),
        )

    def _select_strike(
        self, option_type: str, conviction: float, bullish: bool,
    ) -> dict[str, Any] | None:
        if self._current_price is None:
            return None

        def _usable(row: dict[str, Any]) -> bool:
            """Drop rows whose numeric fields are junk (would break coercion)."""
            for key in ("strike", "strike_price", "premium", "iv"):
                if row.get(key) is not None:
                    try:
                        float(row[key])
                    except (TypeError, ValueError):
                        return False
            return True

        def _row_option_type(row: dict[str, Any]) -> str:
            return str(row.get("option_type") or row.get("drv_option_type") or "").upper()

        def _row_strike(row: dict[str, Any]) -> float:
            return _safe_float(row.get("strike") if row.get("strike") is not None else row.get("strike_price", 0.0), 0.0)

        strikes = [
            {
                "strike": _row_strike(s),
                "premium": _safe_float(s.get("premium"), 0.0),
                "iv": _safe_float(s.get("iv"), 15.0),
            }
            for s in self._chain
            if isinstance(s, dict)
            and _row_option_type(s) == option_type
            and not (_row_strike(s) == 0.0 and s.get("premium") is None)
            and _usable(s)
        ]
        if not strikes:
            return None
        iv = _safe_float(strikes[0].get("iv"), 15.0)
        best = select_strike_by_ev(
            strikes=strikes,
            direction=1.0 if bullish else -1.0,
            conviction=conviction,
            current_price=self._current_price,
            slippage_per_lot=self._slippage,
            brokerage_per_lot=self._brokerage,
            iv=iv,
            days_to_expiry=self._dte,
        )
        if best is None:
            return None
        strike = _safe_float(best.get("strike"), 0.0)
        premium = _safe_float(best.get("premium"), 0.0)
        ev = compute_signal_drift_ev(
            direction=1.0 if bullish else -1.0,
            conviction=conviction,
            current_price=self._current_price,
            strike=strike,
            premium=premium,
            slippage=self._slippage,
            brokerage=self._brokerage,
            iv=_safe_float(best.get("iv"), iv),
            days_to_expiry=self._dte,
        )
        return {"strike": strike, "premium": premium, "ev": ev}
