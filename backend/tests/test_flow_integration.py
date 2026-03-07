"""Tests for flow receiver integration and flow query endpoints."""
import struct
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.network.flow_receiver import FlowReceiver, FlowParser, FlowAggregator
from src.network.metrics_store import FlowRecord


class TestFlowReceiverLifecycle:
    def test_flow_receiver_creates(self):
        metrics = MagicMock()
        topo = MagicMock()
        receiver = FlowReceiver(metrics, topo)
        assert receiver is not None
        assert receiver.parser is not None
        assert receiver.aggregator is not None

    def test_update_device_map(self):
        metrics = MagicMock()
        topo = MagicMock()
        receiver = FlowReceiver(metrics, topo)
        receiver.update_device_map({"10.0.0.1": "router-1"})
        assert receiver.aggregator._device_ip_map == {"10.0.0.1": "router-1"}


class TestFlowAggregator:
    def test_ingest_buffers_records(self):
        agg = FlowAggregator(MagicMock(), MagicMock())
        now = datetime.now(tz=timezone.utc)
        record = FlowRecord(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", src_port=80, dst_port=443,
            protocol=6, bytes=1000, packets=10,
            start_time=now, end_time=now,
            tcp_flags=0, tos=0, input_snmp=0, output_snmp=0,
            src_as=0, dst_as=0, exporter_ip="10.0.0.1",
        )
        agg.ingest(record)
        assert len(agg._buffer) == 1

    @pytest.mark.asyncio
    async def test_flush_writes_to_metrics(self):
        metrics = MagicMock()
        metrics.write_flow = AsyncMock()
        metrics.write_link_metric = AsyncMock()
        topo = MagicMock()
        topo.upsert_link_metric = MagicMock()
        agg = FlowAggregator(metrics, topo)
        now = datetime.now(tz=timezone.utc)
        record = FlowRecord(
            src_ip="10.0.0.1", dst_ip="10.0.0.2", src_port=80, dst_port=443,
            protocol=6, bytes=1000, packets=10,
            start_time=now, end_time=now,
            tcp_flags=0, tos=0, input_snmp=0, output_snmp=0,
            src_as=0, dst_as=0, exporter_ip="10.0.0.1",
        )
        agg.ingest(record)
        count = await agg.flush()
        assert count == 1
        metrics.write_flow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flush_empty_returns_zero(self):
        agg = FlowAggregator(MagicMock(), MagicMock())
        count = await agg.flush()
        assert count == 0


class TestFlowParser:
    def test_detect_unsupported_version(self):
        parser = FlowParser()
        data = struct.pack("!H", 99) + b"\x00" * 20
        records = parser.detect_and_parse(data, "1.2.3.4")
        assert records == []

    def test_detect_too_short(self):
        parser = FlowParser()
        records = parser.detect_and_parse(b"\x00", "1.2.3.4")
        assert records == []


class TestFlowEndpoints:
    def test_top_talkers_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        mock_store = MagicMock()
        mock_store.query_top_talkers = AsyncMock(return_value=[
            {"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "protocol": "6", "bytes": 5000},
        ])
        original = flow_endpoints._metrics_store
        flow_endpoints._metrics_store = mock_store
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/top-talkers")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) >= 1
        finally:
            flow_endpoints._metrics_store = original

    def test_traffic_matrix_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        mock_store = MagicMock()
        mock_store.query_traffic_matrix = AsyncMock(return_value=[
            {"src": "router-1", "dst": "router-2", "bytes": 10000},
        ])
        original = flow_endpoints._metrics_store
        flow_endpoints._metrics_store = mock_store
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/traffic-matrix")
            assert resp.status_code == 200
        finally:
            flow_endpoints._metrics_store = original

    def test_protocol_breakdown_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        mock_store = MagicMock()
        mock_store.query_protocol_breakdown = AsyncMock(return_value=[
            {"protocol": "6", "bytes": 50000},
            {"protocol": "17", "bytes": 20000},
        ])
        original = flow_endpoints._metrics_store
        flow_endpoints._metrics_store = mock_store
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/protocol-breakdown")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
        finally:
            flow_endpoints._metrics_store = original

    def test_flow_status_endpoint(self):
        from src.api.main import app
        from src.api import flow_endpoints
        original = flow_endpoints._flow_receiver
        flow_endpoints._flow_receiver = None
        try:
            client = TestClient(app)
            resp = client.get("/api/v4/network/flows/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False
        finally:
            flow_endpoints._flow_receiver = original
