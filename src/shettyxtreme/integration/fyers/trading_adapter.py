"""Fyers trading adapter: OrderExecutor + AccountInfo (F4).

Thin adapter layer implementing the broker-neutral Protocols on top of the
F2 transport (:class:`FyersHTTPClient` / :class:`FyersSession`) and F1 symbol
resolution (:class:`FyersSymbolResolver`).

Wire contract (verified 2026-08-04):

- ``POST /orders/sync``   -> place (type 1=LIMIT 2=MARKET 3=SL-M 4=SL-L;
  productType CNC/INTRADAY/MARGIN; side 1/-1; validity DAY/IOC).
- ``PATCH /orders/sync``  -> modify (body keyed by ``id``, no ``side``).
- ``DELETE /orders/sync`` -> cancel (body ``{"id": ...}``).
- ``GET /orders?id=...``  -> single order status (orderBook array).

OBSERVER-first (D10): this adapter only submits what the execution layer
asks it to — approval gates live upstream.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from shettyxtreme.core.data_models import (
    Holding,
    OrderBook,
    OrderRequest,
    OrderResult,
    OrderStatus,
    OrderType,
    Position,
)
from shettyxtreme.integration.fyers.client import (
    FyersDataEntitlementError,
    FyersError,
    FyersHTTPClient,
    FyersTokenExpired,
)
from shettyxtreme.integration.fyers.mappings import (
    ORDER_TYPE_MAP,
    PRODUCT_TYPE_MAP,
    SIDE_MAP,
    VALIDITY_MAP,
    fyers_order_status,
    parse_order_type,
    parse_side,
)
from shettyxtreme.integration.fyers.session import FyersSession
from shettyxtreme.integration.fyers.symbols import (
    FyersSymbolResolver,
    SymbolNotFoundError,
)

logger = logging.getLogger(__name__)

#: Internal index names that resolve to the Fyers INDEX instrument type.
_INDEX_SYMBOLS: frozenset[str] = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY"})

_ORDERS_SYNC = "/orders/sync"


def _infer_instrument_type(symbol: str) -> str:
    """Heuristic for plain internal symbols (used when only name+exchange known).

    The big three index names are INDEX; everything else resolves as EQUITY.
    Callers placing derivative orders must pass an already-resolved Fyers
    ticker (``NSE:NIFTY24OCT25000CE``) or a master-backed lookup path.
    """
    return "INDEX" if symbol in _INDEX_SYMBOLS else "EQUITY"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _epoch_to_dt(value: Any) -> datetime:
    """Fyers timestamps are epoch seconds; convert to UTC datetime."""
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return datetime.now(UTC)


class FyersTradingAdapter:
    """Fyers REST trading adapter (OrderExecutor + AccountInfo).

    Args:
        session: Fyers access-token lifecycle.
        client: Fyers REST transport.
        symbol_resolver: Internal-symbol -> Fyers ticker resolution (F1).
    """

    broker_name: str = "fyers-trading"

    def __init__(
        self,
        session: FyersSession,
        client: FyersHTTPClient,
        symbol_resolver: FyersSymbolResolver,
    ) -> None:
        self._session = session
        self._client = client
        self._symbol_resolver = symbol_resolver

    # ------------------------------------------------------------------ lifecycle

    async def connect(self) -> bool:
        """Probe session liveness via ``GET /profile``; True when the token works."""
        try:
            return await self._session.probe_liveness(self._client)
        except FyersError:
            return False

    async def disconnect(self) -> bool:
        """Stateless HTTP adapter — nothing to tear down."""
        return True

    async def is_connected(self) -> bool:
        """Cheap session check (True when the token is not known-expired)."""
        return self._session.is_valid()

    def is_session_valid(self) -> bool:
        """True while the Fyers token is not known to be expired.

        Implements the ``BrokerGateway`` session-validity gate (mission §9
        Q5): the execution layer rejects LIVE placement when this is False —
        the daily Fyers token has no silent refresh, so a re-auth is required.
        """
        return self._session.is_valid()

    # ------------------------------------------------------------------ helpers

    def _fyers_symbol(self, symbol: str, exchange: str) -> str:
        """Resolve an internal symbol to its Fyers ticker.

        Already-resolved Fyers tickers (containing ``:``) pass through.
        """
        s = str(symbol).strip()
        if ":" in s:
            return s
        return self._symbol_resolver.to_fyers(
            s, exchange, _infer_instrument_type(s)
        )

    def _order_payload(self, order: OrderRequest, *, include_side: bool = True) -> dict[str, Any]:
        """Build the Fyers ``/orders/sync`` payload for an internal OrderRequest."""
        order_type = ORDER_TYPE_MAP.get(order.order_type, ORDER_TYPE_MAP[OrderType.MARKET])
        limit_price = 0.0
        stop_price = 0.0
        if order.order_type in (OrderType.LIMIT, OrderType.SL):
            limit_price = order.price if order.price is not None else 0.0
        if order.order_type in (OrderType.SL, OrderType.SL_M):
            stop_price = order.trigger_price if order.trigger_price is not None else 0.0
        payload: dict[str, Any] = {
            "symbol": self._fyers_symbol(order.symbol, order.exchange),
            "qty": _to_int(order.quantity),
            "type": order_type,
            "productType": PRODUCT_TYPE_MAP.get(order.product, "INTRADAY"),
            "limitPrice": limit_price,
            "stopPrice": stop_price,
            "validity": VALIDITY_MAP.get(order.validity, "DAY"),
        }
        if include_side:
            payload["side"] = SIDE_MAP.get(order.side, 1)
        return payload

    @staticmethod
    def _order_result(resp: Any, fallback_id: str = "") -> OrderResult:
        """Decode a ``/orders/sync`` or ``/orders`` entry into an OrderResult."""
        if not isinstance(resp, dict):
            return OrderResult(
                order_id=fallback_id,
                status=OrderStatus.REJECTED,
                message="empty response",
                rejected_reason="empty response",
            )
        order_id = str(resp.get("orderId") or resp.get("id") or fallback_id)
        status_raw = resp.get("status")
        if status_raw is not None:
            status = fyers_order_status(status_raw)
        else:
            status = OrderStatus.OPEN if str(resp.get("s")) == "ok" else OrderStatus.REJECTED
        message = str(resp.get("message") or resp.get("msg") or "")
        rejected = status == OrderStatus.REJECTED
        return OrderResult(
            order_id=order_id,
            status=status,
            message=message,
            filled_quantity=_to_int(resp.get("filledQty") or resp.get("tradedQty")),
            average_price=_to_float(resp.get("tradedPrice") or resp.get("avgPrice")),
            rejected_reason=message if rejected else None,
        )

    def _rejected(self, message: str, order_id: str = "") -> OrderResult:
        return OrderResult(
            order_id=order_id,
            status=OrderStatus.REJECTED,
            message=message,
            rejected_reason=message,
        )

    def _decode_symbol(self, ticker: str, row: dict[str, Any] | None = None) -> tuple[str, str]:
        """Split a Fyers ticker into (internal symbol, internal exchange)."""
        if ":" in ticker:
            try:
                parsed = self._symbol_resolver.from_fyers(ticker)
                return (
                    str(parsed.get("internal_symbol", ticker)),
                    str(parsed.get("exchange", "")),
                )
            except ValueError:
                pass
        if row is not None:
            return str(row.get("symbol", ticker)), str(row.get("exchange", ""))
        return ticker, ""

    @staticmethod
    def _side_label(value: Any) -> str:
        try:
            return parse_side(value).value
        except (KeyError, TypeError, ValueError):
            return "BUY"

    @staticmethod
    def _order_type_label(value: Any) -> str:
        try:
            return parse_order_type(value).value
        except (KeyError, TypeError, ValueError):
            return "MARKET"

    @staticmethod
    def _find_order(resp: Any, order_id: str) -> dict[str, Any] | None:
        if not isinstance(resp, dict):
            return None
        order_book = resp.get("orderBook")
        if not isinstance(order_book, list):
            return None
        for entry in order_book:
            if isinstance(entry, dict) and str(entry.get("id")) == str(order_id):
                return entry
        return None

    @staticmethod
    def _raise_fatal_account_error(exc: FyersError, endpoint: str) -> None:
        """Re-raise fatal account-endpoint failures; let everything else degrade.

        Account endpoints used to swallow every :class:`FyersError` and return
        an empty payload, which masked a dead token (:class:`FyersTokenExpired`)
        and a missing data entitlement (:class:`FyersDataEntitlementError`, code
        -373 — the Dhan-806 twin) behind a healthy-looking empty account. Those
        two must surface (F-INT-011):

        - token expiry re-raises so the upstream re-auth gates fire;
        - the -373 entitlement re-raises with endpoint context so the operator
          sees the app cannot read account data without the entitlement.

        Rate limits and transient API errors still degrade to ``[]``/``{}``.
        """
        if isinstance(exc, FyersDataEntitlementError):
            raise FyersDataEntitlementError(
                f"{exc.message} — {endpoint} (code {exc.code})",
                code=exc.code,
                status_code=exc.status_code,
            ) from exc
        if isinstance(exc, FyersTokenExpired):
            raise exc

    # ------------------------------------------------------------------ OrderExecutor

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """Place an order via ``POST /orders/sync``."""
        try:
            resp = await self._client.post(_ORDERS_SYNC, json=self._order_payload(order))
            return self._order_result(resp)
        except (FyersError, SymbolNotFoundError, ValueError) as exc:
            logger.warning("Fyers place_order failed: %s", exc)
            return self._rejected(str(exc))

    async def modify_order(self, order_id: str, order: OrderRequest) -> OrderResult:
        """Modify an open order via ``PATCH /orders/sync``."""
        try:
            payload = self._order_payload(order, include_side=False)
            payload["id"] = order_id
            resp = await self._client.patch(_ORDERS_SYNC, json=payload)
            return self._order_result(resp, fallback_id=order_id)
        except (FyersError, SymbolNotFoundError, ValueError) as exc:
            logger.warning("Fyers modify_order failed: %s", exc)
            return self._rejected(str(exc), order_id=order_id)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via ``DELETE /orders/sync``."""
        try:
            resp = await self._client.delete(_ORDERS_SYNC, json={"id": order_id})
            return isinstance(resp, dict) and str(resp.get("s")) == "ok"
        except FyersError as exc:
            logger.warning("Fyers cancel_order failed: %s", exc)
            return False

    async def get_order_status(self, order_id: str) -> OrderResult:
        """Fetch one order's status via ``GET /orders?id=...``."""
        try:
            resp = await self._client.get(f"/orders?id={order_id}")
            order = self._find_order(resp, order_id)
            if order is None:
                return self._rejected(
                    f"order {order_id} not found in order book", order_id=order_id
                )
            return self._order_result(order, fallback_id=order_id)
        except FyersError as exc:
            logger.warning("Fyers get_order_status failed: %s", exc)
            return self._rejected(str(exc), order_id=order_id)

    # ------------------------------------------------------------------ AccountInfo

    async def get_positions(self) -> list[Position]:
        """Map ``GET /positions`` netPositions to :class:`Position`."""
        try:
            resp = await self._client.get("/positions")
        except FyersError as exc:
            logger.warning("Fyers get_positions failed: %s", exc)
            self._raise_fatal_account_error(exc, "GET /positions")
            return []
        raw = resp.get("netPositions", []) if isinstance(resp, dict) else []
        positions: list[Position] = []
        for p in raw:
            if not isinstance(p, dict):
                continue
            internal, exchange = self._decode_symbol(str(p.get("symbol", "")), p)
            m2m = p.get("unrealized_profit")
            if m2m is None:
                m2m = p.get("pl")
            positions.append(Position(
                symbol=internal,
                exchange=exchange,
                quantity=_to_int(p.get("qty")),
                buy_avg=_to_float(p.get("buyAvg")),
                sell_avg=_to_float(p.get("sellAvg")),
                net_quantity=_to_int(p.get("netQty")),
                day_buy_quantity=_to_int(p.get("dayBuyQty")),
                day_sell_quantity=_to_int(p.get("daySellQty")),
                m2m=_to_float(m2m),
                pnl=_to_float(p.get("realized_profit")),
                product=str(p.get("productType", "")),
            ))
        return positions

    async def get_holdings(self) -> list[Holding]:
        """Map ``GET /holdings`` to :class:`Holding` (Fyers has no collateral row)."""
        try:
            resp = await self._client.get("/holdings")
        except FyersError as exc:
            logger.warning("Fyers get_holdings failed: %s", exc)
            self._raise_fatal_account_error(exc, "GET /holdings")
            return []
        raw = resp.get("holdings", []) if isinstance(resp, dict) else []
        holdings: list[Holding] = []
        for h in raw:
            if not isinstance(h, dict):
                continue
            internal, exchange = self._decode_symbol(str(h.get("symbol", "")), h)
            pnl = h.get("unrealized_profit")
            if pnl is None:
                pnl = h.get("pl")
            holdings.append(Holding(
                symbol=internal,
                exchange=exchange,
                quantity=_to_int(h.get("qty")),
                avg_price=_to_float(h.get("costPrice")),
                last_price=_to_float(h.get("ltp")),
                pnl=_to_float(pnl),
                collateral=0.0,
            ))
        return holdings

    async def get_order_book(self) -> list[OrderBook]:
        """Map ``GET /orders`` orderBook entries to :class:`OrderBook`."""
        try:
            resp = await self._client.get("/orders")
        except FyersError as exc:
            logger.warning("Fyers get_order_book failed: %s", exc)
            self._raise_fatal_account_error(exc, "GET /orders")
            return []
        raw = resp.get("orderBook", []) if isinstance(resp, dict) else []
        orders: list[OrderBook] = []
        for o in raw:
            if not isinstance(o, dict):
                continue
            internal, exchange = self._decode_symbol(str(o.get("symbol", "")), o)
            orders.append(OrderBook(
                order_id=str(o.get("id", "")),
                symbol=internal,
                exchange=exchange,
                side=self._side_label(o.get("side")),
                order_type=self._order_type_label(o.get("type")),
                quantity=_to_int(o.get("qty")),
                filled_quantity=_to_int(o.get("filledQty")),
                price=_to_float(o.get("limitPrice")),
                status=fyers_order_status(o.get("status")).value,
                timestamp=_epoch_to_dt(o.get("orderDateTime")),
            ))
        return orders

    async def get_trade_book(self) -> list[dict[str, Any]]:
        """Return raw ``GET /tradebook`` rows (Protocol allows untyped lists)."""
        try:
            resp = await self._client.get("/tradebook")
        except FyersError as exc:
            logger.warning("Fyers get_trade_book failed: %s", exc)
            self._raise_fatal_account_error(exc, "GET /tradebook")
            return []
        if not isinstance(resp, dict):
            return []
        raw = resp.get("tradeBook", [])
        return [t for t in raw if isinstance(t, dict)] if isinstance(raw, list) else []

    async def get_margin(self) -> dict[str, Any]:
        """Extract available/utilized/total from the ``GET /funds`` fund_limit array."""
        try:
            resp = await self._client.get("/funds")
        except FyersError as exc:
            logger.warning("Fyers get_margin failed: %s", exc)
            self._raise_fatal_account_error(exc, "GET /funds")
            return {}
        fund_limit = resp.get("fund_limit", []) if isinstance(resp, dict) else []

        def _amount(title: str) -> float:
            for entry in fund_limit:
                if (
                    isinstance(entry, dict)
                    and str(entry.get("title", "")).strip().lower() == title.lower()
                ):
                    return _to_float(entry.get("amount"))
            return 0.0

        total = _amount("Total")
        available = _amount("Available Balance")
        if available == 0.0:
            available = _amount("Clear Balance")
        utilized = _amount("Margin Used")
        if utilized == 0.0:
            utilized = _amount("Net")
        return {"available": available, "utilized": utilized, "total": total}
