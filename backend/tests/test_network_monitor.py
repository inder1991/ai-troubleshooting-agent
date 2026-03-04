"""Tests for the NetworkMonitor collection engine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet
from src.network.adapters.registry import AdapterRegistry
from src.network.monitor import NetworkMonitor


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    return NetworkKnowledgeGraph(store)


@pytest.fixture
def adapters():
    return AdapterRegistry()


@pytest.fixture
def monitor(store, kg, adapters):
    return NetworkMonitor(store, kg, adapters)


class TestProbePass:
    @pytest.mark.asyncio
    async def test_probe_sets_device_status_up(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 2.5
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._probe_pass()

        status = store.get_device_status("r1")
        assert status is not None
        assert status["status"] == "up"

    @pytest.mark.asyncio
    async def test_probe_sets_device_status_down(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = False
            mock_result.avg_rtt = 0
            mock_result.packet_loss = 1.0
            mock_ping.return_value = mock_result
            await monitor._probe_pass()

        status = store.get_device_status("r1")
        assert status["status"] == "down"

    @pytest.mark.asyncio
    async def test_probe_sets_degraded_on_high_latency(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 150.0  # > 100ms threshold
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._probe_pass()

        status = store.get_device_status("r1")
        assert status["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_skips_devices_without_ip(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip=""))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            await monitor._probe_pass()
            mock_ping.assert_not_called()


class TestCollectCycle:
    @pytest.mark.asyncio
    async def test_full_cycle_runs_without_error(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 2.0
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._collect_cycle()

        assert store.get_device_status("r1") is not None

    @pytest.mark.asyncio
    async def test_cycle_records_metric_history(self, store, kg, monitor):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock) as mock_ping:
            mock_result = MagicMock()
            mock_result.is_alive = True
            mock_result.avg_rtt = 2.0
            mock_result.packet_loss = 0.0
            mock_ping.return_value = mock_result
            await monitor._collect_cycle()

        history = store.query_metric_history("device", "r1", "latency_ms", since="2000-01-01")
        assert len(history) >= 1


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_get_snapshot_returns_all_data(self, store, monitor):
        store.upsert_device_status("d1", "up", 2.0, 0.0, "icmp")
        store.upsert_link_metric("d1", "d2", 5.0, 1000000, 0.0, 0.5)
        store.upsert_drift_event("route", "rt1", "missing", "cidr", "10.0.0.0/8", "", "warning")
        store.upsert_discovery_candidate("10.0.0.99", "", "", "probe", "")

        snapshot = monitor.get_snapshot()
        assert len(snapshot["devices"]) == 1
        assert len(snapshot["links"]) == 1
        assert len(snapshot["drifts"]) == 1
        assert len(snapshot["candidates"]) == 1
