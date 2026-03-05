# Flow-First Network Monitoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add SNMP collection, NetFlow/sFlow ingestion, InfluxDB time-series storage, alerting engine, and enhanced Observatory UI to bring network monitoring from ~15% to ~70% of enterprise capability.

**Architecture:** InfluxDB stores all time-series metrics (device health, flow data, alerts). SNMP collector polls device OIDs every 30s. Flow receiver listens on UDP for NetFlow/IPFIX/sFlow. Alert engine evaluates threshold rules against InfluxDB data. Frontend Observatory gets enhanced tabs with Recharts sparklines and gauges.

**Tech Stack:** Python (pysnmp, influxdb-client[async]), InfluxDB 2.x, React + TypeScript + Recharts (already installed)

**Design Doc:** `docs/plans/2026-03-05-flow-first-monitoring-design.md`

---

## Phase 1: Foundation (Tasks 1-5)

### Task 1: MetricsStore — InfluxDB Client Wrapper

**Files:**
- Create: `backend/src/network/metrics_store.py`
- Test: `backend/tests/test_metrics_store.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_metrics_store.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.network.metrics_store import MetricsStore


@pytest.fixture
def mock_influx():
    with patch("src.network.metrics_store.InfluxDBClientAsync") as MockClient:
        client = MockClient.return_value
        client.write_api.return_value = AsyncMock()
        client.query_api.return_value = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        client.close = AsyncMock()
        yield client, MockClient


@pytest.mark.asyncio
async def test_write_device_metric(mock_influx):
    client, MockClient = mock_influx
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    await store.write_device_metric("dev-1", "cpu_pct", 85.0)
    client.write_api.return_value.write.assert_called_once()


@pytest.mark.asyncio
async def test_write_link_metric(mock_influx):
    client, MockClient = mock_influx
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    await store.write_link_metric("dev-1", "dev-2", bytes=1000, packets=10, latency_ms=5.0)
    client.write_api.return_value.write.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_success(mock_influx):
    client, MockClient = mock_influx
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    assert await store.health_check() is True


@pytest.mark.asyncio
async def test_health_check_failure(mock_influx):
    client, MockClient = mock_influx
    client.ping = AsyncMock(side_effect=Exception("connection refused"))
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    assert await store.health_check() is False


@pytest.mark.asyncio
async def test_graceful_write_failure(mock_influx):
    """Writes should not raise if InfluxDB is down — just log warning."""
    client, MockClient = mock_influx
    client.write_api.return_value.write = AsyncMock(side_effect=Exception("timeout"))
    store = MetricsStore(url="http://localhost:8086", token="test", org="test", bucket="test")
    # Should not raise
    await store.write_device_metric("dev-1", "cpu_pct", 85.0)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_metrics_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.network.metrics_store'`

**Step 3: Write the implementation**

```python
# backend/src/network/metrics_store.py
"""InfluxDB time-series metrics store for network monitoring."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client import Point, WritePrecision

logger = logging.getLogger(__name__)


@dataclass
class FlowRecord:
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: int
    bytes: int
    packets: int
    start_time: datetime
    end_time: datetime
    tcp_flags: int = 0
    tos: int = 0
    input_snmp: int = 0
    output_snmp: int = 0
    src_as: int = 0
    dst_as: int = 0
    exporter_ip: str = ""


class MetricsStore:
    """Async InfluxDB wrapper for network metrics. Fails gracefully on write errors."""

    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        self.org = org
        self.bucket = bucket
        self._client = InfluxDBClientAsync(url=url, token=token, org=org)
        self._write_api = self._client.write_api()
        self._query_api = self._client.query_api()

    async def health_check(self) -> bool:
        try:
            return await self._client.ping()
        except Exception:
            logger.warning("InfluxDB health check failed")
            return False

    async def close(self) -> None:
        await self._client.close()

    # ── Writes ──────────────────────────────────────────────

    async def _safe_write(self, point: Point) -> None:
        try:
            await self._write_api.write(bucket=self.bucket, record=point)
        except Exception as e:
            logger.warning("InfluxDB write failed: %s", e)

    async def write_device_metric(
        self, device_id: str, metric: str, value: float
    ) -> None:
        point = (
            Point("device_health")
            .tag("device_id", device_id)
            .tag("metric_type", metric)
            .field("value", float(value))
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        await self._safe_write(point)

    async def write_link_metric(
        self, src: str, dst: str, **fields: Any
    ) -> None:
        point = (
            Point("link_traffic")
            .tag("src_device", src)
            .tag("dst_device", dst)
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        for k, v in fields.items():
            point = point.field(k, float(v))
        await self._safe_write(point)

    async def write_flow(self, flow: FlowRecord) -> None:
        point = (
            Point("flow_summary")
            .tag("src_ip", flow.src_ip)
            .tag("dst_ip", flow.dst_ip)
            .tag("protocol", str(flow.protocol))
            .tag("exporter", flow.exporter_ip)
            .field("src_port", flow.src_port)
            .field("dst_port", flow.dst_port)
            .field("bytes", flow.bytes)
            .field("packets", flow.packets)
            .field("duration", (flow.end_time - flow.start_time).total_seconds())
            .time(flow.end_time, WritePrecision.S)
        )
        await self._safe_write(point)

    async def write_alert_event(
        self, device_id: str, rule_id: str, severity: str,
        value: float, threshold: float, message: str,
    ) -> None:
        point = (
            Point("alert_events")
            .tag("device_id", device_id)
            .tag("rule_id", rule_id)
            .tag("severity", severity)
            .field("value", value)
            .field("threshold", threshold)
            .field("message", message)
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        await self._safe_write(point)

    # ── Queries ─────────────────────────────────────────────

    async def query_device_metrics(
        self, device_id: str, metric: str,
        range_str: str = "1h", resolution: str = "30s",
    ) -> list[dict]:
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{range_str})
          |> filter(fn: (r) => r._measurement == "device_health")
          |> filter(fn: (r) => r.device_id == "{device_id}")
          |> filter(fn: (r) => r.metric_type == "{metric}")
          |> aggregateWindow(every: {resolution}, fn: mean, createEmpty: false)
          |> yield(name: "mean")
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {"time": r.get_time().isoformat(), "value": r.get_value()}
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []

    async def query_top_talkers(
        self, window: str = "5m", limit: int = 20
    ) -> list[dict]:
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["src_ip", "dst_ip", "protocol"])
          |> sum()
          |> group()
          |> sort(columns: ["_value"], desc: true)
          |> limit(n: {limit})
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {
                    "src_ip": r.values.get("src_ip", ""),
                    "dst_ip": r.values.get("dst_ip", ""),
                    "protocol": r.values.get("protocol", ""),
                    "bytes": r.get_value(),
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []

    async def query_traffic_matrix(self, window: str = "15m") -> list[dict]:
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "link_traffic")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["src_device", "dst_device"])
          |> sum()
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {
                    "src": r.values.get("src_device", ""),
                    "dst": r.values.get("dst_device", ""),
                    "bytes": r.get_value(),
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []

    async def query_protocol_breakdown(self, window: str = "1h") -> list[dict]:
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{window})
          |> filter(fn: (r) => r._measurement == "flow_summary")
          |> filter(fn: (r) => r._field == "bytes")
          |> group(columns: ["protocol"])
          |> sum()
          |> group()
          |> sort(columns: ["_value"], desc: true)
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {"protocol": r.values.get("protocol", ""), "bytes": r.get_value()}
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_metrics_store.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/metrics_store.py backend/tests/test_metrics_store.py
git commit -m "feat(monitoring): add MetricsStore InfluxDB client wrapper"
```

---

### Task 2: SNMP Collector

**Files:**
- Create: `backend/src/network/snmp_collector.py`
- Test: `backend/tests/test_snmp_collector.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_snmp_collector.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# backend/src/network/snmp_collector.py
"""SNMP v2c/v3 collector for network device health metrics."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

STANDARD_OIDS = {
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "hrProcessorLoad": "1.3.6.1.2.1.25.3.3.1.2",
    "memTotalReal": "1.3.6.1.4.1.2021.4.5.0",
    "memAvailReal": "1.3.6.1.4.1.2021.4.6.0",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
    "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
    "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
    "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
    "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
}


@dataclass
class SNMPDeviceConfig:
    device_id: str
    ip: str
    version: str = "v2c"
    community: str = "public"
    port: int = 161
    v3_user: str = ""
    v3_auth_proto: str = ""
    v3_auth_key: str = ""
    v3_priv_proto: str = ""
    v3_priv_key: str = ""


class SNMPCollector:
    """Polls SNMP OIDs and writes metrics to MetricsStore."""

    def __init__(self, metrics_store: Any) -> None:
        self.metrics = metrics_store
        self._prev_counters: dict[tuple[str, int], tuple[dict, float]] = {}

    def _compute_rates(
        self, device_id: str, if_index: int, counters: dict
    ) -> dict | None:
        key = (device_id, if_index)
        now = time.time()
        prev = self._prev_counters.get(key)
        self._prev_counters[key] = (counters, now)

        if prev is None:
            return None

        prev_counters, prev_time = prev
        dt = now - prev_time
        if dt <= 0:
            return None

        speed = counters.get("ifSpeed", 1_000_000_000) or 1_000_000_000
        d_in = counters.get("ifInOctets", 0) - prev_counters.get("ifInOctets", 0)
        d_out = counters.get("ifOutOctets", 0) - prev_counters.get("ifOutOctets", 0)
        d_errs = (
            (counters.get("ifInErrors", 0) - prev_counters.get("ifInErrors", 0))
            + (counters.get("ifOutErrors", 0) - prev_counters.get("ifOutErrors", 0))
        )
        d_total = d_in + d_out

        # Handle 32-bit counter wraps
        if d_in < 0:
            d_in += 2**32
        if d_out < 0:
            d_out += 2**32

        bps_in = (d_in * 8) / dt
        bps_out = (d_out * 8) / dt
        utilization = max(bps_in, bps_out) / speed if speed > 0 else 0
        error_rate = d_errs / d_total if d_total > 0 else 0

        return {
            "bps_in": bps_in,
            "bps_out": bps_out,
            "utilization": utilization,
            "error_rate": error_rate,
        }

    async def _snmp_get(self, cfg: SNMPDeviceConfig) -> dict:
        """Execute SNMP GET/WALK against a device. Returns parsed metrics dict."""
        try:
            from pysnmp.hlapi.v3arch.asyncio import (
                get_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
                ContextData, ObjectType, ObjectIdentity,
            )
        except ImportError:
            logger.error("pysnmp not installed — pip install pysnmp-lextudio")
            return {}

        engine = SnmpEngine()
        target = await UdpTransportTarget.create((cfg.ip, cfg.port), timeout=5, retries=1)

        if cfg.version == "v2c":
            auth = CommunityData(cfg.community, mpModel=1)
        else:
            from pysnmp.hlapi.v3arch.asyncio import UsmUserData
            auth = UsmUserData(cfg.v3_user, cfg.v3_auth_key, cfg.v3_priv_key)

        result: dict[str, Any] = {"interfaces": {}}

        # System scalars
        for name, oid in [
            ("cpu_pct", STANDARD_OIDS["hrProcessorLoad"]),
            ("mem_total", STANDARD_OIDS["memTotalReal"]),
            ("mem_avail", STANDARD_OIDS["memAvailReal"]),
        ]:
            err_indication, err_status, _, var_binds = await get_cmd(
                engine, auth, target, ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            if not err_indication and not err_status and var_binds:
                val = var_binds[0][1]
                result[name] = float(val) if hasattr(val, "__float__") else 0.0

        engine.close_dispatcher()
        return result

    async def poll_device(self, cfg: SNMPDeviceConfig) -> dict:
        """Poll a single device, write metrics, return summary."""
        data = await self._snmp_get(cfg)
        device_id = cfg.device_id

        cpu = data.get("cpu_pct", 0)
        mem_total = data.get("mem_total", 0)
        mem_avail = data.get("mem_avail", 0)
        mem_pct = ((mem_total - mem_avail) / mem_total * 100) if mem_total > 0 else 0

        await self.metrics.write_device_metric(device_id, "cpu_pct", cpu)
        await self.metrics.write_device_metric(device_id, "mem_pct", mem_pct)

        for if_idx, if_data in data.get("interfaces", {}).items():
            rates = self._compute_rates(device_id, if_idx, if_data)
            if rates:
                await self.metrics.write_device_metric(
                    device_id, f"if_{if_idx}_bps_in", rates["bps_in"]
                )
                await self.metrics.write_device_metric(
                    device_id, f"if_{if_idx}_bps_out", rates["bps_out"]
                )
                await self.metrics.write_device_metric(
                    device_id, f"if_{if_idx}_utilization", rates["utilization"]
                )

        return {"device_id": device_id, "cpu_pct": cpu, "mem_pct": mem_pct}

    async def poll_all(self, configs: list[SNMPDeviceConfig]) -> list[dict]:
        """Poll all configured devices."""
        results = []
        for cfg in configs:
            try:
                r = await self.poll_device(cfg)
                results.append(r)
            except Exception as e:
                logger.warning("SNMP poll failed for %s: %s", cfg.device_id, e)
                results.append({"device_id": cfg.device_id, "error": str(e)})
        return results
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_snmp_collector.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/snmp_collector.py backend/tests/test_snmp_collector.py
git commit -m "feat(monitoring): add SNMP collector with rate computation"
```

---

### Task 3: Alert Engine

**Files:**
- Create: `backend/src/network/alert_engine.py`
- Test: `backend/tests/test_alert_engine.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_alert_engine.py
import pytest
from unittest.mock import AsyncMock
from src.network.alert_engine import AlertEngine, AlertRule, AlertState


@pytest.fixture
def mock_metrics():
    store = AsyncMock()
    store.query_device_metrics = AsyncMock(return_value=[])
    store.write_alert_event = AsyncMock()
    return store


@pytest.fixture
def engine(mock_metrics):
    return AlertEngine(mock_metrics)


def test_add_rule(engine):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="*",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=300, cooldown_seconds=600,
    )
    engine.add_rule(rule)
    assert len(engine.rules) == 1


def test_default_rules_loaded(mock_metrics):
    engine = AlertEngine(mock_metrics, load_defaults=True)
    assert len(engine.rules) >= 5  # At least 5 default rules


@pytest.mark.asyncio
async def test_threshold_fires(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="dev-1",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=0,
    )
    engine.add_rule(rule)
    # Metric exceeds threshold
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
    alerts = await engine.evaluate("dev-1")
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "warning"
    assert alerts[0]["rule_id"] == "r1"


@pytest.mark.asyncio
async def test_threshold_not_met(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="dev-1",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=0,
    )
    engine.add_rule(rule)
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 50.0}]
    alerts = await engine.evaluate("dev-1")
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_cooldown_prevents_refire(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="dev-1",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=3600,
    )
    engine.add_rule(rule)
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
    alerts1 = await engine.evaluate("dev-1")
    assert len(alerts1) == 1
    # Second evaluation — should be suppressed by cooldown
    alerts2 = await engine.evaluate("dev-1")
    assert len(alerts2) == 0


@pytest.mark.asyncio
async def test_wildcard_filter(engine, mock_metrics):
    rule = AlertRule(
        id="r1", name="High CPU", severity="warning",
        entity_type="device", entity_filter="*",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=0, cooldown_seconds=0,
    )
    engine.add_rule(rule)
    mock_metrics.query_device_metrics.return_value = [{"time": "now", "value": 95.0}]
    alerts = await engine.evaluate("any-device-id")
    assert len(alerts) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_alert_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# backend/src/network/alert_engine.py
"""Threshold-based alert engine evaluating metrics from InfluxDB."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertState(str, Enum):
    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class AlertRule:
    id: str
    name: str
    severity: str  # critical, warning, info
    entity_type: str  # device, link, interface
    entity_filter: str  # "*" or specific device_id
    metric: str
    condition: str  # gt, lt, eq, absent
    threshold: float
    duration_seconds: int = 300
    cooldown_seconds: int = 600
    enabled: bool = True
    description: str = ""


DEFAULT_RULES = [
    AlertRule(
        id="default-unreachable", name="Device Unreachable",
        severity="critical", entity_type="device", entity_filter="*",
        metric="packet_loss", condition="gt", threshold=0.99,
        duration_seconds=90, cooldown_seconds=300,
    ),
    AlertRule(
        id="default-cpu", name="High CPU",
        severity="warning", entity_type="device", entity_filter="*",
        metric="cpu_pct", condition="gt", threshold=90.0,
        duration_seconds=300, cooldown_seconds=600,
    ),
    AlertRule(
        id="default-mem", name="High Memory",
        severity="warning", entity_type="device", entity_filter="*",
        metric="mem_pct", condition="gt", threshold=95.0,
        duration_seconds=300, cooldown_seconds=600,
    ),
    AlertRule(
        id="default-errors", name="Interface Errors",
        severity="warning", entity_type="device", entity_filter="*",
        metric="error_rate", condition="gt", threshold=0.01,
        duration_seconds=300, cooldown_seconds=600,
    ),
    AlertRule(
        id="default-saturation", name="Link Saturation",
        severity="warning", entity_type="device", entity_filter="*",
        metric="utilization", condition="gt", threshold=0.85,
        duration_seconds=600, cooldown_seconds=900,
    ),
    AlertRule(
        id="default-latency", name="Latency Spike",
        severity="warning", entity_type="device", entity_filter="*",
        metric="latency_ms", condition="gt", threshold=200.0,
        duration_seconds=120, cooldown_seconds=300,
    ),
]


class AlertEngine:
    """Evaluates alert rules against InfluxDB metrics."""

    def __init__(self, metrics_store: Any, load_defaults: bool = False) -> None:
        self.metrics = metrics_store
        self.rules: list[AlertRule] = []
        self._states: dict[str, AlertState] = {}  # (rule_id, entity_id) → state
        self._last_fired: dict[str, float] = {}  # (rule_id, entity_id) → timestamp
        self._active_alerts: dict[str, dict] = {}

        if load_defaults:
            for r in DEFAULT_RULES:
                self.add_rule(r)

    def add_rule(self, rule: AlertRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> None:
        self.rules = [r for r in self.rules if r.id != rule_id]

    def get_rules(self) -> list[dict]:
        return [
            {
                "id": r.id, "name": r.name, "severity": r.severity,
                "entity_type": r.entity_type, "entity_filter": r.entity_filter,
                "metric": r.metric, "condition": r.condition,
                "threshold": r.threshold, "duration_seconds": r.duration_seconds,
                "cooldown_seconds": r.cooldown_seconds, "enabled": r.enabled,
                "description": r.description,
            }
            for r in self.rules
        ]

    def get_active_alerts(self) -> list[dict]:
        return list(self._active_alerts.values())

    def acknowledge(self, alert_key: str) -> bool:
        if alert_key in self._active_alerts:
            self._active_alerts[alert_key]["acknowledged"] = True
            return True
        return False

    def _matches_filter(self, entity_id: str, entity_filter: str) -> bool:
        if entity_filter == "*":
            return True
        return entity_id == entity_filter

    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        if condition == "gt":
            return value > threshold
        elif condition == "lt":
            return value < threshold
        elif condition == "eq":
            return abs(value - threshold) < 0.001
        return False

    async def evaluate(self, entity_id: str) -> list[dict]:
        """Evaluate all rules for a given entity. Returns list of newly fired alerts."""
        fired: list[dict] = []
        now = time.time()

        for rule in self.rules:
            if not rule.enabled:
                continue
            if not self._matches_filter(entity_id, rule.entity_filter):
                continue

            key = f"{rule.id}:{entity_id}"

            # Check cooldown
            last = self._last_fired.get(key, 0)
            if now - last < rule.cooldown_seconds and key in self._active_alerts:
                continue

            # Query latest metric value
            data = await self.metrics.query_device_metrics(
                entity_id, rule.metric,
                range_str=f"{max(rule.duration_seconds, 30)}s",
                resolution="30s",
            )

            if not data:
                if rule.condition == "absent":
                    alert = self._fire_alert(rule, entity_id, 0, now)
                    fired.append(alert)
                continue

            latest_value = data[-1].get("value", 0)

            if self._check_condition(latest_value, rule.condition, rule.threshold):
                alert = self._fire_alert(rule, entity_id, latest_value, now)
                fired.append(alert)
            else:
                # Resolve if was firing
                if key in self._active_alerts:
                    del self._active_alerts[key]

        return fired

    def _fire_alert(
        self, rule: AlertRule, entity_id: str, value: float, now: float
    ) -> dict:
        key = f"{rule.id}:{entity_id}"
        self._last_fired[key] = now
        alert = {
            "key": key,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "entity_id": entity_id,
            "severity": rule.severity,
            "metric": rule.metric,
            "value": value,
            "threshold": rule.threshold,
            "condition": rule.condition,
            "fired_at": now,
            "acknowledged": False,
            "message": f"{rule.name}: {rule.metric}={value:.1f} (threshold: {rule.condition} {rule.threshold})",
        }
        self._active_alerts[key] = alert
        return alert

    async def evaluate_all(self, entity_ids: list[str]) -> list[dict]:
        """Evaluate all rules for all entities."""
        all_fired = []
        for eid in entity_ids:
            fired = await self.evaluate(eid)
            all_fired.extend(fired)
            for alert in fired:
                await self.metrics.write_alert_event(
                    device_id=eid, rule_id=alert["rule_id"],
                    severity=alert["severity"], value=alert["value"],
                    threshold=alert["threshold"], message=alert["message"],
                )
        return all_fired
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_alert_engine.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/alert_engine.py backend/tests/test_alert_engine.py
git commit -m "feat(monitoring): add threshold-based alert engine with default rules"
```

---

### Task 4: Flow Receiver (NetFlow v5/v9 UDP Server)

**Files:**
- Create: `backend/src/network/flow_receiver.py`
- Test: `backend/tests/test_flow_receiver.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_flow_receiver.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# backend/src/network/flow_receiver.py
"""NetFlow v5/v9 and sFlow receiver with aggregation pipeline."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .metrics_store import FlowRecord

logger = logging.getLogger(__name__)


@dataclass
class NetFlowV5Header:
    version: int
    count: int
    sys_uptime: int
    unix_secs: int
    unix_nsecs: int
    flow_sequence: int

    @classmethod
    def from_bytes(cls, data: bytes) -> NetFlowV5Header | None:
        if len(data) < 24:
            return None
        version, count, uptime, secs, nsecs, seq = struct.unpack_from("!HHIIII", data)
        return cls(version, count, uptime, secs, nsecs, seq)


@dataclass
class NetFlowV5Record:
    src_ip: str
    dst_ip: str
    next_hop: str
    input_snmp: int
    output_snmp: int
    packets: int
    bytes: int
    first: int
    last: int
    src_port: int
    dst_port: int
    tcp_flags: int
    protocol: int
    tos: int
    src_as: int
    dst_as: int

    V5_RECORD_SIZE = 48


class FlowParser:
    """Parses NetFlow v5 binary packets into FlowRecord objects."""

    def parse_v5(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        header = NetFlowV5Header.from_bytes(data)
        if header is None or header.version != 5:
            return []

        records = []
        offset = 24  # v5 header size
        base_time = datetime.fromtimestamp(header.unix_secs, tz=timezone.utc)

        for _ in range(header.count):
            if offset + 48 > len(data):
                break
            fields = struct.unpack_from("!IIIHHIIIIHHBBBBHHBBH", data, offset)
            offset += 48

            src_ip = socket.inet_ntoa(struct.pack("!I", fields[0]))
            dst_ip = socket.inet_ntoa(struct.pack("!I", fields[1]))

            records.append(FlowRecord(
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=fields[9],
                dst_port=fields[10],
                protocol=fields[12],
                bytes=fields[6],
                packets=fields[5],
                start_time=base_time,
                end_time=base_time,
                tcp_flags=fields[11],
                tos=fields[13],
                input_snmp=fields[3],
                output_snmp=fields[4],
                src_as=fields[14],
                dst_as=fields[15],
                exporter_ip=exporter_ip,
            ))

        return records

    def detect_and_parse(self, data: bytes, exporter_ip: str) -> list[FlowRecord]:
        if len(data) < 4:
            return []
        version = struct.unpack_from("!H", data)[0]
        if version == 5:
            return self.parse_v5(data, exporter_ip)
        logger.debug("Unsupported flow version: %d from %s", version, exporter_ip)
        return []


class FlowAggregator:
    """Buffers flow records and flushes aggregated metrics."""

    def __init__(
        self, metrics_store: Any, topology_store: Any,
        device_ip_map: dict[str, str] | None = None,
    ) -> None:
        self.metrics = metrics_store
        self.topo_store = topology_store
        self._buffer: list[FlowRecord] = []
        self._device_ip_map = device_ip_map or {}

    def ingest(self, flow: FlowRecord) -> None:
        self._buffer.append(flow)

    async def flush(self) -> int:
        if not self._buffer:
            return 0

        batch = self._buffer[:]
        self._buffer.clear()

        # Write individual flows
        for flow in batch:
            await self.metrics.write_flow(flow)

        # Aggregate per (src_device, dst_device)
        link_agg: dict[tuple[str, str], dict] = {}
        for flow in batch:
            src_dev = self._device_ip_map.get(flow.exporter_ip, flow.src_ip)
            dst_dev = flow.dst_ip  # Best-effort mapping
            key = (src_dev, dst_dev)
            if key not in link_agg:
                link_agg[key] = {"bytes": 0, "packets": 0}
            link_agg[key]["bytes"] += flow.bytes
            link_agg[key]["packets"] += flow.packets

        for (src, dst), agg in link_agg.items():
            await self.metrics.write_link_metric(src, dst, **agg)
            try:
                self.topo_store.upsert_link_metric(
                    src, dst, latency_ms=0, bandwidth_bps=agg["bytes"] * 8 // 30,
                    error_rate=0, utilization=0,
                )
            except Exception:
                pass

        return len(batch)


class FlowReceiverProtocol(asyncio.DatagramProtocol):
    """Async UDP protocol for receiving flow packets."""

    def __init__(self, parser: FlowParser, aggregator: FlowAggregator) -> None:
        self.parser = parser
        self.aggregator = aggregator
        self._count = 0

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        exporter_ip = addr[0]
        records = self.parser.detect_and_parse(data, exporter_ip)
        for r in records:
            self.aggregator.ingest(r)
        self._count += len(records)


class FlowReceiver:
    """Manages UDP listeners for NetFlow/sFlow."""

    def __init__(self, metrics_store: Any, topology_store: Any) -> None:
        self.metrics = metrics_store
        self.topo_store = topology_store
        self.parser = FlowParser()
        self.aggregator = FlowAggregator(metrics_store, topology_store)
        self._transports: list[asyncio.BaseTransport] = []
        self._flush_task: asyncio.Task | None = None

    async def start(self, ports: dict[str, int] | None = None) -> None:
        ports = ports or {"netflow": 2055}
        loop = asyncio.get_event_loop()

        for name, port in ports.items():
            try:
                transport, _ = await loop.create_datagram_endpoint(
                    lambda: FlowReceiverProtocol(self.parser, self.aggregator),
                    local_addr=("0.0.0.0", port),
                )
                self._transports.append(transport)
                logger.info("Flow receiver listening on UDP port %d (%s)", port, name)
            except Exception as e:
                logger.warning("Failed to bind UDP port %d (%s): %s", port, name, e)

        self._flush_task = asyncio.create_task(self._flush_loop())

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            count = await self.aggregator.flush()
            if count > 0:
                logger.info("Flushed %d flow records", count)

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
        for t in self._transports:
            t.close()
        await self.aggregator.flush()

    def update_device_map(self, device_ip_map: dict[str, str]) -> None:
        self.aggregator._device_ip_map = device_ip_map
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_flow_receiver.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/flow_receiver.py backend/tests/test_flow_receiver.py
git commit -m "feat(monitoring): add NetFlow v5 receiver with aggregation pipeline"
```

---

### Task 5: Wire Everything into NetworkMonitor + Startup

**Files:**
- Modify: `backend/src/network/monitor.py`
- Modify: `backend/src/api/monitor_endpoints.py`
- Modify: `backend/src/api/main.py`
- Test: `backend/tests/test_monitor_integration.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_monitor_integration.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_monitor_cycle_includes_snmp():
    """Monitor collect cycle should include SNMP pass."""
    from src.network.monitor import NetworkMonitor
    store = MagicMock()
    store.list_device_statuses = MagicMock(return_value=[])
    store.list_link_metrics = MagicMock(return_value=[])
    store.list_active_drift_events = MagicMock(return_value=[])
    store.list_discovery_candidates = MagicMock(return_value=[])
    store.prune_metric_history = MagicMock()

    kg = MagicMock()
    kg.graph = MagicMock()
    kg.graph.nodes = MagicMock(return_value=[])

    adapters = MagicMock()
    adapters.device_bindings = MagicMock(return_value={})
    adapters.all_instances = MagicMock(return_value={})

    metrics_store = AsyncMock()
    metrics_store.write_device_metric = AsyncMock()

    monitor = NetworkMonitor(store, kg, adapters, metrics_store=metrics_store)
    assert monitor.snmp_collector is not None
    assert monitor.alert_engine is not None


@pytest.mark.asyncio
async def test_snapshot_includes_alerts():
    from src.network.monitor import NetworkMonitor
    store = MagicMock()
    store.list_device_statuses = MagicMock(return_value=[])
    store.list_link_metrics = MagicMock(return_value=[])
    store.list_active_drift_events = MagicMock(return_value=[])
    store.list_discovery_candidates = MagicMock(return_value=[])

    kg = MagicMock()
    kg.graph = MagicMock()
    kg.graph.nodes = MagicMock(return_value=[])

    adapters = MagicMock()

    metrics_store = AsyncMock()

    monitor = NetworkMonitor(store, kg, adapters, metrics_store=metrics_store)
    snap = monitor.get_snapshot()
    assert "alerts" in snap
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_monitor_integration.py -v`
Expected: FAIL — `TypeError: NetworkMonitor.__init__() got unexpected keyword argument 'metrics_store'`

**Step 3: Modify NetworkMonitor**

Add to `backend/src/network/monitor.py`:
- Import SNMPCollector, AlertEngine, MetricsStore
- Accept optional `metrics_store` param in `__init__`
- Add `_snmp_pass()` and `_alert_pass()` to cycle
- Add `alerts` to `get_snapshot()`

The exact changes:

1. Add imports at top of monitor.py:
```python
from .snmp_collector import SNMPCollector, SNMPDeviceConfig
from .alert_engine import AlertEngine
```

2. Update `__init__` to accept `metrics_store` and create sub-components:
```python
def __init__(self, store, kg, adapters, metrics_store=None):
    # ... existing init ...
    self.metrics_store = metrics_store
    self.snmp_collector = SNMPCollector(metrics_store) if metrics_store else None
    self.alert_engine = AlertEngine(metrics_store, load_defaults=True) if metrics_store else None
```

3. Add SNMP pass method:
```python
async def _snmp_pass(self):
    if not self.snmp_collector:
        return
    configs = []
    for node_id, attrs in self.kg.graph.nodes(data=True):
        ip = attrs.get("management_ip", "")
        if ip and attrs.get("snmp_enabled"):
            configs.append(SNMPDeviceConfig(
                device_id=node_id, ip=ip,
                version=attrs.get("snmp_version", "v2c"),
                community=attrs.get("snmp_community", "public"),
            ))
    if configs:
        await self.snmp_collector.poll_all(configs)
```

4. Add alert pass:
```python
async def _alert_pass(self):
    if not self.alert_engine:
        return
    device_ids = [d["device_id"] for d in self.store.list_device_statuses()]
    self._latest_alerts = await self.alert_engine.evaluate_all(device_ids)
```

5. Call both in `_collect_cycle()` after existing passes.

6. Update `get_snapshot()` to include alerts:
```python
def get_snapshot(self):
    return {
        "devices": self.store.list_device_statuses(),
        "links": self.store.list_link_metrics(),
        "drifts": self.store.list_active_drift_events(),
        "candidates": self.store.list_discovery_candidates(),
        "alerts": self.alert_engine.get_active_alerts() if self.alert_engine else [],
    }
```

**Step 4: Modify main.py startup**

Add InfluxDB initialization and NetworkMonitor startup in `backend/src/api/main.py`:

```python
# In startup function, after _reload_adapter_instances():
from src.network.metrics_store import MetricsStore
import os

influx_url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
influx_token = os.getenv("INFLUXDB_TOKEN", "")
influx_org = os.getenv("INFLUXDB_ORG", "debugduck")
influx_bucket = os.getenv("INFLUXDB_BUCKET", "network_metrics")

_metrics_store = None
if influx_token:
    _metrics_store = MetricsStore(influx_url, influx_token, influx_org, influx_bucket)

# Create and start monitor
from src.network.monitor import NetworkMonitor
monitor = NetworkMonitor(
    _get_topology_store(), _get_knowledge_graph(),
    _adapter_registry, metrics_store=_metrics_store,
)
_set_monitor(monitor)
asyncio.create_task(monitor.start())
```

**Step 5: Modify monitor_endpoints.py**

Add new endpoints for SNMP, flows, metrics, and alerts in `backend/src/api/monitor_endpoints.py`:

```python
# New endpoints to add:

@monitor_router.get("/alerts")
async def get_alerts():
    if not _monitor:
        return {"alerts": []}
    return {"alerts": _monitor.alert_engine.get_active_alerts() if _monitor.alert_engine else []}

@monitor_router.get("/alerts/rules")
async def get_alert_rules():
    if not _monitor or not _monitor.alert_engine:
        return {"rules": []}
    return {"rules": _monitor.alert_engine.get_rules()}

@monitor_router.post("/alerts/{alert_key}/acknowledge")
async def acknowledge_alert(alert_key: str):
    if not _monitor or not _monitor.alert_engine:
        raise HTTPException(404, "Monitor not running")
    ok = _monitor.alert_engine.acknowledge(alert_key)
    return {"acknowledged": ok}

@monitor_router.get("/metrics/{entity_type}/{entity_id}/{metric}")
async def query_metrics(entity_type: str, entity_id: str, metric: str, range: str = "1h", resolution: str = "30s"):
    if not _monitor or not _monitor.metrics_store:
        return {"data": []}
    data = await _monitor.metrics_store.query_device_metrics(entity_id, metric, range, resolution)
    return {"data": data}

@monitor_router.get("/flows/top-talkers")
async def get_top_talkers(window: str = "5m", limit: int = 20):
    if not _monitor or not _monitor.metrics_store:
        return {"flows": []}
    flows = await _monitor.metrics_store.query_top_talkers(window, limit)
    return {"flows": flows}

@monitor_router.get("/flows/traffic-matrix")
async def get_traffic_matrix(window: str = "15m"):
    if not _monitor or not _monitor.metrics_store:
        return {"matrix": []}
    matrix = await _monitor.metrics_store.query_traffic_matrix(window)
    return {"matrix": matrix}

@monitor_router.get("/flows/protocols")
async def get_protocol_breakdown(window: str = "1h"):
    if not _monitor or not _monitor.metrics_store:
        return {"protocols": []}
    protocols = await _monitor.metrics_store.query_protocol_breakdown(window)
    return {"protocols": protocols}

@monitor_router.get("/config/influxdb/status")
async def influxdb_status():
    if not _monitor or not _monitor.metrics_store:
        return {"connected": False, "reason": "not configured"}
    ok = await _monitor.metrics_store.health_check()
    return {"connected": ok}
```

**Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_monitor_integration.py -v`
Expected: PASS

**Step 7: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 8: Commit**

```bash
git add backend/src/network/monitor.py backend/src/api/monitor_endpoints.py backend/src/api/main.py backend/tests/test_monitor_integration.py
git commit -m "feat(monitoring): wire SNMP, alerts, InfluxDB into monitor cycle and API"
```

---

## Phase 2: Frontend Observatory Enhancements (Tasks 6-10)

### Task 6: Update Types and API Service

**Files:**
- Modify: `frontend/src/components/Observatory/hooks/useMonitorSnapshot.ts`
- Modify: `frontend/src/services/api.ts`

**Step 1: Add new types to useMonitorSnapshot.ts**

After existing interfaces (around line 43), add:

```typescript
export interface AlertEvent {
  key: string;
  rule_id: string;
  rule_name: string;
  entity_id: string;
  severity: 'critical' | 'warning' | 'info';
  metric: string;
  value: number;
  threshold: number;
  condition: string;
  fired_at: number;
  acknowledged: boolean;
  message: string;
}

export interface AlertRule {
  id: string;
  name: string;
  severity: string;
  entity_type: string;
  entity_filter: string;
  metric: string;
  condition: string;
  threshold: number;
  duration_seconds: number;
  cooldown_seconds: number;
  enabled: boolean;
}

export interface MetricDataPoint {
  time: string;
  value: number;
}

export interface TopTalker {
  src_ip: string;
  dst_ip: string;
  protocol: string;
  bytes: number;
}

export interface TrafficMatrixEntry {
  src: string;
  dst: string;
  bytes: number;
}

export interface ProtocolBreakdown {
  protocol: string;
  bytes: number;
}
```

Update `MonitorSnapshot` to include alerts:
```typescript
export interface MonitorSnapshot {
  devices: DeviceStatus[];
  links: LinkMetric[];
  drifts: DriftEvent[];
  candidates: DiscoveryCandidate[];
  alerts: AlertEvent[];
}
```

**Step 2: Add API functions to api.ts**

Append to `frontend/src/services/api.ts`:

```typescript
export async function fetchAlerts(): Promise<{ alerts: AlertEvent[] }> {
  const res = await fetch(`${API}/api/v4/network/monitor/alerts`);
  return res.json();
}

export async function fetchAlertRules(): Promise<{ rules: AlertRule[] }> {
  const res = await fetch(`${API}/api/v4/network/monitor/alerts/rules`);
  return res.json();
}

export async function acknowledgeAlert(alertKey: string): Promise<{ acknowledged: boolean }> {
  const res = await fetch(`${API}/api/v4/network/monitor/alerts/${encodeURIComponent(alertKey)}/acknowledge`, { method: 'POST' });
  return res.json();
}

export async function fetchDeviceMetrics(
  entityId: string, metric: string, range = '1h', resolution = '30s'
): Promise<{ data: MetricDataPoint[] }> {
  const res = await fetch(`${API}/api/v4/network/monitor/metrics/device/${entityId}/${metric}?range=${range}&resolution=${resolution}`);
  return res.json();
}

export async function fetchTopTalkers(window = '5m', limit = 20): Promise<{ flows: TopTalker[] }> {
  const res = await fetch(`${API}/api/v4/network/monitor/flows/top-talkers?window=${window}&limit=${limit}`);
  return res.json();
}

export async function fetchTrafficMatrix(window = '15m'): Promise<{ matrix: TrafficMatrixEntry[] }> {
  const res = await fetch(`${API}/api/v4/network/monitor/flows/traffic-matrix?window=${window}`);
  return res.json();
}

export async function fetchProtocolBreakdown(window = '1h'): Promise<{ protocols: ProtocolBreakdown[] }> {
  const res = await fetch(`${API}/api/v4/network/monitor/flows/protocols?window=${window}`);
  return res.json();
}

export async function fetchInfluxDBStatus(): Promise<{ connected: boolean; reason?: string }> {
  const res = await fetch(`${API}/api/v4/network/monitor/config/influxdb/status`);
  return res.json();
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/Observatory/hooks/useMonitorSnapshot.ts frontend/src/services/api.ts
git commit -m "feat(observatory): add alert/flow/metric types and API service functions"
```

---

### Task 7: Enhanced Device Health Tab (replaces NOC Wall)

**Files:**
- Modify: `frontend/src/components/Observatory/NOCWallTab.tsx`

**Step 1: Rewrite NOCWallTab with CPU/memory gauges and sparklines**

Replace the table-based NOC Wall with a card grid. Each card shows:
- Device name + status dot
- CPU gauge (circular progress)
- Memory gauge (circular progress)
- Latency sparkline (Recharts LineChart, last 1hr)
- Click → opens DeviceStatusSidebar

Key imports to add: `import { LineChart, Line, ResponsiveContainer } from 'recharts';`

Use mock sparkline data until InfluxDB is connected (generate from latency_ms ± random noise).

The component already has the right props interface — just enhance the rendering from a table to cards with gauges.

**Step 2: Commit**

```bash
git add frontend/src/components/Observatory/NOCWallTab.tsx
git commit -m "feat(observatory): enhance Device Health tab with gauges and sparklines"
```

---

### Task 8: Enhanced Traffic Flows Tab

**Files:**
- Modify: `frontend/src/components/Observatory/TrafficFlowsTab.tsx`

**Step 1: Rewrite with top talkers, protocol breakdown, time range selector**

Replace the simple bandwidth bars with:
- Time range selector buttons: 5m | 15m | 1h | 6h | 24h
- Top Talkers table (fetched from `/flows/top-talkers`)
- Protocol Breakdown bar chart (Recharts BarChart)
- Traffic Matrix heatmap (simple colored grid)

Key imports: `import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';`

Add state for `timeRange`, `topTalkers`, `protocols`. Fetch on mount and when timeRange changes.

**Step 2: Commit**

```bash
git add frontend/src/components/Observatory/TrafficFlowsTab.tsx
git commit -m "feat(observatory): enhance Traffic Flows with top talkers and protocol breakdown"
```

---

### Task 9: Alerts Tab

**Files:**
- Create: `frontend/src/components/Observatory/AlertsTab.tsx`
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

**Step 1: Create AlertsTab component**

```typescript
// frontend/src/components/Observatory/AlertsTab.tsx
import React, { useState } from 'react';
import { AlertEvent } from './hooks/useMonitorSnapshot';
import { acknowledgeAlert } from '../../services/api';

interface Props {
  alerts: AlertEvent[];
  onRefresh: () => void;
}

const severityColors: Record<string, string> = {
  critical: '#ef4444',
  warning: '#f59e0b',
  info: '#07b6d5',
};

const AlertsTab: React.FC<Props> = ({ alerts, onRefresh }) => {
  const [filter, setFilter] = useState<string>('all');

  const filtered = filter === 'all'
    ? alerts
    : alerts.filter(a => a.severity === filter);

  const handleAck = async (key: string) => {
    await acknowledgeAlert(key);
    onRefresh();
  };

  return (
    <div className="space-y-3">
      {/* Filter buttons */}
      <div className="flex gap-2">
        {['all', 'critical', 'warning', 'info'].map(s => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className="px-3 py-1 rounded text-xs font-mono"
            style={{
              backgroundColor: filter === s ? '#1a3a40' : 'transparent',
              color: s === 'all' ? '#e2e8f0' : severityColors[s],
              border: `1px solid ${filter === s ? '#07b6d5' : '#224349'}`,
            }}
          >
            {s.toUpperCase()} {s !== 'all' && `(${alerts.filter(a => a.severity === s).length})`}
          </button>
        ))}
      </div>

      {/* Alert list */}
      {filtered.length === 0 ? (
        <div className="text-center py-8 text-[#64748b] font-mono text-sm">
          No active alerts
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(alert => (
            <div
              key={alert.key}
              className="rounded border p-3 flex items-center justify-between"
              style={{
                backgroundColor: '#0a1a1e',
                borderColor: severityColors[alert.severity] + '40',
                borderLeftWidth: '3px',
                borderLeftColor: severityColors[alert.severity],
                opacity: alert.acknowledged ? 0.5 : 1,
              }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                    style={{
                      backgroundColor: severityColors[alert.severity] + '20',
                      color: severityColors[alert.severity],
                    }}
                  >
                    {alert.severity.toUpperCase()}
                  </span>
                  <span className="text-sm font-mono text-[#e2e8f0]">
                    {alert.rule_name}
                  </span>
                </div>
                <div className="text-xs font-mono text-[#64748b] mt-1">
                  {alert.entity_id} — {alert.metric}: {alert.value.toFixed(1)} ({alert.condition} {alert.threshold})
                </div>
              </div>
              {!alert.acknowledged && (
                <button
                  onClick={() => handleAck(alert.key)}
                  className="text-xs font-mono px-2 py-1 rounded border"
                  style={{ borderColor: '#224349', color: '#64748b' }}
                >
                  ACK
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AlertsTab;
```

**Step 2: Add Alerts tab to ObservatoryView**

In `ObservatoryView.tsx`:
- Import `AlertsTab`
- Add `'alerts'` to tab state type
- Add alerts tab button with count badge
- Render `<AlertsTab alerts={snapshot.alerts} onRefresh={refresh} />` when active

**Step 3: Commit**

```bash
git add frontend/src/components/Observatory/AlertsTab.tsx frontend/src/components/Observatory/ObservatoryView.tsx
git commit -m "feat(observatory): add Alerts tab with severity filtering and acknowledgement"
```

---

### Task 10: Live Topology Link Coloring + Alert Bell

**Files:**
- Modify: `frontend/src/components/Observatory/LiveTopologyTab.tsx`
- Modify: `frontend/src/components/Observatory/ObservatoryView.tsx`

**Step 1: Add link coloring by utilization to LiveTopologyTab**

In `LiveTopologyTab.tsx`, modify the SVG link rendering:
- Color links by utilization: green (<50%) → yellow (50-80%) → red (>80%)
- Width scaled by bandwidth (min 1px, max 4px)
- Add hover tooltip showing: bandwidth, latency, error rate, utilization %

```typescript
function linkColor(utilization: number): string {
  if (utilization > 0.8) return '#ef4444';
  if (utilization > 0.5) return '#f59e0b';
  return '#22c55e';
}

function linkWidth(bandwidthBps: number): number {
  if (bandwidthBps > 1_000_000_000) return 4;
  if (bandwidthBps > 100_000_000) return 3;
  if (bandwidthBps > 1_000_000) return 2;
  return 1;
}
```

**Step 2: Add alert bell to ObservatoryView header**

In `ObservatoryView.tsx`, add an alert bell icon (Material Symbol: `notifications`) in the header area:
- Show unread count badge (red circle with number)
- Click → dropdown showing last 5 alerts
- Unread = not acknowledged

**Step 3: Commit**

```bash
git add frontend/src/components/Observatory/LiveTopologyTab.tsx frontend/src/components/Observatory/ObservatoryView.tsx
git commit -m "feat(observatory): add link coloring by utilization and alert bell notification"
```

---

## Phase 3: Dependencies & Verification (Tasks 11-12)

### Task 11: Install Python Dependencies

**Step 1: Add dependencies**

```bash
cd backend && pip install influxdb-client[async] pysnmp-lextudio
```

**Step 2: Update requirements.txt**

Add to `backend/requirements.txt`:
```
influxdb-client[async]>=1.40.0
pysnmp-lextudio>=6.1.0
```

**Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add influxdb-client and pysnmp dependencies"
```

---

### Task 12: Full Verification

**Step 1: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 2: Python tests**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 3: Lint check**

Run: `cd backend && python -m py_compile src/network/metrics_store.py src/network/snmp_collector.py src/network/flow_receiver.py src/network/alert_engine.py`
Expected: No syntax errors

**Step 4: Final commit (if any fixes needed)**

```bash
git add -A && git commit -m "fix: address verification issues from flow-first monitoring"
```

---

## Summary

| Task | Component | Files | Tests |
|------|-----------|-------|-------|
| 1 | MetricsStore (InfluxDB) | `metrics_store.py` | `test_metrics_store.py` |
| 2 | SNMP Collector | `snmp_collector.py` | `test_snmp_collector.py` |
| 3 | Alert Engine | `alert_engine.py` | `test_alert_engine.py` |
| 4 | Flow Receiver | `flow_receiver.py` | `test_flow_receiver.py` |
| 5 | Monitor + API Wiring | `monitor.py`, `main.py`, `monitor_endpoints.py` | `test_monitor_integration.py` |
| 6 | Frontend Types + API | `useMonitorSnapshot.ts`, `api.ts` | — |
| 7 | Device Health Tab | `NOCWallTab.tsx` | — |
| 8 | Traffic Flows Tab | `TrafficFlowsTab.tsx` | — |
| 9 | Alerts Tab | `AlertsTab.tsx`, `ObservatoryView.tsx` | — |
| 10 | Topology + Bell | `LiveTopologyTab.tsx`, `ObservatoryView.tsx` | — |
| 11 | Dependencies | `requirements.txt` | — |
| 12 | Verification | — | Full suite |
