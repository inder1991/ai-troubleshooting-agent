# backend/tests/test_snmp_collector.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig


@pytest.fixture
def mock_metrics():
    return AsyncMock()


def test_snmp_config_defaults():
    cfg = SNMPDeviceConfig(device_id="dev-1", ip="10.0.0.1")
    assert cfg.version == "v2c"
    assert cfg.community == "public"
    assert cfg.port == 161


@pytest.mark.asyncio
async def test_compute_rates_first_poll(mock_metrics):
    """First poll has no previous counters — should return None rates."""
    collector = SNMPCollector(mock_metrics)
    rates = collector._compute_rates("dev-1", 1, {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000})
    assert rates is None  # No previous sample


@pytest.mark.asyncio
async def test_compute_rates_second_poll(mock_metrics):
    """Second poll computes delta rates correctly."""
    collector = SNMPCollector(mock_metrics)
    # First poll — stores baseline
    collector._compute_rates("dev-1", 1, {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000})
    # Simulate 30s later, 10000 bytes increase
    import time
    collector._prev_counters[("dev-1", 1)] = (
        {"ifInOctets": 1000, "ifOutOctets": 2000, "ifSpeed": 1_000_000_000},
        time.time() - 30,
    )
    rates = collector._compute_rates("dev-1", 1, {"ifInOctets": 11000, "ifOutOctets": 12000, "ifSpeed": 1_000_000_000})
    assert rates is not None
    # delta_in = 10000 bytes * 8 / 30s ≈ 2666 bps
    assert 2600 < rates["bps_in"] < 2700
    assert 2600 < rates["bps_out"] < 2700
    assert rates["utilization"] < 0.01  # Tiny fraction of 1Gbps


@pytest.mark.asyncio
async def test_poll_device_writes_metrics(mock_metrics):
    """Successful SNMP poll should write metrics to store."""
    collector = SNMPCollector(mock_metrics)
    cfg = SNMPDeviceConfig(device_id="dev-1", ip="10.0.0.1")
    with patch.object(collector, "_snmp_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "cpu_pct": 45.0,
            "mem_total": 8000000,
            "mem_avail": 4000000,
            "interfaces": {},
        }
        result = await collector.poll_device(cfg)
        assert result["device_id"] == "dev-1"
        assert result["cpu_pct"] == 45.0
        assert mock_metrics.write_device_metric.call_count >= 2  # cpu + mem at minimum
