"""Tests for Phase 4 execution endpoints: order cancel/export, position
close/history (execution_router.py).

Covers:
  - POST /api/execution/orders/{order_id}/cancel — success, terminal-state
    rejection, unknown order, missing engine
  - GET  /api/execution/orders/export — CSV + JSON downloads, days filter,
    format validation
  - POST /api/execution/positions/{symbol}/close — long/short close,
    OBSERVER/LIVE mode safety, missing position/engine
  - GET  /api/execution/positions/history — ledger fill pairing (entry/exit
    with realized P&L), days filter, empty ledger
"""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.execution_orders_router as eor
import shettyxtreme.terminal.api.execution_router as er
from shettyxtreme.execution.ledger import TradeLedger
from shettyxtreme.execution.mode_router import ModeRoutingExecutor
from shettyxtreme.execution.paper_trading import PaperTradingEngine
from shettyxtreme.terminal.api.execution_orders_router import router


def _make_app(
    tmp_path,
    monkeypatch,
    with_executor: bool = True,
    with_ledger: bool = False,
) -> FastAPI:
    """Build an app wired like production: paper engine + mode router."""
    paper = PaperTradingEngine()
    executor = None
    if with_executor:
        executor = ModeRoutingExecutor(
            paper_engine=paper,
            mode_provider=er.get_mode_value,
            kill_switch_provider=lambda: False,
        )
    # Sandbox the module-level ledger fallback path (never the repo data/).
    monkeypatch.setattr(eor, "_LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setattr(er, "_current_mode", "PAPER")
    app = FastAPI()
    app.include_router(router)
    app.state.paper_engine = paper
    if executor is not None:
        app.state.mode_executor = executor
    if with_ledger:
        app.state.trade_ledger = TradeLedger(str(tmp_path / "ledger.db"))
    return app


@pytest_asyncio.fixture
async def app_client(
    tmp_path, monkeypatch,
) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    app = _make_app(tmp_path, monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield app, ac


@pytest_asyncio.fixture
async def app_client_with_ledger(
    tmp_path, monkeypatch,
) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    app = _make_app(tmp_path, monkeypatch, with_ledger=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield app, ac


def _seed_ltp(paper: PaperTradingEngine, symbol: str, ltp: float) -> None:
    paper._ltp_cache[symbol.upper()] = ltp


async def _place(
    paper: PaperTradingEngine,
    symbol: str = "NIFTY",
    side: str = "BUY",
    order_type: str = "MARKET",
    quantity: int = 10,
    price: float = 0.0,
    ltp: float = 100.0,
):
    """Place an order directly on the paper engine (LTP seeded)."""
    _seed_ltp(paper, symbol, ltp)
    return await paper.place_order(
        symbol=symbol, exchange="NSE", side=side,
        order_type=order_type, quantity=quantity, price=price,
    )


# ── POST /orders/{order_id}/cancel ────────────────────────────────────────

class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_open_limit_order(self, app_client) -> None:
        app, client = app_client
        paper = app.state.paper_engine
        result = await _place(paper, order_type="LIMIT", price=99.0)
        assert result.status == "OPEN"  # pending, cancellable

        resp = await client.post(f"/api/execution/orders/{result.order_id}/cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["order_id"] == result.order_id
        assert data["cancelled"] is True
        assert data["status"] == "CANCELLED"
        # The paper book reflects the cancelled state.
        book = paper.get_order_book()
        assert book[0].status == "CANCELLED"

    @pytest.mark.asyncio
    async def test_cancel_filled_order_rejected(self, app_client) -> None:
        app, client = app_client
        result = await _place(app.state.paper_engine)  # MARKET -> FILLED

        resp = await client.post(f"/api/execution/orders/{result.order_id}/cancel")
        assert resp.status_code == 400
        assert "FILLED" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_rejected(self, app_client) -> None:
        app, client = app_client
        paper = app.state.paper_engine
        result = await _place(paper, order_type="LIMIT", price=99.0)
        first = await client.post(f"/api/execution/orders/{result.order_id}/cancel")
        assert first.status_code == 200

        second = await client.post(f"/api/execution/orders/{result.order_id}/cancel")
        assert second.status_code == 400
        assert "already cancelled" in second.json()["detail"]

    @pytest.mark.asyncio
    async def test_cancel_unknown_order_404(self, app_client) -> None:
        _, client = app_client
        resp = await client.post("/api/execution/orders/NO-SUCH-ORDER/cancel")
        assert resp.status_code == 404
        assert "order not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_cancel_missing_engine_503(self, tmp_path, monkeypatch) -> None:
        app = _make_app(tmp_path, monkeypatch, with_executor=False)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/execution/orders/X/cancel")
        assert resp.status_code == 503


# ── GET /orders/export ────────────────────────────────────────────────────

class TestExportOrders:
    @pytest.mark.asyncio
    async def test_export_csv_download(self, app_client) -> None:
        app, client = app_client
        paper = app.state.paper_engine
        r1 = await _place(paper, symbol="NIFTY", quantity=10)
        r2 = await _place(paper, symbol="BANKNIFTY", side="SELL", quantity=5)

        resp = await client.get("/api/execution/orders/export?format=csv&days=30")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        disposition = resp.headers["content-disposition"]
        assert "attachment" in disposition
        assert "orders_export.csv" in disposition

        text = resp.text
        assert "# orders" in text
        assert r1.order_id in text
        assert r2.order_id in text
        assert "BANKNIFTY" in text

    @pytest.mark.asyncio
    async def test_export_csv_parses_cleanly(self, app_client) -> None:
        app, client = app_client
        await _place(app.state.paper_engine, quantity=3)
        await _place(app.state.paper_engine, side="SELL", quantity=7)

        resp = await client.get("/api/execution/orders/export?format=csv&days=30")
        rows = list(csv.reader(io.StringIO(resp.text)))
        # Section header, column header (20 columns), then data rows.
        assert rows[0] == ["# orders"]
        assert len(rows[1]) == 20
        for row in rows[2:]:
            assert len(row) == 20, f"ragged row: {row}"

    @pytest.mark.asyncio
    async def test_export_json(self, app_client) -> None:
        app, client = app_client
        r1 = await _place(app.state.paper_engine, symbol="NIFTY", quantity=10)

        resp = await client.get("/api/execution/orders/export?format=json&days=30")
        assert resp.status_code == 200
        assert "json" in resp.headers["content-type"]
        assert "orders_export.json" in resp.headers["content-disposition"]
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        order = body[0]
        assert order["order_id"] == r1.order_id
        assert order["symbol"] == "NIFTY"
        assert order["side"] == "BUY"
        assert order["status"] == "FILLED"
        assert order["quantity"] == 10
        assert order["created_at"]  # ISO string in JSON

    @pytest.mark.asyncio
    async def test_export_defaults_to_csv(self, app_client) -> None:
        _, client = app_client
        resp = await client.get("/api/execution/orders/export?days=30")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")

    @pytest.mark.asyncio
    async def test_export_rejects_unknown_format(self, app_client) -> None:
        _, client = app_client
        resp = await client.get("/api/execution/orders/export?format=xml")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_export_days_filter(self, app_client) -> None:
        app, client = app_client
        paper = app.state.paper_engine
        await _place(paper, quantity=10)
        # Age the placed order beyond the 30-day window.
        paper._orders[0].created_at = datetime.now(UTC) - timedelta(days=40)

        old = await client.get("/api/execution/orders/export?format=json&days=30")
        assert old.json() == []
        recent = await client.get("/api/execution/orders/export?format=json&days=60")
        assert len(recent.json()) == 1


# ── POST /positions/{symbol}/close ────────────────────────────────────────

class TestClosePosition:
    @pytest.mark.asyncio
    async def test_close_long_position(self, app_client) -> None:
        app, client = app_client
        paper = app.state.paper_engine
        await _place(paper, side="BUY", quantity=10, ltp=100.0)

        resp = await client.post("/api/execution/positions/NIFTY/close")
        assert resp.status_code == 200
        data = resp.json()
        assert data["side"] == "SELL"
        assert data["quantity"] == 10
        assert data["status"] == "FILLED"
        assert data["tag"] == "close:NIFTY"
        assert data["average_price"] > 0
        # The position is now flat.
        remaining = paper.get_positions()
        assert all(p.net_quantity == 0 for p in remaining)

    @pytest.mark.asyncio
    async def test_close_short_position(self, app_client) -> None:
        app, client = app_client
        paper = app.state.paper_engine
        await _place(paper, side="SELL", quantity=5, ltp=200.0)

        resp = await client.post("/api/execution/positions/NIFTY/close")
        assert resp.status_code == 200
        data = resp.json()
        assert data["side"] == "BUY"
        assert data["quantity"] == 5
        assert data["status"] == "FILLED"
        assert all(p.net_quantity == 0 for p in paper.get_positions())

    @pytest.mark.asyncio
    async def test_close_no_position_404(self, app_client) -> None:
        _, client = app_client
        resp = await client.post("/api/execution/positions/NIFTY/close")
        assert resp.status_code == 404
        assert "no open position" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_close_flat_position_404(self, app_client) -> None:
        app, client = app_client
        paper = app.state.paper_engine
        await _place(paper, side="BUY", quantity=10, ltp=100.0)
        await _place(paper, side="SELL", quantity=10, ltp=100.0)  # closes it

        resp = await client.post("/api/execution/positions/NIFTY/close")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_close_observer_mode_blocked(self, app_client, monkeypatch) -> None:
        app, client = app_client
        await _place(app.state.paper_engine, side="BUY", quantity=10)
        monkeypatch.setattr(er, "_current_mode", "OBSERVER")

        resp = await client.post("/api/execution/positions/NIFTY/close")
        assert resp.status_code == 400
        assert "OBSERVER" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_close_live_requires_csrf(self, app_client, monkeypatch) -> None:
        app, client = app_client
        await _place(app.state.paper_engine, side="BUY", quantity=10)
        monkeypatch.setattr(er, "_current_mode", "LIVE")

        # No CSRF header -> 403 (F-EXEC-001).
        resp = await client.post("/api/execution/positions/NIFTY/close")
        assert resp.status_code == 403

        # With the minted token, the mode router rejects (no live adapter).
        er._mint_csrf_token()
        resp = await client.post(
            "/api/execution/positions/NIFTY/close",
            headers={"X-CSRF-Token": er.get_csrf_token()},
        )
        assert resp.status_code == 400
        assert "live trading adapter not initialized" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_close_missing_engine_503(self, tmp_path, monkeypatch) -> None:
        app = _make_app(tmp_path, monkeypatch, with_executor=False)
        await _place(app.state.paper_engine, side="BUY", quantity=10)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/execution/positions/NIFTY/close")
        assert resp.status_code == 503


# ── GET /positions/history ────────────────────────────────────────────────

class TestPositionHistory:
    def _record(self, ledger: TradeLedger, fill_id: str, side: str,
                quantity: int, price: float, days_ago: int = 0) -> None:
        recorded = datetime.now(UTC) - timedelta(days=days_ago)
        ledger.record_fill({
            "fill_id": fill_id, "order_id": f"o-{fill_id}", "symbol": "NIFTY",
            "side": side, "quantity": quantity, "price": price,
            "product": "MIS", "source": "test",
            "recorded_at": recorded.isoformat(),
        })

    @pytest.mark.asyncio
    async def test_history_long_pair(self, app_client_with_ledger) -> None:
        app, client = app_client_with_ledger
        ledger = app.state.trade_ledger
        self._record(ledger, "f1", "BUY", 10, 100.0)
        self._record(ledger, "f2", "SELL", 10, 110.0)

        resp = await client.get("/api/execution/positions/history?days=30")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        item = items[0]
        assert item["symbol"] == "NIFTY"
        assert item["entry_price"] == 100.0
        assert item["exit_price"] == 110.0
        assert item["quantity"] == 10
        assert item["realized_pnl"] == pytest.approx(100.0)
        assert item["opened_at"]
        assert item["closed_at"]

    @pytest.mark.asyncio
    async def test_history_short_pair(self, app_client_with_ledger) -> None:
        app, client = app_client_with_ledger
        ledger = app.state.trade_ledger
        self._record(ledger, "f1", "SELL", 5, 200.0)
        self._record(ledger, "f2", "BUY", 5, 180.0)

        resp = await client.get("/api/execution/positions/history?days=30")
        items = resp.json()
        assert len(items) == 1
        assert items[0]["realized_pnl"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_history_empty_when_no_fills(self, app_client_with_ledger) -> None:
        _, client = app_client_with_ledger
        resp = await client.get("/api/execution/positions/history?days=30")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_history_days_filter(self, app_client_with_ledger) -> None:
        app, client = app_client_with_ledger
        ledger = app.state.trade_ledger
        # Recent round-trip pairs; the stale one falls outside the window.
        self._record(ledger, "f1", "BUY", 10, 100.0)
        self._record(ledger, "f2", "SELL", 10, 110.0)
        self._record(ledger, "f3", "BUY", 4, 50.0, days_ago=40)
        self._record(ledger, "f4", "SELL", 4, 60.0, days_ago=40)

        recent = await client.get("/api/execution/positions/history?days=30")
        assert len(recent.json()) == 1
        assert recent.json()[0]["quantity"] == 10

        wide = await client.get("/api/execution/positions/history?days=60")
        assert len(wide.json()) == 2

    @pytest.mark.asyncio
    async def test_history_missing_ledger_returns_empty(
        self, tmp_path, monkeypatch,
    ) -> None:
        app = _make_app(tmp_path, monkeypatch, with_ledger=False)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/execution/positions/history?days=30")
        assert resp.status_code == 200
        assert resp.json() == []
