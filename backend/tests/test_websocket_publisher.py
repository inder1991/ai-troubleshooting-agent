"""Tests for WebSocketTopologyPublisher."""

from __future__ import annotations

import asyncio

import pytest

from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import (
    DEVICE_CHANGED,
    EventType,
    make_device_event,
)
from src.network.event_bus.websocket_publisher import WebSocketTopologyPublisher


# ── Fake WebSocket helpers ────────────────────────────────────────────


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True


class BrokenWebSocket:
    async def send_json(self, data: dict) -> None:
        raise ConnectionError("WebSocket gone")

    async def close(self) -> None:
        pass


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_and_receive():
    bus = MemoryEventBus()
    publisher = WebSocketTopologyPublisher()
    await bus.start()
    await publisher.subscribe(bus)

    ws = FakeWebSocket()
    publisher.register("client-1", ws)

    event = make_device_event("sw-1", EventType.UPDATED, "snmp_poller", data={"hostname": "switch-1"})
    await bus.publish(DEVICE_CHANGED, event.to_dict())

    # Give the consumer loop time to dispatch
    await asyncio.sleep(0.1)

    assert len(ws.sent) == 1
    delta = ws.sent[0]
    assert delta["event_type"] == EventType.UPDATED
    assert delta["entity_id"] == "sw-1"
    assert delta["entity_type"] == "node"
    assert delta["data"]["hostname"] == "switch-1"

    await bus.stop()


@pytest.mark.asyncio
async def test_unregister_stops_delivery():
    bus = MemoryEventBus()
    publisher = WebSocketTopologyPublisher()
    await bus.start()
    await publisher.subscribe(bus)

    ws = FakeWebSocket()
    publisher.register("client-1", ws)
    publisher.unregister("client-1")

    event = make_device_event("sw-2", EventType.CREATED, "snmp_poller")
    await bus.publish(DEVICE_CHANGED, event.to_dict())

    await asyncio.sleep(0.1)

    assert len(ws.sent) == 0

    await bus.stop()


@pytest.mark.asyncio
async def test_broken_websocket_auto_unregisters():
    bus = MemoryEventBus()
    publisher = WebSocketTopologyPublisher()
    await bus.start()
    await publisher.subscribe(bus)

    broken = BrokenWebSocket()
    publisher.register("client-bad", broken)

    event = make_device_event("sw-3", EventType.DELETED, "snmp_poller")
    await bus.publish(DEVICE_CHANGED, event.to_dict())

    await asyncio.sleep(0.1)

    assert "client-bad" not in publisher._clients

    await bus.stop()
