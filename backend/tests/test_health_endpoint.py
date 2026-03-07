"""Tests for NetworkMonitor heartbeat tracking and /health endpoint."""
from __future__ import annotations

import os
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.network.topology_store import TopologyStore
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.adapters.registry import AdapterRegistry
from src.network.monitor import NetworkMonitor


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


# ═══════════════════════════════════════════════════════════════════
# 1. Initial state — properties are None before any cycle
# ═══════════════════════════════════════════════════════════════════


class TestHeartbeatInitialState:
    def test_last_cycle_at_initially_none(self, monitor):
        assert monitor.last_cycle_at is None

    def test_last_cycle_duration_initially_none(self, monitor):
        assert monitor.last_cycle_duration is None


# ═══════════════════════════════════════════════════════════════════
# 2. After _collect_cycle(), properties are populated
# ═══════════════════════════════════════════════════════════════════


class TestHeartbeatAfterCycle:
    @pytest.mark.asyncio
    async def test_collect_cycle_sets_last_cycle_at(self, monitor):
        """After a collect cycle, last_cycle_at must be set (not None)."""
        # Stub out all passes so no real I/O happens
        monitor._probe_pass = AsyncMock()
        monitor._adapter_pass = AsyncMock()
        monitor._drift_pass = AsyncMock()
        monitor._discovery_pass = AsyncMock()
        monitor._snmp_pass = AsyncMock()
        monitor._dns_pass = AsyncMock()
        monitor._alert_pass = AsyncMock()
        monitor.store.prune_metric_history = MagicMock()

        await monitor._collect_cycle()

        assert monitor.last_cycle_at is not None

    @pytest.mark.asyncio
    async def test_collect_cycle_sets_last_cycle_duration(self, monitor):
        """After a collect cycle, last_cycle_duration must be >= 0."""
        monitor._probe_pass = AsyncMock()
        monitor._adapter_pass = AsyncMock()
        monitor._drift_pass = AsyncMock()
        monitor._discovery_pass = AsyncMock()
        monitor._snmp_pass = AsyncMock()
        monitor._dns_pass = AsyncMock()
        monitor._alert_pass = AsyncMock()
        monitor.store.prune_metric_history = MagicMock()

        await monitor._collect_cycle()

        assert monitor.last_cycle_duration is not None
        assert monitor.last_cycle_duration >= 0


# ═══════════════════════════════════════════════════════════════════
# 3. health_status() thresholds
# ═══════════════════════════════════════════════════════════════════


class TestHealthStatus:
    def test_healthy_when_recent(self, monitor):
        """If last cycle was within 120 s, status is 'healthy'."""
        monitor._last_cycle_at = time.monotonic()  # just now
        assert monitor.health_status() == "healthy"

    def test_degraded_when_stale(self, monitor):
        """If last cycle was 3 minutes ago (180 s), status is 'degraded'."""
        monitor._last_cycle_at = time.monotonic() - 180
        assert monitor.health_status() == "degraded"

    def test_unhealthy_when_very_stale(self, monitor):
        """If last cycle was 10 minutes ago (600 s), status is 'unhealthy'."""
        monitor._last_cycle_at = time.monotonic() - 600
        assert monitor.health_status() == "unhealthy"

    def test_unhealthy_when_no_cycle_ever(self, monitor):
        """If no cycle has ever run, status is 'unhealthy'."""
        assert monitor.health_status() == "unhealthy"


# ═══════════════════════════════════════════════════════════════════
# 4. /health API endpoint
# ═══════════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_endpoint_returns_expected_fields(self, monitor):
        """GET /api/v4/network/monitor/health returns status, duration, interval, components."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import src.api.monitor_endpoints as ep

        # Wire the monitor into the endpoint module
        ep._monitor = monitor

        # Simulate a recent cycle
        monitor._last_cycle_at = time.monotonic()
        monitor._last_cycle_duration = 0.42

        app = FastAPI()
        app.include_router(ep.monitor_router)

        client = TestClient(app)
        resp = client.get("/api/v4/network/monitor/health")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "healthy"
        assert data["last_cycle_duration_s"] == pytest.approx(0.42)
        assert data["cycle_interval_s"] == 30
        assert isinstance(data["components"], dict)
        assert "dns_monitor" in data["components"]
        assert "alert_engine" in data["components"]
        assert "snmp_collector" in data["components"]

    @pytest.mark.asyncio
    async def test_health_endpoint_when_monitor_not_started(self):
        """If monitor hasn't been injected, return 'unavailable'."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import src.api.monitor_endpoints as ep

        ep._monitor = None

        app = FastAPI()
        app.include_router(ep.monitor_router)

        client = TestClient(app)
        resp = client.get("/api/v4/network/monitor/health")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "unavailable"
