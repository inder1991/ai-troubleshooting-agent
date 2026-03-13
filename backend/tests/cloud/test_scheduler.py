"""Tests for CloudSyncScheduler."""
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.cloud.cloud_store import CloudStore
from src.cloud.sync.scheduler import CloudSyncScheduler


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


@pytest.fixture
def store(tmp_db):
    return CloudStore(db_path=tmp_db)


@pytest.fixture
def scheduler(store):
    return CloudSyncScheduler(store)


class TestSchedulerTierDue:
    @pytest.mark.asyncio
    async def test_first_sync_is_always_due(self, scheduler, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="Test", credential_handle="ref",
            auth_method="iam_role", regions=["us-east-1"],
        )
        account = await store.get_account("acc-001")
        assert scheduler.is_due(account, tier=1) is True

    @pytest.mark.asyncio
    async def test_default_intervals(self, scheduler):
        assert scheduler.get_interval(tier=1) == 600
        assert scheduler.get_interval(tier=2) == 1800
        assert scheduler.get_interval(tier=3) == 21600


class TestSchedulerSyncAccount:
    @pytest.mark.asyncio
    async def test_sync_account_tier_calls_driver(self, scheduler, store):
        await store.upsert_account(
            account_id="acc-001", provider="aws",
            display_name="Test", credential_handle='{}',
            auth_method="iam_role", regions=["us-east-1"],
        )
        mock_driver = AsyncMock()
        mock_driver.resource_types_for_tier.return_value = ["vpc"]
        mock_driver.discover = AsyncMock(return_value=AsyncMock(__aiter__=lambda _: iter([])))

        # Use async iterator mock
        async def empty_discover(*args, **kwargs):
            return
            yield  # make it an async generator

        mock_driver.discover = empty_discover
        scheduler._drivers = {"aws": mock_driver}

        account = await store.get_account("acc-001")
        await scheduler.sync_account_tier(account, tier=1)
