# backend/tests/test_snmp_collector.py
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig


@pytest.fixture
def mock_metrics():
    """Create a mock metrics store with spec for MetricsStore-like interface."""
    m = AsyncMock()
    m.write_device_metric = AsyncMock()
    return m


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
        # Verify the correct metric names and values were written
        mock_metrics.write_device_metric.assert_any_call("dev-1", "cpu_pct", 45.0)
        mock_metrics.write_device_metric.assert_any_call("dev-1", "mem_pct", 50.0)


def test_64bit_counter_oids_exist():
    from src.network.snmp_collector import STANDARD_OIDS
    assert "ifHCInOctets" in STANDARD_OIDS
    assert "ifHCOutOctets" in STANDARD_OIDS


def test_compute_rates_64bit_no_wrap():
    from src.network.snmp_collector import SNMPCollector
    collector = SNMPCollector(metrics_store=None)
    device_id = "dev-hc"
    if_index = 1
    counters_1 = {
        "ifHCInOctets": 10_000_000_000,
        "ifHCOutOctets": 5_000_000_000,
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,
    }
    result1 = collector._compute_rates(device_id, if_index, counters_1)
    assert result1 is None

    collector._prev_counters[(device_id, if_index)] = (counters_1, time.time() - 30)
    counters_2 = {
        "ifHCInOctets": 10_375_000_000,
        "ifHCOutOctets": 5_187_500_000,
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,
    }
    result2 = collector._compute_rates(device_id, if_index, counters_2)
    assert result2 is not None
    assert abs(result2["bps_in"] - 100_000_000) < 1_000_000
    assert result2["utilization"] < 0.02


def test_compute_rates_prefers_hc_counters():
    from src.network.snmp_collector import SNMPCollector
    collector = SNMPCollector(metrics_store=None)
    device_id = "dev-hc-pref"
    if_index = 1
    counters_1 = {
        "ifInOctets": 1_000_000,
        "ifOutOctets": 500_000,
        "ifHCInOctets": 50_000_000_000,
        "ifHCOutOctets": 25_000_000_000,
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,
    }
    collector._prev_counters[(device_id, if_index)] = (counters_1, time.time() - 30)
    counters_2 = {
        "ifInOctets": 2_000_000,
        "ifOutOctets": 1_000_000,
        "ifHCInOctets": 50_100_000_000,
        "ifHCOutOctets": 25_050_000_000,
        "ifInErrors": 0,
        "ifOutErrors": 0,
        "ifSpeed": 10_000_000_000,
    }
    result = collector._compute_rates(device_id, if_index, counters_2)
    assert result is not None
    assert result["bps_in"] > 20_000_000


@pytest.mark.asyncio
async def test_snmp_get_populates_interfaces(monkeypatch):
    import src.network.snmp_collector as snmp_mod
    from src.network.snmp_collector import SNMPCollector, SNMPDeviceConfig

    async def mock_walk(cfg):
        return {
            1: {"ifDescr": "GigabitEthernet0/0", "ifOperStatus": 1, "ifSpeed": 1_000_000_000,
                "ifInOctets": 1000, "ifOutOctets": 2000, "ifHCInOctets": 100000,
                "ifHCOutOctets": 200000, "ifInErrors": 0, "ifOutErrors": 0},
            2: {"ifDescr": "GigabitEthernet0/1", "ifOperStatus": 1, "ifSpeed": 10_000_000_000,
                "ifInOctets": 5000, "ifOutOctets": 6000, "ifHCInOctets": 500000,
                "ifHCOutOctets": 600000, "ifInErrors": 1, "ifOutErrors": 0},
        }

    collector = SNMPCollector(metrics_store=None)
    monkeypatch.setattr(collector, "_walk_interfaces", mock_walk)

    # Mock the pysnmp imports and get_cmd so _snmp_get doesn't fail
    mock_val = MagicMock()
    mock_val.__float__ = MagicMock(return_value=42.0)
    mock_var_bind = [(MagicMock(), mock_val)]

    async def mock_get_cmd(*args, **kwargs):
        return (None, None, None, mock_var_bind)

    mock_engine = MagicMock()
    mock_engine.close_dispatcher = MagicMock()
    mock_target = MagicMock()

    async def mock_create(*args, **kwargs):
        return mock_target

    mock_target.create = mock_create

    # Seed module-level names (may not exist when pysnmp is not installed)
    for attr, val in [
        ("_PYSNMP_AVAILABLE", True),
        ("SnmpEngine", MagicMock(return_value=mock_engine)),
        ("get_cmd", mock_get_cmd),
        ("CommunityData", MagicMock()),
        ("UdpTransportTarget", mock_target),
        ("ContextData", MagicMock()),
        ("ObjectType", MagicMock()),
        ("ObjectIdentity", MagicMock()),
    ]:
        if not hasattr(snmp_mod, attr):
            setattr(snmp_mod, attr, None)
        monkeypatch.setattr(snmp_mod, attr, val)

    cfg = SNMPDeviceConfig(device_id="dev-walk", ip="10.0.0.1")
    result = await collector._snmp_get(cfg)
    assert len(result["interfaces"]) == 2
    assert result["interfaces"][1]["ifDescr"] == "GigabitEthernet0/0"


# ── Negative tests ──


def test_compute_rates_empty_counters():
    """Empty counter dict should store baseline and return None."""
    collector = SNMPCollector(metrics_store=None)
    result = collector._compute_rates("dev-empty", 1, {})
    assert result is None


@pytest.mark.asyncio
async def test_poll_device_empty_snmp_response():
    """poll_device with empty SNMP response should handle gracefully."""
    mock_m = AsyncMock()
    mock_m.write_device_metric = AsyncMock()
    collector = SNMPCollector(mock_m)
    cfg = SNMPDeviceConfig(device_id="dev-empty", ip="10.0.0.1")
    with patch.object(collector, "_snmp_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        result = await collector.poll_device(cfg)
        assert result["device_id"] == "dev-empty"
        assert result["cpu_pct"] == 0


@pytest.mark.asyncio
async def test_poll_device_none_metrics_store():
    """poll_device with None metrics_store should raise AttributeError."""
    collector = SNMPCollector(metrics_store=None)
    cfg = SNMPDeviceConfig(device_id="dev-none", ip="10.0.0.1")
    with patch.object(collector, "_snmp_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"cpu_pct": 10, "mem_total": 100, "mem_avail": 50, "interfaces": {}}
        with pytest.raises(AttributeError):
            await collector.poll_device(cfg)
