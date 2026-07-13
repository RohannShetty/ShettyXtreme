"""Dhan Trading API adapter: order placement, positions, holdings, EDIS, margin.

Implements core.interfaces.order_executor.OrderExecutor and
core.interfaces.account_info.AccountInfo protocols.

Uses DhanHQ-py directly with trading-specific credentials.
Includes SessionHealth wrapper for automatic token refresh (~3AM IST daily expiry).
DhanHQ-py sync HTTP has no auto-refresh; this wrapper handles that.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from dhanhq import DhanContext
from dhanhq import dhanhq as DhanHQClient

from shettyxtreme.core.interfaces.account_info import (
    AccountInfo,
    Holding,
    OrderBook,
    Position,
)
from shettyxtreme.core.interfaces.order_executor import (
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

EXCHANGE_MAP: dict[str, str] = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "BFO": "BSE_FNO",
    "MCX": "MCX",
    "IDX": "IDX_I",
}

PRODUCT_MAP: dict[ProductType, str] = {
    ProductType.CNC: "CNC",
    ProductType.NRML: "NRML",
    ProductType.MIS: "INTRADAY",
}

ORDER_TYPE_MAP: dict[OrderType, str] = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.SL: "STOP_LOSS",
    OrderType.SL_M: "STOP_LOSS_MARKET",
}

VALIDITY_MAP: dict[str, str] = {
    "DAY": "DAY",
    "IOC": "IOC",
}


class SessionHealth:
    """Monitors and manages Dhan session token health.

    DhanHQ-py sync HTTP has no auto-refresh. Dhan tokens expire ~3AM IST daily.
    This wrapper detects expiry and triggers re-authentication.
    """

    def __init__(self, client_id: str, access_token: str) -> None:
        self._client_id: str = client_id
        self._access_token: str = access_token
        self._context: DhanContext | None = None
        self._last_success_time: float = 0.0
        self._refresh_threshold_hours: float = 20.0
        self._init_context()

    def _init_context(self) -> None:
        """Initialize or reinitialize the DhanContext."""
        self._context = DhanContext(
            client_id=self._client_id,
            access_token=self._access_token,
        )
        self._last_success_time = time.time()

    @property
    def context(self) -> DhanContext:
        """Return the current DhanContext, refreshing if stale."""
        if self._context is None or self._is_stale():
            self._init_context()
        return self._context  # type: ignore[return-value]

    def _is_stale(self) -> bool:
        """Check if the session is likely expired."""
        if self._last_success_time == 0.0:
            return True
        elapsed_hours: float = (time.time() - self._last_success_time) / 3600.0
        return elapsed_hours > self._refresh_threshold_hours

    def mark_success(self) -> None:
        """Record a successful API call timestamp."""
        self._last_success_time = time.time()

    def refresh(self) -> None:
        """Force re-initialization of the DhanContext."""
        self._init_context()

    def check_and_refresh(self) -> bool:
        """Check staleness and refresh if needed. Returns True if refreshed."""
        if self._is_stale():
            logger.info("Dhan trading session stale, refreshing.")
            self._init_context()
            return True
        return False


class DhanTradingAdapter:
    """Dhan Trading API adapter.

    Implements OrderExecutor and AccountInfo protocols.
    Uses trading-specific credentials (separate from data credentials
    to avoid Dhan error 806).

    Handles: order placement, modification, cancellation, positions,
    holdings, EDIS, margin/funds, order book, trade book.
    """

    broker_name: str = "dhan-trading"

    def __init__(self, client_id: str, access_token: str) -> None:
        self._client_id: str = client_id
        self._access_token: str = access_token
        self._session: SessionHealth = SessionHealth(client_id, access_token)
        self._dhan: DhanHQClient | None = None
        self._connected: bool = False
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the DhanHQ client with trading context."""
        ctx: DhanContext = self._session.context
        self._dhan = DhanHQClient(ctx)
        self._connected = True

    def _ensure_client(self) -> DhanHQClient:
        """Ensure the Dhan client is alive; refresh session if stale."""
        if self._dhan is None or self._session.check_and_refresh():
            self._init_client()
        return self._dhan  # type: ignore[return-value]

    # ---- Connection ----

    async def connect(self) -> bool:
        """Connect to Dhan trading API. Returns True if successful."""
        try:
            self._init_client()
            return self._connected
        except Exception as exc:
            logger.error("Dhan trading connect failed: %s", exc)
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Dhan trading API."""
        self._connected = False
        self._dhan = None
        return True

    async def is_connected(self) -> bool:
        """Return whether the trading adapter is connected."""
        return self._connected

    def refresh_session(self) -> None:
        """Force a session refresh (re-authenticate)."""
        self._session.refresh()
        self._init_client()

    # ---- OrderExecutor protocol ----

    async def place_order(self, order: Order) -> OrderResult:
        """Place an order via DhanHQ trading API."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: dict[str, Any] = dhan.place_order(
                security_id=order.symbol,
                exchange_segment=EXCHANGE_MAP.get(order.exchange, order.exchange),
                transaction_type=order.side.value,
                quantity=order.quantity,
                order_type=ORDER_TYPE_MAP.get(order.order_type, "MARKET"),
                product_type=PRODUCT_MAP.get(order.product, "INTRADAY"),
                price=order.price if order.price else 0.0,
                trigger_price=order.trigger_price if order.trigger_price else 0.0,
                validity=VALIDITY_MAP.get(order.validity, "DAY"),
                tag=order.tag,
            )
            self._session.mark_success()
            status: OrderStatus = OrderStatus.PENDING
            if isinstance(result, dict):
                if result.get("status") == "success" or "orderId" in result:
                    status = OrderStatus.OPEN
                elif result.get("status") == "error":
                    status = OrderStatus.REJECTED
            order_id: str = str(
                result.get("orderId", result.get("order_id", "")) if isinstance(result, dict) else ""
            )
            message: str = result.get("message", "") if isinstance(result, dict) else str(result)
            return OrderResult(
                order_id=order_id, status=status, message=message,
                rejected_reason=message if status == OrderStatus.REJECTED else None,
            )
        except Exception as exc:
            logger.error("Dhan place_order failed: %s", exc)
            return OrderResult(order_id="", status=OrderStatus.REJECTED,
                            message=str(exc), rejected_reason=str(exc))

    async def modify_order(self, order_id: str, order: Order) -> OrderResult:
        """Modify an existing order via DhanHQ trading API."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: dict[str, Any] = dhan.modify_order(
                order_id=order_id,
                order_type=ORDER_TYPE_MAP.get(order.order_type, "MARKET"),
                leg_name="LEG_1",
                quantity=order.quantity,
                price=order.price if order.price else 0.0,
                trigger_price=order.trigger_price if order.trigger_price else 0.0,
                disclosed_quantity=0,
                validity=VALIDITY_MAP.get(order.validity, "DAY"),
            )
            self._session.mark_success()
            return OrderResult(
                order_id=order_id, status=OrderStatus.OPEN,
                message=str(result.get("message", "")) if isinstance(result, dict) else str(result),
            )
        except Exception as exc:
            logger.error("Dhan modify_order failed: %s", exc)
            return OrderResult(order_id=order_id, status=OrderStatus.REJECTED,
                            message=str(exc), rejected_reason=str(exc))

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via DhanHQ trading API."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: dict[str, Any] = dhan.cancel_order(order_id)
            self._session.mark_success()
            if isinstance(result, dict):
                return result.get("status") != "error"
            return True
        except Exception as exc:
            logger.error("Dhan cancel_order failed: %s", exc)
            return False

    async def get_order_status(self, order_id: str) -> OrderResult:
        """Get the status of a specific order."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: dict[str, Any] = dhan.get_order_by_id(order_id)
            self._session.mark_success()
            status_str: str = ""
            if isinstance(result, dict):
                status_str = str(result.get("status", result.get("data", {}).get("status", "")))
            return OrderResult(order_id=order_id, status=self._parse_order_status(status_str),
                            message=status_str)
        except Exception as exc:
            logger.error("Dhan get_order_status failed: %s", exc)
            return OrderResult(order_id=order_id, status=OrderStatus.REJECTED,
                            message=str(exc), rejected_reason=str(exc))

    @staticmethod
    def _parse_order_status(status_str: str) -> OrderStatus:
        """Map Dhan status strings to our OrderStatus enum."""
        mapping: dict[str, OrderStatus] = {
            "TRADED": OrderStatus.FILLED,
            "FILLED": OrderStatus.FILLED,
            "COMPLETE": OrderStatus.FILLED,
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.OPEN,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return mapping.get(status_str.upper(), OrderStatus.PENDING)

    # ---- AccountInfo protocol ----

    async def get_positions(self) -> list[Position]:
        """Get positions. Dhan does NOT include LTP in positions."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.get_positions()
            self._session.mark_success()
            positions: list[Position] = []
            raw_list: list[dict[str, Any]] = []
            if isinstance(result, dict):
                raw_list = result.get("data", [])
            elif isinstance(result, list):
                raw_list = result
            for p in raw_list:
                positions.append(Position(
                    symbol=str(p.get("securityId", p.get("symbol", ""))),
                    exchange=str(p.get("exchangeSegment", "NSE")),
                    quantity=int(p.get("quantity", 0)),
                    buy_avg=float(p.get("buyAvg", 0)),
                    sell_avg=float(p.get("sellAvg", 0)),
                    net_quantity=int(p.get("netQty", 0)),
                    day_buy_quantity=int(p.get("dayBuyQty", 0)),
                    day_sell_quantity=int(p.get("daySellQty", 0)),
                    m2m=float(p.get("mtm", 0)),
                    pnl=float(p.get("realizedProfit", 0)),
                    product=str(p.get("productType", "MIS")),
                ))
            return positions
        except Exception as exc:
            logger.error("Dhan get_positions failed: %s", exc)
            return []

    async def get_holdings(self) -> list[Holding]:
        """Get delivery holdings from Dhan."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.get_holdings()
            self._session.mark_success()
            holdings: list[Holding] = []
            raw_list: list[dict[str, Any]] = []
            if isinstance(result, dict):
                raw_list = result.get("data", [])
            elif isinstance(result, list):
                raw_list = result
            for h in raw_list:
                holdings.append(Holding(
                    symbol=str(h.get("securityId", "")),
                    exchange=str(h.get("exchangeSegment", "NSE")),
                    quantity=int(h.get("quantity", 0)),
                    avg_price=float(h.get("avgCostPrice", 0)),
                    last_price=float(h.get("lastPrice", 0)),
                    pnl=float(h.get("profit", 0)),
                    collateral=float(h.get("collateral", 0)),
                ))
            return holdings
        except Exception as exc:
            logger.error("Dhan get_holdings failed: %s", exc)
            return []

    async def get_positions_with_ltp(self) -> list[Position]:
        """Get positions enriched with LTP via separate multiquote call."""
        positions: list[Position] = await self.get_positions()
        if not positions:
            return positions
        dhan: DhanHQClient = self._ensure_client()
        securities: dict[str, list[str]] = {}
        for pos in positions:
            seg: str = EXCHANGE_MAP.get(pos.exchange, pos.exchange)
            securities.setdefault(seg, []).append(pos.symbol)
        try:
            quotes: Any = dhan.ticker_data(securities)
            self._session.mark_success()
            if isinstance(quotes, dict):
                quote_data: dict[str, Any] = quotes.get("data", {})
                for pos in positions:
                    seg_key: str = EXCHANGE_MAP.get(pos.exchange, pos.exchange)
                    seg_quotes: dict[str, Any] = quote_data.get(seg_key, {})
                    ltp_val: Any = seg_quotes.get(pos.symbol, {})
                    if isinstance(ltp_val, dict):
                        ltp_f: float = float(ltp_val.get("last_price", 0))
                        pos.pnl += ltp_f * abs(pos.net_quantity) if pos.net_quantity != 0 else 0.0
        except Exception as exc:
            logger.error("Dhan positions_with_ltp quote fetch failed: %s", exc)
        return positions

    async def get_order_book(self) -> list[OrderBook]:
        """Get today order book from Dhan."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.get_order_list()
            self._session.mark_success()
            orders: list[OrderBook] = []
            raw_list: list[dict[str, Any]] = []
            if isinstance(result, dict):
                raw_list = result.get("data", [])
            elif isinstance(result, list):
                raw_list = result
            for o in raw_list:
                raw_ts: Any = o.get("createTime", o.get("timestamp"))
                ts: datetime
                if isinstance(raw_ts, str):
                    ts = datetime.fromisoformat(raw_ts)
                else:
                    ts = datetime.now()
                orders.append(OrderBook(
                    order_id=str(o.get("orderId", "")),
                    symbol=str(o.get("securityId", "")),
                    exchange=str(o.get("exchangeSegment", "NSE")),
                    side=str(o.get("transactionType", "BUY")),
                    order_type=str(o.get("orderType", "MARKET")),
                    quantity=int(o.get("quantity", 0)),
                    filled_quantity=int(o.get("filledQty", 0)),
                    price=float(o.get("price", 0)),
                    status=str(o.get("status", "")),
                    timestamp=ts,
                ))
            return orders
        except Exception as exc:
            logger.error("Dhan get_order_book failed: %s", exc)
            return []

    async def get_trade_book(self) -> list[dict[str, Any]]:
        """Get today trade book from Dhan."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.get_trade_book()
            self._session.mark_success()
            raw_list: list[dict[str, Any]] = []
            if isinstance(result, dict):
                raw_list = result.get("data", [])
            elif isinstance(result, list):
                raw_list = result
            return raw_list
        except Exception as exc:
            logger.error("Dhan get_trade_book failed: %s", exc)
            return []

    async def get_margin(self) -> dict[str, Any]:
        """Get fund limits and margin details from Dhan."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.get_fund_limits()
            self._session.mark_success()
            if isinstance(result, dict):
                return result.get("data", result)
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.error("Dhan get_margin failed: %s", exc)
            return {}

    # ---- EDIS ----

    async def edis_generate_tpin(self) -> dict[str, Any]:
        """Generate a TPIN for e-DIS authentication."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.generate_tpin()
            self._session.mark_success()
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.error("Dhan edis_generate_tpin failed: %s", exc)
            return {}

    async def edis_inquiry(self) -> dict[str, Any]:
        """Check e-DIS status/inquiry."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.edis_inquiry()
            self._session.mark_success()
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.error("Dhan edis_inquiry failed: %s", exc)
            return {}

    # ---- Utility ----

    async def convert_position(self, security_id: str, exchange_segment: str,
                               from_product: str, to_product: str,
                               quantity: int) -> dict[str, Any]:
        """Convert a position from one product type to another."""
        dhan: DhanHQClient = self._ensure_client()
        try:
            result: Any = dhan.convert_position(
                security_id=security_id, exchange_segment=exchange_segment,
                fromProductType=from_product, toProductType=to_product,
                quantity=quantity,
            )
            self._session.mark_success()
            return result if isinstance(result, dict) else {}
        except Exception as exc:
            logger.error("Dhan convert_position failed: %s", exc)
            return {}
