"""Task 1.12 — Elasticsearch / OpenSearch query allowlist.

LLM-driven log search can hallucinate leading-wildcard queries
(``*error*``), unbounded time ranges (``now-30d``), or scripted queries
— any of which can take down the ES cluster.

``validate_elk_query(body)`` inspects the search body BEFORE dispatch
and rejects unsafe shapes.
"""
from __future__ import annotations

import pytest


def test_reject_leading_wildcard_query_string():
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="leading wildcard"):
        validate_elk_query({"query": {"query_string": {"query": "*error*"}}})


def test_reject_leading_question_mark_query_string():
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="leading wildcard"):
        validate_elk_query({"query": {"query_string": {"query": "?error"}}})


def test_reject_query_string_without_field_qualifier():
    """A bare ``query_string.query`` with no ``default_field``/``fields``
    and no ``field:value`` qualifier fans out across every mapped
    field — this is how accidental cluster-wide scans happen."""
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery

    with pytest.raises(UnsafeQuery):
        validate_elk_query({"query": {"query_string": {"query": "500"}}})


def test_accept_query_string_with_default_field():
    from src.tools.elk_safety import validate_elk_query

    validate_elk_query({
        "size": 100,
        "query": {
            "bool": {
                "must": [
                    {"query_string": {"query": "500", "default_field": "status"}}
                ],
                "filter": [
                    {"range": {"@timestamp": {"gte": "now-1h", "lte": "now"}}},
                ],
            },
        },
    })


def test_accept_query_string_with_field_qualifier():
    from src.tools.elk_safety import validate_elk_query

    validate_elk_query({
        "size": 100,
        "query": {
            "bool": {
                "must": [
                    {"query_string": {"query": 'level:"ERROR" AND service:"api"'}}
                ],
                "filter": [
                    {"range": {"@timestamp": {"gte": "now-1h", "lte": "now"}}},
                ],
            },
        },
    })


def test_reject_unbounded_time_range():
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="time range"):
        validate_elk_query({
            "query": {"range": {"@timestamp": {"gte": "now-30d", "lte": "now"}}}
        })


def test_reject_missing_time_range_on_top_level():
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery

    # No range filter at all — cluster-wide.
    with pytest.raises(UnsafeQuery, match="time range"):
        validate_elk_query({"query": {"match_all": {}}, "size": 100})


def test_reject_script_query():
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="script"):
        validate_elk_query({
            "query": {"script": {"script": {"source": "doc['x'].value * 2"}}}
        })


def test_reject_size_over_limit():
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery, MAX_HITS_PER_PAGE

    with pytest.raises(UnsafeQuery, match="size"):
        validate_elk_query({
            "query": {"range": {"@timestamp": {"gte": "now-1h", "lte": "now"}}},
            "size": MAX_HITS_PER_PAGE + 1,
        })


def test_accept_size_at_limit():
    from src.tools.elk_safety import validate_elk_query, MAX_HITS_PER_PAGE

    validate_elk_query({
        "query": {"range": {"@timestamp": {"gte": "now-1h", "lte": "now"}}},
        "size": MAX_HITS_PER_PAGE,
    })


def test_accept_nested_bool_with_range_filter():
    """Real-world queries nest a range inside bool.filter."""
    from src.tools.elk_safety import validate_elk_query

    validate_elk_query({
        "size": 100,
        "query": {
            "bool": {
                "must": [{"match_phrase": {"service": "checkout"}}],
                "filter": [
                    {"range": {"@timestamp": {"gte": "now-2h", "lte": "now"}}},
                ],
            }
        },
    })


def test_reject_range_exceeding_7d():
    """Time range > 7d is outside the safety envelope (matches the
    PromQL bound and ES-capacity reality)."""
    from src.tools.elk_safety import validate_elk_query, UnsafeQuery

    with pytest.raises(UnsafeQuery, match="time range"):
        validate_elk_query({
            "size": 100,
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"@timestamp": {"gte": "now-8d", "lte": "now"}}},
                    ],
                }
            },
        })


def test_accept_time_range_7d_boundary():
    from src.tools.elk_safety import validate_elk_query

    validate_elk_query({
        "size": 100,
        "query": {
            "bool": {
                "filter": [
                    {"range": {"@timestamp": {"gte": "now-7d", "lte": "now"}}},
                ],
            }
        },
    })
