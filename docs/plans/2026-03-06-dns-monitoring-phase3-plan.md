# DNS Monitoring Implementation Plan (Phase 3)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add DNS monitoring to the network observatory — query timing, server health checks, critical hostname verification, record drift detection, and NXDOMAIN tracking.

**Architecture:** New `dns_monitor.py` module with a `DNSMonitor` class that performs async DNS queries against configured servers and hostnames. Integrates into `NetworkMonitor._collect_cycle()` as a new `_dns_pass()`. Metrics flow to InfluxDB via `MetricsStore`. DNS-specific alert rules added to `AlertEngine.DEFAULT_RULES`. API endpoints for DNS config management.

**Tech Stack:** Python `dnspython` (async DNS resolver), existing InfluxDB metrics store, existing alert engine, existing FastAPI endpoints pattern.

---

### Task 1: DNS Monitor Core — Models and DNSMonitor Class

**Files:**
- Create: `backend/src/network/dns_monitor.py`
- Modify: `backend/src/network/models.py` (add DNS config models)
- Test: `backend/tests/test_dns_monitor.py`

**Step 1: Add DNS models to `models.py`**

Add after the existing model classes in `backend/src/network/models.py`:

```python
class DNSRecordType(str, Enum):
    A = "A"
    AAAA = "AAAA"
    MX = "MX"
    NS = "NS"
    CNAME = "CNAME"
    TXT = "TXT"
    SOA = "SOA"
    PTR = "PTR"


class DNSServerConfig(BaseModel):
    id: str
    name: str
    ip: str
    port: int = 53
    enabled: bool = True


class DNSWatchedHostname(BaseModel):
    hostname: str
    record_type: DNSRecordType = DNSRecordType.A
    expected_values: list[str] = []  # Empty = just monitor, don't check drift
    critical: bool = False  # If True, failure fires critical alert


class DNSMonitorConfig(BaseModel):
    servers: list[DNSServerConfig] = []
    watched_hostnames: list[DNSWatchedHostname] = []
    query_timeout: float = 5.0
    enabled: bool = True
```

**Step 2: Write the failing tests for DNSMonitor**

Create `backend/tests/test_dns_monitor.py`:

```python
"""Tests for DNS monitoring module."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.dns_monitor import DNSMonitor, DNSQueryResult
from src.network.models import (
    DNSServerConfig, DNSWatchedHostname, DNSMonitorConfig, DNSRecordType,
)


@pytest.fixture
def dns_config():
    return DNSMonitorConfig(
        servers=[
            DNSServerConfig(id="dns-1", name="Primary DNS", ip="8.8.8.8"),
            DNSServerConfig(id="dns-2", name="Secondary DNS", ip="8.8.4.4"),
        ],
        watched_hostnames=[
            DNSWatchedHostname(
                hostname="api.example.com",
                record_type=DNSRecordType.A,
                expected_values=["10.0.0.1"],
                critical=True,
            ),
            DNSWatchedHostname(
                hostname="web.example.com",
                record_type=DNSRecordType.A,
            ),
        ],
    )


@pytest.fixture
def mock_metrics():
    m = AsyncMock()
    m.write_dns_metric = AsyncMock()
    return m


@pytest.fixture
def monitor(dns_config, mock_metrics):
    return DNSMonitor(dns_config, mock_metrics)


class TestDNSQueryResult:
    def test_result_success(self):
        r = DNSQueryResult(
            hostname="example.com", record_type="A", server_ip="8.8.8.8",
            values=["93.184.216.34"], latency_ms=12.5, success=True,
        )
        assert r.success
        assert r.latency_ms == 12.5
        assert "93.184.216.34" in r.values

    def test_result_failure(self):
        r = DNSQueryResult(
            hostname="nxdomain.example.com", record_type="A",
            server_ip="8.8.8.8", values=[], latency_ms=0,
            success=False, error="NXDOMAIN",
        )
        assert not r.success
        assert r.error == "NXDOMAIN"


class TestDNSMonitor:
    def test_init(self, monitor, dns_config):
        assert monitor.config == dns_config
        assert len(monitor.config.servers) == 2

    @pytest.mark.asyncio
    async def test_query_hostname_success(self, monitor):
        mock_answer = MagicMock()
        mock_rdata = MagicMock()
        mock_rdata.to_text.return_value = "10.0.0.1"
        mock_answer.__iter__ = lambda self: iter([mock_rdata])

        with patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = mock_answer
            result = await monitor.query_hostname("api.example.com", "A", "8.8.8.8")

        assert result.success
        assert "10.0.0.1" in result.values
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_query_hostname_nxdomain(self, monitor):
        with patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = Exception("NXDOMAIN")
            result = await monitor.query_hostname("bad.example.com", "A", "8.8.8.8")

        assert not result.success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_query_hostname_timeout(self, monitor):
        with patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = Exception("Timeout")
            result = await monitor.query_hostname("slow.example.com", "A", "8.8.8.8")

        assert not result.success

    @pytest.mark.asyncio
    async def test_check_server_health(self, monitor):
        mock_answer = MagicMock()
        mock_rdata = MagicMock()
        mock_rdata.to_text.return_value = "93.184.216.34"
        mock_answer.__iter__ = lambda self: iter([mock_rdata])

        with patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = mock_answer
            health = await monitor.check_server_health("8.8.8.8")

        assert health["server_ip"] == "8.8.8.8"
        assert health["healthy"] is True
        assert health["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_check_server_health_down(self, monitor):
        with patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.side_effect = Exception("Timeout")
            health = await monitor.check_server_health("8.8.8.8")

        assert health["healthy"] is False

    @pytest.mark.asyncio
    async def test_detect_drift(self, monitor):
        expected = DNSWatchedHostname(
            hostname="api.example.com", record_type=DNSRecordType.A,
            expected_values=["10.0.0.1"], critical=True,
        )
        result = DNSQueryResult(
            hostname="api.example.com", record_type="A", server_ip="8.8.8.8",
            values=["10.0.0.2"], latency_ms=5.0, success=True,
        )
        drifts = monitor.detect_drift(expected, result)
        assert len(drifts) == 1
        assert drifts[0]["drift_type"] == "dns_record_mismatch"
        assert drifts[0]["expected"] == "10.0.0.1"
        assert drifts[0]["actual"] == "10.0.0.2"

    @pytest.mark.asyncio
    async def test_detect_drift_no_expected(self, monitor):
        """No expected values configured = no drift check, just monitoring."""
        hostname = DNSWatchedHostname(hostname="web.example.com", record_type=DNSRecordType.A)
        result = DNSQueryResult(
            hostname="web.example.com", record_type="A", server_ip="8.8.8.8",
            values=["10.0.0.5"], latency_ms=5.0, success=True,
        )
        drifts = monitor.detect_drift(hostname, result)
        assert len(drifts) == 0

    @pytest.mark.asyncio
    async def test_run_pass_writes_metrics(self, monitor, mock_metrics):
        mock_answer = MagicMock()
        mock_rdata = MagicMock()
        mock_rdata.to_text.return_value = "10.0.0.1"
        mock_answer.__iter__ = lambda self: iter([mock_rdata])

        with patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = mock_answer
            results = await monitor.run_pass()

        assert mock_metrics.write_dns_metric.call_count > 0
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_run_pass_disabled(self, dns_config, mock_metrics):
        dns_config.enabled = False
        monitor = DNSMonitor(dns_config, mock_metrics)
        results = await monitor.run_pass()
        assert results == []
        mock_metrics.write_dns_metric.assert_not_called()
```

**Step 3: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_dns_monitor.py -v`
Expected: FAIL (module not found)

**Step 4: Implement DNSMonitor**

Create `backend/src/network/dns_monitor.py`:

```python
"""DNS monitoring — query timing, server health, hostname verification, record drift."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    import dns.asyncresolver
    import dns.rdatatype
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False

from .models import DNSMonitorConfig, DNSWatchedHostname

# Module-level function for easy mocking in tests
async def dns_resolver_resolve(
    qname: str, rdtype: str, nameserver: str, lifetime: float
) -> Any:
    """Resolve a DNS query using dnspython. Isolated for testability."""
    resolver = dns.asyncresolver.Resolver()
    resolver.nameservers = [nameserver]
    resolver.lifetime = lifetime
    return await resolver.resolve(qname, rdtype)


_HEALTH_CHECK_HOSTNAME = "google.com"


@dataclass
class DNSQueryResult:
    hostname: str
    record_type: str
    server_ip: str
    values: list[str]
    latency_ms: float
    success: bool
    error: str | None = None


class DNSMonitor:
    """Performs DNS queries against configured servers, measures latency,
    verifies expected records, and detects drift."""

    def __init__(self, config: DNSMonitorConfig, metrics_store: Any = None) -> None:
        self.config = config
        self.metrics = metrics_store
        self._nxdomain_counts: dict[str, int] = {}

    async def query_hostname(
        self, hostname: str, record_type: str, server_ip: str
    ) -> DNSQueryResult:
        """Query a single hostname against a single DNS server."""
        if not HAS_DNSPYTHON:
            return DNSQueryResult(
                hostname=hostname, record_type=record_type, server_ip=server_ip,
                values=[], latency_ms=0, success=False,
                error="dnspython not installed",
            )
        start = time.monotonic()
        try:
            answer = await dns_resolver_resolve(
                hostname, record_type, server_ip, self.config.query_timeout,
            )
            elapsed = (time.monotonic() - start) * 1000
            values = [rdata.to_text() for rdata in answer]
            return DNSQueryResult(
                hostname=hostname, record_type=record_type, server_ip=server_ip,
                values=values, latency_ms=round(elapsed, 2), success=True,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            error_str = str(e)
            if "NXDOMAIN" in error_str.upper():
                key = f"{server_ip}:{hostname}"
                self._nxdomain_counts[key] = self._nxdomain_counts.get(key, 0) + 1
            return DNSQueryResult(
                hostname=hostname, record_type=record_type, server_ip=server_ip,
                values=[], latency_ms=round(elapsed, 2), success=False,
                error=error_str,
            )

    async def check_server_health(self, server_ip: str) -> dict:
        """Quick health check: resolve a well-known hostname to verify the server responds."""
        result = await self.query_hostname(_HEALTH_CHECK_HOSTNAME, "A", server_ip)
        return {
            "server_ip": server_ip,
            "healthy": result.success,
            "latency_ms": result.latency_ms,
            "error": result.error,
        }

    def detect_drift(
        self, watched: DNSWatchedHostname, result: DNSQueryResult
    ) -> list[dict]:
        """Compare resolved values against expected values. Returns drift events."""
        if not watched.expected_values or not result.success:
            return []

        drifts = []
        resolved_set = set(result.values)
        expected_set = set(watched.expected_values)

        if resolved_set != expected_set:
            for expected in expected_set - resolved_set:
                drifts.append({
                    "entity_type": "dns",
                    "entity_id": f"{result.server_ip}:{watched.hostname}",
                    "drift_type": "dns_record_mismatch",
                    "field": f"{watched.hostname}/{watched.record_type.value}",
                    "expected": expected,
                    "actual": ", ".join(sorted(resolved_set)) or "(missing)",
                    "severity": "critical" if watched.critical else "warning",
                })
            for extra in resolved_set - expected_set:
                drifts.append({
                    "entity_type": "dns",
                    "entity_id": f"{result.server_ip}:{watched.hostname}",
                    "drift_type": "dns_record_unexpected",
                    "field": f"{watched.hostname}/{watched.record_type.value}",
                    "expected": ", ".join(sorted(expected_set)),
                    "actual": extra,
                    "severity": "warning",
                })
        return drifts

    async def run_pass(self) -> list[DNSQueryResult]:
        """Execute one full DNS monitoring pass: health checks + hostname queries."""
        if not self.config.enabled:
            return []

        results: list[DNSQueryResult] = []

        # 1. Server health checks
        for server in self.config.servers:
            if not server.enabled:
                continue
            health = await self.check_server_health(server.ip)
            if self.metrics:
                await self.metrics.write_dns_metric(
                    server_id=server.id, server_ip=server.ip,
                    hostname=_HEALTH_CHECK_HOSTNAME,
                    record_type="A",
                    latency_ms=health["latency_ms"],
                    success=health["healthy"],
                    metric_type="server_health",
                )

        # 2. Watched hostname queries (against each server)
        for watched in self.config.watched_hostnames:
            for server in self.config.servers:
                if not server.enabled:
                    continue
                result = await self.query_hostname(
                    watched.hostname, watched.record_type.value, server.ip,
                )
                results.append(result)

                if self.metrics:
                    await self.metrics.write_dns_metric(
                        server_id=server.id, server_ip=server.ip,
                        hostname=watched.hostname,
                        record_type=watched.record_type.value,
                        latency_ms=result.latency_ms,
                        success=result.success,
                        metric_type="query",
                    )

        return results

    def get_nxdomain_counts(self) -> dict[str, int]:
        """Return accumulated NXDOMAIN counts per server:hostname key."""
        return dict(self._nxdomain_counts)

    def reset_nxdomain_counts(self) -> None:
        self._nxdomain_counts.clear()
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_dns_monitor.py -v`
Expected: All 12 tests PASS

**Step 6: Commit**

```bash
git add backend/src/network/dns_monitor.py backend/src/network/models.py backend/tests/test_dns_monitor.py
git commit -m "feat(dns): add DNSMonitor core with query timing, health checks, and drift detection"
```

---

### Task 2: MetricsStore — DNS Metric Write and Query Methods

**Files:**
- Modify: `backend/src/network/metrics_store.py` (add `write_dns_metric` and `query_dns_metrics`)
- Test: `backend/tests/test_dns_metrics.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_dns_metrics.py`:

```python
"""Tests for DNS metric write/query methods in MetricsStore."""
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock influxdb_client before importing
if "influxdb_client" not in sys.modules:
    _mock_influx = types.ModuleType("influxdb_client")
    _mock_influx.Point = MagicMock()
    _mock_influx.WritePrecision = MagicMock()
    _mock_async = types.ModuleType("influxdb_client.client")
    _mock_async_mod = types.ModuleType("influxdb_client.client.influxdb_client_async")
    _mock_async_mod.InfluxDBClientAsync = MagicMock()
    sys.modules["influxdb_client"] = _mock_influx
    sys.modules["influxdb_client.client"] = _mock_async
    sys.modules["influxdb_client.client.influxdb_client_async"] = _mock_async_mod

from src.network.metrics_store import MetricsStore


@pytest.fixture
def store():
    with patch.object(MetricsStore, "__init__", lambda self, *a, **kw: None):
        s = MetricsStore.__new__(MetricsStore)
        s.org = "test-org"
        s.bucket = "test-bucket"
        s._write_api = AsyncMock()
        s._query_api = AsyncMock()
        s._client = AsyncMock()
        return s


class TestWriteDNSMetric:
    @pytest.mark.asyncio
    async def test_write_dns_metric_success(self, store):
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="api.example.com", record_type="A",
            latency_ms=12.5, success=True, metric_type="query",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_dns_metric_failure(self, store):
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="bad.example.com", record_type="A",
            latency_ms=0.0, success=False, metric_type="query",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_dns_metric_server_health(self, store):
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="google.com", record_type="A",
            latency_ms=3.2, success=True, metric_type="server_health",
        )
        store._write_api.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_dns_metric_handles_influx_error(self, store):
        store._write_api.write.side_effect = Exception("connection refused")
        # Should not raise
        await store.write_dns_metric(
            server_id="dns-1", server_ip="8.8.8.8",
            hostname="api.example.com", record_type="A",
            latency_ms=5.0, success=True, metric_type="query",
        )


class TestQueryDNSMetrics:
    @pytest.mark.asyncio
    async def test_query_dns_metrics_returns_data(self, store):
        mock_record = MagicMock()
        mock_record.get_time.return_value = MagicMock(isoformat=lambda: "2026-03-06T12:00:00Z")
        mock_record.get_value.return_value = 12.5
        mock_record.values = {"hostname": "api.example.com", "server_id": "dns-1"}
        mock_table = MagicMock()
        mock_table.records = [mock_record]
        store._query_api.query = AsyncMock(return_value=[mock_table])

        data = await store.query_dns_metrics(
            server_id="dns-1", hostname="api.example.com", range_str="1h",
        )
        assert len(data) == 1
        assert data[0]["value"] == 12.5

    @pytest.mark.asyncio
    async def test_query_dns_metrics_empty(self, store):
        store._query_api.query = AsyncMock(return_value=[])
        data = await store.query_dns_metrics(server_id="dns-1", range_str="1h")
        assert data == []

    @pytest.mark.asyncio
    async def test_query_dns_metrics_handles_error(self, store):
        store._query_api.query = AsyncMock(side_effect=Exception("timeout"))
        data = await store.query_dns_metrics(server_id="dns-1", range_str="1h")
        assert data == []
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_dns_metrics.py -v`
Expected: FAIL (methods not found)

**Step 3: Add `write_dns_metric` and `query_dns_metrics` to MetricsStore**

In `backend/src/network/metrics_store.py`, add after the `write_alert_event` method (~line 120):

```python
    async def write_dns_metric(
        self, server_id: str, server_ip: str, hostname: str,
        record_type: str, latency_ms: float, success: bool,
        metric_type: str = "query",
    ) -> None:
        point = (
            Point("dns_health")
            .tag("server_id", server_id)
            .tag("server_ip", server_ip)
            .tag("hostname", hostname)
            .tag("record_type", record_type)
            .tag("metric_type", metric_type)
            .field("latency_ms", float(latency_ms))
            .field("success", 1 if success else 0)
            .time(datetime.now(timezone.utc), WritePrecision.S)
        )
        await self._safe_write(point)
```

Add after the `query_protocol_breakdown` method (~line 247):

```python
    async def query_dns_metrics(
        self, server_id: str = "", hostname: str = "",
        range_str: str = "1h", resolution: str = "30s",
    ) -> list[dict]:
        range_str = self._validate_duration(range_str)
        resolution = self._validate_duration(resolution)
        filters = ['r._measurement == "dns_health"']
        if server_id:
            server_id = self._validate_id(server_id)
            filters.append(f'r.server_id == "{server_id}"')
        if hostname:
            filters.append(f'r.hostname == "{hostname}"')
        filter_expr = " and ".join(filters)
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{range_str})
          |> filter(fn: (r) => {filter_expr})
          |> filter(fn: (r) => r._field == "latency_ms")
          |> aggregateWindow(every: {resolution}, fn: mean, createEmpty: false)
          |> yield(name: "mean")
        '''
        try:
            tables = await self._query_api.query(query)
            return [
                {
                    "time": r.get_time().isoformat(),
                    "value": r.get_value(),
                    "hostname": r.values.get("hostname", ""),
                    "server_id": r.values.get("server_id", ""),
                }
                for table in tables for r in table.records
            ]
        except Exception as e:
            logger.warning("InfluxDB DNS query failed: %s", e)
            return []
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_dns_metrics.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/src/network/metrics_store.py backend/tests/test_dns_metrics.py
git commit -m "feat(dns): add DNS metric write and query methods to MetricsStore"
```

---

### Task 3: Monitor Integration — Wire DNS Pass into Collection Cycle

**Files:**
- Modify: `backend/src/network/monitor.py` (add `_dns_pass`, init `DNSMonitor`)
- Modify: `backend/src/network/alert_engine.py` (add DNS alert rules)
- Test: `backend/tests/test_dns_integration.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_dns_integration.py`:

```python
"""Tests for DNS integration into NetworkMonitor and AlertEngine."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.adapters.registry import AdapterRegistry
from src.network.monitor import NetworkMonitor
from src.network.models import (
    DNSServerConfig, DNSWatchedHostname, DNSMonitorConfig, DNSRecordType,
)
from src.network.alert_engine import AlertEngine, DEFAULT_RULES


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
def dns_config():
    return DNSMonitorConfig(
        servers=[DNSServerConfig(id="dns-1", name="Primary", ip="8.8.8.8")],
        watched_hostnames=[
            DNSWatchedHostname(
                hostname="api.example.com",
                record_type=DNSRecordType.A,
                expected_values=["10.0.0.1"],
                critical=True,
            ),
        ],
    )


class TestDNSPassIntegration:
    @pytest.mark.asyncio
    async def test_monitor_creates_dns_monitor(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        assert monitor.dns_monitor is not None
        assert monitor.dns_monitor.config.enabled

    @pytest.mark.asyncio
    async def test_monitor_dns_pass_runs(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.run_pass = AsyncMock(return_value=[])
        monitor.dns_monitor.detect_drift = MagicMock(return_value=[])
        monitor.dns_monitor.config = dns_config

        await monitor._dns_pass()
        monitor.dns_monitor.run_pass.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_dns_pass_stores_drift(self, store, kg, adapters, dns_config):
        from src.network.dns_monitor import DNSQueryResult
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)

        mock_result = DNSQueryResult(
            hostname="api.example.com", record_type="A",
            server_ip="8.8.8.8", values=["10.0.0.2"],
            latency_ms=5.0, success=True,
        )
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.run_pass = AsyncMock(return_value=[mock_result])
        monitor.dns_monitor.config = dns_config
        monitor.dns_monitor.detect_drift = MagicMock(return_value=[{
            "entity_type": "dns",
            "entity_id": "8.8.8.8:api.example.com",
            "drift_type": "dns_record_mismatch",
            "field": "api.example.com/A",
            "expected": "10.0.0.1",
            "actual": "10.0.0.2",
            "severity": "critical",
        }])

        await monitor._dns_pass()
        drifts = store.list_active_drift_events()
        assert len(drifts) == 1
        assert drifts[0]["drift_type"] == "dns_record_mismatch"

    @pytest.mark.asyncio
    async def test_monitor_without_dns_config(self, store, kg, adapters):
        monitor = NetworkMonitor(store, kg, adapters)
        assert monitor.dns_monitor is None
        # Should not raise
        await monitor._dns_pass()

    @pytest.mark.asyncio
    async def test_collect_cycle_includes_dns(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.run_pass = AsyncMock(return_value=[])
        monitor.dns_monitor.config = dns_config
        monitor.dns_monitor.detect_drift = MagicMock(return_value=[])

        with patch("src.network.monitor.async_ping", new_callable=AsyncMock):
            await monitor._collect_cycle()

        monitor.dns_monitor.run_pass.assert_called_once()


class TestDNSAlertRules:
    def test_default_rules_include_dns(self):
        dns_rules = [r for r in DEFAULT_RULES if r.id.startswith("default-dns")]
        assert len(dns_rules) >= 2  # At least failure + latency rules

    def test_dns_resolution_failure_rule(self):
        rule = next((r for r in DEFAULT_RULES if r.id == "default-dns-failure"), None)
        assert rule is not None
        assert rule.severity == "critical"
        assert rule.metric == "dns_success"
        assert rule.condition == "lt"

    def test_dns_latency_rule(self):
        rule = next((r for r in DEFAULT_RULES if r.id == "default-dns-latency"), None)
        assert rule is not None
        assert rule.severity == "warning"
        assert rule.metric == "dns_latency_ms"
        assert rule.condition == "gt"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_dns_integration.py -v`
Expected: FAIL

**Step 3: Add DNS alert rules to `alert_engine.py`**

In `backend/src/network/alert_engine.py`, add two rules to the end of the `DEFAULT_RULES` list:

```python
    AlertRule(
        id="default-dns-failure", name="DNS Resolution Failure",
        severity="critical", entity_type="device", entity_filter="*",
        metric="dns_success", condition="lt", threshold=1.0,
        duration_seconds=60, cooldown_seconds=300,
        description="DNS resolution failing for a watched hostname",
    ),
    AlertRule(
        id="default-dns-latency", name="DNS High Latency",
        severity="warning", entity_type="device", entity_filter="*",
        metric="dns_latency_ms", condition="gt", threshold=500.0,
        duration_seconds=120, cooldown_seconds=600,
        description="DNS query latency exceeds 500ms",
    ),
```

**Step 4: Wire `_dns_pass()` into `monitor.py`**

In `backend/src/network/monitor.py`:

1. Add import at top:
```python
from .dns_monitor import DNSMonitor
from .models import DNSMonitorConfig
```

2. Add `dns_config` parameter to `__init__`:
```python
def __init__(self, store: TopologyStore, kg, adapters,
             prometheus_url: str | None = None, metrics_store=None,
             dns_config: DNSMonitorConfig | None = None):
```

3. Add initialization after `self._latest_alerts`:
```python
        self.dns_monitor: DNSMonitor | None = None
        if dns_config and dns_config.enabled:
            self.dns_monitor = DNSMonitor(dns_config, metrics_store)
```

4. Add `_dns_pass()` call to `_collect_cycle()` (after `_snmp_pass`, before `_alert_pass`):
```python
    async def _collect_cycle(self):
        await self._probe_pass()
        await self._adapter_pass()
        await self._drift_pass()
        await self._discovery_pass()
        await self._snmp_pass()
        await self._dns_pass()
        await self._alert_pass()
        self.store.prune_metric_history(older_than_days=7)
```

5. Add the `_dns_pass` method:
```python
    async def _dns_pass(self):
        if not self.dns_monitor:
            return
        try:
            results = await self.dns_monitor.run_pass()
            # Check for drift on watched hostnames with expected values
            for watched in self.dns_monitor.config.watched_hostnames:
                matching = [r for r in results
                            if r.hostname == watched.hostname
                            and r.record_type == watched.record_type.value]
                for result in matching:
                    drifts = self.dns_monitor.detect_drift(watched, result)
                    for event in drifts:
                        self.store.upsert_drift_event(
                            event["entity_type"], event["entity_id"],
                            event["drift_type"], event["field"],
                            event["expected"], event["actual"],
                            event["severity"],
                        )
        except Exception as e:
            logger.debug("DNS pass failed: %s", e)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_dns_integration.py -v`
Expected: All 8 tests PASS

**Step 6: Commit**

```bash
git add backend/src/network/monitor.py backend/src/network/alert_engine.py backend/tests/test_dns_integration.py
git commit -m "feat(dns): integrate DNS pass into monitor cycle and add DNS alert rules"
```

---

### Task 4: DNS API Endpoints

**Files:**
- Create: `backend/src/api/dns_endpoints.py`
- Modify: `backend/src/api/main.py` (register router)
- Test: `backend/tests/test_dns_endpoints.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_dns_endpoints.py`:

```python
"""Tests for DNS monitoring API endpoints."""
import sys
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock influxdb_client before importing
if "influxdb_client" not in sys.modules:
    _mock_influx = types.ModuleType("influxdb_client")
    _mock_influx.Point = MagicMock()
    _mock_influx.WritePrecision = MagicMock()
    _mock_async = types.ModuleType("influxdb_client.client")
    _mock_async_mod = types.ModuleType("influxdb_client.client.influxdb_client_async")
    _mock_async_mod.InfluxDBClientAsync = MagicMock()
    sys.modules["influxdb_client"] = _mock_influx
    sys.modules["influxdb_client.client"] = _mock_async
    sys.modules["influxdb_client.client.influxdb_client_async"] = _mock_async_mod

from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestDNSConfigEndpoints:
    def test_get_dns_config(self, client):
        resp = client.get("/api/v4/dns/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "servers" in data
        assert "watched_hostnames" in data
        assert "enabled" in data

    def test_update_dns_config(self, client):
        config = {
            "servers": [{"id": "dns-1", "name": "Google", "ip": "8.8.8.8"}],
            "watched_hostnames": [
                {"hostname": "api.example.com", "record_type": "A",
                 "expected_values": ["10.0.0.1"], "critical": True},
            ],
            "query_timeout": 5.0,
            "enabled": True,
        }
        resp = client.put("/api/v4/dns/config", json=config)
        assert resp.status_code == 200
        data = resp.json()
        assert data["servers"][0]["ip"] == "8.8.8.8"

    def test_add_dns_server(self, client):
        server = {"id": "dns-new", "name": "Cloudflare", "ip": "1.1.1.1"}
        resp = client.post("/api/v4/dns/servers", json=server)
        assert resp.status_code == 200

    def test_remove_dns_server(self, client):
        # First add, then remove
        server = {"id": "dns-del", "name": "ToDelete", "ip": "9.9.9.9"}
        client.post("/api/v4/dns/servers", json=server)
        resp = client.delete("/api/v4/dns/servers/dns-del")
        assert resp.status_code == 200

    def test_add_watched_hostname(self, client):
        hostname = {"hostname": "new.example.com", "record_type": "A", "critical": False}
        resp = client.post("/api/v4/dns/hostnames", json=hostname)
        assert resp.status_code == 200

    def test_remove_watched_hostname(self, client):
        hostname = {"hostname": "remove.example.com", "record_type": "A"}
        client.post("/api/v4/dns/hostnames", json=hostname)
        resp = client.delete("/api/v4/dns/hostnames/remove.example.com")
        assert resp.status_code == 200


class TestDNSQueryEndpoints:
    def test_query_dns_now(self, client):
        resp = client.post("/api/v4/dns/query", json={
            "hostname": "example.com", "record_type": "A", "server_ip": "8.8.8.8",
        })
        # May fail if no real DNS, but endpoint should exist and return 200 or structured error
        assert resp.status_code in (200, 500)

    def test_get_dns_metrics(self, client):
        resp = client.get("/api/v4/dns/metrics", params={"range": "1h"})
        assert resp.status_code == 200

    def test_get_dns_nxdomain_counts(self, client):
        resp = client.get("/api/v4/dns/nxdomain")
        assert resp.status_code == 200
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_dns_endpoints.py -v`
Expected: FAIL (404s — endpoints don't exist)

**Step 3: Implement DNS endpoints**

Create `backend/src/api/dns_endpoints.py`:

```python
"""DNS monitoring API endpoints."""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from ..network.models import (
    DNSServerConfig, DNSWatchedHostname, DNSMonitorConfig, DNSRecordType,
)
from ..network.dns_monitor import DNSMonitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v4/dns", tags=["dns"])

# Module-level state — the monitor instance sets this at startup
_dns_config = DNSMonitorConfig()
_dns_monitor: DNSMonitor | None = None
_metrics_store = None


def init_dns_endpoints(dns_monitor: DNSMonitor | None, metrics_store=None) -> None:
    """Called at app startup to wire in the live DNSMonitor instance."""
    global _dns_monitor, _dns_config, _metrics_store
    _dns_monitor = dns_monitor
    if dns_monitor:
        _dns_config = dns_monitor.config
    _metrics_store = metrics_store


# ── Config CRUD ──────────────────────────────────────────────────────

@router.get("/config")
async def get_dns_config():
    return _dns_config.model_dump()


@router.put("/config")
async def update_dns_config(config: DNSMonitorConfig):
    global _dns_config, _dns_monitor
    _dns_config = config
    _dns_monitor = DNSMonitor(config, _metrics_store)
    return _dns_config.model_dump()


@router.post("/servers")
async def add_dns_server(server: DNSServerConfig):
    _dns_config.servers.append(server)
    return {"status": "ok", "server_count": len(_dns_config.servers)}


@router.delete("/servers/{server_id}")
async def remove_dns_server(server_id: str):
    _dns_config.servers = [s for s in _dns_config.servers if s.id != server_id]
    return {"status": "ok", "server_count": len(_dns_config.servers)}


@router.post("/hostnames")
async def add_watched_hostname(hostname: DNSWatchedHostname):
    _dns_config.watched_hostnames.append(hostname)
    return {"status": "ok", "hostname_count": len(_dns_config.watched_hostnames)}


@router.delete("/hostnames/{hostname}")
async def remove_watched_hostname(hostname: str):
    _dns_config.watched_hostnames = [
        h for h in _dns_config.watched_hostnames if h.hostname != hostname
    ]
    return {"status": "ok", "hostname_count": len(_dns_config.watched_hostnames)}


# ── Query & Metrics ──────────────────────────────────────────────────

@router.post("/query")
async def query_dns_now(body: dict):
    hostname = body.get("hostname", "")
    record_type = body.get("record_type", "A")
    server_ip = body.get("server_ip", "8.8.8.8")
    if not _dns_monitor:
        monitor = DNSMonitor(DNSMonitorConfig())
    else:
        monitor = _dns_monitor
    result = await monitor.query_hostname(hostname, record_type, server_ip)
    return {
        "hostname": result.hostname,
        "record_type": result.record_type,
        "server_ip": result.server_ip,
        "values": result.values,
        "latency_ms": result.latency_ms,
        "success": result.success,
        "error": result.error,
    }


@router.get("/metrics")
async def get_dns_metrics(range: str = "1h", server_id: str = "", hostname: str = ""):
    if not _metrics_store:
        return []
    return await _metrics_store.query_dns_metrics(
        server_id=server_id, hostname=hostname, range_str=range,
    )


@router.get("/nxdomain")
async def get_nxdomain_counts():
    if not _dns_monitor:
        return {}
    return _dns_monitor.get_nxdomain_counts()
```

**Step 4: Register router in `main.py`**

In `backend/src/api/main.py`, add the import and include:

```python
from .dns_endpoints import router as dns_router
app.include_router(dns_router)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_dns_endpoints.py -v`
Expected: All 9 tests PASS

**Step 6: Commit**

```bash
git add backend/src/api/dns_endpoints.py backend/src/api/main.py backend/tests/test_dns_endpoints.py
git commit -m "feat(dns): add DNS monitoring API endpoints"
```

---

### Task 5: DNS Snapshot Integration

**Files:**
- Modify: `backend/src/network/monitor.py` (add DNS data to snapshot)
- Modify: `backend/tests/test_dns_integration.py` (add snapshot test)

**Step 1: Write the failing test**

Add to `backend/tests/test_dns_integration.py`:

```python
class TestDNSSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_includes_dns(self, store, kg, adapters, dns_config):
        monitor = NetworkMonitor(store, kg, adapters, dns_config=dns_config)
        monitor.dns_monitor = MagicMock()
        monitor.dns_monitor.get_nxdomain_counts.return_value = {"8.8.8.8:bad.com": 5}
        monitor.dns_monitor.config = dns_config

        snapshot = monitor.get_snapshot()
        assert "dns" in snapshot
        assert "nxdomain_counts" in snapshot["dns"]
        assert "servers" in snapshot["dns"]

    @pytest.mark.asyncio
    async def test_snapshot_without_dns(self, store, kg, adapters):
        monitor = NetworkMonitor(store, kg, adapters)
        snapshot = monitor.get_snapshot()
        assert "dns" in snapshot
        assert snapshot["dns"]["servers"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_dns_integration.py::TestDNSSnapshot -v`
Expected: FAIL

**Step 3: Add DNS data to `get_snapshot()`**

In `backend/src/network/monitor.py`, update `get_snapshot()`:

```python
    def get_snapshot(self) -> dict:
        dns_data = {
            "servers": [],
            "nxdomain_counts": {},
            "enabled": False,
        }
        if self.dns_monitor:
            dns_data = {
                "servers": [s.model_dump() for s in self.dns_monitor.config.servers],
                "nxdomain_counts": self.dns_monitor.get_nxdomain_counts(),
                "enabled": self.dns_monitor.config.enabled,
            }
        return {
            "devices": self.store.list_device_statuses(),
            "links": self.store.list_link_metrics(),
            "drifts": self.store.list_active_drift_events(),
            "candidates": self.store.list_discovery_candidates(),
            "alerts": self.alert_engine.get_active_alerts() if self.alert_engine else [],
            "dns": dns_data,
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_dns_integration.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/network/monitor.py backend/tests/test_dns_integration.py
git commit -m "feat(dns): include DNS data in monitor snapshot"
```

---

### Task 6: Final Verification — All Tests Pass

**Files:** None (verification only)

**Step 1: Run all tests**

```bash
cd backend && python3 -m pytest tests/ -v --tb=short
```

Expected: All tests pass (existing + new DNS tests)

**Step 2: Verify no import errors**

```bash
cd backend && python3 -c "from src.network.dns_monitor import DNSMonitor; print('OK')"
cd backend && python3 -c "from src.api.dns_endpoints import router; print('OK')"
```

**Step 3: Verify DNS alert rules loaded**

```bash
cd backend && python3 -c "
from src.network.alert_engine import DEFAULT_RULES
dns_rules = [r for r in DEFAULT_RULES if 'dns' in r.id]
for r in dns_rules:
    print(f'{r.id}: {r.name} ({r.severity})')
assert len(dns_rules) >= 2, 'Expected at least 2 DNS alert rules'
print('OK')
"
```

**Step 4: Commit (if any fixes needed)**

```bash
git add -A && git commit -m "fix: final adjustments for DNS monitoring phase 3"
```
