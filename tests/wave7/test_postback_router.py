"""Tests for PostbackRouter (Dhan order status updates)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.terminal.api.postback_router import router, set_event_bus


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
    payload = {
        "order_id": "DH12345",
        "status": "PLACED",
        "filled_quantity": 0,
        "average_price": 0.0,
    }
    client.post("/api/postback/dhan", json=payload)
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
    payload = {
        "order_id": "DH99999",
        "status": "FILLED",
        "filled_quantity": 50,
        "average_price": 18450.75,
        "extra_field": "ignored",
    }
    client.post("/api/postback/dhan", json=payload)
    _drain_event_bus(bus)

    assert len(captured) == 1
    data = captured[0].data
    assert data["order_id"] == "DH99999"
    assert data["status"] == "FILLED"
    assert data["filled_quantity"] == 50
    assert data["average_price"] == 18450.75
