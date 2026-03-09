"""Tests for FlowAggregator enhancements — conversations, app detection, ASN grouping."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.network.flow_receiver import FlowAggregator, APP_PORTS
from src.network.metrics_store import FlowRecord


def _make_flow(
    src_ip="10.0.0.1", dst_ip="10.0.0.2",
    src_port=50000, dst_port=443,
    protocol=6, bytes_=1000, packets=10,
    src_as=0, dst_as=0,
) -> FlowRecord:
    now = datetime.now(timezone.utc)
    return FlowRecord(
        src_ip=src_ip, dst_ip=dst_ip,
        src_port=src_port, dst_port=dst_port,
        protocol=protocol, bytes=bytes_, packets=packets,
        start_time=now, end_time=now,
        src_as=src_as, dst_as=dst_as,
        exporter_ip="10.0.0.254",
    )


@pytest.fixture
def aggregator():
    metrics_store = MagicMock()
    metrics_store.write_flow = AsyncMock()
    metrics_store.write_link_metric = AsyncMock()
    topo_store = MagicMock()
    topo_store.upsert_link_metric = MagicMock()
    return FlowAggregator(metrics_store, topo_store)


# ── Conversation Aggregation ──

@pytest.mark.asyncio
async def test_conversations_aggregation(aggregator):
    aggregator.ingest(_make_flow("10.0.0.1", "10.0.0.2", bytes_=500))
    aggregator.ingest(_make_flow("10.0.0.1", "10.0.0.2", bytes_=300))
    aggregator.ingest(_make_flow("10.0.0.3", "10.0.0.4", bytes_=1000))

    await aggregator.flush()

    convos = aggregator.get_conversations()
    assert len(convos) == 2
    # Sorted by bytes desc
    assert convos[0]["bytes"] == 1000
    assert convos[0]["src_ip"] == "10.0.0.3"
    assert convos[1]["bytes"] == 800  # 500 + 300
    assert convos[1]["src_ip"] == "10.0.0.1"
    assert convos[1]["flows"] == 2


@pytest.mark.asyncio
async def test_conversations_limit(aggregator):
    for i in range(20):
        aggregator.ingest(_make_flow(f"10.0.{i}.1", f"10.0.{i}.2", bytes_=i * 100))

    await aggregator.flush()

    convos = aggregator.get_conversations(limit=5)
    assert len(convos) == 5


# ── Application Detection ──

@pytest.mark.asyncio
async def test_application_detection_https(aggregator):
    aggregator.ingest(_make_flow(dst_port=443, bytes_=1000))
    aggregator.ingest(_make_flow(dst_port=443, bytes_=2000))

    await aggregator.flush()

    apps = aggregator.get_applications()
    https_app = next((a for a in apps if a["application"] == "HTTPS"), None)
    assert https_app is not None
    assert https_app["bytes"] == 3000
    assert https_app["flows"] == 2
    assert https_app["percentage"] == 100.0


@pytest.mark.asyncio
async def test_application_detection_multiple(aggregator):
    aggregator.ingest(_make_flow(dst_port=443, bytes_=600))
    aggregator.ingest(_make_flow(dst_port=53, bytes_=200))
    aggregator.ingest(_make_flow(dst_port=22, bytes_=200))

    await aggregator.flush()

    apps = aggregator.get_applications()
    assert len(apps) == 3
    app_names = {a["application"] for a in apps}
    assert "HTTPS" in app_names
    assert "DNS" in app_names
    assert "SSH" in app_names

    # Check percentages sum to 100
    total_pct = sum(a["percentage"] for a in apps)
    assert abs(total_pct - 100.0) < 0.01


@pytest.mark.asyncio
async def test_application_detection_unknown_port(aggregator):
    aggregator.ingest(_make_flow(dst_port=9999, bytes_=1000))

    await aggregator.flush()

    apps = aggregator.get_applications()
    assert len(apps) == 1
    assert apps[0]["application"] == "Other"


def test_app_ports_contains_common_ports():
    assert APP_PORTS[443] == "HTTPS"
    assert APP_PORTS[53] == "DNS"
    assert APP_PORTS[80] == "HTTP"
    assert APP_PORTS[22] == "SSH"
    assert APP_PORTS[3306] == "MySQL"
    assert APP_PORTS[5432] == "PostgreSQL"
    assert APP_PORTS[6379] == "Redis"
    assert APP_PORTS[27017] == "MongoDB"


# ── ASN Grouping ──

@pytest.mark.asyncio
async def test_asn_aggregation(aggregator):
    aggregator.ingest(_make_flow(src_as=64512, dst_as=64513, bytes_=500))
    aggregator.ingest(_make_flow(src_as=64512, dst_as=64514, bytes_=300))

    await aggregator.flush()

    asns = aggregator.get_asn_breakdown()
    assert len(asns) == 3  # 64512, 64513, 64514
    asn_map = {a["asn"]: a for a in asns}
    assert asn_map[64512]["bytes"] == 800  # 500 + 300 (src in both flows)
    assert asn_map[64513]["bytes"] == 500
    assert asn_map[64514]["bytes"] == 300


@pytest.mark.asyncio
async def test_asn_zero_excluded(aggregator):
    aggregator.ingest(_make_flow(src_as=0, dst_as=0, bytes_=1000))

    await aggregator.flush()

    asns = aggregator.get_asn_breakdown()
    assert len(asns) == 0  # ASN 0 should be excluded


@pytest.mark.asyncio
async def test_asn_limit(aggregator):
    for i in range(1, 50):
        aggregator.ingest(_make_flow(src_as=i, bytes_=i * 10))

    await aggregator.flush()

    asns = aggregator.get_asn_breakdown(limit=10)
    assert len(asns) == 10
    # Should be sorted by bytes desc
    assert asns[0]["bytes"] >= asns[1]["bytes"]


# ── Event Bus Publishing ──

@pytest.mark.asyncio
async def test_flush_publishes_to_event_bus(aggregator):
    bus = MagicMock()
    bus.publish = MagicMock()  # sync mock since FlowAggregator calls it sync
    aggregator.set_event_bus(bus)

    aggregator.ingest(_make_flow(bytes_=1000))
    await aggregator.flush()

    bus.publish.assert_called_once()
    args = bus.publish.call_args
    assert args[0][0] == "flows"
    aggregate = args[0][1]
    assert aggregate["flow_count"] == 1
    assert aggregate["total_bytes"] == 1000


@pytest.mark.asyncio
async def test_flush_no_publish_without_bus(aggregator):
    # No event bus set — should not raise
    aggregator.ingest(_make_flow(bytes_=1000))
    count = await aggregator.flush()
    assert count == 1


# ── Data Freshness ──

@pytest.mark.asyncio
async def test_data_resets_on_each_flush(aggregator):
    aggregator.ingest(_make_flow(dst_port=443, bytes_=1000))
    await aggregator.flush()

    assert len(aggregator.get_conversations()) == 1
    assert len(aggregator.get_applications()) == 1

    # Second flush with different data
    aggregator.ingest(_make_flow(dst_port=53, bytes_=500, src_ip="10.1.1.1"))
    await aggregator.flush()

    # Should only have the second flush's data
    convos = aggregator.get_conversations()
    assert len(convos) == 1
    assert convos[0]["src_ip"] == "10.1.1.1"

    apps = aggregator.get_applications()
    assert len(apps) == 1
    assert apps[0]["application"] == "DNS"
