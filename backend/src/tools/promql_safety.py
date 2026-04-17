"""PromQL safety middleware (Task 1.11).

Every Prometheus query issued by the agents flows through
``validate_promql`` before dispatch. Unsafe queries raise
``UnsafeQuery`` and never reach the server.

Bounds:
- Namespace label required on every query (``namespace="..."`` or
  ``namespace=~"..."``) — no cluster-wide scans.
- Duration suffix support: s, m, h, d, w (year `y` rejected outright).
- Range capped at 7 days.
- Step minimum 60s.
- Cardinality (range ÷ step) capped at 100_000 points per series.
- Query string length capped at 10_000 chars so attacker-controlled
  PromQL from logs / tool calls can't embed megabytes of regex.
"""
from __future__ import annotations

import re


MAX_RANGE_S = 7 * 24 * 3600       # 7 days
MIN_STEP_S = 60                   # 1-minute granularity
MAX_CARDINALITY_POINTS = 100_000  # per-series cap
MAX_QUERY_LEN = 10_000


class UnsafeQuery(ValueError):
    """Raised when a PromQL query violates any safety bound."""


# Matches a duration literal like ``[5m]`` / ``[300s]`` / ``[1h]``.
# Captures (value, unit). Year 'y' is deliberately omitted so ``[1y]``
# slips through the unit loop and is rejected by the "no known
# duration" catch.
_DURATION_RE = re.compile(r"\[(\d+)([smhdw])\]")
# Namespace label filter. Accepts ``namespace="foo"`` or ``namespace=~"..."``
# or ``namespace!="..."``.
_NAMESPACE_RE = re.compile(r'namespace\s*[=~!]+\s*"[^"]+"')
# Year/any-other unit duration — used for explicit rejection with a
# clearer error message when the user supplies ``[1y]`` etc.
_ANY_DURATION_RE = re.compile(r"\[(\d+)([a-zA-Z]+)\]")


_UNIT_SECONDS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 7 * 86400,
}


def _to_secs(value: int, unit: str) -> int:
    try:
        return value * _UNIT_SECONDS[unit]
    except KeyError as e:
        raise UnsafeQuery(
            f"unsupported duration unit {unit!r}; allowed: s, m, h, d, w"
        ) from e


def validate_promql(
    query: str,
    *,
    step_s: int = 60,
    range_h: int = 24,
) -> None:
    """Raise UnsafeQuery if the query violates any safety bound; return
    None on success. The caller is expected to call this BEFORE
    dispatching to Prometheus.

    ``step_s`` and ``range_h`` are the dispatch-time parameters the
    caller will send to ``/api/v1/query_range`` — they are validated
    alongside the query text so the cardinality check has full info.
    """
    if not query or not query.strip():
        raise UnsafeQuery("empty PromQL query")
    if len(query) > MAX_QUERY_LEN:
        raise UnsafeQuery(
            f"query length {len(query)} exceeds max {MAX_QUERY_LEN}"
        )
    if step_s <= 0:
        raise UnsafeQuery(f"step {step_s}s must be positive")

    # Cheap reject: any duration whose unit is outside our allow-list
    # (e.g. 1y) fails here with a specific message.
    for m in _ANY_DURATION_RE.finditer(query):
        unit = m.group(2)
        if unit not in _UNIT_SECONDS:
            raise UnsafeQuery(
                f"duration unit {unit!r} rejected (range likely too large); "
                f"allowed: s, m, h, d, w"
            )

    # Range bound + cardinality check on every [..] duration literal.
    # Cardinality runs BEFORE the step minimum check so an obviously
    # blown-up (range, step) pair like 7d×1s reports 'cardinality' —
    # the most actionable reason — rather than the looser 'step too
    # small' message.
    for m in _DURATION_RE.finditer(query):
        secs = _to_secs(int(m.group(1)), m.group(2))
        if secs > MAX_RANGE_S:
            raise UnsafeQuery(
                f"range {secs}s exceeds max {MAX_RANGE_S}s ({secs // 86400}d > 7d)"
            )
        if (secs / step_s) > MAX_CARDINALITY_POINTS:
            raise UnsafeQuery(
                f"cardinality {int(secs / step_s)} exceeds max "
                f"{MAX_CARDINALITY_POINTS} points (range={secs}s / step={step_s}s)"
            )

    if step_s < MIN_STEP_S:
        raise UnsafeQuery(
            f"step {step_s}s below minimum {MIN_STEP_S}s"
        )

    # Namespace label must be present.
    if not _NAMESPACE_RE.search(query):
        raise UnsafeQuery(
            "namespace label required (use namespace=\"...\" or namespace=~\"...\")"
        )

    # Separate range_h bound check in case the caller passed a larger
    # dispatch window than any [..] duration in the query.
    if range_h * 3600 > MAX_RANGE_S:
        raise UnsafeQuery(
            f"range_h {range_h}h exceeds max {MAX_RANGE_S // 3600}h"
        )
