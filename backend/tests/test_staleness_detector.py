"""Tests for StalenessDetector — stale entity scanning and event publishing."""

from __future__ import annotations

import asyncio

import pytest

from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.topology_channels import STALE_DETECTED
from src.network.models import Device as PydanticDevice, DeviceType
from src.network.repository.sqlite_repository import SQLiteRepository
from src.network.repository.staleness_detector import StalenessDetector
from src.network.topology_store import TopologyStore


@pytest.fixture
def setup(tmp_path):
    store = TopologyStore(str(tmp_path / "test.db"))
    repo = SQLiteRepository(store)
    bus = MemoryEventBus()

    store.add_device(PydanticDevice(
        id="old-device",
        name="old-device",
        device_type=DeviceType.ROUTER,
        management_ip="10.0.0.1",
        vendor="cisco",
        last_seen="2026-01-01T00:00:00Z",
    ))
    store.add_device(PydanticDevice(
        id="fresh-device",
        name="fresh-device",
        device_type=DeviceType.SWITCH,
        management_ip="10.0.0.2",
        vendor="cisco",
    ))

    loop = asyncio.new_event_loop()
    loop.run_until_complete(bus.start())
    detector = StalenessDetector(repo=repo, event_bus=bus, stale_threshold_minutes=1)
    yield detector, bus, repo, loop
    loop.run_until_complete(bus.stop())
    loop.close()


def test_detects_stale_devices(setup):
    """old-device (last_seen in 2026-01-01) should be detected as stale."""
    detector, bus, repo, loop = setup
    captured: list[dict] = []

    async def handler(channel: str, event: dict) -> None:
        captured.append(event)

    loop.run_until_complete(bus.subscribe(STALE_DETECTED, handler))
    count = loop.run_until_complete(detector.scan_once())

    # Give the consumer task a moment to deliver the event
    loop.run_until_complete(asyncio.sleep(0.2))

    assert count >= 1
    stale_ids = [e["entity_id"] for e in captured]
    assert "old-device" in stale_ids


def test_fresh_device_not_flagged(setup):
    """fresh-device (last_seen defaults to now) must NOT appear in stale events."""
    detector, bus, repo, loop = setup
    captured: list[dict] = []

    async def handler(channel: str, event: dict) -> None:
        captured.append(event)

    loop.run_until_complete(bus.subscribe(STALE_DETECTED, handler))
    loop.run_until_complete(detector.scan_once())

    # Give the consumer task a moment to deliver the event
    loop.run_until_complete(asyncio.sleep(0.2))

    stale_ids = [e["entity_id"] for e in captured]
    assert "fresh-device" not in stale_ids
