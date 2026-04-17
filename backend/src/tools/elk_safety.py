"""Elasticsearch / OpenSearch query allowlist (Task 1.12).

``validate_elk_query(body)`` inspects a search body BEFORE dispatch
and rejects unsafe shapes:

- ``query_string.query`` with a leading ``*`` or ``?`` — a leading
  wildcard forces ES to walk every doc in every segment and is the
  classic log-search DoS.
- ``query_string.query`` with no field qualifier (no ``default_field``,
  no ``fields``, and no ``field:value`` in the query text) — this is
  an implicit cross-field scan against every mapped field.
- Any ``script`` query — arbitrary scoring / filter code.
- ``size > MAX_HITS_PER_PAGE`` (default 5_000). Deep pagination must
  use search_after / scroll, not a single giant page.
- Time range: a ``range.@timestamp`` clause must be present at the
  top level or inside a bool; its ``gte`` must be ≤ 7 days from now.

A missing ``@timestamp`` range is a cluster-wide scan — rejected.
"""
from __future__ import annotations

import re
from typing import Any


MAX_HITS_PER_PAGE = 5_000
MAX_RANGE_DAYS = 7


class UnsafeQuery(ValueError):
    """Raised when an ES/OS query body violates any safety bound."""


# Matches "now-<N><unit>" or "now" for ES relative-time syntax.
_NOW_RE = re.compile(r"^now(?:([-+])(\d+)([smhdwMy]))?$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
# We do NOT support M (month) / y (year) in relative time — both are
# longer than 7d and will always fail the range check, so reject them
# explicitly with a clearer error message.
_UNSUPPORTED_UNITS = {"M", "y"}


def _now_to_seconds_from_now(value: Any) -> int | None:
    """Parse an ES relative-time string like ``now-1h`` or ``now-7d``
    into seconds-before-now. Returns None if the value isn't
    relative-time syntax (absolute timestamps are out of scope for
    this validator — callers get the safe-by-default treatment of the
    caller-enforced dispatch envelope). Raises UnsafeQuery for
    explicitly-unsupported units (M, y)."""
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    if s == "now":
        return 0
    # Normalise case only for the 'now-' prefix — the unit letter case
    # matters (M vs m).
    s_case_preserve = value.strip()
    m = re.match(r"^now([-+])(\d+)([smhdwMy])$", s_case_preserve)
    if not m:
        return None
    sign, num, unit = m.group(1), int(m.group(2)), m.group(3)
    if unit in _UNSUPPORTED_UNITS:
        raise UnsafeQuery(
            f"time range unit {unit!r} unsupported (max 7d); use s/m/h/d/w"
        )
    mult = _UNIT_SECONDS.get(unit)
    if mult is None:
        return None
    secs = num * mult
    return secs if sign == "-" else -secs


def _check_query_string(qs: dict) -> None:
    query = qs.get("query")
    if not isinstance(query, str):
        raise UnsafeQuery("query_string.query must be a non-empty string")
    if not query.strip():
        raise UnsafeQuery("query_string.query must not be empty")
    # Reject leading wildcards.
    if query.lstrip('"(').startswith(("*", "?")):
        raise UnsafeQuery(
            "query_string with leading wildcard rejected (walks every doc)"
        )
    # Require a field qualifier of some kind.
    has_default_field = "default_field" in qs
    has_fields_list = "fields" in qs and qs["fields"]
    has_field_colon = bool(re.search(r"\b\w+\s*:\s*\S", query))
    if not (has_default_field or has_fields_list or has_field_colon):
        raise UnsafeQuery(
            "query_string without default_field/fields/field:value is a "
            "cluster-wide scan; qualify the query"
        )


def _walk_for_issues(node: Any, *, found_range: list) -> None:
    """Depth-first walk of the query body. Rejects ``script`` and
    records whether a valid ``range.@timestamp`` clause exists."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "script":
                raise UnsafeQuery("script queries rejected (arbitrary code)")
            if k == "query_string" and isinstance(v, dict):
                _check_query_string(v)
            if k == "range" and isinstance(v, dict) and "@timestamp" in v:
                ts = v["@timestamp"]
                if not isinstance(ts, dict):
                    raise UnsafeQuery("range.@timestamp must be an object")
                gte = ts.get("gte")
                if gte is None:
                    raise UnsafeQuery("range.@timestamp.gte required")
                secs_back = _now_to_seconds_from_now(gte)
                if secs_back is None:
                    # Absolute timestamps — let them through; the caller
                    # is responsible for the envelope. Still counts as a
                    # range clause so we don't reject for "no time range".
                    found_range.append(True)
                else:
                    if secs_back > MAX_RANGE_DAYS * 86400:
                        raise UnsafeQuery(
                            f"time range {gte!r} exceeds max "
                            f"{MAX_RANGE_DAYS}d window"
                        )
                    found_range.append(True)
            _walk_for_issues(v, found_range=found_range)
    elif isinstance(node, list):
        for item in node:
            _walk_for_issues(item, found_range=found_range)


def validate_elk_query(body: dict) -> None:
    """Raise ``UnsafeQuery`` if the ES/OS search body violates any
    safety bound; return None on success. Caller dispatches the body
    unchanged to ``/_search``."""
    if not isinstance(body, dict):
        raise UnsafeQuery("query body must be a dict")

    size = body.get("size")
    if size is not None:
        if not isinstance(size, int) or size < 0:
            raise UnsafeQuery("size must be a non-negative integer")
        if size > MAX_HITS_PER_PAGE:
            raise UnsafeQuery(
                f"size {size} exceeds max {MAX_HITS_PER_PAGE} hits per page"
            )

    found_range: list = []
    _walk_for_issues(body, found_range=found_range)
    if not found_range:
        raise UnsafeQuery(
            "no @timestamp time range clause — cluster-wide scan rejected"
        )
