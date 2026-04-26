"""Q13 compliant — sensitive value passed through redact_ helper.

Pretend-path: backend/src/services/auth.py
"""
import structlog

log = structlog.get_logger()


def redact_token(value: str) -> str:
    return value[:4] + "..."  # implementation lives in observability/logging.py


def authorize(header: str) -> None:
    log.info("incoming_request", auth=redact_token(header))
