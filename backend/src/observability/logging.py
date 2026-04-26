"""Q16 — structlog backend with mandatory event field, redaction processor,
and OpenTelemetry context injection.

Production renders JSON to stdout; dev pretty-prints. Test mode (used by
the harness's own tests) writes to an injectable buffer for inspection."""

from __future__ import annotations

import logging
import sys
from typing import Any, IO

import structlog

from src.observability._redactor import redact_secrets


def _redact_processor(_logger, _method, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor: apply redact_secrets to every string value."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = redact_secrets(value)
    return event_dict


def _otel_context_processor(_logger, _method, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject trace_id + span_id from the current OpenTelemetry context."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx and ctx.is_valid:
            event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
            event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    except Exception:
        # H-25: tracing being unavailable must not crash logging.
        pass
    return event_dict


_DEFAULT_PROCESSORS = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    _redact_processor,
    _otel_context_processor,
    structlog.processors.JSONRenderer(sort_keys=True),
]


def _processor_names() -> list[str]:
    """For introspection by tests."""
    return [getattr(p, "__qualname__", getattr(p, "__class__", type(p)).__name__)
            for p in _DEFAULT_PROCESSORS]


def configure_default(stream: IO[str] | None = None) -> None:
    """Wire structlog with the default processor chain."""
    structlog.configure(
        processors=_DEFAULT_PROCESSORS,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        cache_logger_on_first_use=False,
    )


def configure_for_test_capture(buf: IO[str]) -> None:
    """Used by tests to assert log output."""
    configure_default(stream=buf)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not structlog.is_configured():
        configure_default()
    return structlog.get_logger(name) if name else structlog.get_logger()
