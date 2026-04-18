"""ELK log-reconstruction fallback — when Jaeger/Tempo can't help.

Used when:
  1. Primary trace backend returns "no data" for the requested trace_id.
  2. Primary trace backend is unreachable entirely.

Reconstructs a best-effort call chain from log entries matching the
trace_id across several common correlation-field conventions. The output
is intentionally LOWER confidence than real spans — callers must reflect
this in the trace_source + ``elk_reconstruction_confidence`` fields.

Key improvements over the v0 implementation:
  * Async httpx via shared ``get_client("elasticsearch")`` (K.5).
  * Bounded time window — REQUIRED, no more full-index scans.
  * Broader field coverage including OTel conventions.
  * Retry-aware chain reconstruction — consecutive same-service ERRORs
    are clustered so we don't mark 3 retries as 3 separate failures.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

from src.integrations.http_clients import get_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Correlation field names we try, in priority order. Order matters because
# OTel conventions are more trustworthy than ad-hoc request-ID headers.
_CORRELATION_FIELDS = [
    "trace_id",
    "traceId",
    "otel.trace_id",
    "trace.id",
    "TraceID",
    "span.trace_id",
    "correlation_id",
    "request_id",
    "x-request-id",
    "X-Request-ID",
]


@dataclass
class ReconstructedHop:
    """A single hop in the log-reconstructed call chain."""

    service_name: str
    timestamp: str  # ISO 8601 from Elasticsearch
    message: str
    level: str
    status: str  # "ok" | "error" | "timeout"
    is_retry_of_previous: bool = False


@dataclass
class ReconstructionResult:
    hops: list[ReconstructedHop]
    services: list[str]
    total_logs: int
    confidence: int  # 0-100 — deterministic, not LLM-derived


class ElkLogReconstructor:
    """Async reconstructor — 1 ES query, pure-logic chain building."""

    def __init__(self, es_base_url: str, *, auth_header: Optional[str] = None) -> None:
        self._base_url = es_base_url.rstrip("/")
        self._auth_header = auth_header

    async def reconstruct(
        self,
        trace_id: str,
        *,
        start: datetime,
        end: datetime,
        index: str = "app-logs-*",
        size: int = 500,
    ) -> ReconstructionResult:
        """Returns the reconstructed chain, or an empty-hop result when no
        matching logs were found. Never raises on "no data" — callers
        distinguish via ``hops == []``."""

        should_clauses = [{"match": {f: trace_id}} for f in _CORRELATION_FIELDS]
        query_body = {
            "size": size,
            "sort": [{"@timestamp": {"order": "asc"}}],
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": start.isoformat(),
                                    "lte": end.isoformat(),
                                }
                            }
                        }
                    ],
                    "should": should_clauses,
                    "minimum_should_match": 1,
                }
            },
        }

        headers = {"Content-Type": "application/json"}
        if self._auth_header:
            headers["Authorization"] = self._auth_header

        client = get_client("elasticsearch")
        try:
            resp = await client.post(
                f"{self._base_url}/{index}/_search",
                json=query_body,
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("ELK reconstruction: query failed: %s", e)
            return ReconstructionResult(hops=[], services=[], total_logs=0, confidence=0)

        hits = (resp.json().get("hits") or {}).get("hits") or []
        return _hops_from_hits(hits, trace_id)


# ── Pure-logic chain reconstruction ──────────────────────────────────────


def _hops_from_hits(hits: list[dict], trace_id: str) -> ReconstructionResult:
    if not hits:
        return ReconstructionResult(hops=[], services=[], total_logs=0, confidence=0)

    raw_hops: list[ReconstructedHop] = []
    services_seen: set[str] = set()

    for hit in hits:
        src = hit.get("_source") or {}
        service = _extract_service(src)
        level = (src.get("level") or src.get("log.level") or "INFO").upper()
        message = src.get("message") or ""

        status = "ok"
        if level in ("ERROR", "FATAL", "CRITICAL"):
            status = "error"
        elif "timeout" in message.lower() or "timed out" in message.lower():
            status = "timeout"

        services_seen.add(service)
        raw_hops.append(
            ReconstructedHop(
                service_name=service,
                timestamp=src.get("@timestamp", ""),
                message=str(message)[:300],  # truncate overly long log lines
                level=level,
                status=status,
            )
        )

    # Retry-aware clustering: consecutive ERROR hops from the SAME service
    # within ~1 second are likely retries — flag all but the first as
    # retry_of_previous so downstream doesn't report N failure points.
    _mark_retry_clusters(raw_hops)

    confidence = _score_confidence(raw_hops, len(services_seen))

    return ReconstructionResult(
        hops=raw_hops,
        services=sorted(services_seen),
        total_logs=len(hits),
        confidence=confidence,
    )


def _extract_service(src: dict) -> str:
    """Try several common shapes for 'what service emitted this log'."""
    if v := src.get("service"):
        return str(v) if isinstance(v, str) else str(v.get("name", "unknown"))
    if v := src.get("service.name"):
        return str(v)
    k8s = src.get("kubernetes") or {}
    if container := k8s.get("container"):
        if isinstance(container, dict):
            return str(container.get("name", "unknown"))
    if ns := src.get("namespace"):
        return str(ns)
    return "unknown"


def _mark_retry_clusters(hops: list[ReconstructedHop]) -> None:
    """Mark consecutive same-service ERROR hops as retries (except the first)."""
    prev: Optional[ReconstructedHop] = None
    for hop in hops:
        if (
            prev is not None
            and prev.status == "error"
            and hop.status == "error"
            and hop.service_name == prev.service_name
        ):
            hop.is_retry_of_previous = True
        prev = hop


def _score_confidence(hops: list[ReconstructedHop], service_count: int) -> int:
    """Deterministic 0-100 confidence for an ELK-reconstructed chain.

    High confidence requires: multiple services, enough log density, and
    some diagnostic signal (at least one ERROR marking the failure).
    """
    if not hops:
        return 0
    score = 0

    # Service diversity — 1 service = probably missing hops.
    if service_count >= 3:
        score += 30
    elif service_count == 2:
        score += 20
    else:
        score += 10

    # Log density — ≥ 10 hops gives a coherent picture.
    if len(hops) >= 20:
        score += 30
    elif len(hops) >= 10:
        score += 20
    elif len(hops) >= 5:
        score += 10

    # Error presence — at least one ERROR hop means we have a candidate failure point.
    if any(h.status == "error" and not h.is_retry_of_previous for h in hops):
        score += 25
    if any(h.status == "timeout" for h in hops):
        score += 15

    return min(score, 100)
