"""Periodic WAL checkpoint and size monitoring."""
from __future__ import annotations

import asyncio
import os

from src.utils.logger import get_logger

logger = get_logger(__name__)


class WALMonitor:
    WAL_SIZE_ALERT_MB = 100
    CHECKPOINT_INTERVAL_SECONDS = 300

    async def run_once(self, store) -> None:
        """Single checkpoint pass. Called by run_loop or directly in tests."""
        try:
            await store.execute("PRAGMA wal_checkpoint(PASSIVE)")
            wal_path = store._db_path + "-wal"
            if os.path.exists(wal_path):
                wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024)
                if wal_size_mb > self.WAL_SIZE_ALERT_MB:
                    logger.warning(
                        "WAL file large: %.1f MB. Attempting TRUNCATE.",
                        wal_size_mb,
                    )
                    await store.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as e:
            logger.warning("WAL checkpoint failed: %s", e)

    async def run_loop(self, store) -> None:
        """Background loop -- runs until cancelled."""
        while True:
            await asyncio.sleep(self.CHECKPOINT_INTERVAL_SECONDS)
            await self.run_once(store)
