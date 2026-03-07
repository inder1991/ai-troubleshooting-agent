"""Tests for concurrent execution of NetworkMonitor passes and DNS queries.

Verifies that:
  1. probe/adapter/drift/discovery/snmp/dns passes run concurrently (not sequentially)
  2. alert pass runs AFTER all others complete
  3. a single pass failure doesn't crash the whole cycle
  4. multiple adapters are queried concurrently in _adapter_pass()
  5. DNS servers are queried concurrently in dns_monitor.run_pass()
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.adapters.registry import AdapterRegistry
from src.network.monitor import NetworkMonitor
from src.network.dns_monitor import DNSMonitor
from src.network.models import (
    DNSMonitorConfig,
    DNSRecordType,
    DNSServerConfig,
    DNSWatchedHostname,
)


# ── Fixtures ──

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


# ── Helpers ──

def _make_slow_coro(name: str, duration: float, call_log: list[tuple[str, float]]):
    """Return an async function that sleeps *duration* seconds and logs start/end."""
    async def _coro(*args, **kwargs):
        t0 = time.monotonic()
        call_log.append((f"{name}_start", t0))
        await asyncio.sleep(duration)
        call_log.append((f"{name}_end", time.monotonic()))
    return _coro


# ═══════════════════════════════════════════════════════════════════
# 1. Passes run concurrently (not sequentially)
# ═══════════════════════════════════════════════════════════════════

class TestCollectCycleConcurrency:
    """The six data-collection passes must overlap in time, proving gather."""

    @pytest.mark.asyncio
    async def test_passes_run_concurrently(self, monitor):
        """If 6 passes each take 0.1 s, total wall-time should be ~0.1 s (not ~0.6 s)."""
        call_log: list[tuple[str, float]] = []
        DELAY = 0.1

        monitor._probe_pass = AsyncMock(side_effect=_make_slow_coro("probe", DELAY, call_log))
        monitor._adapter_pass = AsyncMock(side_effect=_make_slow_coro("adapter", DELAY, call_log))
        monitor._drift_pass = AsyncMock(side_effect=_make_slow_coro("drift", DELAY, call_log))
        monitor._discovery_pass = AsyncMock(side_effect=_make_slow_coro("discovery", DELAY, call_log))
        monitor._snmp_pass = AsyncMock(side_effect=_make_slow_coro("snmp", DELAY, call_log))
        monitor._dns_pass = AsyncMock(side_effect=_make_slow_coro("dns", DELAY, call_log))
        monitor._alert_pass = AsyncMock()
        monitor.store.prune_metric_history = MagicMock()

        t0 = time.monotonic()
        await monitor._collect_cycle()
        elapsed = time.monotonic() - t0

        # Concurrent: ~0.1 s.  Sequential would be >= 0.6 s.
        assert elapsed < 0.35, f"Passes appear sequential; elapsed={elapsed:.3f}s"


# ═══════════════════════════════════════════════════════════════════
# 2. alert_pass runs AFTER all data passes
# ═══════════════════════════════════════════════════════════════════

class TestAlertPassOrdering:
    @pytest.mark.asyncio
    async def test_alert_pass_runs_after_data_passes(self, monitor):
        """_alert_pass must start only after all 6 data passes have finished."""
        order: list[str] = []

        def _make_pass_fn(name):
            async def _pass():
                order.append(f"{name}_start")
                await asyncio.sleep(0.05)
                order.append(f"{name}_end")
            return _pass

        # Directly replace methods with plain async functions (not AsyncMock)
        # so _collect_cycle's gather receives real coroutines.
        monitor._probe_pass = _make_pass_fn("probe")
        monitor._adapter_pass = _make_pass_fn("adapter")
        monitor._drift_pass = _make_pass_fn("drift")
        monitor._discovery_pass = _make_pass_fn("discovery")
        monitor._snmp_pass = _make_pass_fn("snmp")
        monitor._dns_pass = _make_pass_fn("dns")

        async def _alert():
            order.append("alert_start")

        monitor._alert_pass = _alert
        monitor.store.prune_metric_history = MagicMock()

        await monitor._collect_cycle()

        # All data passes must end BEFORE alert starts
        alert_idx = order.index("alert_start")
        for name in ("probe", "adapter", "drift", "discovery", "snmp", "dns"):
            end_tag = f"{name}_end"
            assert end_tag in order, f"{end_tag} not logged"
            assert order.index(end_tag) < alert_idx, (
                f"{end_tag} happened after alert_start; order={order}"
            )


# ═══════════════════════════════════════════════════════════════════
# 3. Single pass failure doesn't crash the cycle
# ═══════════════════════════════════════════════════════════════════

class TestPassFailureIsolation:
    @pytest.mark.asyncio
    async def test_one_pass_exception_does_not_crash_cycle(self, monitor):
        """If _drift_pass raises, the cycle still completes and _alert_pass runs."""
        monitor._probe_pass = AsyncMock()
        monitor._adapter_pass = AsyncMock()
        monitor._drift_pass = AsyncMock(side_effect=RuntimeError("drift boom"))
        monitor._discovery_pass = AsyncMock()
        monitor._snmp_pass = AsyncMock()
        monitor._dns_pass = AsyncMock()
        monitor._alert_pass = AsyncMock()
        monitor.store.prune_metric_history = MagicMock()

        # Should NOT raise
        await monitor._collect_cycle()

        # alert_pass must still be called
        monitor._alert_pass.assert_awaited_once()
        # prune must still run
        monitor.store.prune_metric_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_pass_failures_still_complete(self, monitor):
        """Even if several passes fail, alert and prune still execute."""
        monitor._probe_pass = AsyncMock(side_effect=RuntimeError("probe boom"))
        monitor._adapter_pass = AsyncMock(side_effect=RuntimeError("adapter boom"))
        monitor._drift_pass = AsyncMock()
        monitor._discovery_pass = AsyncMock(side_effect=RuntimeError("disco boom"))
        monitor._snmp_pass = AsyncMock()
        monitor._dns_pass = AsyncMock(side_effect=RuntimeError("dns boom"))
        monitor._alert_pass = AsyncMock()
        monitor.store.prune_metric_history = MagicMock()

        await monitor._collect_cycle()

        monitor._alert_pass.assert_awaited_once()
        monitor.store.prune_metric_history.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# 4. Multiple adapters queried concurrently in _adapter_pass()
# ═══════════════════════════════════════════════════════════════════

class TestAdapterPassConcurrency:
    @pytest.mark.asyncio
    async def test_adapters_run_concurrently(self, store, kg):
        """Three adapters each taking 0.1 s should finish in ~0.1 s total."""
        call_log: list[tuple[str, float]] = []
        DELAY = 0.1

        reg = AdapterRegistry()
        for i in range(3):
            adapter = MagicMock()

            async def _slow_get_interfaces(_i=i):
                call_log.append((f"adapter_{_i}_start", time.monotonic()))
                await asyncio.sleep(DELAY)
                call_log.append((f"adapter_{_i}_end", time.monotonic()))
                return []

            adapter.get_interfaces = _slow_get_interfaces
            adapter.vendor = MagicMock()
            adapter.vendor.value = "mock"
            reg.register(f"inst_{i}", adapter)

        mon = NetworkMonitor(store, kg, reg)

        t0 = time.monotonic()
        await mon._adapter_pass()
        elapsed = time.monotonic() - t0

        assert elapsed < 0.25, f"Adapters appear sequential; elapsed={elapsed:.3f}s"
        # All three must have started
        starts = [e for e in call_log if "start" in e[0]]
        assert len(starts) == 3


# ═══════════════════════════════════════════════════════════════════
# 5. DNS servers queried concurrently in dns_monitor.run_pass()
# ═══════════════════════════════════════════════════════════════════

class TestDNSMonitorConcurrency:
    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_dns_servers_queried_concurrently(self, mock_resolve):
        """Three DNS servers each taking 0.1 s should complete in ~0.1 s, not ~0.3 s."""
        DELAY = 0.1
        call_log: list[tuple[str, float]] = []

        servers = [
            DNSServerConfig(id=f"dns{i}", name=f"DNS {i}", ip=f"10.0.0.{50+i}")
            for i in range(3)
        ]
        watched = [
            DNSWatchedHostname(hostname="api.example.com", record_type=DNSRecordType.A),
        ]
        config = DNSMonitorConfig(servers=servers, watched_hostnames=watched, enabled=True)
        mon = DNSMonitor(config)

        async def _slow_resolve(server_ip, *args, **kwargs):
            call_log.append((f"{server_ip}_start", time.monotonic()))
            await asyncio.sleep(DELAY)
            call_log.append((f"{server_ip}_end", time.monotonic()))
            return ["10.1.1.1"]

        mock_resolve.side_effect = _slow_resolve

        t0 = time.monotonic()
        metrics = await mon.run_pass()
        elapsed = time.monotonic() - t0

        # All 3 servers × 1 hostname = 3 metrics
        assert len(metrics) == 3

        # Concurrent: ~0.1 s.  Sequential would be ~0.3 s.
        assert elapsed < 0.25, f"DNS servers queried sequentially; elapsed={elapsed:.3f}s"

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_dns_results_still_correct_after_parallel(self, mock_resolve):
        """Ensure the parallelised run_pass still returns correct metric dicts."""
        servers = [
            DNSServerConfig(id="dns1", name="DNS 1", ip="10.0.0.51"),
            DNSServerConfig(id="dns2", name="DNS 2", ip="10.0.0.52"),
        ]
        watched = [
            DNSWatchedHostname(
                hostname="api.example.com",
                record_type=DNSRecordType.A,
                expected_values=["10.1.1.1"],
                critical=True,
            ),
        ]
        config = DNSMonitorConfig(servers=servers, watched_hostnames=watched, enabled=True)
        mon = DNSMonitor(config)

        mock_resolve.return_value = ["10.1.1.1"]

        metrics = await mon.run_pass()
        assert len(metrics) == 2
        for m in metrics:
            assert m["measurement"] == "dns_query"
            assert m["hostname"] == "api.example.com"
            assert m["success"] is True
            assert m["drift"] is None
            assert m["critical"] is True

    @pytest.mark.asyncio
    @patch("src.network.dns_monitor.HAS_DNSPYTHON", True)
    @patch("src.network.dns_monitor.dns_resolver_resolve", new_callable=AsyncMock)
    async def test_dns_drift_still_detected_after_parallel(self, mock_resolve):
        """Drift detection must still work correctly in parallelised mode."""
        servers = [
            DNSServerConfig(id="dns1", name="Primary", ip="10.0.0.53"),
        ]
        watched = [
            DNSWatchedHostname(
                hostname="api.example.com",
                record_type=DNSRecordType.A,
                expected_values=["10.1.1.1"],
                critical=True,
            ),
        ]
        config = DNSMonitorConfig(servers=servers, watched_hostnames=watched, enabled=True)
        mon = DNSMonitor(config)

        # Return wrong answer to trigger drift
        mock_resolve.return_value = ["10.2.2.2"]

        metrics = await mon.run_pass()
        assert len(metrics) == 1
        m = metrics[0]
        assert m["drift"] is not None
        assert "10.1.1.1" in m["drift"]["missing"]
        assert "10.2.2.2" in m["drift"]["extra"]


# ═══════════════════════════════════════════════════════════════════
# 6. Drift pass concurrency
# ═══════════════════════════════════════════════════════════════════

class TestDriftPassConcurrency:
    @pytest.mark.asyncio
    async def test_drift_devices_checked_concurrently(self, store, kg):
        """Multiple device×adapter drift checks should run in parallel."""
        call_log: list[tuple[str, float]] = []
        DELAY = 0.1

        reg = AdapterRegistry()
        adapter = MagicMock()
        adapter.vendor = MagicMock()
        adapter.vendor.value = "mock"
        reg.register("inst_0", adapter, device_ids=["d1", "d2", "d3"])

        mon = NetworkMonitor(store, kg, reg)

        async def _slow_check(device_id, adapter):
            call_log.append((f"{device_id}_start", time.monotonic()))
            await asyncio.sleep(DELAY)
            call_log.append((f"{device_id}_end", time.monotonic()))
            return []

        mon.drift_engine.check_device = AsyncMock(side_effect=_slow_check)

        t0 = time.monotonic()
        await mon._drift_pass()
        elapsed = time.monotonic() - t0

        # 3 devices × 0.1 s each: concurrent ≈ 0.1 s, sequential ≈ 0.3 s
        assert elapsed < 0.25, f"Drift checks appear sequential; elapsed={elapsed:.3f}s"
        starts = [e for e in call_log if "start" in e[0]]
        assert len(starts) == 3
