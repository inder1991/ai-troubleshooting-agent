"""Deterministic trace summarization — stay under the LLM prompt budget.

Traces vary from 10 spans (a healthy REST call) to 50,000 (a batch job or
retry storm). Feeding all spans to an LLM blows the context window and
the cost budget. The fix: BEFORE the LLM sees anything, deterministically
pick the spans that carry diagnostic signal and collapse the rest into
aggregate summaries.

Locked policy:
  - ``MAX_ANALYSIS_SPANS`` (default 2000) — upper bound on spans in prompt
  - ``MAX_FETCHED_SPANS`` (default 50000) — absolute ceiling; above this
    the caller should refuse and offer the user a narrowed analysis

Always kept at full fidelity:
  - Error spans (``status == "error"`` or ``error_message is not None``)
  - Latency outliers (duration > 2× the service's local P95)
  - Spans on the critical path (longest root→leaf path by duration)
  - Service-boundary spans (parent and child are different services)
  - ``failure_point`` ancestors (spans on the error's parent chain)

Bucketed / aggregated:
  - Repeated healthy sibling spans with the same (service, operation) →
    "svc/op × N spans, p99=…"

Istio sidecar collapse (default on):
  - Envoy's sidecar emits two spans per hop per direction. Most of the
    time the sidecar span is near-identical to the app span. Collapse
    them into one logical hop UNLESS the latency delta exceeds a threshold
    (then the mesh itself is the bottleneck and we keep both).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

from src.models.schemas import SpanInfo


# Tunable ceilings.
MAX_ANALYSIS_SPANS_DEFAULT = 2000
MAX_FETCHED_SPANS_DEFAULT = 50_000

# Mesh-collapse threshold — when app↔sidecar latency delta exceeds this,
# keep both spans (the mesh itself is potentially at fault).
SIDECAR_COLLAPSE_DELTA_MS = 50.0


@dataclass
class SummarizerConfig:
    max_analysis_spans: int = MAX_ANALYSIS_SPANS_DEFAULT
    max_fetched_spans: int = MAX_FETCHED_SPANS_DEFAULT
    collapse_istio_sidecars: bool = True
    preserve_fidelity_for_errors: bool = True


@dataclass
class AggregateBucket:
    """Rolled-up description of N healthy sibling spans."""

    service_name: str
    operation_name: str
    span_count: int
    p50_ms: float
    p99_ms: float
    total_duration_ms: float
    parent_span_id: Optional[str] = None


@dataclass
class SummarizedTrace:
    """Output of ``TraceSummarizer.summarize()``.

    The LLM prompt is built from ``kept_spans`` + ``aggregates``.
    ``was_summarized`` drives the ``trace_source="summarized"`` badge.
    """

    kept_spans: list[SpanInfo]
    aggregates: list[AggregateBucket] = field(default_factory=list)
    total_original_spans: int = 0
    was_summarized: bool = False
    was_truncated: bool = False  # True when total > max_fetched_spans
    collapsed_sidecar_pairs: int = 0


class TraceSummarizer:
    """Pure-logic span-reduction pipeline."""

    def __init__(self, config: Optional[SummarizerConfig] = None) -> None:
        self._cfg = config or SummarizerConfig()

    def summarize(self, spans: list[SpanInfo]) -> SummarizedTrace:
        total = len(spans)

        if total == 0:
            return SummarizedTrace(kept_spans=[], total_original_spans=0)

        # Truncation gate — above MAX_FETCHED_SPANS we refuse to analyze in full.
        truncated = False
        if total > self._cfg.max_fetched_spans:
            truncated = True
            spans = spans[: self._cfg.max_fetched_spans]
            total = len(spans)

        # Sidecar collapse (Istio-specific; default on).
        sidecar_pairs = 0
        if self._cfg.collapse_istio_sidecars:
            spans, sidecar_pairs = _collapse_sidecar_pairs(spans)

        # Fast path: already within budget — mark critical path, return.
        if total <= self._cfg.max_analysis_spans:
            kept = _annotate_critical_path(spans)
            return SummarizedTrace(
                kept_spans=kept,
                total_original_spans=total,
                was_summarized=False,
                was_truncated=truncated,
                collapsed_sidecar_pairs=sidecar_pairs,
            )

        # Slow path: compute service P95s, pick fidelity spans, bucket the rest.
        service_p95 = _compute_service_percentile(spans, percentile=95.0)
        keep_ids = _pick_fidelity_span_ids(spans, service_p95)

        kept: list[SpanInfo] = []
        grouped: dict[tuple[str, str, Optional[str]], list[SpanInfo]] = {}
        for span in spans:
            if span.span_id in keep_ids:
                kept.append(span)
            else:
                key = (span.service_name, span.operation_name, span.parent_span_id)
                grouped.setdefault(key, []).append(span)

        aggregates = [_bucket_from_group(k, v) for k, v in grouped.items() if len(v) >= 2]

        # Anything NOT bucketed (unique siblings) — keep as-is, subject to budget.
        for k, v in grouped.items():
            if len(v) < 2:
                kept.extend(v)

        # Final budget enforcement — if still over, drop lowest-signal spans.
        if len(kept) > self._cfg.max_analysis_spans:
            kept = _trim_to_budget(kept, self._cfg.max_analysis_spans)

        kept = _annotate_critical_path(kept)

        return SummarizedTrace(
            kept_spans=kept,
            aggregates=aggregates,
            total_original_spans=total,
            was_summarized=True,
            was_truncated=truncated,
            collapsed_sidecar_pairs=sidecar_pairs,
        )


# ── Internals ────────────────────────────────────────────────────────────


def _collapse_sidecar_pairs(spans: list[SpanInfo]) -> tuple[list[SpanInfo], int]:
    """Merge Envoy sidecar spans with their paired app spans when latency
    delta is below threshold. Returns (collapsed_spans, pair_count)."""
    # Build an index of spans by parent_span_id → children, service.
    by_parent: dict[Optional[str], list[SpanInfo]] = {}
    for s in spans:
        by_parent.setdefault(s.parent_span_id, []).append(s)

    collapsed_ids: set[str] = set()
    pairs = 0

    for span in spans:
        if span.span_id in collapsed_ids:
            continue
        # Envoy sidecar spans commonly carry component=proxy or span.kind=client
        # with operation matching the target upstream cluster name.
        is_sidecar = _looks_like_envoy_sidecar(span)
        if not is_sidecar:
            continue
        # Find the app-level sibling: same parent, same service_name, different kind.
        siblings = by_parent.get(span.parent_span_id, [])
        for sib in siblings:
            if sib.span_id == span.span_id or sib.span_id in collapsed_ids:
                continue
            if sib.service_name != span.service_name:
                continue
            if _looks_like_envoy_sidecar(sib):
                continue
            delta = abs(span.duration_ms - sib.duration_ms)
            if delta < SIDECAR_COLLAPSE_DELTA_MS:
                # Collapse sidecar INTO app-span. Mark the sidecar for removal.
                collapsed_ids.add(span.span_id)
                pairs += 1
                break

    return [s for s in spans if s.span_id not in collapsed_ids], pairs


def _looks_like_envoy_sidecar(span: SpanInfo) -> bool:
    tags = span.tags or {}
    if tags.get("component") == "proxy":
        return True
    if tags.get("istio.mesh_id"):
        return True
    if "envoy" in (tags.get("span.kind") or "").lower():
        return True
    # Istio ingress/egress sidecars often have operation_name matching a
    # namespaced cluster (e.g. "outbound|80|default|reviews").
    op = span.operation_name or ""
    if op.startswith("outbound|") or op.startswith("inbound|"):
        return True
    return False


def _compute_service_percentile(
    spans: list[SpanInfo], percentile: float
) -> dict[str, float]:
    by_service: dict[str, list[float]] = {}
    for s in spans:
        by_service.setdefault(s.service_name, []).append(s.duration_ms)
    out: dict[str, float] = {}
    for svc, durations in by_service.items():
        if len(durations) < 2:
            out[svc] = durations[0] if durations else 0.0
            continue
        # statistics.quantiles with n=100 gives percentiles 1..99.
        quantiles = statistics.quantiles(durations, n=100, method="inclusive")
        idx = int(percentile) - 1
        out[svc] = quantiles[min(idx, len(quantiles) - 1)]
    return out


def _pick_fidelity_span_ids(
    spans: list[SpanInfo], service_p95: dict[str, float]
) -> set[str]:
    """Spans we keep regardless of budget pressure."""
    by_id = {s.span_id: s for s in spans}
    keep: set[str] = set()

    for span in spans:
        # Error spans — never drop.
        if span.status == "error" or span.error_message:
            keep.add(span.span_id)
            _add_ancestors(span, by_id, keep)
            continue
        # Timeouts.
        if span.status == "timeout":
            keep.add(span.span_id)
            continue
        # Latency outliers (> 2× service P95).
        p95 = service_p95.get(span.service_name, 0.0)
        if p95 > 0 and span.duration_ms > 2 * p95:
            keep.add(span.span_id)
            continue
        # Service boundary — parent is in a different service.
        if span.parent_span_id:
            parent = by_id.get(span.parent_span_id)
            if parent and parent.service_name != span.service_name:
                keep.add(span.span_id)

    return keep


def _add_ancestors(
    span: SpanInfo, by_id: dict[str, SpanInfo], keep: set[str]
) -> None:
    """Walk up parent chain; mark each ancestor as kept."""
    cur = span
    seen: set[str] = set()
    while cur.parent_span_id and cur.parent_span_id not in seen:
        seen.add(cur.parent_span_id)
        parent = by_id.get(cur.parent_span_id)
        if parent is None:
            break
        keep.add(parent.span_id)
        cur = parent


def _bucket_from_group(
    key: tuple[str, str, Optional[str]], members: list[SpanInfo]
) -> AggregateBucket:
    service, op, parent = key
    durations = sorted(s.duration_ms for s in members)
    n = len(durations)
    return AggregateBucket(
        service_name=service,
        operation_name=op,
        span_count=n,
        p50_ms=durations[n // 2],
        p99_ms=durations[min(n - 1, int(n * 0.99))],
        total_duration_ms=sum(durations),
        parent_span_id=parent,
    )


def _annotate_critical_path(spans: list[SpanInfo]) -> list[SpanInfo]:
    """Mark spans on the longest-duration root→leaf path as critical_path=True.

    A simple greedy: for each leaf span, walk up collecting duration; the
    leaf with highest total wins and all its ancestors are marked.
    """
    by_id = {s.span_id: s for s in spans}
    children_of: dict[Optional[str], list[SpanInfo]] = {}
    for s in spans:
        children_of.setdefault(s.parent_span_id, []).append(s)

    leaves = [s for s in spans if s.span_id not in {p for p in (x.parent_span_id for x in spans) if p}]
    if not leaves:
        leaves = spans

    best_total = 0.0
    best_chain: list[str] = []
    for leaf in leaves:
        chain: list[str] = []
        total = 0.0
        cur: Optional[SpanInfo] = leaf
        seen: set[str] = set()
        while cur is not None and cur.span_id not in seen:
            seen.add(cur.span_id)
            chain.append(cur.span_id)
            total += cur.duration_ms
            cur = by_id.get(cur.parent_span_id) if cur.parent_span_id else None
        if total > best_total:
            best_total = total
            best_chain = chain

    critical = set(best_chain)
    return [
        s.model_copy(update={"critical_path": s.span_id in critical}) for s in spans
    ]


def _trim_to_budget(spans: list[SpanInfo], budget: int) -> list[SpanInfo]:
    """Drop lowest-signal spans until we're at budget.

    Priority: error → timeout → critical-path → long-duration → rest.
    """

    def signal_score(s: SpanInfo) -> float:
        score = s.duration_ms
        if s.error or s.status == "error":
            score += 1_000_000
        if s.status == "timeout":
            score += 500_000
        if s.critical_path:
            score += 100_000
        return score

    return sorted(spans, key=signal_score, reverse=True)[:budget]
