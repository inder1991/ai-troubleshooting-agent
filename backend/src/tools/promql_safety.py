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


# ── PR-C — UI "Run inline" validator ──────────────────────────────────
#
# Distinct from ``validate_promql`` because the UI-driven path has
# different trust assumptions:
#
#   · validate_promql is for agent queries; it enforces the namespace
#     label because agents are constructing queries from trusted
#     templates (promql_library). We don't want an agent bug to sweep
#     the whole cluster.
#
#   · validate_promql_run is for queries typed/selected in the Run-
#     inline affordance. The operator is authoring them, so we don't
#     require a namespace label (they may be legitimately querying
#     cluster-global signals like ``up``). What we DO enforce:
#
#       · range window capped at 4h (enough for ad-hoc reproduction
#         but narrow enough to cap cost/latency)
#       · step must be between 15s and 300s (5m) — prevents both
#         high-resolution blow-ups and 1-point flat lines
#       · reject leading-wildcard label matches (e.g. ``{__name__=~".+"}``)
#         and unscoped metric-wildcard regex (``{__name__=~"..*"}``)
#         that would return every series in the TSDB
#
# Anything that fails these bounds raises ``UnsafeQuery``. Callers
# catch and return a 400 to the frontend.

MAX_RUN_RANGE_S = 4 * 3600       # 4h — ad-hoc reproduction window
MIN_RUN_STEP_S = 15              # lower than agent path (60s) — UI needs finer detail
MAX_RUN_STEP_S = 300             # 5m — higher than this and the chart is a straight line

# Leading-wildcard / metric-wildcard patterns. We reject anything that
# looks like ``__name__=~".*"`` / ``=~".+..."`` — it would match every
# series in the TSDB regardless of other filters and OOM Prometheus.
_METRIC_WILDCARD_RE = re.compile(
    r'__name__\s*=~\s*"(\.[\*\+]|\.[\*\+]\w|\.\*\.\*)', re.IGNORECASE
)
# Leading-wildcard on any label filter: ``=~".*xxx"`` / ``=~".+xxx"``.
_LEADING_WILDCARD_RE = re.compile(r'=~\s*"\.[\*\+]')


def _parse_step(step: str) -> int:
    """Parse a Prometheus step literal ("60s", "2m", "300") to seconds."""
    s = step.strip().lower()
    if not s:
        raise UnsafeQuery("step is required")
    # Bare integer → seconds.
    if s.isdigit():
        return int(s)
    m = re.match(r"^(\d+)([smhdw])$", s)
    if not m:
        raise UnsafeQuery(
            f"step {step!r} not a valid duration (e.g. 60s, 2m)"
        )
    return _to_secs(int(m.group(1)), m.group(2))


def validate_promql_run(
    query: str,
    start: str,
    end: str,
    step: str,
) -> None:
    """Validate a UI-originated PromQL range query.

    ``start`` and ``end`` are RFC3339 strings or unix seconds (int-as-str)
    — same formats Prometheus accepts for /api/v1/query_range.

    Raises ``UnsafeQuery`` on any violation. Returns None on success.
    """
    if not query or not query.strip():
        raise UnsafeQuery("empty PromQL query")
    if len(query) > MAX_QUERY_LEN:
        raise UnsafeQuery(
            f"query length {len(query)} exceeds max {MAX_QUERY_LEN}"
        )

    # Destructive-pattern guard — reject queries that would return every
    # series in the TSDB.
    if _METRIC_WILDCARD_RE.search(query):
        raise UnsafeQuery(
            "metric-wildcard (__name__=~'.*' / '.+') is not allowed — "
            "scope to a specific metric"
        )
    if _LEADING_WILDCARD_RE.search(query):
        raise UnsafeQuery(
            "leading-wildcard label match (=~'.*...' / =~'.+...') is not "
            "allowed — use a specific prefix or exact match"
        )

    # Step bounds.
    step_s = _parse_step(step)
    if step_s < MIN_RUN_STEP_S:
        raise UnsafeQuery(
            f"step {step_s}s below minimum {MIN_RUN_STEP_S}s for UI run"
        )
    if step_s > MAX_RUN_STEP_S:
        raise UnsafeQuery(
            f"step {step_s}s above maximum {MAX_RUN_STEP_S}s for UI run"
        )

    # Window bounds. Accept RFC3339 or unix-seconds (int-as-str).
    start_s = _parse_ts(start)
    end_s = _parse_ts(end)
    if end_s <= start_s:
        raise UnsafeQuery("end must be strictly after start")
    span_s = end_s - start_s
    if span_s > MAX_RUN_RANGE_S:
        raise UnsafeQuery(
            f"range {span_s}s exceeds max {MAX_RUN_RANGE_S}s "
            f"({MAX_RUN_RANGE_S // 3600}h) for UI run"
        )


def _parse_ts(ts: str) -> float:
    """Accept unix-seconds (int-as-str) or RFC3339."""
    s = ts.strip()
    if not s:
        raise UnsafeQuery("timestamp is required")
    # Unix seconds (possibly float).
    try:
        return float(s)
    except ValueError:
        pass
    # RFC3339 — best-effort.
    from datetime import datetime
    try:
        # Handle trailing 'Z' for UTC.
        s_iso = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s_iso).timestamp()
    except ValueError as e:
        raise UnsafeQuery(f"timestamp {ts!r} not a valid unix-seconds or RFC3339") from e
