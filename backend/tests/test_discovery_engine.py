"""Tests for auto-discovery engine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import Device, DeviceType, Subnet
from src.network.discovery_engine import DiscoveryEngine


@pytest.fixture
def store(tmp_path):
    return TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))


@pytest.fixture
def kg(store):
    kg = NetworkKnowledgeGraph(store)
    return kg


@pytest.fixture
def engine(store, kg):
    return DiscoveryEngine(store, kg)


class TestAdapterDiscovery:
    @pytest.mark.asyncio
    async def test_discovers_unknown_ip_from_adapter(self, store, kg, engine):
        # Known device in KG
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        # Adapter reports an interface with unknown IP
        adapter = AsyncMock()
        iface = MagicMock()
        iface.ip = "10.0.0.99"
        iface.name = "unknown-peer"
        adapter.get_interfaces.return_value = [iface]

        from src.network.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        registry.register("r1", adapter)

        candidates = await engine.discover_from_adapters(registry)
        assert any(c["ip"] == "10.0.0.99" for c in candidates)

    @pytest.mark.asyncio
    async def test_skips_known_ips(self, store, kg, engine):
        store.add_device(Device(id="r1", name="R1", device_type=DeviceType.ROUTER, management_ip="10.0.0.1"))
        kg.load_from_store()

        adapter = AsyncMock()
        iface = MagicMock()
        iface.ip = "10.0.0.1"  # already known
        iface.name = "known"
        adapter.get_interfaces.return_value = [iface]

        from src.network.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        registry.register("r1", adapter)

        candidates = await engine.discover_from_adapters(registry)
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_adapter_failure_skipped(self, store, kg, engine):
        kg.load_from_store()
        adapter = AsyncMock()
        adapter.get_interfaces.side_effect = Exception("timeout")

        from src.network.adapters.registry import AdapterRegistry
        registry = AdapterRegistry()
        registry.register("r1", adapter)

        candidates = await engine.discover_from_adapters(registry)
        assert candidates == []


class TestSubnetProbe:
    @pytest.mark.asyncio
    async def test_skips_large_subnets(self, store, kg, engine):
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/16"))  # /16 = 65K hosts, too large
        kg.load_from_store()
        # Should not attempt to scan
        with patch.object(engine, "_ping_check", new_callable=AsyncMock) as mock_ping:
            await engine.probe_known_subnets()
            mock_ping.assert_not_called()

    @pytest.mark.asyncio
    async def test_scans_small_subnets(self, store, kg, engine):
        store.add_subnet(Subnet(id="s1", cidr="10.0.0.0/30"))  # /30 = 2 hosts
        kg.load_from_store()
        with patch.object(engine, "_ping_check", new_callable=AsyncMock,
                          return_value=("10.0.0.1", True)) as mock_ping:
            candidates = await engine.probe_known_subnets()
            assert mock_ping.call_count > 0


class TestReverseDNS:
    @pytest.mark.asyncio
    async def test_reverse_dns_returns_hostname(self, engine):
        with patch("socket.gethostbyaddr", return_value=("printer.local", [], ["10.0.0.5"])):
            result = await engine.reverse_dns("10.0.0.5")
            assert result == "printer.local"

    @pytest.mark.asyncio
    async def test_reverse_dns_returns_empty_on_failure(self, engine):
        import socket
        with patch("socket.gethostbyaddr", side_effect=socket.herror):
            result = await engine.reverse_dns("10.0.0.5")
            assert result == ""
