"""Realism models for paper trading — slippage, fees, margin, fill probability.

Injected into PaperTradingEngine to make simulated fills behave like real
Indian-market executions: bid/ask spread, brokerage/STT/GST, probabilistic
limit fills, and margin-based order rejection.

All models are stateless; mutable state (tick counters, cached bid/ask)
lives in the engine.  Each model returns a result dataclass so the engine
can inspect components without coupling to the calculation.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SlippageResult:
    """Result of slippage computation."""
    adjusted_price: float
    slippage_bps: float
    source: str            # "spread", "fixed", "none"


@dataclass
class FeeBreakdown:
    """Itemised transaction costs for a single fill."""
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    total: float

    @staticmethod
    def zero() -> FeeBreakdown:
        return FeeBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@dataclass
class MarginResult:
    """Result of a margin check."""
    required: float
    available: float
    ok: bool


# ---------------------------------------------------------------------------
# Default rates (India, options-focused)
# ---------------------------------------------------------------------------
_DEFAULT_BROKERAGE_FLAT = 20.0        # ₹20 per order
_DEFAULT_BROKERAGE_PCT = 0.0003       # 0.03% of notional
_DEFAULT_STT_BUY = 0.001              # 0.1% buy side (equity delivery)
_DEFAULT_STT_SELL = 0.001             # 0.1% sell side (options)
_DEFAULT_STT_OPTIONS = 0.0001         # 0.01% options premium
_DEFAULT_EXCHANGE_EQUITY = 0.0001     # 0.01% BSE
_DEFAULT_EXCHANGE_OPTIONS = 0.0005    # 0.05% NSE
_DEFAULT_GST_RATE = 0.18              # 18%
_DEFAULT_SEBI_RATE = 0.000001         # ₹10 per crore
_DEFAULT_STAMP_BUY = 0.00003          # 0.003% options buy
_DEFAULT_STAMP_EQUITY = 0.00015       # 0.015% equity delivery


# ---------------------------------------------------------------------------
# Slippage model
# ---------------------------------------------------------------------------

class SlippageModel:
    """Layered slippage calculator.

    Priority:
      1. Spread-based (bid/ask available) → BUY at ask, SELL at bid + residual bps
      2. Fixed bps by order type → MARKET 5 bps, LIMIT 2 bps
      3. Volume-based add-on → +1 bps per 10% of tick volume exceeded
    """

    def __init__(
        self,
        bps_market: float = 5.0,
        bps_limit: float = 2.0,
        residual_bps: float = 2.0,
    ) -> None:
        self._bps_market = bps_market
        self._bps_limit = bps_limit
        self._residual_bps = residual_bps

    def compute(
        self,
        base_price: float,
        side: str,
        order_type: str,
        bid: float | None,
        ask: float | None,
        volume: int,
        quantity: int,
    ) -> SlippageResult:
        """Compute the fill price after slippage.

        Args:
            base_price: LTP or limit price (depending on order type).
            side: "BUY" or "SELL".
            order_type: "MARKET", "LIMIT", or "SL".
            bid/ask: Best bid/ask from the current tick (None when unavailable).
            volume: Tick volume for volume-based add-on.
            quantity: Order quantity.

        Returns:
            SlippageResult with adjusted fill price.
        """
        if base_price <= 0:
            return SlippageResult(base_price, 0.0, "none")

        # --- Layer 1: spread-based (when bid/ask available) ---
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            if side == "BUY":
                price = ask
            else:
                price = bid
            # Add small residual bps on top of the spread
            residual_mult = self._residual_bps / 10_000.0
            if side == "BUY":
                price *= (1.0 + residual_mult)
            else:
                price *= (1.0 - residual_mult)

            # --- Layer 3: volume-based add-on (spread-aware) ---
            vol_bps = self._volume_bps(quantity, volume)
            if vol_bps > 0:
                vol_mult = vol_bps / 10_000.0
                if side == "BUY":
                    price *= (1.0 + vol_mult)
                else:
                    price *= (1.0 - vol_mult)

            return SlippageResult(round(price, 4), self._residual_bps + vol_bps, "spread")

        # --- Layer 2: fixed bps by order type (spread unavailable) ---
        if order_type == "MARKET":
            fixed_bps = self._bps_market
        elif order_type == "LIMIT":
            fixed_bps = self._bps_limit
        else:
            # SL (triggered) — treat like market
            fixed_bps = self._bps_market

        # --- Layer 3: volume-based add-on (fixed-bps path) ---
        vol_bps = self._volume_bps(quantity, volume)
        total_bps = fixed_bps + vol_bps

        mult = total_bps / 10_000.0
        if side == "BUY":
            price = base_price * (1.0 + mult)
        else:
            price = base_price * (1.0 - mult)

        return SlippageResult(round(price, 4), total_bps, "fixed")

    @staticmethod
    def _volume_bps(quantity: int, volume: int) -> float:
        """Volume-based slippage add-on: +1 bps per 10% of tick volume."""
        if volume <= 0:
            return 0.0
        ratio = quantity / volume
        if ratio <= 0.1:
            return 0.0
        increments = math.ceil((ratio - 0.1) / 0.1)
        return float(increments)  # 1 bps per increment


# ---------------------------------------------------------------------------
# India-correct fees model
# ---------------------------------------------------------------------------

class FeesModel:
    """Per-fill transaction cost calculator for Indian markets.

    Components:
      - Brokerage: ₹20 per order OR 0.03% of notional, whichever is lower
      - STT: 0.01% on options premium (sell side), 0.125% on equity sell
      - Exchange: NSE 0.05% (options), BSE 0.01% (equity)
      - GST: 18% on (brokerage + exchange charges + SEBI charges)
      - SEBI: ₹10 per crore (0.0001%)
      - Stamp duty: 0.003% options buy, 0.015% equity delivery buy
    """

    def __init__(
        self,
        brokerage_flat: float = _DEFAULT_BROKERAGE_FLAT,
        brokerage_pct: float = _DEFAULT_BROKERAGE_PCT,
        stt_buy: float = _DEFAULT_STT_BUY,
        stt_sell: float = _DEFAULT_STT_SELL,
        stt_options: float = _DEFAULT_STT_OPTIONS,
        exchange_equity: float = _DEFAULT_EXCHANGE_EQUITY,
        exchange_options: float = _DEFAULT_EXCHANGE_OPTIONS,
        gst_rate: float = _DEFAULT_GST_RATE,
        sebi_rate: float = _DEFAULT_SEBI_RATE,
        stamp_buy: float = _DEFAULT_STAMP_BUY,
        stamp_equity: float = _DEFAULT_STAMP_EQUITY,
    ) -> None:
        self._brokerage_flat = brokerage_flat
        self._brokerage_pct = brokerage_pct
        self._stt_buy = stt_buy
        self._stt_sell = stt_sell
        self._stt_options = stt_options
        self._exchange_equity = exchange_equity
        self._exchange_options = exchange_options
        self._gst_rate = gst_rate
        self._sebi_rate = sebi_rate
        self._stamp_buy = stamp_buy
        self._stamp_equity = stamp_equity

    def compute(
        self,
        quantity: int,
        price: float,
        side: str,
        exchange: str = "",
    ) -> FeeBreakdown:
        """Compute all transaction costs for a single fill.

        Args:
            quantity: Fill quantity.
            price: Fill price per unit.
            side: "BUY" or "SELL".
            exchange: Exchange code (NSE, NSE_FO, BSE, MCX).

        Returns:
            FeeBreakdown with all components itemised.
        """
        notional = quantity * price

        # --- Brokerage: ₹20 OR 0.03%, whichever is lower ---
        brokerage_pct_amount = notional * self._brokerage_pct
        brokerage = min(self._brokerage_flat, brokerage_pct_amount)

        # --- STT ---
        is_options = "FO" in exchange.upper() or "FNO" in exchange.upper()
        if is_options:
            stt = notional * self._stt_options  # 0.01% on options
        elif side == "SELL":
            stt = notional * self._stt_sell  # 0.125% equity sell
        else:
            stt = 0.0

        # --- Exchange transaction charges ---
        if is_options:
            exchange_charges = notional * self._exchange_options
        else:
            exchange_charges = notional * self._exchange_equity

        # --- GST: 18% on (brokerage + exchange charges + SEBI charges) ---
        sebi_charges = notional * self._sebi_rate
        gst = (brokerage + exchange_charges + sebi_charges) * self._gst_rate

        # --- Stamp duty: buy side only ---
        if side == "BUY":
            if is_options:
                stamp_duty = notional * self._stamp_buy
            else:
                stamp_duty = notional * self._stamp_equity
        else:
            stamp_duty = 0.0

        total = brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty

        return FeeBreakdown(
            brokerage=round(brokerage, 4),
            stt=round(stt, 4),
            exchange_charges=round(exchange_charges, 4),
            gst=round(gst, 4),
            sebi_charges=round(sebi_charges, 4),
            stamp_duty=round(stamp_duty, 4),
            total=round(total, 4),
        )


# ---------------------------------------------------------------------------
# Margin policy
# ---------------------------------------------------------------------------

class MarginPolicy:
    """Engine-side margin calculator.

    Rules (simplified):
      - MIS equity: 20% of notional
      - CNC equity: 100% of notional
      - Derivatives (FO): 100% of notional (options buy / futures proxy)
      - Options selling: notional + 10% of notional (simplified SPAN proxy)
    """

    def __init__(
        self,
        equity_mis_pct: float = 0.20,
        futures_pct: float = 0.10,
        options_buy_pct: float = 1.0,
        options_sell_pct: float = 1.10,
    ) -> None:
        self._equity_mis_pct = equity_mis_pct
        self._futures_pct = futures_pct
        self._options_buy_pct = options_buy_pct
        self._options_sell_pct = options_sell_pct

    def required_margin(
        self,
        quantity: int,
        price: float,
        side: str,
        exchange: str = "",
        product: str = "MIS",
    ) -> float:
        """Compute required margin for an order.

        Args:
            quantity: Order quantity.
            price: Expected fill price.
            side: "BUY" or "SELL".
            exchange: Exchange code.
            product: Product type (MIS, CNC, NRML).

        Returns:
            Required margin in INR.
        """
        notional = quantity * price
        exchange_upper = exchange.upper()
        is_deriv = "FO" in exchange_upper or "FNO" in exchange_upper

        if is_deriv:
            if side == "SELL":
                return notional * self._options_sell_pct
            return notional * self._options_buy_pct

        product_upper = product.upper()
        if product_upper == "CNC":
            return notional  # 100% cash

        # MIS (intraday equity): leverage
        return notional * self._equity_mis_pct


# ---------------------------------------------------------------------------
# Fill probability model
# ---------------------------------------------------------------------------

class FillProbabilityModel:
    """Probabilistic fill model for limit orders.

    Distance-based: fill_prob = exp(-distance_bps / 10)
    Time-in-market: after 5 ticks without fill, +10% per tick
    Gap-through: cancel if LTP gaps past the limit
    """

    def __init__(
        self,
        distance_decay: float = 10.0,
        time_boost_start: int = 5,
        time_boost_per_tick: float = 0.10,
        rng: random.Random | None = None,
    ) -> None:
        self._distance_decay = distance_decay
        self._time_boost_start = time_boost_start
        self._time_boost_per_tick = time_boost_per_tick
        self._rng = rng or random.Random()

    def should_fill(
        self,
        order_price: float,
        side: str,
        ltp: float,
        bid: float | None,
        ask: float | None,
        volume: int,
        quantity: int,
        ticks_waiting: int,
    ) -> tuple[bool, float]:
        """Determine whether a limit order should fill this tick.

        Returns:
            (should_fill, fill_probability) — probability is always computed;
            should_fill is the random decision.
        """
        if ltp <= 0 or order_price <= 0:
            return False, 0.0

        # Touch detection: BUY limit fills when ask <= limit (or ltp <= limit)
        # SELL limit fills when bid >= limit (or ltp >= limit)
        if side == "BUY":
            ref_price = ask if (ask is not None and ask > 0) else ltp
            if ref_price > order_price:
                return False, 0.0  # price hasn't reached limit
            distance_bps = abs(order_price - ref_price) / order_price * 10_000
        else:
            ref_price = bid if (bid is not None and bid > 0) else ltp
            if ref_price < order_price:
                return False, 0.0
            distance_bps = abs(ref_price - order_price) / order_price * 10_000

        # Base probability: closer to touch → higher probability
        prob = math.exp(-distance_bps / self._distance_decay)

        # Time-in-market boost: after N ticks, increase probability
        if ticks_waiting >= self._time_boost_start:
            extra_ticks = ticks_waiting - self._time_boost_start + 1
            prob += extra_ticks * self._time_boost_per_tick

        # Volume-based partial fill: if order qty > 10% of tick volume, cap 50-80%
        if volume > 0 and quantity > volume * 0.1:
            cap = self._rng.uniform(0.5, 0.8)
            prob = min(prob, cap)

        prob = min(prob, 1.0)
        roll = self._rng.random()
        return roll < prob, prob

    def check_gap_through(
        self,
        order_price: float,
        side: str,
        ltp: float,
    ) -> bool:
        """Check if LTP has gapped through the limit price.

        BUY: cancel if LTP > limit (price ran away above)
        SELL: cancel if LTP < limit (price ran away below)
        """
        if side == "BUY" and ltp > order_price:
            return True
        if side == "SELL" and ltp < order_price:
            return True
        return False
