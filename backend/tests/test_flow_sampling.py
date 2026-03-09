"""Tests for flow sampling rate compensation (#25)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.network.metrics_store import FlowRecord
from src.network.flow_receiver import FlowAggregator


def _make_flow(
    src_ip="10.0.0.1",
    dst_ip="10.0.0.2",
    src_port=12345,
    dst_port=443,
    protocol=6,
    bytes_=1000,
    packets=10,
    sampling_interval=1,
):
    now = datetime.now(tz=timezone.utc)
    return FlowRecord(
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=dst_port,
        protocol=protocol,
        bytes=bytes_,
        packets=packets,
        start_time=now,
        end_time=now,
        exporter_ip=src_ip,
        sampling_interval=sampling_interval,
    )


@pytest.fixture
def aggregator():
    metrics = AsyncMock()
    topo = MagicMock()
    topo.upsert_link_metric = MagicMock()
    return FlowAggregator(metrics, topo)


@pytest.mark.asyncio
async def test_sampling_compensation_multiplies_bytes_and_packets(aggregator):
    """Flows with sampling_interval=100 should have bytes and packets multiplied."""
    flow = _make_flow(bytes_=1000, packets=10, sampling_interval=100)
    aggregator.ingest(flow)
    await aggregator.flush()

    # After flush, the flow object should have been compensated
    assert flow.bytes == 1000 * 100
    assert flow.packets == 10 * 100


@pytest.mark.asyncio
async def test_sampling_compensation_reflected_in_conversations(aggregator):
    """Top talkers (conversations) should reflect compensated values."""
    flow = _make_flow(bytes_=500, packets=5, sampling_interval=100)
    aggregator.ingest(flow)
    await aggregator.flush()

    convos = aggregator.get_conversations()
    assert len(convos) == 1
    assert convos[0]["bytes"] == 500 * 100
    assert convos[0]["packets"] == 5 * 100


@pytest.mark.asyncio
async def test_sampling_interval_1_no_change(aggregator):
    """sampling_interval=1 should not alter the values."""
    flow = _make_flow(bytes_=1000, packets=10, sampling_interval=1)
    aggregator.ingest(flow)
    await aggregator.flush()

    assert flow.bytes == 1000
    assert flow.packets == 10


@pytest.mark.asyncio
async def test_sampling_compensation_in_applications(aggregator):
    """Application breakdown should use compensated values."""
    flow = _make_flow(dst_port=443, bytes_=200, packets=2, sampling_interval=50)
    aggregator.ingest(flow)
    await aggregator.flush()

    apps = aggregator.get_applications()
    https_app = next(a for a in apps if a["application"] == "HTTPS")
    assert https_app["bytes"] == 200 * 50
    assert https_app["packets"] == 2 * 50


@pytest.mark.asyncio
async def test_sampling_compensation_multiple_flows(aggregator):
    """Multiple flows with different sampling intervals are each compensated."""
    f1 = _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2", bytes_=100, packets=1, sampling_interval=10)
    f2 = _make_flow(src_ip="10.0.0.3", dst_ip="10.0.0.4", bytes_=200, packets=2, sampling_interval=100)
    aggregator.ingest(f1)
    aggregator.ingest(f2)
    await aggregator.flush()

    assert f1.bytes == 100 * 10
    assert f1.packets == 1 * 10
    assert f2.bytes == 200 * 100
    assert f2.packets == 2 * 100
