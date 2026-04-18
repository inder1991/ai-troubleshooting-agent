"""App-level retry cluster detector.

Catches retry patterns that Envoy's ``URX`` flag won't — application-level
retries (gRPC interceptors, promise.retry loops, custom retry policies).

Rule:
  ≥ 3 sibling spans with same ``(service_name, operation_name)`` under the
  same parent, where the first N-1 attempts have non-OK status.

Severity:
  3-4 attempts   medium
  5+ attempts    high
  All fail       critical (independent of count)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from src.models.schemas import PatternFinding, SpanInfo


_DEFAULT_MIN_ATTEMPTS = 3


class RetryClusterDetector:
    kind = "app_level_retry"

    def __init__(self, min_attempts: int = _DEFAULT_MIN_ATTEMPTS) -> None:
        self._min = min_attempts

    def detect(self, spans: list[SpanInfo]) -> list[PatternFinding]:
        if not spans:
            return []

        groups: dict[tuple[Optional[str], str, str], list[SpanInfo]] = defaultdict(list)
        for s in spans:
            if not s.parent_span_id:
                continue
            groups[(s.parent_span_id, s.service_name, s.operation_name)].append(s)

        findings: list[PatternFinding] = []
        for (parent_id, service, op), members in groups.items():
            if len(members) < self._min:
                continue

            # Sort by start_time_us when present; otherwise use insertion order.
            members_sorted = sorted(
                members,
                key=lambda m: m.start_time_us if m.start_time_us is not None else 0,
            )

            non_ok_count = sum(1 for m in members_sorted if m.status != "ok")
            # Retry cluster requires failure on early attempts, not random misses.
            # Rule: at least the first N-1 attempts must be non-OK.
            first_nminus1 = members_sorted[: len(members_sorted) - 1]
            if not first_nminus1 or not all(m.status != "ok" for m in first_nminus1):
                continue

            final_outcome = members_sorted[-1].status
            first_error = members_sorted[0].error_message or "(no error message)"
            all_failed = final_outcome != "ok"
            severity = _severity_for_cluster(len(members_sorted), all_failed)
            findings.append(
                PatternFinding(
                    kind="app_level_retry",
                    confidence=_confidence_for_cluster(len(members_sorted), non_ok_count),
                    severity=severity,
                    human_summary=(
                        f"App-level retry cluster: {service}/{op} attempted "
                        f"{len(members_sorted)} times under one parent span. "
                        f"Final outcome: {final_outcome}. First-attempt error: "
                        f"{first_error}. Retries are masking the root cause — "
                        f"investigate the first attempt's diagnostic signal."
                    ),
                    span_ids_involved=[m.span_id for m in members_sorted],
                    service_name=service,
                    metadata={
                        "parent_span_id": parent_id,
                        "operation": op,
                        "attempts": len(members_sorted),
                        "non_ok_count": non_ok_count,
                        "final_outcome": final_outcome,
                        "first_error_message": first_error,
                        "all_failed": all_failed,
                    },
                )
            )
        return findings


# ── helpers ──────────────────────────────────────────────────────────────


def _severity_for_cluster(attempts: int, all_failed: bool) -> str:
    if all_failed:
        return "critical"
    if attempts >= 5:
        return "high"
    return "medium"


def _confidence_for_cluster(attempts: int, failures: int) -> int:
    base = 65 + min((attempts - 3) * 5, 20)
    if failures >= attempts - 1:
        base += 5
    return min(base, 95)
