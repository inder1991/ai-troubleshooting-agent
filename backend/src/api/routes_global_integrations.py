"""Global integration CRUD API endpoints."""

import os
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.integrations.profile_models import GlobalIntegration
from src.integrations.profile_store import GlobalIntegrationStore
from src.integrations.credential_resolver import get_credential_resolver
from src.integrations.audit_store import AuditLogger
from src.integrations.probe import GlobalProbe
from src.utils.logger import get_logger

logger = get_logger("routes_global_integrations")

router = APIRouter(prefix="/api/v5/global-integrations", tags=["global-integrations"])

_db_path = os.environ.get("DEBUGDUCK_DB_PATH", "./data/debugduck.db")
_gi_store: GlobalIntegrationStore | None = None
_audit: AuditLogger | None = None


def get_gi_store() -> GlobalIntegrationStore:
    global _gi_store
    if _gi_store is None:
        _gi_store = GlobalIntegrationStore(db_path=_db_path)
        _gi_store._ensure_tables()
        _gi_store.seed_defaults()
    return _gi_store


def get_audit() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger(db_path=_db_path)
        _audit._ensure_tables()
    return _audit


# --- Request models ---

class CreateGlobalIntegrationRequest(BaseModel):
    service_type: Literal["elk", "jira", "confluence", "remedy"]
    name: str
    category: Optional[str] = ""
    url: Optional[str] = ""
    auth_method: Optional[str] = "none"
    auth_data: Optional[str] = None


class UpdateGlobalIntegrationRequest(BaseModel):
    url: Optional[str] = None
    auth_method: Optional[str] = None
    auth_data: Optional[str] = None  # plaintext, will be encrypted


class SaveAllRequest(BaseModel):
    integrations: list[dict]


# --- Routes ---

@router.get("/")
async def list_global_integrations():
    return [gi.to_safe_dict() for gi in get_gi_store().list_all()]


@router.post("/")
async def create_global_integration(request: CreateGlobalIntegrationRequest):
    store = get_gi_store()
    audit = get_audit()
    resolver = get_credential_resolver()

    gi = GlobalIntegration(
        service_type=request.service_type,
        name=request.name,
        category=request.category or "",
        url=request.url or "",
        auth_method=request.auth_method or "none",
    )

    if request.auth_data:
        handle = resolver.encrypt_and_store(gi.id, "credential", request.auth_data.strip())
        gi.auth_credential_handle = handle
        gi.status = "not_validated"

    store.add(gi)
    audit.log("global_integration", gi.id, "created", f"Created {gi.name}")

    return gi.to_safe_dict()


@router.delete("/{integration_id}")
async def delete_global_integration(integration_id: str):
    store = get_gi_store()
    audit = get_audit()
    resolver = get_credential_resolver()

    gi = store.get(integration_id)
    if not gi:
        raise HTTPException(status_code=404, detail="Global integration not found")

    # Clean up stored credentials
    if gi.auth_credential_handle:
        try:
            resolver.delete(gi.id, "credential")
        except Exception:
            pass  # Best-effort cleanup

    store.delete(integration_id)
    audit.log("global_integration", integration_id, "deleted", f"Deleted {gi.name}")

    return {"status": "deleted"}


@router.put("/{integration_id}")
async def update_global_integration(integration_id: str, request: UpdateGlobalIntegrationRequest):
    store = get_gi_store()
    audit = get_audit()
    resolver = get_credential_resolver()

    gi = store.get(integration_id)
    if not gi:
        raise HTTPException(status_code=404, detail="Global integration not found")

    if request.url is not None:
        gi.url = request.url
    if request.auth_method is not None:
        gi.auth_method = request.auth_method

    if request.auth_data:
        handle = resolver.encrypt_and_store(gi.id, "credential", request.auth_data.strip())
        gi.auth_credential_handle = handle
        gi.status = "not_validated"

    gi.updated_at = datetime.now()
    store.update(gi)
    audit.log("global_integration", gi.id, "updated", f"Updated {gi.name}")

    return gi.to_safe_dict()


@router.post("/{integration_id}/test")
async def test_global_integration(integration_id: str):
    store = get_gi_store()
    audit = get_audit()
    resolver = get_credential_resolver()

    gi = store.get(integration_id)
    if not gi:
        raise HTTPException(status_code=404, detail="Global integration not found")

    # Resolve credentials for testing
    credentials = None
    if gi.auth_credential_handle:
        try:
            credentials = resolver.resolve(gi.id, "credential", gi.auth_credential_handle)
        except Exception as e:
            gi.status = "conn_error"
            store.update(gi)
            return {"reachable": False, "error": f"Credential resolution failed: {e}"}

    probe = GlobalProbe()
    result = await probe.test_connection(gi.service_type, gi.url, gi.auth_method, credentials)

    # Update status based on result
    if result.reachable:
        gi.status = "connected"
    else:
        gi.status = "conn_error"
    gi.last_verified = datetime.now()
    gi.updated_at = datetime.now()
    store.update(gi)

    audit.log("global_integration", gi.id, "test_connection", f"Reachable: {result.reachable}")

    return result.model_dump()


@router.post("/save-all")
async def save_all_global_integrations(request: SaveAllRequest):
    store = get_gi_store()
    audit = get_audit()
    resolver = get_credential_resolver()
    updated = 0

    for item in request.integrations:
        gi = store.get(item.get("id", ""))
        if not gi:
            continue

        if "url" in item:
            gi.url = item["url"]
        if "auth_method" in item:
            gi.auth_method = item["auth_method"]
        if item.get("auth_data"):
            handle = resolver.encrypt_and_store(gi.id, "credential", item["auth_data"].strip())
            gi.auth_credential_handle = handle
            gi.status = "not_validated"

        gi.updated_at = datetime.now()
        store.update(gi)
        updated += 1

    audit.log("global_integration", "batch", "updated", f"Batch saved {updated} integrations")

    return {"status": "saved", "updated": updated}
