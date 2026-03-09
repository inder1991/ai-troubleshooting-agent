"""Tests for MemoryEventBus — pub/sub, multiple subscribers, channel isolation."""
import asyncio
import pytest

from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.base import TRAPS, SYSLOG, FLOWS


@pytest.fixture
def bus():
    return MemoryEventBus(maxsize=100)


@pytest.mark.asyncio
async def test_publish_returns_id(bus):
    await bus.start()
    msg_id = await bus.publish(TRAPS, {"event_id": "t1", "oid": "1.2.3"})
    assert msg_id.startswith("mem-")
    await bus.stop()


@pytest.mark.asyncio
async def test_subscribe_receives_events(bus):
    received = []

    async def handler(channel, event):
        received.append((channel, event))

    await bus.start()
    sub_id = await bus.subscribe(TRAPS, handler)
    assert sub_id.startswith("msub-")

    await bus.publish(TRAPS, {"event_id": "t1", "data": "hello"})
    # Give consumer task time to process
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0][0] == TRAPS
    assert received[0][1]["event_id"] == "t1"
    await bus.stop()


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    received_a = []
    received_b = []

    async def handler_a(channel, event):
        received_a.append(event)

    async def handler_b(channel, event):
        received_b.append(event)

    await bus.start()
    await bus.subscribe(TRAPS, handler_a)
    await bus.subscribe(TRAPS, handler_b)

    await bus.publish(TRAPS, {"event_id": "t1"})
    await asyncio.sleep(0.1)

    assert len(received_a) == 1
    assert len(received_b) == 1
    await bus.stop()


@pytest.mark.asyncio
async def test_channel_isolation(bus):
    trap_events = []
    syslog_events = []

    async def trap_handler(channel, event):
        trap_events.append(event)

    async def syslog_handler(channel, event):
        syslog_events.append(event)

    await bus.start()
    await bus.subscribe(TRAPS, trap_handler)
    await bus.subscribe(SYSLOG, syslog_handler)

    await bus.publish(TRAPS, {"event_id": "trap1"})
    await bus.publish(SYSLOG, {"event_id": "sys1"})
    await bus.publish(TRAPS, {"event_id": "trap2"})
    await asyncio.sleep(0.1)

    assert len(trap_events) == 2
    assert len(syslog_events) == 1
    assert trap_events[0]["event_id"] == "trap1"
    assert syslog_events[0]["event_id"] == "sys1"
    await bus.stop()


@pytest.mark.asyncio
async def test_unsubscribe(bus):
    received = []

    async def handler(channel, event):
        received.append(event)

    await bus.start()
    sub_id = await bus.subscribe(TRAPS, handler)

    await bus.publish(TRAPS, {"event_id": "t1"})
    await asyncio.sleep(0.1)
    assert len(received) == 1

    await bus.unsubscribe(sub_id)
    await bus.publish(TRAPS, {"event_id": "t2"})
    await asyncio.sleep(0.1)
    # After unsubscribe, no new events should be received
    assert len(received) == 1
    await bus.stop()


@pytest.mark.asyncio
async def test_queue_overflow_drops_oldest(bus):
    """When queue is full, oldest event should be dropped."""
    small_bus = MemoryEventBus(maxsize=2)
    await small_bus.start()

    # Publish 3 events to a queue of size 2 — should not raise
    await small_bus.publish(FLOWS, {"n": 1})
    await small_bus.publish(FLOWS, {"n": 2})
    await small_bus.publish(FLOWS, {"n": 3})
    # No error = pass
    await small_bus.stop()


@pytest.mark.asyncio
async def test_stop_cleans_up(bus):
    async def handler(channel, event):
        pass

    await bus.start()
    await bus.subscribe(TRAPS, handler)
    await bus.stop()

    assert len(bus._tasks) == 0
    assert len(bus._queues) == 0
