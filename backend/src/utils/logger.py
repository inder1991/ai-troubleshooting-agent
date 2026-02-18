"""
Structured JSON logging module.

Usage:
    from src.utils.logger import get_logger
    logger = get_logger("my_module")
    logger.info("Something happened", extra={"session_id": "abc", "profile_id": "xyz"})
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key in ("session_id", "profile_id", "action", "extra",
                     "agent_name", "tool", "tokens", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with JSON formatting.

    Returns a standard Python logger configured with JSON output.
    The log level is controlled by the LOG_LEVEL environment variable (default: INFO).
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        logger.propagate = False

    return logger
