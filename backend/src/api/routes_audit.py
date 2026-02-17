"""Audit log API endpoints."""

import os
from typing import Optional

from fastapi import APIRouter, Query

from src.integrations.audit_store import AuditLogger

router = APIRouter(prefix="/api/v5/audit", tags=["audit"])

_db_path = os.environ.get("DEBUGDUCK_DB_PATH", "./data/debugduck.db")
_audit: AuditLogger | None = None


def get_audit() -> AuditLogger:
    global _audit
    if _audit is None:
        _audit = AuditLogger(db_path=_db_path)
        _audit._ensure_tables()
    return _audit


@router.get("/")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    entity_type: Optional[str] = Query(None),
):
    return get_audit().list_recent(limit=limit, entity_type=entity_type)
