"""Cloud sync engine — processes discovery batches into CloudStore."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from src.cloud.cloud_store import CloudStore
from src.cloud.redaction import compress_raw, make_raw_preview, redact_raw
from src.cloud.sync.batch_controller import BatchSizeController
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CloudSyncEngine:
    def __init__(self, store: CloudStore):
        self._store = store
        self._batch_ctrl = BatchSizeController()

    async def process_batch(
        self, batch: "DiscoveryBatch", sync_job_id: str
    ) -> dict[str, int]:
        """Process a single discovery batch. Returns stats dict."""
        from src.cloud.models import DiscoveryBatch  # avoid circular

        stats = {"created": 0, "updated": 0, "unchanged": 0, "relations_created": 0}

        # Phase 1: Load native_id -> resource_id cache
        native_cache = await self._store.load_native_id_cache(
            batch.account_id, batch.region
        )

        # Phase 2: Process items
        for item in batch.items:
            redacted = redact_raw(item.raw)
            raw_json_str = json.dumps(redacted, sort_keys=True, default=str)
            resource_hash = hashlib.sha256(raw_json_str.encode()).hexdigest()

            existing_id = native_cache.get(item.native_id)
            if existing_id:
                existing_hash = await self._store.get_resource_hash(
                    provider="aws",  # TODO: pass from batch
                    account_id=batch.account_id,
                    region=batch.region,
                    native_id=item.native_id,
                )
                if existing_hash == resource_hash:
                    await self._store.touch_resource(existing_id, sync_job_id)
                    stats["unchanged"] += 1
                    continue
                else:
                    resource_id = existing_id
                    stats["updated"] += 1
            else:
                resource_id = str(uuid.uuid4())
                stats["created"] += 1

            compressed = compress_raw(redacted)
            preview = make_raw_preview(redacted)
            tags_str = json.dumps(item.tags) if item.tags else None

            await self._store.upsert_resource(
                resource_id=resource_id,
                provider="aws",
                account_id=batch.account_id,
                region=batch.region,
                resource_type=batch.resource_type,
                native_id=item.native_id,
                name=item.name,
                raw_compressed=compressed,
                raw_preview=preview,
                tags=tags_str,
                resource_hash=resource_hash,
                source=batch.source,
                sync_job_id=sync_job_id,
                sync_tier=1,
            )
            native_cache[item.native_id] = resource_id

        # Phase 3: Process relations
        for rel in batch.relations:
            source_id = native_cache.get(rel.source_native_id)
            target_id = native_cache.get(rel.target_native_id)
            if source_id and target_id:
                relation_id = str(uuid.uuid4())
                metadata_str = json.dumps(rel.metadata) if rel.metadata else None
                await self._store.upsert_relation(
                    relation_id=relation_id,
                    source_resource_id=source_id,
                    target_resource_id=target_id,
                    relation_type=rel.relation_type,
                    metadata=metadata_str,
                )
                stats["relations_created"] += 1

        return stats

    async def mark_stale_deleted(
        self,
        account_id: str,
        region: str,
        resource_types: list[str],
        cutoff_ts: str,
    ) -> int:
        """Soft-delete resources not seen since cutoff_ts."""
        return await self._store.mark_stale_deleted(
            account_id, region, resource_types, cutoff_ts
        )

    async def acquire_sync_lock(
        self, account_id: str, tier: int
    ) -> str | None:
        """Try to acquire sync lock. Returns sync_job_id or None."""
        STALE_THRESHOLD_SECONDS = 900
        running = await self._store.find_running_job(account_id, tier)
        if running:
            from datetime import datetime, timezone
            started = datetime.fromisoformat(running["started_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - started).total_seconds()
            if age < STALE_THRESHOLD_SECONDS:
                return None
            # Stale lock — reclaim
            await self._store.complete_sync_job(
                running["sync_job_id"],
                status="failed",
                errors=[{"error": "stale_lock_reclaimed"}],
            )

        job_id = str(uuid.uuid4())
        await self._store.create_sync_job(job_id, account_id, tier)
        return job_id

    async def release_sync_lock(
        self,
        sync_job_id: str,
        status: str = "completed",
        items_seen: int = 0,
        items_created: int = 0,
        items_updated: int = 0,
        items_deleted: int = 0,
        api_calls: int = 0,
        errors: list[dict] | None = None,
    ) -> None:
        await self._store.complete_sync_job(
            sync_job_id, status=status,
            items_seen=items_seen, items_created=items_created,
            items_updated=items_updated, items_deleted=items_deleted,
            api_calls=api_calls, errors=errors,
        )
