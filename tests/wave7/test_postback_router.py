"""Tests for the order-update bridge (Fyers order socket -> ORDER_UPDATED).

Fyers has no postback webhooks: order status updates arrive as JSON frames
on the order WebSocket and are parsed by ``consume_order_message``. The
legacy HTTP POST path is retained for the migration window.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.terminal.api.postback_router import (
    _extract_order_updates,
    _normalize_update,
    consume_order_message,
    router,
    set_event_bus,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _drain_event_bus(bus: EventBus) -> None:
    while not bus._queue.empty():
        event = bus._queue.get_nowait()
        handlers = bus._subscribers.get(event.topic, [])
        for h in handlers:
            asyncio.run(h(event))


@pytest.fixture(autouse=True)
def _reset_event_bus() -> None:
    set_event_bus(None)
    yield
    set_event_bus(None)


# ── Order-socket frame parsing ─────────────────────────────────────────

def test_extract_bare_order_dict() -> None:
    updates = _extract_order_updates({"id": "FY123", "status": 3, "filledQty": 10})
    assert len(updates) == 1
    assert updates[0]["id"] == "FY123"


def test_extract_envelope_with_data() -> None:
    updates = _extract_order_updates(
        {"T": "ORD", "data": {"id": "FY1", "status": 3, "filledQty": 5}}
    )
    assert len(updates) == 1
    assert updates[0]["id"] == "FY1"


def test_extract_orders_list() -> None:
    updates = _extract_order_updates(
        {"T": "ORD", "orders": [{"id": "FY1"}, {"id": "FY2"}]}
    )
    assert [u["id"] for u in updates] == ["FY1", "FY2"]


def test_extract_ignores_non_order_frames() -> None:
    assert _extract_order_updates({"T": "OK", "code": 0}) == []
    assert _extract_order_updates("ping") == []
    assert _extract_order_updates(None) == []


def test_normalize_update_maps_fyers_fields() -> None:
    normalized = _normalize_update(
        {"id": "FY1", "status": 3, "filledQty": 50, "tradedPrice": 18450.75}
    )
    assert normalized["order_id"] == "FY1"
    assert normalized["status"] == 3
    assert normalized["filled_quantity"] == 50
    assert normalized["average_price"] == 18450.75


# ── consume_order_message (socket path) ────────────────────────────────

def test_consume_order_message_publishes_event() -> None:
    bus = EventBus()
    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.ORDER_UPDATED, handler)
    set_event_bus(bus)

    asyncio.run(consume_order_message(
        {"T": "ORD", "data": {"id": "FY1", "status": 3, "filledQty": 50}}
    ))
    _drain_event_bus(bus)

    assert len(captured) == 1
    assert captured[0].topic == Topic.ORDER_UPDATED
    assert captured[0].data["order_id"] == "FY1"


def test_consume_order_message_ignores_non_orders() -> None:
    bus = EventBus()
    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.ORDER_UPDATED, handler)
    set_event_bus(bus)

    asyncio.run(consume_order_message({"T": "OK", "code": 0}))

    assert captured == []


# ── Legacy HTTP POST path (migration window) ──────────────────────────

def test_postback_returns_ok() -> None:
    app = _make_app()
    client = TestClient(app)
    payload = {
        "order_id": "DH12345",
        "status": "PLACED",
        "filled_quantity": 0,
        "average_price": 0.0,
    }
    resp = client.post("/api/postback/dhan", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_postback_publishes_event() -> None:
    bus = EventBus()
    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.ORDER_UPDATED, handler)
    set_event_bus(bus)

    app = _make_app()
    client = TestClient(app)
    client.post("/api/postback/dhan", json={
        "order_id": "DH12345",
        "status": "PLACED",
        "filled_quantity": 0,
        "average_price": 0.0,
    })
    _drain_event_bus(bus)

    assert len(captured) == 1
    assert captured[0].topic == Topic.ORDER_UPDATED


def test_postback_handles_invalid_json() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/api/postback/dhan",
        content="not json at all",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "error"}


def test_postback_handles_empty_body() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/api/postback/dhan", json={})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_postback_extracts_order_fields() -> None:
    bus = EventBus()
    captured: list[Event] = []

    async def handler(event: Event) -> None:
        captured.append(event)

    bus.subscribe(Topic.ORDER_UPDATED, handler)
    set_event_bus(bus)

    app = _make_app()
    client = TestClient(app)
    client.post("/api/postback/dhan", json={
        "order_id": "DH99999",
        "status": "FILLED",
        "filled_quantity": 50,
        "average_price": 18450.75,
        "extra_field": "ignored",
    })
    _drain_event_bus(bus)

    assert len(captured) == 1
    data = captured[0].data
    assert data["order_id"] == "DH99999"
    assert data["status"] == "FILLED"
    assert data["filled_quantity"] == 50
    assert data["average_price"] == 18450.75
