"""Tests for MemoryEventBus — pub/sub, multiple subscribers, channel isolation, DLQ, backpressure."""
import asyncio
import pytest

from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.base import TRAPS, SYSLOG, FLOWS
from src.network.event_bus.errors import BackpressureError


@pytest.fixture
def bus():
    """Create a MemoryEventBus with spec-compatible interface."""
    return MemoryEventBus(maxsize=100)


@pytest.fixture
def spec_bus():
    """Create a MemoryEventBus verified against the EventBus spec."""
    b = MemoryEventBus(maxsize=100)
    # Verify it implements the EventBus protocol
    assert hasattr(b, "publish")
    assert hasattr(b, "subscribe")
    assert hasattr(b, "unsubscribe")
    assert hasattr(b, "start")
    assert hasattr(b, "stop")
    return b


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
async def test_queue_overflow_triggers_backpressure(bus):
    """With a tiny queue (maxsize=2), backpressure fires on the 3rd publish.

    80% of 2 = 1.6.  After two publishes qsize=2, and ``2 > 1.6`` is True,
    so the third ``publish`` raises ``BackpressureError``.
    """
    small_bus = MemoryEventBus(maxsize=2)
    await small_bus.start()

    await small_bus.publish(FLOWS, {"n": 1})  # qsize → 1; 1 > 1.6? No
    await small_bus.publish(FLOWS, {"n": 2})  # qsize → 2; checked before enqueue: 1 > 1.6? No → enqueued
    with pytest.raises(BackpressureError):
        await small_bus.publish(FLOWS, {"n": 3})  # qsize=2; 2 > 1.6? Yes → raises
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


# ── Task 8: Dead Letter Queue ────────────────────────────────────────


@pytest.mark.asyncio
async def test_failed_handler_routes_to_dlq():
    bus = MemoryEventBus(maxsize=100)
    await bus.start()

    async def failing_handler(channel, event):
        raise ValueError("handler crashed")

    await bus.subscribe("traps", failing_handler)
    await bus.publish("traps", {"oid": "1.2.3", "severity": "critical"})
    await asyncio.sleep(0.2)

    dlq = bus.get_dlq("traps")
    assert len(dlq) == 1
    assert dlq[0]["event"]["oid"] == "1.2.3"
    assert "handler crashed" in dlq[0]["error"]
    assert "timestamp" in dlq[0]
    await bus.stop()


@pytest.mark.asyncio
async def test_dlq_empty_for_clean_channel():
    bus = MemoryEventBus(maxsize=100)
    await bus.start()

    async def good_handler(channel, event):
        pass

    await bus.subscribe(TRAPS, good_handler)
    await bus.publish(TRAPS, {"oid": "1.2.3"})
    await asyncio.sleep(0.1)

    dlq = bus.get_dlq(TRAPS)
    assert len(dlq) == 0
    await bus.stop()


@pytest.mark.asyncio
async def test_dlq_isolates_channels():
    bus = MemoryEventBus(maxsize=100)
    await bus.start()

    async def failing_handler(channel, event):
        raise RuntimeError("boom")

    async def good_handler(channel, event):
        pass

    await bus.subscribe(TRAPS, failing_handler)
    await bus.subscribe(SYSLOG, good_handler)

    await bus.publish(TRAPS, {"oid": "1.2.3"})
    await bus.publish(SYSLOG, {"msg": "ok"})
    await asyncio.sleep(0.2)

    assert len(bus.get_dlq(TRAPS)) == 1
    assert len(bus.get_dlq(SYSLOG)) == 0
    await bus.stop()


# ── Task 9: Backpressure ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backpressure_raises_on_full_queue():
    bus = MemoryEventBus(maxsize=10)
    await bus.start()
    # Don't subscribe any consumer so messages pile up
    with pytest.raises(BackpressureError):
        for i in range(20):
            await bus.publish("traps", {"i": i})
    await bus.stop()


@pytest.mark.asyncio
async def test_publish_under_threshold_succeeds():
    """Publishing below 80% capacity should not raise."""
    bus = MemoryEventBus(maxsize=100)
    await bus.start()
    # 80% of 100 = 80; publishing up to 80 should be fine
    for i in range(80):
        await bus.publish(TRAPS, {"i": i})
    # Should not have raised
    await bus.stop()


@pytest.mark.asyncio
async def test_backpressure_threshold_boundary():
    """Verify the exact boundary: qsize=80 passes, qsize=81 raises.

    maxsize=100 → threshold = 80.0 (strictly greater).
    After 81 publishes, qsize=81; the 82nd publish sees ``81 > 80.0`` → raises.
    """
    bus = MemoryEventBus(maxsize=100)
    await bus.start()
    # Fill to 81 — the 81st publish checks qsize=80 which is NOT > 80.0
    for i in range(81):
        await bus.publish(TRAPS, {"i": i})

    # The 82nd publish checks qsize=81 which IS > 80.0 → backpressure
    with pytest.raises(BackpressureError):
        await bus.publish(TRAPS, {"i": 82})
    await bus.stop()


# ── Negative tests ──


@pytest.mark.asyncio
async def test_publish_empty_event(bus):
    """Publishing an empty dict should succeed without errors."""
    await bus.start()
    msg_id = await bus.publish(TRAPS, {})
    assert msg_id.startswith("mem-")
    await bus.stop()


@pytest.mark.asyncio
async def test_unsubscribe_invalid_id(bus):
    """Unsubscribing with a non-existent ID should not raise."""
    await bus.start()
    await bus.unsubscribe("nonexistent-sub-id")  # Should be a no-op
    await bus.stop()


@pytest.mark.asyncio
async def test_publish_none_value_in_event(bus):
    """Publishing event with None values should serialize cleanly via JSON."""
    received = []

    async def handler(channel, event):
        received.append(event)

    await bus.start()
    await bus.subscribe(TRAPS, handler)
    await bus.publish(TRAPS, {"key": None, "list": [None]})
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0]["key"] is None
    assert received[0]["list"] == [None]
    await bus.stop()
