"""Tests for biflow stitching in FlowAggregator."""
import pytest
import time
from datetime import datetime, timezone

from src.network.flow_receiver import FlowAggregator
from src.network.metrics_store import FlowRecord


def _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2", src_port=12345, dst_port=443,
               protocol=6, bytes_=1000, packets=10, src_as=0, dst_as=0,
               sampling_interval=1) -> FlowRecord:
    now = datetime.now(timezone.utc)
    return FlowRecord(
        src_ip=src_ip, dst_ip=dst_ip, src_port=src_port, dst_port=dst_port,
        protocol=protocol, bytes=bytes_, packets=packets,
        start_time=now, end_time=now,
        src_as=src_as, dst_as=dst_as, exporter_ip="192.168.1.1",
        sampling_interval=sampling_interval,
    )


class TestBiflowStitching:
    def test_stitch_creates_biflow(self):
        """Two flows with reversed src/dst should stitch into a single biflow."""
        agg = FlowAggregator(buffer_size=1000)
        forward = _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2",
                             src_port=12345, dst_port=443, bytes_=1000, packets=10)
        reverse = _make_flow(src_ip="10.0.0.2", dst_ip="10.0.0.1",
                             src_port=443, dst_port=12345, bytes_=2000, packets=15)

        agg.stitch_biflow(forward)
        agg.stitch_biflow(reverse)

        biflows = agg.get_biflows()
        assert len(biflows) == 1
        bf = biflows[0]
        assert bf["forward_bytes"] == 1000
        assert bf["reverse_bytes"] == 2000
        assert bf["forward_packets"] == 10
        assert bf["reverse_packets"] == 15
        assert bf["protocol"] == 6

    def test_stitch_unmatched_stays_single(self):
        """A flow with no matching reverse should appear as a unidirectional biflow."""
        agg = FlowAggregator(buffer_size=1000)
        forward = _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2",
                             src_port=12345, dst_port=443, bytes_=1000)
        agg.stitch_biflow(forward)

        biflows = agg.get_biflows()
        assert len(biflows) == 1
        assert biflows[0]["forward_bytes"] == 1000
        assert biflows[0]["reverse_bytes"] == 0

    def test_stitch_different_5tuples_separate(self):
        """Flows with different 5-tuples should not be stitched together."""
        agg = FlowAggregator(buffer_size=1000)
        f1 = _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2",
                        src_port=12345, dst_port=443, bytes_=1000)
        f2 = _make_flow(src_ip="10.0.0.3", dst_ip="10.0.0.4",
                        src_port=54321, dst_port=80, bytes_=2000)

        agg.stitch_biflow(f1)
        agg.stitch_biflow(f2)

        biflows = agg.get_biflows()
        assert len(biflows) == 2

    def test_stitch_timeout_evicts(self):
        """Biflows older than timeout should be evicted."""
        agg = FlowAggregator(buffer_size=1000, biflow_timeout=0.1)
        f = _make_flow(bytes_=1000)
        agg.stitch_biflow(f)
        assert len(agg.get_biflows()) == 1

        time.sleep(0.15)
        agg.evict_expired_biflows()
        assert len(agg.get_biflows()) == 0

    def test_stitch_canonical_key_order(self):
        """The canonical key should be the same regardless of direction."""
        agg = FlowAggregator(buffer_size=1000)
        # Same 5-tuple, just reversed
        f1 = _make_flow(src_ip="10.0.0.1", dst_ip="10.0.0.2",
                        src_port=12345, dst_port=443)
        f2 = _make_flow(src_ip="10.0.0.2", dst_ip="10.0.0.1",
                        src_port=443, dst_port=12345)

        key1 = agg._biflow_key(f1)
        key2 = agg._biflow_key(f2)
        assert key1 == key2

    def test_stitch_max_biflows_bounded(self):
        """Biflow table should not exceed MAX_BIFLOWS."""
        agg = FlowAggregator(buffer_size=1000)
        agg.MAX_BIFLOWS = 10
        for i in range(20):
            f = _make_flow(src_ip=f"10.0.{i // 256}.{i % 256}",
                           dst_ip="10.1.0.1", src_port=i + 1024, dst_port=443)
            agg.stitch_biflow(f)
        assert len(agg._biflows) <= 10
