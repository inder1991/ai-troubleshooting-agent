"""Structured JSON logging with correlation ID support.

Usage:
    from src.utils.structured_logging import setup_structured_logging, new_correlation_id

    setup_structured_logging(level="INFO")

    # At the start of each request / task:
    cid = new_correlation_id()

    # All subsequent log messages will include the correlation_id.
    logger.info("Processing request")
"""
from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

# Context variable for correlation ID — propagates across async tasks
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


class JSONFormatter(logging.Formatter):
    """Outputs log records as single-line JSON with correlation_id, timestamp,
    level, logger, and message fields."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id.get(""),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_structured_logging(level: str = "INFO") -> None:
    """Configure the root logger with JSONFormatter on a StreamHandler."""
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def new_correlation_id() -> str:
    """Generate and set a new 8-character correlation ID.

    Returns the new ID so callers can pass it along in headers, etc.
    """
    cid = str(uuid.uuid4())[:8]
    correlation_id.set(cid)
    return cid
