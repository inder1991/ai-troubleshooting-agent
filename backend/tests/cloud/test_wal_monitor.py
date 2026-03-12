"""Tests for WAL monitor."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.cloud.sync.wal_monitor import WALMonitor


class TestWALMonitor:
    def test_default_thresholds(self):
        monitor = WALMonitor()
        assert monitor.WAL_SIZE_ALERT_MB == 100
        assert monitor.CHECKPOINT_INTERVAL_SECONDS == 300

    @pytest.mark.asyncio
    async def test_checkpoint_calls_passive(self):
        monitor = WALMonitor()
        store = AsyncMock()
        store._db_path = "/tmp/test.db"
        store.execute = AsyncMock(return_value=[])
        with patch("os.path.exists", return_value=False):
            await monitor.run_once(store)
        store.execute.assert_called_once_with("PRAGMA wal_checkpoint(PASSIVE)")

    @pytest.mark.asyncio
    async def test_large_wal_triggers_truncate(self):
        monitor = WALMonitor()
        monitor.WAL_SIZE_ALERT_MB = 0
        store = AsyncMock()
        store._db_path = "/tmp/test.db"
        store.execute = AsyncMock(return_value=[])
        fd, wal_path = tempfile.mkstemp()
        os.write(fd, b"x" * 1024)
        os.close(fd)
        store._db_path = wal_path.replace("-wal", "")
        os.rename(wal_path, store._db_path + "-wal")
        try:
            with patch("os.path.exists", return_value=True), \
                 patch("os.path.getsize", return_value=200 * 1024 * 1024):
                await monitor.run_once(store)
            calls = [c.args[0] for c in store.execute.call_args_list]
            assert "PRAGMA wal_checkpoint(PASSIVE)" in calls
            assert "PRAGMA wal_checkpoint(TRUNCATE)" in calls
        finally:
            for ext in ("", "-wal"):
                try:
                    os.unlink(store._db_path + ext)
                except FileNotFoundError:
                    pass
