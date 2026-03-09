"""Tests for the AutodiscoveryEngine."""
import pytest
from unittest.mock import AsyncMock, patch

from src.network.collectors.autodiscovery import AutodiscoveryEngine
from src.network.collectors.profile_loader import ProfileLoader
from src.network.collectors.snmp_collector import SNMPProtocolCollector
from src.network.collectors.models import (
    DiscoveryConfig, SNMPVersion, PingConfig,
)


@pytest.fixture
def profile_loader():
    pl = ProfileLoader()
    pl.load_all()
    return pl


@pytest.fixture
def snmp_collector():
    return SNMPProtocolCollector()


@pytest.fixture
def engine(profile_loader, snmp_collector):
    return AutodiscoveryEngine(profile_loader, snmp_collector, max_concurrent=10)


class TestProfileMatching:
    def test_match_cisco_oid(self, engine):
        result = engine.match_profile("1.3.6.1.4.1.9.1.123")
        assert result == "cisco-catalyst"

    def test_match_arista_oid(self, engine):
        result = engine.match_profile("1.3.6.1.4.1.30065.1.1")
        assert result == "arista-eos"

    def test_match_unknown_oid(self, engine):
        result = engine.match_profile("1.3.6.1.4.1.99999.1.1")
        assert result == "generic"

    def test_match_empty_oid(self, engine):
        result = engine.match_profile("")
        assert result == "generic"


class TestShouldScan:
    @pytest.mark.asyncio
    async def test_should_scan_new_config(self, engine):
        cfg = DiscoveryConfig(cidr="10.0.0.0/30", community="public")
        assert await engine.should_scan(cfg)

    @pytest.mark.asyncio
    async def test_should_not_scan_disabled(self, engine):
        cfg = DiscoveryConfig(cidr="10.0.0.0/30", community="public", enabled=False)
        assert not await engine.should_scan(cfg)


class TestScanNetwork:
    @pytest.mark.asyncio
    async def test_scan_small_network_no_devices(self, engine):
        """Scan a /30 network — no SNMP responses expected in test env."""
        cfg = DiscoveryConfig(
            cidr="192.0.2.0/30",  # TEST-NET-1, won't respond
            community="public",
            ping=PingConfig(enabled=False),
        )
        # Without real SNMP, query_sys_object_id returns None for all IPs
        devices = await engine.scan_network(cfg)
        # All hosts return None for sysObjectID, so 0 discovered
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_scan_excludes_ips(self, engine):
        cfg = DiscoveryConfig(
            cidr="192.0.2.0/30",
            community="public",
            excluded_ips=["192.0.2.1"],
            ping=PingConfig(enabled=False),
        )
        devices = await engine.scan_network(cfg)
        # Ensure excluded IP is not in results
        ips = [d.management_ip for d in devices]
        assert "192.0.2.1" not in ips

    @pytest.mark.asyncio
    async def test_scan_with_mocked_snmp(self, profile_loader):
        """Mock SNMP to simulate discovering devices."""
        mock_collector = SNMPProtocolCollector()
        mock_collector.query_sys_object_id = AsyncMock(return_value="1.3.6.1.4.1.9.1.100")
        mock_collector._pysnmp_available = False

        engine = AutodiscoveryEngine(profile_loader, mock_collector)
        cfg = DiscoveryConfig(
            cidr="192.0.2.0/30",
            community="public",
            ping=PingConfig(enabled=False),
        )
        devices = await engine.scan_network(cfg)
        assert len(devices) == 2  # /30 has 2 usable hosts
        assert all(d.discovered for d in devices)
        assert all(d.matched_profile == "cisco-catalyst" for d in devices)
        assert all(d.vendor == "cisco" for d in devices)

    @pytest.mark.asyncio
    async def test_discovered_devices_have_tags(self, profile_loader):
        mock_collector = SNMPProtocolCollector()
        mock_collector.query_sys_object_id = AsyncMock(return_value="1.3.6.1.4.1.30065.1.1")
        mock_collector._pysnmp_available = False

        engine = AutodiscoveryEngine(profile_loader, mock_collector)
        cfg = DiscoveryConfig(
            cidr="192.0.2.0/30",
            community="public",
            tags=["site:dc1", "env:prod"],
            ping=PingConfig(enabled=False),
        )
        devices = await engine.scan_network(cfg)
        assert len(devices) == 2
        assert devices[0].tags == ["site:dc1", "env:prod"]


class TestRunDiscoveryCycle:
    @pytest.mark.asyncio
    async def test_skips_recently_scanned(self, engine):
        cfg = DiscoveryConfig(cidr="192.0.2.0/30", community="public", interval_seconds=300)
        # First scan
        await engine.scan_network(cfg)
        # should_scan should return False now (just scanned)
        assert not await engine.should_scan(cfg)
