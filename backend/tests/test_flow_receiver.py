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


# ── NetFlow v9 helpers ──────────────────────────────────────────────

def _build_v9_template_packet(template_id=256):
    import struct, socket
    header = struct.pack("!HHIIII", 9, 1, 1000, 1709740800, 1, 100)
    fields = [
        (1, 4), (2, 4), (7, 2), (11, 2), (4, 1), (8, 4), (12, 4),
    ]
    field_count = len(fields)
    template_record = struct.pack("!HH", template_id, field_count)
    for ftype, flen in fields:
        template_record += struct.pack("!HH", ftype, flen)
    flowset_length = 4 + len(template_record)
    pad = (4 - flowset_length % 4) % 4
    flowset = struct.pack("!HH", 0, flowset_length + pad) + template_record + b"\x00" * pad
    return header + flowset


def _build_v9_data_packet(template_id=256):
    import struct, socket
    header = struct.pack("!HHIIII", 9, 1, 2000, 1709740830, 2, 100)
    src_ip = socket.inet_aton("10.0.0.1")
    dst_ip = socket.inet_aton("10.0.0.2")
    data_record = struct.pack("!IIHHB", 1500, 10, 12345, 443, 6) + src_ip + dst_ip
    record_size = len(data_record)
    flowset_length = 4 + record_size
    pad = (4 - flowset_length % 4) % 4
    flowset = struct.pack("!HH", template_id, flowset_length + pad) + data_record + b"\x00" * pad
    return header + flowset


def test_parse_v9_template_then_data():
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()
    template_pkt = _build_v9_template_packet(template_id=256)
    records = parser.detect_and_parse(template_pkt, "10.0.0.254")
    assert records == []

    data_pkt = _build_v9_data_packet(template_id=256)
    records = parser.detect_and_parse(data_pkt, "10.0.0.254")
    assert len(records) == 1
    assert records[0].src_ip == "10.0.0.1"
    assert records[0].dst_ip == "10.0.0.2"
    assert records[0].src_port == 12345
    assert records[0].dst_port == 443
    assert records[0].protocol == 6
    assert records[0].bytes == 1500
    assert records[0].packets == 10


def test_parse_v9_data_without_template():
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()
    data_pkt = _build_v9_data_packet(template_id=999)
    records = parser.detect_and_parse(data_pkt, "10.0.0.254")
    assert records == []


def test_parse_v9_multiple_exporters():
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()
    tpl = _build_v9_template_packet(template_id=256)
    parser.detect_and_parse(tpl, "10.0.0.1")
    data = _build_v9_data_packet(template_id=256)
    records = parser.detect_and_parse(data, "10.0.0.2")
    assert records == []
    records = parser.detect_and_parse(data, "10.0.0.1")
    assert len(records) == 1


# ── IPFIX helpers ───────────────────────────────────────────────────

def _build_ipfix_template_packet(template_id=256):
    import struct
    fields = [(1, 4), (2, 4), (7, 2), (11, 2), (4, 1), (8, 4), (12, 4)]
    field_count = len(fields)
    template_record = struct.pack("!HH", template_id, field_count)
    for ftype, flen in fields:
        template_record += struct.pack("!HH", ftype, flen)
    set_length = 4 + len(template_record)
    pad = (4 - set_length % 4) % 4
    template_set = struct.pack("!HH", 2, set_length + pad) + template_record + b"\x00" * pad
    total_length = 16 + len(template_set)
    header = struct.pack("!HHIII", 10, total_length, 1709740800, 1, 200)
    return header + template_set


def _build_ipfix_data_packet(template_id=256):
    import struct, socket
    src_ip = socket.inet_aton("192.168.1.1")
    dst_ip = socket.inet_aton("192.168.1.2")
    data_record = struct.pack("!IIHHB", 2500, 15, 54321, 80, 6) + src_ip + dst_ip
    set_length = 4 + len(data_record)
    pad = (4 - set_length % 4) % 4
    data_set = struct.pack("!HH", template_id, set_length + pad) + data_record + b"\x00" * pad
    total_length = 16 + len(data_set)
    header = struct.pack("!HHIII", 10, total_length, 1709740830, 2, 200)
    return header + data_set


def test_parse_ipfix_template_then_data():
    from src.network.flow_receiver import FlowParser
    parser = FlowParser()
    tpl = _build_ipfix_template_packet(template_id=300)
    records = parser.detect_and_parse(tpl, "10.0.0.100")
    assert records == []
    data = _build_ipfix_data_packet(template_id=300)
    records = parser.detect_and_parse(data, "10.0.0.100")
    assert len(records) == 1
    assert records[0].src_ip == "192.168.1.1"
    assert records[0].dst_ip == "192.168.1.2"
    assert records[0].bytes == 2500
    assert records[0].protocol == 6
