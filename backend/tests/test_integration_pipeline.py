"""Integration tests for the NDM data pipeline.

Each test uses real SQLite (via tmp_path) but mocks external services
like InfluxDB. This validates end-to-end data flow through the system.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig
from src.network.event_bus.memory_bus import MemoryEventBus
from src.network.event_bus.base import TRAPS
from src.network.collectors.event_store import EventStore
from src.network.alert_engine import AlertEngine, AlertRule


# ── Test 1: SNMP collect writes metrics ──


class TestSNMPCollectWritesMetrics:
    """Create SNMPCollector with mocked _snmp_get, call poll_device,
    verify metrics_store.write_device_metric was called with correct values.
    """

    @pytest.mark.asyncio
    async def test_snmp_collect_writes_metrics(self):
        mock_metrics = AsyncMock()
        mock_metrics.write_device_metric = AsyncMock()

        collector = SNMPCollector(mock_metrics)
        cfg = SNMPDeviceConfig(device_id="dev-int-1", ip="10.0.0.1")

        with patch.object(collector, "_snmp_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "cpu_pct": 72.5,
                "mem_total": 16_000_000,
                "mem_avail": 4_000_000,
                "interfaces": {
                    1: {
                        "ifDescr": "Gi0/0",
                        "ifSpeed": 1_000_000_000,
                        "ifInOctets": 1000,
                        "ifOutOctets": 2000,
                        "ifInErrors": 0,
                        "ifOutErrors": 0,
                    }
                },
            }

            result = await collector.poll_device(cfg)

        # Verify correct return shape
        assert result["device_id"] == "dev-int-1"
        assert result["cpu_pct"] == 72.5

        # Verify CPU metric was written with exact value
        mock_metrics.write_device_metric.assert_any_call("dev-int-1", "cpu_pct", 72.5)

        # Verify memory metric was computed correctly: (16M - 4M) / 16M * 100 = 75%
        mock_metrics.write_device_metric.assert_any_call("dev-int-1", "mem_pct", 75.0)

        # At minimum cpu + mem should be written
        assert mock_metrics.write_device_metric.call_count >= 2

    @pytest.mark.asyncio
    async def test_snmp_collect_no_interfaces(self):
        """Poll device with no interfaces still writes CPU and memory."""
        mock_metrics = AsyncMock()
        mock_metrics.write_device_metric = AsyncMock()

        collector = SNMPCollector(mock_metrics)
        cfg = SNMPDeviceConfig(device_id="dev-no-iface", ip="10.0.0.2")

        with patch.object(collector, "_snmp_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "cpu_pct": 10.0,
                "mem_total": 8_000_000,
                "mem_avail": 7_000_000,
                "interfaces": {},
            }
            result = await collector.poll_device(cfg)

        assert result["cpu_pct"] == 10.0
        # Only cpu + mem written (no interface rates on first poll)
        assert mock_metrics.write_device_metric.call_count == 2


# ── Test 2: Flow ingest to aggregation ──


class TestFlowIngestToAggregation:
    """Create FlowAggregator, ingest 100 flows, flush, verify
    top_talkers and conversations have expected entries.
    """

    @pytest.mark.asyncio
    async def test_flow_ingest_to_aggregation(self, tmp_path):
        from src.network.flow_receiver import FlowAggregator
        from src.network.metrics_store import FlowRecord

        mock_metrics = AsyncMock()
        mock_metrics.write_flow = AsyncMock()
        mock_metrics.write_link_metric = AsyncMock()

        # Use a mock topology store
        mock_topo = MagicMock()
        mock_topo.upsert_link_metric = MagicMock()

        aggregator = FlowAggregator(mock_metrics, mock_topo)

        # Ingest 100 flows: 50 from 10.0.0.1 -> 10.0.0.2 and 50 from 10.0.0.3 -> 10.0.0.4
        now = datetime.now(timezone.utc)
        for i in range(50):
            aggregator.ingest(FlowRecord(
                src_ip="10.0.0.1", dst_ip="10.0.0.2",
                src_port=40000 + i, dst_port=443,
                protocol=6, bytes=1000, packets=10,
                start_time=now, end_time=now,
                exporter_ip="10.0.0.1",
            ))
        for i in range(50):
            aggregator.ingest(FlowRecord(
                src_ip="10.0.0.3", dst_ip="10.0.0.4",
                src_port=50000 + i, dst_port=80,
                protocol=6, bytes=2000, packets=20,
                start_time=now, end_time=now,
                exporter_ip="10.0.0.3",
            ))

        # Flush and verify
        count = await aggregator.flush()
        assert count == 100

        # Verify write_flow was called 100 times
        assert mock_metrics.write_flow.call_count == 100

        # Verify conversations
        conversations = aggregator.get_conversations()
        assert len(conversations) >= 2

        # Find the (10.0.0.3 -> 10.0.0.4) conversation — should have more bytes
        conv_34 = [c for c in conversations if c["src_ip"] == "10.0.0.3" and c["dst_ip"] == "10.0.0.4"]
        assert len(conv_34) == 1
        assert conv_34[0]["bytes"] == 100_000  # 50 * 2000

        # Verify applications (port 443 = HTTPS, port 80 = HTTP)
        apps = aggregator.get_applications()
        app_names = [a["application"] for a in apps]
        assert "HTTPS" in app_names
        assert "HTTP" in app_names

    @pytest.mark.asyncio
    async def test_flow_empty_flush(self, tmp_path):
        """Flushing with no flows returns 0."""
        from src.network.flow_receiver import FlowAggregator

        mock_metrics = AsyncMock()
        mock_topo = MagicMock()
        aggregator = FlowAggregator(mock_metrics, mock_topo)

        count = await aggregator.flush()
        assert count == 0


# ── Test 3: Event bus to event store ──


class TestEventBusToEventStore:
    """Create MemoryEventBus + EventStore, publish trap event,
    subscribe handler that inserts into store, verify event is queryable.
    """

    @pytest.mark.asyncio
    async def test_event_bus_to_event_store(self, tmp_path):
        db_path = os.path.join(str(tmp_path), "events.db")
        event_store = EventStore(db_path=db_path)
        bus = MemoryEventBus(maxsize=100)

        # Handler that writes events into the EventStore
        async def trap_handler(channel: str, event: dict) -> None:
            event_store.insert_trap(event)

        await bus.start()
        await bus.subscribe(TRAPS, trap_handler)

        # Publish a trap event
        trap_event = {
            "event_id": "trap-001",
            "device_ip": "10.0.0.1",
            "device_id": "dev-1",
            "oid": "1.3.6.1.2.1.1.3.0",
            "value": "uptime changed",
            "severity": "warning",
            "timestamp": time.time(),
        }
        await bus.publish(TRAPS, trap_event)

        # Give consumer time to process
        await asyncio.sleep(0.2)

        # Query the event store
        traps = event_store.query_traps(device_id="dev-1")
        assert len(traps) == 1
        assert traps[0]["event_id"] == "trap-001"
        assert traps[0]["oid"] == "1.3.6.1.2.1.1.3.0"
        assert traps[0]["severity"] == "warning"

        await bus.stop()

    @pytest.mark.asyncio
    async def test_event_bus_multiple_traps(self, tmp_path):
        """Multiple trap events should all be stored."""
        db_path = os.path.join(str(tmp_path), "events2.db")
        event_store = EventStore(db_path=db_path)
        bus = MemoryEventBus(maxsize=100)

        async def trap_handler(channel: str, event: dict) -> None:
            event_store.insert_trap(event)

        await bus.start()
        await bus.subscribe(TRAPS, trap_handler)

        for i in range(5):
            await bus.publish(TRAPS, {
                "event_id": f"trap-{i:03d}",
                "device_ip": "10.0.0.1",
                "device_id": "dev-1",
                "oid": f"1.3.6.1.{i}",
                "severity": "info",
                "timestamp": time.time(),
            })

        await asyncio.sleep(0.3)

        traps = event_store.query_traps(device_id="dev-1")
        assert len(traps) == 5

        await bus.stop()


# ── Test 4: Topology store concurrent writes ──


class TestTopologyStoreConcurrentWrites:
    """Use threading to write 50 devices concurrently to TopologyStore,
    verify all devices are present.
    """

    def test_topology_store_concurrent_writes(self, tmp_path):
        from src.network.topology_store import TopologyStore
        from src.network.models import Device, DeviceType

        db_path = os.path.join(str(tmp_path), "topo.db")
        store = TopologyStore(db_path=db_path)

        errors: list[Exception] = []

        def write_device(i: int) -> None:
            try:
                device = Device(
                    id=f"dev-{i:03d}",
                    name=f"switch-{i}",
                    vendor="Cisco",
                    device_type=DeviceType.SWITCH,
                    management_ip=f"10.0.{i // 256}.{i % 256}",
                )
                store.add_device(device)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_device, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"

        # Verify all 50 devices are present
        devices = store.list_devices()
        assert len(devices) == 50

        # Verify we can look up each device by ID
        for i in range(50):
            dev = store.get_device(f"dev-{i:03d}")
            assert dev is not None
            assert dev.name == f"switch-{i}"

    def test_topology_store_concurrent_different_types(self, tmp_path):
        """Concurrent writes of different device types should all succeed."""
        from src.network.topology_store import TopologyStore
        from src.network.models import Device, DeviceType

        db_path = os.path.join(str(tmp_path), "topo2.db")
        store = TopologyStore(db_path=db_path)

        device_types = [DeviceType.ROUTER, DeviceType.SWITCH, DeviceType.FIREWALL, DeviceType.HOST]
        errors: list[Exception] = []

        def write_device(i: int) -> None:
            try:
                device = Device(
                    id=f"dev-type-{i:03d}",
                    name=f"device-{i}",
                    vendor="Test",
                    device_type=device_types[i % len(device_types)],
                    management_ip=f"192.168.{i // 256}.{i % 256}",
                )
                store.add_device(device)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_device, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert len(store.list_devices()) == 20


# ── Test 5: Alert engine fires on threshold ──


class TestAlertEngineFiresOnThreshold:
    """Create AlertEngine with a CPU>80 rule, evaluate with cpu=90,
    verify alert is created.
    """

    @pytest.mark.asyncio
    async def test_alert_engine_fires_on_threshold(self):
        mock_metrics = AsyncMock()

        # Return cpu=90 when queried
        mock_metrics.query_device_metrics = AsyncMock(return_value=[
            {"time": "2026-03-10T00:00:00Z", "value": 90.0}
        ])

        engine = AlertEngine(mock_metrics)
        engine.add_rule(AlertRule(
            id="test-cpu-high",
            name="High CPU Test",
            severity="critical",
            entity_type="device",
            entity_filter="*",
            metric="cpu_pct",
            condition="gt",
            threshold=80.0,
            duration_seconds=30,
            cooldown_seconds=600,
        ))

        fired = await engine.evaluate("dev-test-1")

        assert len(fired) == 1
        alert = fired[0]
        assert alert["rule_id"] == "test-cpu-high"
        assert alert["entity_id"] == "dev-test-1"
        assert alert["severity"] == "critical"
        assert alert["value"] == 90.0
        assert alert["threshold"] == 80.0
        assert alert["condition"] == "gt"

        # Verify alert is now in active alerts
        active = engine.get_active_alerts()
        assert len(active) == 1
        assert active[0]["key"] == "test-cpu-high:dev-test-1"

    @pytest.mark.asyncio
    async def test_alert_engine_does_not_fire_below_threshold(self):
        """Alert should NOT fire when value is below threshold."""
        mock_metrics = AsyncMock()
        mock_metrics.query_device_metrics = AsyncMock(return_value=[
            {"time": "2026-03-10T00:00:00Z", "value": 50.0}
        ])

        engine = AlertEngine(mock_metrics)
        engine.add_rule(AlertRule(
            id="test-cpu-low",
            name="CPU Below Threshold",
            severity="warning",
            entity_type="device",
            entity_filter="*",
            metric="cpu_pct",
            condition="gt",
            threshold=80.0,
        ))

        fired = await engine.evaluate("dev-test-2")
        assert len(fired) == 0
        assert len(engine.get_active_alerts()) == 0

    @pytest.mark.asyncio
    async def test_alert_engine_fires_lt_condition(self):
        """Alert should fire for lt (less-than) condition."""
        mock_metrics = AsyncMock()
        mock_metrics.query_device_metrics = AsyncMock(return_value=[
            {"time": "2026-03-10T00:00:00Z", "value": 0.5}
        ])

        engine = AlertEngine(mock_metrics)
        engine.add_rule(AlertRule(
            id="test-dns-fail",
            name="DNS Failure",
            severity="critical",
            entity_type="device",
            entity_filter="*",
            metric="dns_success",
            condition="lt",
            threshold=1.0,
        ))

        fired = await engine.evaluate("dev-dns-1")
        assert len(fired) == 1
        assert fired[0]["rule_id"] == "test-dns-fail"

    @pytest.mark.asyncio
    async def test_alert_engine_with_store(self, tmp_path):
        """Alert should be persisted to TopologyStore alert history."""
        from src.network.topology_store import TopologyStore

        db_path = os.path.join(str(tmp_path), "alert.db")
        topo_store = TopologyStore(db_path=db_path)

        mock_metrics = AsyncMock()
        mock_metrics.query_device_metrics = AsyncMock(return_value=[
            {"time": "2026-03-10T00:00:00Z", "value": 95.0}
        ])

        engine = AlertEngine(mock_metrics)
        engine.set_store(topo_store)
        engine.add_rule(AlertRule(
            id="store-cpu",
            name="CPU with Store",
            severity="warning",
            entity_type="device",
            entity_filter="*",
            metric="cpu_pct",
            condition="gt",
            threshold=80.0,
        ))

        fired = await engine.evaluate("dev-store-1")
        assert len(fired) == 1

        # Verify alert is persisted in SQLite
        history = topo_store.list_alert_history(entity_id="dev-store-1")
        assert len(history) == 1
        assert history[0]["rule_id"] == "store-cpu"
        assert history[0]["state"] == "firing"
