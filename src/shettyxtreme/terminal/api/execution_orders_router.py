"""Order/position action endpoints (Phase 4): cancel, export, close, history.

Kept as a separate router module so ``execution_router.py`` stays under the
1000-line god-module guard. Reuses the mode router, paper engine, position
projection and trade ledger wired on ``app.state`` by the terminal app.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from shettyxtreme.core.data_models import (
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
)
from shettyxtreme.execution.ledger import pair_fills
from shettyxtreme.terminal.api.execution_router import (
    _enum_str,
    _order_response,
    _require_csrf_token,
    get_mode_value,
)
from shettyxtreme.terminal.api.models import (
    CancelOrderResponse,
    OrderResponse,
    PositionHistoryItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/execution", tags=["execution"])

# Fallback ledger path for position-history reads when the app has not wired
# a shared TradeLedger on app.state (mirrors analytics_router's per-call open).
_LEDGER_DB_PATH = "data/ledger.db"


# ── Order export (Phase 4) ────────────────────────────────────────────────

_ORDER_EXPORT_COLUMNS = [
    "order_id", "symbol", "exchange", "side", "order_type", "quantity",
    "price", "status", "filled_quantity", "average_price", "tag",
    "created_at", "strike", "expiry", "option_type", "lot_size",
    "stop_loss", "target", "rationale", "confidence",
]


def _orders_to_csv(orders: list[OrderResponse]) -> str:
    """Render orders to a CSV document (stdlib csv, section header)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["# orders"])
    writer.writerow(_ORDER_EXPORT_COLUMNS)
    for order in orders:
        row = order.model_dump()
        row["created_at"] = order.created_at.isoformat() if order.created_at else ""
        writer.writerow([row.get(col, "") for col in _ORDER_EXPORT_COLUMNS])
    return buf.getvalue()


@router.get("/orders/export")
async def export_orders(
    request: Request,
    format: str = Query("csv", pattern="^(csv|json)$"),
    days: int = Query(30, ge=1, le=365),
) -> Response:
    """Export the order book as a CSV or JSON file download (Phase 4).

    Args:
        format: ``csv`` (default) or ``json``.
        days: Include orders created within the last ``days`` days (default 30).

    Returns:
        ``orders_export.csv`` (text/csv) or ``orders_export.json`` (JSON
        array), both with ``Content-Disposition: attachment``.
    """
    paper = getattr(request.app.state, "paper_engine", None)
    orders: list[OrderResponse] = []
    if paper is not None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        orders = [
            _order_response(o)
            for o in paper.get_order_book()
            if o.created_at is None or o.created_at >= cutoff
        ]
        # Newest first.
        orders = sorted(
            orders,
            key=lambda o: o.created_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
    if format == "json":
        return JSONResponse(
            content=[o.model_dump(mode="json") for o in orders],
            headers={"Content-Disposition": 'attachment; filename="orders_export.json"'},
        )
    return Response(
        content=_orders_to_csv(orders),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="orders_export.csv"'},
    )


# ── Order cancellation (Phase 4) ──────────────────────────────────────────

@router.post("/orders/{order_id}/cancel", response_model=CancelOrderResponse)
async def cancel_order(
    request: Request,
    order_id: str,
) -> CancelOrderResponse:
    """Cancel an order through the mode router (D10, Phase 4).

    PAPER/OBSERVER cancels hit the paper engine; LIVE cancels go to the
    live adapter (gated on session validity + kill switch by the router).
    Failures are distinguished: unknown order (404), terminal state (400),
    environment failure such as an armed kill switch (400).
    """
    executor = getattr(request.app.state, "mode_executor", None)
    if executor is None:
        raise HTTPException(status_code=503, detail="execution engine not initialized")
    cancelled = await executor.cancel_order(order_id)
    if cancelled:
        return CancelOrderResponse(
            order_id=order_id, cancelled=True, status="CANCELLED",
            message="order cancelled",
        )
    # Distinguish the failure by consulting the paper order book.
    paper = getattr(request.app.state, "paper_engine", None)
    order = None
    if paper is not None:
        order = next(
            (o for o in paper.get_order_book() if o.order_id == order_id), None
        )
    if order is not None:
        status = str(order.status).upper()
        if status in ("FILLED", "PARTIALLY_FILLED"):
            raise HTTPException(
                status_code=400, detail=f"cannot cancel order in state {status}"
            )
        if status == "CANCELLED":
            raise HTTPException(status_code=400, detail="order already cancelled")
        raise HTTPException(
            status_code=400,
            detail="cancel failed - kill switch armed or engine unavailable",
        )
    if get_mode_value().upper() == "LIVE":
        raise HTTPException(
            status_code=400,
            detail="cancel failed - live adapter unavailable or order unknown",
        )
    raise HTTPException(status_code=404, detail=f"order not found: {order_id}")


# ── Position close (Phase 4) ──────────────────────────────────────────────

def _position_field(pos: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a Position dataclass or a projection dict."""
    if isinstance(pos, dict):
        return pos.get(key, default)
    return getattr(pos, key, default)


def _find_open_position(
    request: Request, symbol: str,
) -> Any | None:
    """Locate an open position (abs net quantity > 0) by symbol.

    The paper engine is authoritative for PAPER/OBSERVER trades (true
    net_quantity/buy_avg/sell_avg); the position projection is the fallback
    for deployments without a paper engine.
    """
    wanted = symbol.upper()
    paper = getattr(request.app.state, "paper_engine", None)
    if paper is not None:
        for pos in paper.get_positions():
            if str(pos.symbol).upper() == wanted and pos.net_quantity != 0:
                return pos
    projection = getattr(request.app.state, "position_projection", None)
    if projection is not None:
        for pos in projection.get():
            qty = _position_field(pos, "net_quantity", 0)
            try:
                open_qty = int(qty or 0)
            except (TypeError, ValueError):
                open_qty = 0
            if str(_position_field(pos, "symbol", "")).upper() == wanted and open_qty != 0:
                return pos
    return None


@router.post("/positions/{symbol}/close", response_model=OrderResponse)
async def close_position(
    request: Request,
    symbol: str,
) -> OrderResponse:
    """Close an open position with an opposite-side market order (Phase 4).

    Long positions (net_quantity > 0) are closed with a SELL, short
    positions with a BUY, sized to the absolute net quantity. The order
    flows through the mode router exactly like any placement (D10):
    OBSERVER never places, LIVE requires the per-session CSRF token, and
    an armed kill switch blocks the close.
    """
    position = _find_open_position(request, symbol)
    if position is None:
        raise HTTPException(
            status_code=404, detail=f"no open position for symbol: {symbol}"
        )

    mode = get_mode_value()
    if mode == "OBSERVER":
        raise HTTPException(
            status_code=400,
            detail="OBSERVER mode never places orders - switch to PAPER or LIVE",
        )
    if mode == "LIVE":
        _require_csrf_token(request)

    executor = getattr(request.app.state, "mode_executor", None)
    if executor is None:
        raise HTTPException(status_code=503, detail="execution engine not initialized")

    try:
        net_qty = int(_position_field(position, "net_quantity", 0))
    except (TypeError, ValueError):
        net_qty = 0
    if net_qty == 0:
        raise HTTPException(
            status_code=404, detail=f"no open position for symbol: {symbol}"
        )
    side = OrderSide.SELL if net_qty > 0 else OrderSide.BUY
    quantity = abs(net_qty)

    exchange = str(_position_field(position, "exchange", "NSE"))
    product_raw = str(_position_field(position, "product", "MIS"))
    product = (
        ProductType(product_raw)
        if product_raw in ProductType._member_names_
        else ProductType.MIS
    )

    # Carry option identity into the closing order when the position is an
    # option (from fill context or the Fyers symbol parser).
    strike = _position_field(position, "strike", None)
    expiry = _position_field(position, "expiry", None)
    option_type = _position_field(position, "option_type", None)
    if strike is None:
        try:
            from shettyxtreme.integration.fyers.symbols import from_fyers
            parsed = from_fyers(str(_position_field(position, "symbol", "")))
            if parsed.get("instrument_type") == "OPTION":
                strike = parsed.get("strike")
                parsed_expiry = parsed.get("expiry")
                expiry = str(parsed_expiry) if parsed_expiry else None
                option_type = parsed.get("option_type")
        except (ValueError, ImportError):
            pass

    symbol_name = str(_position_field(position, "symbol", symbol))
    order_req = OrderRequest(
        symbol=symbol_name,
        exchange=exchange,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        price=0.0,  # MARKET fills at LTP; paper engine rejects when no LTP
        product=product,
        tag=f"close:{symbol_name}",
        strike=strike,
        expiry=expiry,
        option_type=option_type,
    )
    result = await executor.place_order(order_req)
    if result.status == OrderStatus.REJECTED:
        raise HTTPException(
            status_code=400, detail=result.message or "close order rejected"
        )

    # Return the placed order from the paper book when visible there,
    # so the response carries the real fill details (PAPER mode).
    paper = getattr(request.app.state, "paper_engine", None)
    if paper is not None:
        placed = next(
            (o for o in paper.get_order_book() if o.order_id == result.order_id),
            None,
        )
        if placed is not None:
            return _order_response(placed)
    return OrderResponse(
        order_id=result.order_id,
        symbol=symbol_name,
        exchange=exchange,
        side=side.value,
        order_type="MARKET",
        quantity=quantity,
        price=0.0,
        status=_enum_str(result.status) or "FILLED",
        filled_quantity=result.filled_quantity,
        average_price=result.average_price,
        tag=f"close:{symbol_name}",
        strike=strike,
        expiry=expiry,
        option_type=option_type,
    )


# ── Position history (Phase 4) ────────────────────────────────────────────

@router.get("/positions/history", response_model=list[PositionHistoryItem])
async def position_history(
    request: Request,
    days: int = Query(30, ge=1, le=365),
) -> list[PositionHistoryItem]:
    """Closed positions with realized P&L (Phase 4).

    Reconstructs position history from the trade ledger: fills are
    FIFO-paired per symbol (``pair_fills``), so each pair is one closed
    position with entry price, exit price, quantity and realized PnL.
    Only fully paired (closed) fills appear — open remainder stays hidden.
    """
    ledger = getattr(request.app.state, "trade_ledger", None)
    owned = False
    if ledger is None:
        from shettyxtreme.execution.ledger import TradeLedger
        try:
            ledger = TradeLedger(_LEDGER_DB_PATH)
            owned = True
        except Exception:
            logger.warning("trade ledger unavailable for position history")
            return []
    try:
        fills = ledger.list(limit=1000)
    except Exception:
        logger.exception("position history read failed")
        return []
    finally:
        if owned:
            ledger.close()

    cutoff = datetime.now(UTC) - timedelta(days=days)
    recent: list[dict] = []
    for fill in fills:
        try:
            recorded = datetime.fromisoformat(str(fill.get("recorded_at", "")))
        except (TypeError, ValueError):
            continue
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=UTC)
        if recorded >= cutoff:
            recent.append(fill)

    items: list[PositionHistoryItem] = []
    for pair in pair_fills(recent):
        entry = pair["entry_fill"]
        exit_fill = pair["exit_fill"]
        items.append(
            PositionHistoryItem(
                symbol=pair["symbol"],
                entry_price=float(entry["price"]),
                exit_price=float(exit_fill["price"]),
                quantity=int(pair["quantity"]),
                realized_pnl=float(pair["pnl"]),
                opened_at=entry.get("recorded_at"),
                closed_at=exit_fill.get("recorded_at"),
            )
        )
    # Most recently closed first.
    items.sort(
        key=lambda i: i.closed_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return items
