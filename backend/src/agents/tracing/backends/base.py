"""TraceBackend protocol — the abstraction the TracingAgent depends on.

Two concrete implementations in v1: ``JaegerBackend`` + ``TempoBackend``.
Zipkin arrives in v2 on customer demand.

SaaS APM vendors (Datadog / X-Ray / GCP Trace / Honeycomb / New Relic / etc.)
are explicitly OUT of scope. Customers using those route via OTLP export
into self-hosted Tempo or Jaeger.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from src.models.schemas import SpanInfo, TraceSummary


class BackendError(Exception):
    """Base exception for any TraceBackend operation failure."""


class BackendUnreachable(BackendError):
    """Raised when the backend's HTTP endpoint is unreachable (DNS / TCP / 5xx).

    Distinct from ``TraceNotFound`` so callers can distinguish "the trace
    doesn't exist" (a finding) from "we couldn't reach the service" (a
    coverage gap).
    """


class TraceNotFound(BackendError):
    """Raised when the backend reports the specific trace ID has no spans.

    Not an error condition — callers should emit a negative finding and
    optionally fall back to ELK log reconstruction.
    """


@runtime_checkable
class TraceBackend(Protocol):
    """Minimal surface every tracing backend must expose.

    Kept deliberately narrow — the agent's business logic lives in
    ``TracingAgent``, not here. Each adapter is a thin wire-protocol layer.
    """

    #: Short identifier — goes into ``TraceAnalysisResult.trace_source``.
    backend_id: str

    async def list_services(self) -> list[str]:
        """Return service names reporting to this backend.

        Must filter out backend-internal services (``jaeger-query``,
        ``jaeger-collector``, ``tempo-distributor``, ``otel-collector``).

        Raises ``BackendUnreachable`` when the endpoint can't be reached.
        """
        ...

    async def get_trace(self, trace_id: str) -> list[SpanInfo]:
        """Fetch a complete trace by ID.

        Returns an empty list if the trace has zero spans. Raises
        ``TraceNotFound`` if the backend explicitly reports "no such trace"
        (vs. "trace exists but is empty"). Raises ``BackendUnreachable``
        on transport errors.

        The returned spans are raw — redaction and summarization are
        applied by higher layers before the spans reach the LLM.
        """
        ...

    async def find_traces(
        self,
        service: str,
        start: datetime,
        end: datetime,
        *,
        min_duration_ms: Optional[int] = None,
        max_duration_ms: Optional[int] = None,
        has_error: Optional[bool] = None,
        operation: Optional[str] = None,
        tags: Optional[dict[str, str]] = None,
        limit: int = 20,
    ) -> list[TraceSummary]:
        """Mine candidate traces matching a filter — foundation of trace-mining.

        Returns lightweight ``TraceSummary`` objects (trace_id + metadata),
        not full span lists — mining must stay cheap so ranking can pick
        the top-N and only THEN incur the cost of ``get_trace()``.

        ``has_error=True`` asks the backend to return only error-carrying
        traces (implementations filter client-side if backend's native
        query doesn't support it).
        """
        ...
