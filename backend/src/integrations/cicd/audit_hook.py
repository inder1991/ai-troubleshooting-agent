"""Audit hook for CICDClient read operations.

Wraps AuditLogger.log() in a lazy module-level singleton so every read from
Jenkins/ArgoCD clients leaves a structured audit trail. Fires best-effort:
failures are logged but never raised (must not break read path).
"""
from __future__ import annotations

import logging
from typing import Optional

from src.integrations.audit_store import AuditLogger

_logger = logging.getLogger(__name__)
_audit_logger: Optional[AuditLogger] = None


def _get_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        al = AuditLogger()
        al._ensure_tables()
        _audit_logger = al
    return _audit_logger


def record_cicd_read(
    source: str, instance: str, method: str, details: str = ""
) -> None:
    """Record a CICDClient read. Best-effort — never raises."""
    try:
        _get_logger().log(
            entity_type="integration_cicd",
            entity_id=f"{source}/{instance}",
            action=f"read:{method}",
            details=details or None,
            actor="system",
        )
    except Exception as exc:  # pragma: no cover — defensive
        _logger.warning("cicd audit hook failed: %s", exc)
