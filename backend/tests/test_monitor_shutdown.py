"""Tests for graceful shutdown with timeout in NetworkMonitor."""

import asyncio
import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.network.monitor import NetworkMonitor


@pytest.fixture
def monitor(tmp_path):
    """Create a NetworkMonitor with mocked dependencies."""
    from src.network.topology_store import TopologyStore
    from src.network.knowledge_graph import NetworkKnowledgeGraph
    from src.network.adapters.registry import AdapterRegistry

    store = TopologyStore(db_path=os.path.join(str(tmp_path), "test.db"))
    kg = NetworkKnowledgeGraph(store)
    adapters = AdapterRegistry()

    instance_db = os.path.join(str(tmp_path), "instance.db")
    with patch("src.network.monitor.InstanceStore", lambda: __import__('src.network.collectors.instance_store', fromlist=['InstanceStore']).InstanceStore(db_path=instance_db)):
        m = NetworkMonitor(store=store, kg=kg, adapters=adapters)
    return m


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_stop_completes_normally(self, monitor):
        """stop() should complete without error when no subsystems are running."""
        await monitor.stop()
        # Should not raise

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, monitor):
        """stop() should set _running to False."""
        monitor._running = True
        await monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_stop_with_hanging_subsystem(self, monitor):
        """stop() should complete within a reasonable time even if a subsystem hangs."""
        # Create a trap_listener that hangs forever on stop
        hanging_listener = MagicMock()

        async def hang_forever():
            await asyncio.sleep(3600)  # hang for an hour

        hanging_listener.stop = hang_forever
        monitor.trap_listener = hanging_listener

        # stop() should timeout after 10s but we override the timeout for speed
        # by directly calling with a shorter timeout
        monitor._running = True

        async def fast_cleanup():
            """A cleanup that hangs."""
            await asyncio.sleep(3600)

        monitor._cleanup = fast_cleanup

        # stop() should complete within a reasonable time because of the 10s timeout
        # We override the wait_for timeout for faster testing
        original_wait_for = asyncio.wait_for

        async def fast_wait_for(coro, *, timeout):
            # Use a shorter timeout for testing
            return await original_wait_for(coro, timeout=0.1)

        with patch("src.network.monitor.asyncio.wait_for", side_effect=fast_wait_for):
            await monitor.stop()

        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task_on_timeout(self, monitor):
        """When shutdown times out, the monitor task should be force-cancelled."""
        # Start a long-running task
        async def run_forever():
            while True:
                await asyncio.sleep(0.01)

        monitor._task = asyncio.create_task(run_forever())

        # Make _cleanup hang so we hit the timeout
        async def hanging_cleanup():
            await asyncio.sleep(3600)

        monitor._cleanup = hanging_cleanup

        original_wait_for = asyncio.wait_for

        async def fast_wait_for(coro, *, timeout):
            return await original_wait_for(coro, timeout=0.1)

        with patch("src.network.monitor.asyncio.wait_for", side_effect=fast_wait_for):
            await monitor.stop()

        # Task should be cancelled/done
        assert monitor._task.done()

    @pytest.mark.asyncio
    async def test_stop_with_successful_cleanup(self, monitor):
        """When cleanup finishes within timeout, stop() should work cleanly."""
        cleanup_called = False

        async def fast_cleanup():
            nonlocal cleanup_called
            cleanup_called = True

        monitor._cleanup = fast_cleanup
        await monitor.stop()
        assert cleanup_called is True

    @pytest.mark.asyncio
    async def test_cleanup_stops_all_subsystems(self, monitor):
        """_cleanup should call stop on all subsystems."""
        mock_trap = AsyncMock()
        mock_syslog = AsyncMock()
        mock_processor = AsyncMock()
        mock_bus = AsyncMock()

        monitor.trap_listener = mock_trap
        monitor.syslog_listener = mock_syslog
        monitor.event_processor = mock_processor
        monitor.event_bus = mock_bus

        await monitor._cleanup()

        mock_trap.stop.assert_called_once()
        mock_syslog.stop.assert_called_once()
        mock_processor.stop.assert_called_once()
        mock_bus.stop.assert_called_once()
