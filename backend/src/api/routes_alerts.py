"""Alertmanager v2 webhook receiver.

POST /api/v5/alerts/webhook
Accepts Alertmanager firing alerts and auto-creates cluster diagnostic sessions.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v5/alerts", tags=["alerts"])

# Deduplication: (namespace, workload) -> (session_id, created_at)
_active_alert_sessions: dict[tuple[str, str], tuple[str, float]] = {}
_DEDUP_WINDOW_SECONDS = 1800  # 30 minutes

# Hold references to background tasks to prevent GC before completion
_background_tasks: set = set()


def _prune_expired_sessions() -> None:
    """Remove dedup entries older than the dedup window."""
    now = time.time()
    expired = [k for k, (_, created_at) in _active_alert_sessions.items()
               if now - created_at >= _DEDUP_WINDOW_SECONDS]
    for k in expired:
        del _active_alert_sessions[k]

ALERT_DIAGNOSTIC_DELAY_SECONDS = int(os.getenv("ALERT_DIAGNOSTIC_DELAY_SECONDS", "120"))


# ── Pydantic models ──────────────────────────────────────────────────────────

class AlertmanagerAlert(BaseModel):
    status: str
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}


class AlertmanagerPayload(BaseModel):
    alerts: list[AlertmanagerAlert]
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}


# ── Scope derivation ─────────────────────────────────────────────────────────

def _derive_scope(merged_labels: dict[str, str]) -> tuple[dict, str]:
    """Derive DiagnosticScope and scan_mode from merged alert labels."""
    namespace = merged_labels.get("namespace", "")
    workload = merged_labels.get("workload", "")
    severity = merged_labels.get("severity", "warning").lower()

    scan_mode = "comprehensive" if severity == "critical" else "diagnostic"
    include_cp = severity == "critical"

    if workload and namespace:
        scope = {
            "level": "workload",
            "namespaces": [namespace],
            "workload_key": None,
            "domains": ["node", "network"],
            "include_control_plane": include_cp,
        }
    elif namespace:
        scope = {
            "level": "namespace",
            "namespaces": [namespace],
            "workload_key": None,
            "domains": ["ctrl_plane", "node", "network", "storage", "rbac"],
            "include_control_plane": include_cp,
        }
    else:
        scope = {
            "level": "cluster",
            "namespaces": [],
            "workload_key": None,
            "domains": ["ctrl_plane", "node", "network", "storage", "rbac"],
            "include_control_plane": True,
        }

    return scope, scan_mode


# ── Webhook endpoint ─────────────────────────────────────────────────────────

@router.post("/webhook")
async def alertmanager_webhook(payload: AlertmanagerPayload):
    """Receive Alertmanager v2 webhook and schedule a cluster diagnostic session."""
    # Only process firing alerts
    firing = [a for a in payload.alerts if a.status == "firing"]
    if not firing:
        return {"status": "ignored", "reason": "no firing alerts"}

    # Merge labels: commonLabels wins over groupLabels
    merged = {**payload.groupLabels, **payload.commonLabels}
    severity = merged.get("severity", "warning").lower()

    if severity == "info":
        return {"status": "ignored", "reason": "severity=info"}

    scope, scan_mode = _derive_scope(merged)

    namespace = merged.get("namespace", "")
    workload = merged.get("workload", "")
    dedup_key = (namespace, workload)

    # Deduplication check
    existing = _active_alert_sessions.get(dedup_key)
    if existing:
        existing_session_id, created_at = existing
        if time.time() - created_at < _DEDUP_WINDOW_SECONDS:
            return {
                "status": "deduplicated",
                "session_id": existing_session_id,
                "message": "Diagnostic already running for this target",
            }

    # Create session
    session_id = str(uuid.uuid4())
    alertname = merged.get("alertname", "UnknownAlert")
    service_name = f"{alertname}-{namespace}" if namespace else alertname
    incident_id = f"ALERT-{session_id[:8].upper()}"

    _prune_expired_sessions()
    _active_alert_sessions[dedup_key] = (session_id, time.time())

    # Schedule delayed diagnostic (keep task reference to prevent GC)
    task = asyncio.create_task(_run_delayed_diagnostic(
        session_id=session_id,
        service_name=service_name,
        incident_id=incident_id,
        scope=scope,
        scan_mode=scan_mode,
        delay=ALERT_DIAGNOSTIC_DELAY_SECONDS,
        dedup_key=dedup_key,
    ))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    logger.info(
        "Alertmanager webhook: scheduled diagnostic",
        extra={"session_id": session_id, "scope_level": scope["level"],
               "severity": severity, "alert_count": len(firing)},
    )

    return {
        "status": "scheduled",
        "session_id": session_id,
        "delay_seconds": ALERT_DIAGNOSTIC_DELAY_SECONDS,
        "scope": scope,
        "alert_count": len(firing),
        "incident_id": incident_id,
    }


async def _run_delayed_diagnostic(
    session_id: str,
    service_name: str,
    incident_id: str,
    scope: dict,
    scan_mode: str,
    delay: int,
    dedup_key: tuple[str, str] = ("", ""),
) -> None:
    """Wait delay seconds then trigger cluster diagnostic (runs as background task).

    Note: run_cluster_diagnosis requires a LangGraph graph and cluster_client,
    which must be established through the normal session-creation flow. This
    background task logs the intent and marks the session ready for pickup by
    a human or automated operator via the standard POST /api/v4/sessions endpoint.
    A full auto-connect implementation would require kubeconfig resolution, which
    is out of scope for the webhook receiver.
    """
    await asyncio.sleep(delay)

    try:
        import datetime

        # Import here to avoid circular imports at module load time
        from src.utils.event_emitter import EventEmitter
        from src.observability.store import get_store
        from src.api.routes_v4 import sessions, session_locks

        store = get_store()
        emitter = EventEmitter(session_id=session_id, store=store)

        sessions[session_id] = {
            "service_name": service_name,
            "incident_id": incident_id,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "emitter": emitter,
            "state": {},
            "diagnostic_scope": scope,
            "scan_mode": scan_mode,
            "capability": "cluster_diagnostics",
            "alert_triggered": True,
        }
        session_locks[session_id] = asyncio.Lock()

        logger.info(
            "Alert-triggered session registered (awaiting cluster connection)",
            extra={"session_id": session_id, "incident_id": incident_id},
        )
    except Exception as exc:
        logger.error(
            "Alert-triggered diagnostic session registration failed: %s", exc,
            extra={"session_id": session_id},
        )
        _active_alert_sessions.pop(dedup_key, None)
