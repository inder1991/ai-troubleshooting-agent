"""Jaeger backend — async httpx, auth-aware, handles find + get + list.

Endpoint conventions (Jaeger Query HTTP API):

    GET /api/services                             — list all services
    GET /api/traces/{trace_id}                    — fetch single trace
    GET /api/traces?service=X&start=...&end=...   — search/mining

All three are async and use the shared ``get_client("jaeger")`` singleton
so we get connection pooling, traceparent injection, and per-backend
circuit-breaker posture for free (K.5 + K.11 from the Phase-3 work).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import httpx

from src.integrations.http_clients import get_client
from src.models.schemas import SpanInfo, TraceSummary
from src.utils.logger import get_logger

from .base import BackendUnreachable, TraceBackend, TraceNotFound

logger = get_logger(__name__)


# Backend-internal services we filter out of ``list_services``.
_INTERNAL_SERVICES = {
    "jaeger-query",
    "jaeger-collector",
    "jaeger-agent",
    "tempo-distributor",
    "tempo-query",
    "tempo-querier",
    "otel-collector",
    "otelcol",
}


class JaegerBackend:
    """Implementation of TraceBackend for Jaeger query API."""

    backend_id = "jaeger"

    def __init__(
        self,
        base_url: str,
        *,
        auth_header: Optional[str] = None,
        backend_key: str = "jaeger",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_header = auth_header
        self._backend_key = backend_key

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": self._auth_header} if self._auth_header else {}

    async def list_services(self) -> list[str]:
        client = get_client(self._backend_key)
        try:
            resp = await client.get(
                f"{self._base_url}/api/services",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendUnreachable(
                f"Cannot reach Jaeger at {self._base_url}: {e}"
            ) from e

        data = resp.json()
        services = [s for s in data.get("data") or [] if s not in _INTERNAL_SERVICES]
        return services

    async def get_trace(self, trace_id: str) -> list[SpanInfo]:
        client = get_client(self._backend_key)
        try:
            resp = await client.get(
                f"{self._base_url}/api/traces/{trace_id}",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendUnreachable(
                f"Cannot reach Jaeger at {self._base_url}: {e}"
            ) from e

        data = resp.json()
        traces = data.get("data") or []
        if not traces:
            raise TraceNotFound(f"Trace {trace_id} not found in Jaeger")

        spans = _parse_jaeger_spans(traces)
        if not spans:
            raise TraceNotFound(f"Trace {trace_id} has zero spans in Jaeger")
        return spans

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
        params: dict[str, str] = {
            "service": service,
            "start": str(int(start.timestamp() * 1_000_000)),  # microseconds
            "end": str(int(end.timestamp() * 1_000_000)),
            "limit": str(limit),
        }
        if min_duration_ms is not None:
            params["minDuration"] = f"{min_duration_ms}ms"
        if max_duration_ms is not None:
            params["maxDuration"] = f"{max_duration_ms}ms"
        if operation:
            params["operation"] = operation
        if tags:
            # Jaeger's tags query wants space-separated JSON-ish string.
            params["tags"] = " ".join(f'"{k}":"{v}"' for k, v in tags.items())

        client = get_client(self._backend_key)
        try:
            resp = await client.get(
                f"{self._base_url}/api/traces",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendUnreachable(
                f"Cannot reach Jaeger find_traces: {e}"
            ) from e

        traces = resp.json().get("data") or []
        summaries = [_summary_from_trace(t) for t in traces]
        summaries = [s for s in summaries if s is not None]

        if has_error is True:
            summaries = [s for s in summaries if s.has_error]
        elif has_error is False:
            summaries = [s for s in summaries if not s.has_error]

        return summaries


# ── Parsers ──────────────────────────────────────────────────────────────


def _parse_jaeger_spans(traces: list[dict]) -> list[SpanInfo]:
    """Flatten Jaeger's `data: [{ spans, processes }]` into SpanInfo list."""
    out: list[SpanInfo] = []
    for trace in traces:
        processes = trace.get("processes") or {}
        for span in trace.get("spans") or []:
            out.append(_parse_single_span(span, processes))
    return out


def _parse_single_span(span: dict, processes: dict) -> SpanInfo:
    process_id = span.get("processID", "")
    process = processes.get(process_id) or {}
    service_name = process.get("serviceName", "unknown")

    # Process-level tags (host, pod, service.version, etc.) — kept separately
    # from span-scoped tags so the redactor can treat them differently later.
    process_tags: dict[str, str] = {
        t["key"]: str(t.get("value", ""))
        for t in process.get("tags") or []
        if t.get("key")
    }

    duration_us = int(span.get("duration") or 0)
    start_time_us = int(span.get("startTime") or 0)

    # Error detection — prefer span.tags.error=true, fall back to
    # http.status_code >=500 / grpc.status_code != OK.
    error = False
    error_msg: Optional[str] = None
    for tag in span.get("tags") or []:
        key = tag.get("key")
        val = tag.get("value")
        if key == "error" and val:
            error = True
        elif key in ("error.message", "error.kind", "error.type") and val:
            error_msg = str(val) if error_msg is None else error_msg
        elif key == "http.status_code":
            try:
                if int(val) >= 500:
                    error = True
            except (TypeError, ValueError):
                pass
        elif key == "otel.status_code" and str(val).upper() == "ERROR":
            error = True

    # Timeout detection — deterministic signal from tags wins over duration.
    status: str = "ok"
    tag_dict = {t.get("key"): t.get("value") for t in span.get("tags") or []}
    if tag_dict.get("error.kind") == "timeout" or str(tag_dict.get("otel.status_code", "")).lower() == "timeout":
        status = "timeout"
    elif error:
        status = "error"

    # Span kind.
    kind_raw = tag_dict.get("span.kind") or tag_dict.get("kind")
    kind_normalized: Optional[str] = None
    if isinstance(kind_raw, str):
        k = kind_raw.lower().strip()
        if k in {"server", "client", "producer", "consumer", "internal"}:
            kind_normalized = k

    # References — walk the list looking for a real parent; fall back to
    # the first reference, whatever it is.
    parent_span_id: Optional[str] = None
    for ref in span.get("references") or []:
        if ref.get("refType") == "CHILD_OF":
            parent_span_id = ref.get("spanID")
            break
    if parent_span_id is None and span.get("references"):
        parent_span_id = span["references"][0].get("spanID")

    # Span-scoped events (structured logs — very useful diagnostic carrier).
    events: list[dict] = []
    for log in span.get("logs") or []:
        event = {"timestamp": log.get("timestamp")}
        for f in log.get("fields") or []:
            if f.get("key"):
                event[f["key"]] = f.get("value")
        events.append(event)

    # Flatten tags into a string->string dict. Values may be bool / int /
    # float / str; str() them for consistent downstream handling. Filter
    # keys we handled separately to avoid dup.
    span_tags: dict[str, str] = {}
    skip_keys = {"error", "error.message", "error.kind", "error.type"}
    for tag in span.get("tags") or []:
        k = tag.get("key")
        if not k or k in skip_keys:
            continue
        v = tag.get("value")
        span_tags[k] = str(v) if v is not None else ""

    return SpanInfo(
        span_id=span.get("spanID", ""),
        service_name=service_name,
        operation_name=span.get("operationName", ""),
        duration_ms=round(duration_us / 1000.0, 2),
        status=status,  # type: ignore[arg-type]
        error_message=error_msg,
        parent_span_id=parent_span_id,
        tags=span_tags,
        start_time_us=start_time_us,
        kind=kind_normalized,  # type: ignore[arg-type]
        events=events,
        process_tags=process_tags,
    )


def _summary_from_trace(trace: dict) -> Optional[TraceSummary]:
    """Build a TraceSummary from a Jaeger search result trace."""
    spans = trace.get("spans") or []
    processes = trace.get("processes") or {}
    if not spans:
        return None

    # Root span = one with no CHILD_OF reference (or first by startTime).
    root = None
    for s in spans:
        refs = s.get("references") or []
        if not any(r.get("refType") == "CHILD_OF" for r in refs):
            root = s
            break
    if root is None:
        root = min(spans, key=lambda s: int(s.get("startTime") or 0))

    root_service = (
        processes.get(root.get("processID", ""), {}).get("serviceName", "unknown")
    )
    start_time_us = int(root.get("startTime") or 0)
    duration_ms = round(int(root.get("duration") or 0) / 1000.0, 2)

    services: set[str] = set()
    error_count = 0
    for s in spans:
        proc = processes.get(s.get("processID", ""), {})
        svc = proc.get("serviceName", "unknown")
        services.add(svc)
        for t in s.get("tags") or []:
            if t.get("key") == "error" and t.get("value"):
                error_count += 1
                break

    return TraceSummary(
        trace_id=root.get("traceID") or trace.get("traceID") or "",
        root_service=root_service,
        root_operation=root.get("operationName", ""),
        start_time_us=start_time_us,
        duration_ms=duration_ms,
        span_count=len(spans),
        error_count=error_count,
        services=sorted(services),
    )


# Runtime sanity check: confirm the class satisfies the protocol.
_: TraceBackend = JaegerBackend(base_url="http://localhost:16686")
