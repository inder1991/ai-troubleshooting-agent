"""Cloud integration API endpoints."""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.cloud.cloud_store import CloudStore
from src.cloud.redaction import decompress_raw
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ── Request/Response Models ──


class CreateAccountRequest(BaseModel):
    provider: str
    display_name: str
    credential_handle: str
    auth_method: str
    regions: list[str]
    native_account_id: str | None = None
    org_parent_id: str | None = None
    sync_config: dict | None = None


class AccountResponse(BaseModel):
    account_id: str
    provider: str
    display_name: str
    auth_method: str
    regions: list[str]
    sync_enabled: bool = True
    last_sync_status: str = "never"
    consecutive_failures: int = 0


class TriggerSyncRequest(BaseModel):
    tiers: list[int] = Field(default=[1, 2, 3])


# ── Router Factory ──


def create_cloud_router(store: CloudStore) -> APIRouter:
    router = APIRouter(prefix="/api/v4/cloud", tags=["cloud"])

    # ── Accounts ──

    @router.get("/accounts")
    async def list_accounts():
        accounts = await store.list_accounts()
        return [_row_to_account(a) for a in accounts]

    @router.post("/accounts", status_code=201)
    async def create_account(req: CreateAccountRequest):
        account_id = str(uuid.uuid4())
        await store.upsert_account(
            account_id=account_id,
            provider=req.provider,
            display_name=req.display_name,
            credential_handle=req.credential_handle,
            auth_method=req.auth_method,
            regions=req.regions,
            native_account_id=req.native_account_id,
            org_parent_id=req.org_parent_id,
            sync_config=req.sync_config,
        )
        account = await store.get_account(account_id)
        return _row_to_account(account)

    @router.get("/accounts/{account_id}")
    async def get_account(account_id: str):
        account = await store.get_account(account_id)
        if not account:
            raise HTTPException(404, "Account not found")
        return _row_to_account(account)

    @router.delete("/accounts/{account_id}")
    async def delete_account(account_id: str):
        await store.delete_account(account_id)
        return {"status": "deleted"}

    # ── Resources ──

    @router.get("/resources")
    async def list_resources(
        account_id: str | None = None,
        region: str | None = None,
        resource_type: str | None = None,
        limit: int = 500,
    ):
        resources = await store.list_resources(
            account_id=account_id, region=region,
            resource_type=resource_type, limit=limit,
        )
        return [dict(r) for r in resources]

    @router.get("/resources/{resource_id}")
    async def get_resource(resource_id: str):
        resource = await store.get_resource(resource_id)
        if not resource:
            raise HTTPException(404, "Resource not found")
        result = dict(resource)
        # Decompress raw for detail view
        if result.get("raw_compressed"):
            try:
                result["raw"] = decompress_raw(result["raw_compressed"])
            except Exception:
                result["raw"] = None
            del result["raw_compressed"]
        return result

    @router.get("/resources/{resource_id}/relations")
    async def list_relations(resource_id: str):
        relations = await store.list_relations(resource_id)
        return [dict(r) for r in relations]

    # ── Sync Jobs ──

    @router.get("/sync/jobs")
    async def list_sync_jobs(account_id: str | None = None, limit: int = 50):
        if account_id:
            rows = await store._execute(
                "SELECT * FROM cloud_sync_jobs WHERE account_id = ? ORDER BY started_at DESC LIMIT ?",
                (account_id, limit),
            )
        else:
            rows = await store._execute(
                "SELECT * FROM cloud_sync_jobs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in rows]

    @router.post("/accounts/{account_id}/sync")
    async def trigger_sync(account_id: str, req: TriggerSyncRequest):
        account = await store.get_account(account_id)
        if not account:
            raise HTTPException(404, "Account not found")
        return {"status": "queued", "message": "Sync triggered for tiers " + str(req.tiers)}

    # ── Health Check ──

    @router.post("/accounts/{account_id}/health")
    async def health_check(account_id: str):
        account = await store.get_account(account_id)
        if not account:
            raise HTTPException(404, "Account not found")
        return {
            "status": "health_check_not_implemented",
            "message": "Connect a driver to enable health checks",
        }

    return router


def _row_to_account(row) -> dict:
    return {
        "account_id": row["account_id"],
        "provider": row["provider"],
        "display_name": row["display_name"],
        "auth_method": row["auth_method"],
        "regions": json.loads(row["regions"]),
        "sync_enabled": bool(row["sync_enabled"]),
        "last_sync_status": row["last_sync_status"],
        "consecutive_failures": row["consecutive_failures"] or 0,
    }
