"""W3C Trace Context propagation — ``traceparent`` / ``tracestate`` headers.

Independent of the OpenTelemetry SDK so we can enforce traceparent
injection on outbound calls regardless of whether OTel is installed
in a given deployment. When OTel IS installed, its FastAPI / httpx
instrumentations set the same header and this module's helpers become
no-ops (the instrumentation wins because it runs earlier in the stack).

W3C Trace Context header format:
    traceparent: <version>-<trace_id>-<parent_id>-<flags>
                 "00"-32hex-16hex-2hex

This module provides:
  - ``TraceContext`` dataclass with parse / format.
  - ``current_trace_id()`` and ``set_trace_id()`` using a contextvars.
  - ``inject_traceparent(headers)`` — merge the current context into
    outbound headers without mutating the caller's dict.
  - ``extract_traceparent(headers)`` — parse an incoming header into a
    ``TraceContext`` (or None for missing/malformed).
"""
from __future__ import annotations

import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


TRACEPARENT_HEADER: str = "traceparent"
TRACESTATE_HEADER: str = "tracestate"

_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-"
    r"(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<parent_id>[0-9a-f]{16})-"
    r"(?P<flags>[0-9a-f]{2})$"
)


@dataclass(frozen=True)
class TraceContext:
    trace_id: str      # 32 hex chars (128-bit)
    parent_id: str     # 16 hex chars (64-bit span id)
    flags: str = "01"  # sampled

    def format_header(self) -> str:
        return f"00-{self.trace_id}-{self.parent_id}-{self.flags}"


def _new_trace_id() -> str:
    return secrets.token_hex(16)  # 32 hex chars


def _new_span_id() -> str:
    return secrets.token_hex(8)   # 16 hex chars


_current: ContextVar[Optional[TraceContext]] = ContextVar(
    "trace_context_current", default=None
)


def current_trace_id() -> Optional[str]:
    ctx = _current.get()
    return ctx.trace_id if ctx else None


def current_context() -> Optional[TraceContext]:
    return _current.get()


def set_context(ctx: TraceContext) -> None:
    """Install ``ctx`` as the current trace context for this task."""
    _current.set(ctx)


def start_new_trace() -> TraceContext:
    """Generate a fresh trace + root span and install it. Returns the ctx."""
    ctx = TraceContext(trace_id=_new_trace_id(), parent_id=_new_span_id())
    _current.set(ctx)
    return ctx


def extract_traceparent(headers: dict) -> Optional[TraceContext]:
    """Parse an incoming ``traceparent`` header. Returns None if missing/bad."""
    if not headers:
        return None
    # Header lookups are case-insensitive; normalise.
    for k, v in headers.items():
        if str(k).lower() == TRACEPARENT_HEADER:
            m = _TRACEPARENT_RE.match(str(v).strip())
            if not m:
                return None
            return TraceContext(
                trace_id=m.group("trace_id"),
                parent_id=m.group("parent_id"),
                flags=m.group("flags"),
            )
    return None


def inject_traceparent(headers: dict | None) -> dict:
    """Return a NEW dict with ``traceparent`` set from the current context.

    If no context is active and none is in ``headers``, starts a new trace
    so the outbound call carries *some* traceparent (better for debugging
    than silent omission).
    """
    merged: dict = dict(headers or {})
    # Don't clobber a caller-provided traceparent.
    if any(str(k).lower() == TRACEPARENT_HEADER for k in merged):
        return merged
    ctx = _current.get()
    if ctx is None:
        ctx = start_new_trace()
    merged[TRACEPARENT_HEADER] = ctx.format_header()
    return merged


def structlog_fields() -> dict:
    """Convenience: {trace_id, parent_id} for structured-log enrichment."""
    ctx = _current.get()
    if ctx is None:
        return {}
    return {"trace_id": ctx.trace_id, "parent_id": ctx.parent_id}
