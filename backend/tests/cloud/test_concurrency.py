"""Tests for sync concurrency guard."""
import asyncio
import pytest
from src.cloud.sync.concurrency import SyncConcurrencyGuard


class TestSyncConcurrencyGuard:
    def test_creates_lock_per_account(self):
        guard = SyncConcurrencyGuard()
        lock1 = guard.get_lock("acc-001")
        lock2 = guard.get_lock("acc-002")
        assert lock1 is not lock2

    def test_same_account_returns_same_lock(self):
        guard = SyncConcurrencyGuard()
        lock1 = guard.get_lock("acc-001")
        lock2 = guard.get_lock("acc-001")
        assert lock1 is lock2

    @pytest.mark.asyncio
    async def test_lock_blocks_concurrent_access(self):
        guard = SyncConcurrencyGuard()
        lock = guard.get_lock("acc-001")
        results = []

        async def task(name: str, delay: float):
            async with lock:
                results.append(f"{name}-start")
                await asyncio.sleep(delay)
                results.append(f"{name}-end")

        await asyncio.gather(task("A", 0.05), task("B", 0.01))
        assert results[0] == "A-start"
        assert results[1] == "A-end"
        assert results[2] == "B-start"

    @pytest.mark.asyncio
    async def test_is_locked(self):
        guard = SyncConcurrencyGuard()
        lock = guard.get_lock("acc-001")
        assert not lock.locked()
        async with lock:
            assert lock.locked()
        assert not lock.locked()
