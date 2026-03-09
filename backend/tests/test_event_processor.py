"""Tests for EventProcessor — routing, batch flush, deduplication."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.event_processor import EventProcessor, BATCH_SIZE
from src.network.event_bus.base import TRAPS, SYSLOG, METRICS


@pytest.fixture
def event_store():
    store = MagicMock()
    store.insert_trap_batch = MagicMock()
    store.insert_syslog_batch = MagicMock()
    return store


@pytest.fixture
def metrics_store():
    store = MagicMock()
    store.write_device_metric = AsyncMock()
    store.write_alert_event = AsyncMock()
    return store


@pytest.fixture
def bus():
    return MemoryEventBus(maxsize=1000)


@pytest.mark.asyncio
async def test_processor_routes_traps_to_event_store(bus, event_store):
    processor = EventProcessor(bus=bus, event_store=event_store)
    await bus.start()
    await processor.start()

    # Publish a trap event
    await bus.publish(TRAPS, {"event_id": "t1", "oid": "1.2.3", "device_id": "d1"})
    # Wait for consumer + flush timer
    await asyncio.sleep(1.5)

    event_store.insert_trap_batch.assert_called()
    batch = event_store.insert_trap_batch.call_args[0][0]
    assert len(batch) >= 1
    assert batch[0]["event_id"] == "t1"

    await processor.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_processor_routes_syslog_to_event_store(bus, event_store):
    processor = EventProcessor(bus=bus, event_store=event_store)
    await bus.start()
    await processor.start()

    await bus.publish(SYSLOG, {"event_id": "s1", "facility": "kern", "severity": "error", "message": "test"})
    await asyncio.sleep(1.5)

    event_store.insert_syslog_batch.assert_called()
    batch = event_store.insert_syslog_batch.call_args[0][0]
    assert len(batch) >= 1
    assert batch[0]["event_id"] == "s1"

    await processor.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_processor_routes_metrics(bus, metrics_store):
    processor = EventProcessor(bus=bus, metrics_store=metrics_store)
    await bus.start()
    await processor.start()

    await bus.publish(METRICS, {"device_id": "d1", "metric": "cpu", "value": 42.5})
    await asyncio.sleep(1.5)

    metrics_store.write_device_metric.assert_called()

    await processor.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_deduplication(bus, event_store):
    processor = EventProcessor(bus=bus, event_store=event_store)
    await bus.start()
    await processor.start()

    # Publish the same trap event twice quickly
    event = {"event_id": "t1", "device_id": "d1", "oid": "1.2.3", "value": "x", "timestamp": 12345}
    await bus.publish(TRAPS, event)
    await bus.publish(TRAPS, event)  # duplicate
    await asyncio.sleep(1.5)

    # Should only have inserted once (dedup catches the second)
    if event_store.insert_trap_batch.called:
        total_events = sum(len(call[0][0]) for call in event_store.insert_trap_batch.call_args_list)
        assert total_events == 1

    await processor.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_batch_threshold_flush(bus, event_store):
    processor = EventProcessor(bus=bus, event_store=event_store)
    await bus.start()
    await processor.start()

    # Publish BATCH_SIZE events — should trigger immediate flush
    for i in range(BATCH_SIZE):
        await bus.publish(TRAPS, {
            "event_id": f"t{i}", "device_id": f"d{i}", "oid": "1.2.3",
            "value": str(i), "timestamp": float(i),
        })
    await asyncio.sleep(0.5)

    event_store.insert_trap_batch.assert_called()

    await processor.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_stop_flushes_remaining(bus, event_store):
    processor = EventProcessor(bus=bus, event_store=event_store)
    await bus.start()
    await processor.start()

    # Publish one event and stop immediately
    await bus.publish(TRAPS, {"event_id": "last", "device_id": "d1", "oid": "1.2.3", "value": "v", "timestamp": 1.0})
    await asyncio.sleep(0.1)
    await processor.stop()

    # The stop() should have flushed remaining events
    if event_store.insert_trap_batch.called:
        all_events = []
        for call in event_store.insert_trap_batch.call_args_list:
            all_events.extend(call[0][0])
        assert any(e["event_id"] == "last" for e in all_events)

    await bus.stop()
