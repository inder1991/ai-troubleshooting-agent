# backend/tests/test_flow_receiver.py
import pytest
import struct
from unittest.mock import AsyncMock
from src.network.flow_receiver import FlowParser, NetFlowV5Header, NetFlowV5Record
from src.network.metrics_store import FlowRecord


def _build_v5_packet(records: list[dict]) -> bytes:
    """Build a valid NetFlow v5 packet for testing."""
    count = len(records)
    # Header: version(2) + count(2) + sysuptime(4) + unix_secs(4) + unix_nsecs(4)
    #         + flow_seq(4) + engine_type(1) + engine_id(1) + sampling(2)
    header = struct.pack(
        "!HHIIIIBBh",
        5, count, 1000, 1709600000, 0, 1, 0, 0, 0,
    )
    body = b""
    for r in records:
        body += struct.pack(
            "!IIIHHIIIIHHBBBBHHBBH",
            int.from_bytes(bytes(map(int, r.get("src_ip", "10.0.0.1").split("."))), "big"),
            int.from_bytes(bytes(map(int, r.get("dst_ip", "10.0.0.2").split("."))), "big"),
            0, 0, 0,  # nexthop, input, output
            r.get("packets", 100),
            r.get("bytes", 5000),
            0, 0,  # first, last
            r.get("src_port", 12345),
            r.get("dst_port", 80),
            0,  # pad1
            0,  # tcp_flags
            r.get("protocol", 6),
            0,  # tos
            0, 0,  # src_as, dst_as
            0, 0,  # src_mask, dst_mask
            0,  # pad2
        )
    return header + body


def test_parse_v5_single_record():
    packet = _build_v5_packet([{"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "bytes": 5000}])
    parser = FlowParser()
    records = parser.parse_v5(packet, "192.168.1.1")
    assert len(records) == 1
    assert records[0].src_ip == "10.0.0.1"
    assert records[0].dst_ip == "10.0.0.2"
    assert records[0].bytes == 5000
    assert records[0].exporter_ip == "192.168.1.1"


def test_parse_v5_multiple_records():
    packet = _build_v5_packet([
        {"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2"},
        {"src_ip": "10.0.0.3", "dst_ip": "10.0.0.4"},
    ])
    parser = FlowParser()
    records = parser.parse_v5(packet, "192.168.1.1")
    assert len(records) == 2


def test_parse_v5_invalid_packet():
    parser = FlowParser()
    records = parser.parse_v5(b"\x00\x05\x00\x01", "192.168.1.1")  # Too short
    assert len(records) == 0


@pytest.mark.asyncio
async def test_flow_aggregator():
    from src.network.flow_receiver import FlowAggregator
    mock_metrics = AsyncMock()
    mock_store = type("MockStore", (), {"upsert_link_metric": lambda *a, **kw: None})()
    agg = FlowAggregator(mock_metrics, mock_store, device_ip_map={"192.168.1.1": "dev-1"})
    flow = FlowRecord(
        src_ip="10.0.0.1", dst_ip="10.0.0.2",
        src_port=12345, dst_port=80, protocol=6,
        bytes=5000, packets=100,
        start_time=__import__("datetime").datetime.now(),
        end_time=__import__("datetime").datetime.now(),
        exporter_ip="192.168.1.1",
    )
    agg.ingest(flow)
    assert len(agg._buffer) == 1
    await agg.flush()
    assert mock_metrics.write_flow.call_count == 1
