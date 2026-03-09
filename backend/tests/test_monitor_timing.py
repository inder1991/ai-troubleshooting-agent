"""Tests for per-pass timing in NetworkMonitor."""

import asyncio
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.network.monitor import NetworkMonitor


@pytest.fixture
def monitor(tmp_path):
    """Create a NetworkMonitor with mocked dependencies, patching InstanceStore to use tmp_path."""
    from src.network.topology_store import TopologyStore
    from src.network.knowledge_graph import NetworkKnowledgeGraph
    from src.network.adapters.registry import AdapterRegistry

    store = TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))
    kg = NetworkKnowledgeGraph(store)
    adapters = AdapterRegistry()

    # Patch InstanceStore to use a temp database so it doesn't fail on missing data dir
    instance_db = os.path.join(str(tmp_path), "instance.db")
    with patch("src.network.monitor.InstanceStore", lambda: __import__('src.network.collectors.instance_store', fromlist=['InstanceStore']).InstanceStore(db_path=instance_db)):
        m = NetworkMonitor(store=store, kg=kg, adapters=adapters)
    return m


class TestMonitorTiming:
    def test_initial_stats(self, monitor):
        """Before any pass, stats should show zero pass_count and 0.0 duration."""
        stats = monitor.get_stats()
        assert stats["pass_count"] == 0
        assert stats["last_pass_duration_s"] == 0.0

    def test_get_stats_structure(self, monitor):
        """get_stats should return a dict with pass_count and last_pass_duration_s."""
        stats = monitor.get_stats()
        assert "pass_count" in stats
        assert "last_pass_duration_s" in stats
        assert isinstance(stats["pass_count"], int)
        assert isinstance(stats["last_pass_duration_s"], float)

    @pytest.mark.asyncio
    async def test_pass_count_increments(self, monitor):
        """After running one collect cycle via _run_loop, pass_count should increment."""
        monitor._collect_cycle = AsyncMock()

        call_count = 0

        async def fake_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                await monitor._run_loop()
            except asyncio.CancelledError:
                pass

        stats = monitor.get_stats()
        assert stats["pass_count"] == 1
        assert stats["last_pass_duration_s"] >= 0.0

    @pytest.mark.asyncio
    async def test_pass_count_increments_multiple(self, monitor):
        """After 3 cycles, pass_count should be 3."""
        monitor._collect_cycle = AsyncMock()

        call_count = 0

        async def fake_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                await monitor._run_loop()
            except asyncio.CancelledError:
                pass

        stats = monitor.get_stats()
        assert stats["pass_count"] == 3

    @pytest.mark.asyncio
    async def test_pass_duration_positive(self, monitor):
        """Pass duration should be a positive float after a cycle."""
        import time

        async def slow_cycle():
            # Use time.sleep to avoid being caught by asyncio.sleep patch
            time.sleep(0.02)

        monitor._collect_cycle = slow_cycle

        call_count = 0

        async def fake_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                await monitor._run_loop()
            except asyncio.CancelledError:
                pass

        stats = monitor.get_stats()
        assert stats["last_pass_duration_s"] >= 0.01

    @pytest.mark.asyncio
    async def test_timing_survives_cycle_error(self, monitor):
        """Pass count and timing should still update even if _collect_cycle raises."""
        monitor._collect_cycle = AsyncMock(side_effect=RuntimeError("boom"))

        call_count = 0

        async def fake_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                raise asyncio.CancelledError()

        with patch("asyncio.sleep", side_effect=fake_sleep):
            try:
                await monitor._run_loop()
            except asyncio.CancelledError:
                pass

        stats = monitor.get_stats()
        assert stats["pass_count"] == 1
        assert stats["last_pass_duration_s"] >= 0.0
