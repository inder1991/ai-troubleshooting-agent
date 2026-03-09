"""Tests for SNMP Protocol Collector (simulated mode)."""
import pytest

from src.network.collectors.snmp_collector import SNMPProtocolCollector
from src.network.collectors.models import (
    CollectedData, DeviceInstance, DeviceProfile, ProtocolConfig,
    SNMPCredentials, SNMPVersion, MetricDefinition, MetricSymbol,
    MetadataFieldDef, PingConfig,
)


@pytest.fixture
def collector():
    return SNMPProtocolCollector()


def _make_device(ip: str = "10.0.0.1") -> DeviceInstance:
    return DeviceInstance(
        management_ip=ip,
        hostname="test-device",
        protocols=[ProtocolConfig(
            protocol="snmp", priority=5,
            snmp=SNMPCredentials(version=SNMPVersion.V2C, community="public"),
        )],
        ping_config=PingConfig(enabled=False),
    )


def _make_profile() -> DeviceProfile:
    return DeviceProfile(
        name="test-profile",
        vendor="test",
        device_type="switch",
        metrics=[
            MetricDefinition(
                MIB="TEST-MIB",
                symbol=MetricSymbol(OID="1.3.6.1.4.1.9.9.109.1.1.1.1.10", name="cpuUtil"),
            ),
        ],
        metadata_fields={
            "vendor": MetadataFieldDef(value="test"),
        },
    )


class TestSNMPCollectorSimulated:
    """Tests for simulated mode (no pysnmp required)."""

    @pytest.mark.asyncio
    async def test_collect_returns_data(self, collector):
        device = _make_device()
        profile = _make_profile()
        data = await collector.collect(device, profile)
        assert isinstance(data, CollectedData)
        assert data.device_id == device.device_id
        assert data.protocol == "snmp"
        assert data.timestamp > 0

    @pytest.mark.asyncio
    async def test_collect_has_metrics(self, collector):
        device = _make_device()
        profile = _make_profile()
        data = await collector.collect(device, profile)
        assert data.cpu_pct is not None
        assert data.mem_pct is not None
        assert data.uptime_seconds is not None
        assert data.temperature is not None

    @pytest.mark.asyncio
    async def test_collect_has_metadata(self, collector):
        device = _make_device()
        profile = _make_profile()
        data = await collector.collect(device, profile)
        assert "vendor" in data.metadata
        assert data.metadata["vendor"] == "test"

    @pytest.mark.asyncio
    async def test_collect_has_interface_metrics(self, collector):
        device = _make_device()
        profile = _make_profile()
        data = await collector.collect(device, profile)
        assert len(data.interface_metrics) > 0

    @pytest.mark.asyncio
    async def test_collect_batch(self, collector):
        devices = [
            (_make_device("10.0.0.1"), _make_profile()),
            (_make_device("10.0.0.2"), _make_profile()),
        ]
        results = await collector.collect_batch(devices)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_collect_no_creds_raises(self, collector):
        device = DeviceInstance(
            management_ip="10.0.0.1",
            protocols=[],  # No SNMP creds
            ping_config=PingConfig(enabled=False),
        )
        with pytest.raises(ValueError, match="No SNMP credentials"):
            await collector.collect(device, _make_profile())

    @pytest.mark.asyncio
    async def test_health_check_no_creds(self, collector):
        device = DeviceInstance(
            management_ip="10.0.0.1",
            protocols=[],
            ping_config=PingConfig(enabled=False),
        )
        health = await collector.health_check(device)
        assert health.status == "error"
        assert "No SNMP credentials" in health.message


class TestSNMPCollectorCustomMetrics:
    @pytest.mark.asyncio
    async def test_custom_metrics_from_profile(self, collector):
        device = _make_device()
        profile = DeviceProfile(
            name="multi-metric",
            vendor="test",
            device_type="router",
            metrics=[
                MetricDefinition(
                    MIB="TEST-MIB",
                    symbol=MetricSymbol(OID="1.2.3.4", name="metricA"),
                ),
                MetricDefinition(
                    MIB="TEST-MIB",
                    symbol=MetricSymbol(OID="1.2.3.5", name="metricB"),
                ),
            ],
            metadata_fields={},
        )
        data = await collector.collect(device, profile)
        # In simulated mode, custom_metrics should have entries for scalar symbols
        assert "metricA" in data.custom_metrics
        assert "metricB" in data.custom_metrics
