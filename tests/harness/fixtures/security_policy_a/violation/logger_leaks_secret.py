"""Q13 violation — logger sees a Bearer token without redaction.

Pretend-path: backend/src/services/auth.py
"""
import structlog

log = structlog.get_logger()

def authorize(header: str) -> None:
    log.info("incoming_request", auth=f"Authorization: Bearer {header}")
