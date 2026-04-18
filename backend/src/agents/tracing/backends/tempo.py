"""Tempo backend — inherits Jaeger endpoints where possible, overrides search.

Tempo exposes a Jaeger-compatible query API at ``/api/traces/{id}`` and
``/api/services``. Its search endpoint diverges from Jaeger's (different
param names, different response shape), so that's where we override.

Reference: https://grafana.com/docs/tempo/latest/api_docs/
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import httpx

from src.integrations.http_clients import get_client
from src.models.schemas import TraceSummary
from src.utils.logger import get_logger

from .base import BackendUnreachable, TraceBackend
from .jaeger import JaegerBackend

logger = get_logger(__name__)


class TempoBackend(JaegerBackend):
    """Tempo TraceBackend — reuses Jaeger's get_trace + list_services paths.

    Key differences from Jaeger:
      - Tempo's search endpoint is ``/api/search`` (not ``/api/traces``).
      - Duration params are in Go-duration strings ("100ms", "5s").
      - Response shape is ``{"traces": [...]}`` not ``{"data": [...]}``.
      - Each search result is already a summary (no embedded spans), which
        means we can skip the span-walk step that Jaeger needs.
    """

    backend_id = "tempo"

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
        # Tempo's search uses TraceQL-style params. We build the tags param
        # using TraceQL syntax: `{ resource.service.name="checkout" }`.
        traceql_parts = [f'resource.service.name="{service}"']
        if operation:
            traceql_parts.append(f'name="{operation}"')
        if tags:
            for k, v in tags.items():
                traceql_parts.append(f'.{k}="{v}"')

        params: dict[str, str] = {
            "q": "{ " + " && ".join(traceql_parts) + " }",
            "start": str(int(start.timestamp())),  # Tempo: seconds, not µs
            "end": str(int(end.timestamp())),
            "limit": str(limit),
        }
        if min_duration_ms is not None:
            params["minDuration"] = f"{min_duration_ms}ms"
        if max_duration_ms is not None:
            params["maxDuration"] = f"{max_duration_ms}ms"

        client = get_client(self._backend_key)
        try:
            resp = await client.get(
                f"{self._base_url}/api/search",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendUnreachable(f"Cannot reach Tempo search: {e}") from e

        body = resp.json()
        traces = body.get("traces") or []
        summaries = [_summary_from_tempo_trace(t) for t in traces]
        summaries = [s for s in summaries if s is not None]

        if has_error is True:
            summaries = [s for s in summaries if s.has_error]
        elif has_error is False:
            summaries = [s for s in summaries if not s.has_error]

        return summaries


def _summary_from_tempo_trace(trace: dict) -> Optional[TraceSummary]:
    """Tempo search returns shape:
        {"traceID": "...", "rootServiceName": "...", "rootTraceName": "...",
         "startTimeUnixNano": "...", "durationMs": N, "spanSet": {"spans": [...]}}
    """
    trace_id = trace.get("traceID")
    if not trace_id:
        return None

    # Tempo returns startTime in nanoseconds as a string.
    start_ns_raw = trace.get("startTimeUnixNano") or "0"
    try:
        start_ns = int(start_ns_raw)
    except (TypeError, ValueError):
        start_ns = 0
    start_time_us = start_ns // 1000

    span_set = trace.get("spanSet") or {}
    matched_spans = span_set.get("spans") or []
    # Heuristic error count — Tempo doesn't give the full span list in a
    # search result; only the matched ones. Check their attributes.
    error_count = 0
    services: set[str] = set()
    if trace.get("rootServiceName"):
        services.add(trace["rootServiceName"])
    for s in matched_spans:
        for attr in s.get("attributes") or []:
            if attr.get("key") in {"error", "otel.status_code"}:
                val = (attr.get("value") or {})
                raw = val.get("stringValue") or val.get("boolValue")
                if raw in (True, "true", "True", "ERROR", "error"):
                    error_count += 1
                    break

    return TraceSummary(
        trace_id=trace_id,
        root_service=trace.get("rootServiceName", "unknown"),
        root_operation=trace.get("rootTraceName", ""),
        start_time_us=start_time_us,
        duration_ms=float(trace.get("durationMs") or 0),
        span_count=int(trace.get("spanSet", {}).get("matched") or len(matched_spans)),
        error_count=error_count,
        services=sorted(services),
    )


# Runtime sanity check.
_: TraceBackend = TempoBackend(base_url="http://localhost:3100")
