"""Cloud sync scheduler — manages per-account, per-tier sync jobs."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from src.cloud.cloud_store import CloudStore
from src.cloud.drivers.base import CloudProviderDriver
from src.cloud.sync.concurrency import SyncConcurrencyGuard
from src.cloud.sync.engine import CloudSyncEngine
from src.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_INTERVALS = {1: 600, 2: 1800, 3: 21600}


class CloudSyncScheduler:
    def __init__(self, store: CloudStore):
        self._store = store
        self._engine = CloudSyncEngine(store)
        self._guard = SyncConcurrencyGuard()
        self._drivers: dict[str, CloudProviderDriver] = {}
        self._last_sync: dict[str, float] = {}  # "acc:tier" -> timestamp

    def register_driver(self, provider: str, driver: CloudProviderDriver) -> None:
        self._drivers[provider] = driver

    def get_interval(self, tier: int, sync_config: dict | None = None) -> int:
        if sync_config:
            return sync_config.get(f"tier_{tier}_interval", _DEFAULT_INTERVALS[tier])
        return _DEFAULT_INTERVALS[tier]

    def is_due(self, account: Any, tier: int) -> bool:
        key = f"{account['account_id']}:{tier}"
        last = self._last_sync.get(key, 0)
        config = json.loads(account["sync_config"]) if account["sync_config"] else None
        interval = self.get_interval(tier, config)
        return (datetime.now(timezone.utc).timestamp() - last) >= interval

    async def sync_account_tier(self, account: Any, tier: int) -> None:
        provider = account["provider"]
        driver = self._drivers.get(provider)
        if not driver:
            logger.warning("No driver for provider %s", provider)
            return

        account_id = account["account_id"]
        lock = self._guard.get_lock(account_id)
        if lock.locked():
            logger.debug("Skipping %s tier %d — another sync running", account_id, tier)
            return

        async with lock:
            job_id = await self._engine.acquire_sync_lock(account_id, tier)
            if not job_id:
                return

            resource_types = driver.resource_types_for_tier(tier)
            regions = json.loads(account["regions"])
            total_stats = {"seen": 0, "created": 0, "updated": 0, "deleted": 0, "api_calls": 0}

            try:
                for region in regions:
                    async for batch in driver.discover(
                        self._account_to_model(account), region, resource_types
                    ):
                        stats = await self._engine.process_batch(batch, job_id)
                        total_stats["seen"] += stats["created"] + stats["updated"] + stats["unchanged"]
                        total_stats["created"] += stats["created"]
                        total_stats["updated"] += stats["updated"]
                        total_stats["api_calls"] += 1

                # Soft-delete stale resources
                interval = self.get_interval(tier)
                from datetime import timedelta
                cutoff = (datetime.now(timezone.utc) - timedelta(seconds=interval * 2)).isoformat()
                for region in regions:
                    await self._engine.mark_stale_deleted(
                        account_id, region, resource_types, cutoff
                    )

                await self._engine.release_sync_lock(
                    job_id, status="completed",
                    items_seen=total_stats["seen"],
                    items_created=total_stats["created"],
                    items_updated=total_stats["updated"],
                    items_deleted=total_stats["deleted"],
                    api_calls=total_stats["api_calls"],
                )
                await self._store.update_account_sync_status(
                    account_id, status="ok", consecutive_failures=0
                )
                key = f"{account_id}:{tier}"
                self._last_sync[key] = datetime.now(timezone.utc).timestamp()

            except Exception as e:
                logger.error("Sync failed for %s tier %d: %s", account_id, tier, e)
                await self._engine.release_sync_lock(
                    job_id, status="failed",
                    errors=[{"error": str(e)}],
                )
                current = account["consecutive_failures"] or 0
                new_failures = current + 1
                status = "paused" if new_failures >= 5 else "error"
                await self._store.update_account_sync_status(
                    account_id, status=status,
                    error=str(e), consecutive_failures=new_failures,
                )

    def _account_to_model(self, row: Any):
        from src.cloud.models import CloudAccount
        return CloudAccount(
            account_id=row["account_id"],
            provider=row["provider"],
            display_name=row["display_name"],
            credential_handle=row["credential_handle"],
            auth_method=row["auth_method"],
            regions=json.loads(row["regions"]),
        )

    async def run_loop(self) -> None:
        """Main scheduler loop — runs until cancelled."""
        while True:
            try:
                accounts = await self._store.list_accounts()
                for account in accounts:
                    if not account["sync_enabled"]:
                        continue
                    if account["last_sync_status"] == "paused":
                        continue
                    for tier in [1, 2, 3]:
                        if self.is_due(account, tier):
                            asyncio.create_task(
                                self.sync_account_tier(account, tier)
                            )
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)
            await asyncio.sleep(60)
