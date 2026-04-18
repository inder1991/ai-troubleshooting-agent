"""JaegerBackend parser + search-response-handling tests.

Network I/O is mocked via patching the shared httpx client so we exercise
response-parsing logic without a real Jaeger.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.tracing.backends.base import BackendUnreachable, TraceNotFound
from src.agents.tracing.backends.jaeger import (
    JaegerBackend,
    _parse_jaeger_spans,
    _summary_from_trace,
)


# ── Parser (pure) ────────────────────────────────────────────────────────


def test_parse_simple_trace():
    traces = [
        {
            "traceID": "t1",
            "processes": {"p1": {"serviceName": "api", "tags": []}},
            "spans": [
                {
                    "spanID": "s1", "processID": "p1",
                    "operationName": "GET /api", "duration": 100_000,
                    "startTime": 1_700_000_000_000_000,
                    "tags": [{"key": "http.status_code", "value": 200},
                             {"key": "span.kind", "value": "server"}],
                }
            ],
        }
    ]
    spans = _parse_jaeger_spans(traces)
    assert len(spans) == 1
    assert spans[0].service_name == "api"
    assert spans[0].duration_ms == 100.0
    assert spans[0].kind == "server"
    assert spans[0].start_time_us == 1_700_000_000_000_000


def test_parse_http_5xx_marks_error():
    traces = [{
        "processes": {"p1": {"serviceName": "svc"}},
        "spans": [{
            "spanID": "s1", "processID": "p1", "operationName": "op",
            "duration": 10_000,
            "tags": [{"key": "http.status_code", "value": 503}],
        }],
    }]
    spans = _parse_jaeger_spans(traces)
    assert spans[0].status == "error"


def test_parse_otel_status_error_marks_error():
    traces = [{
        "processes": {"p1": {"serviceName": "svc"}},
        "spans": [{
            "spanID": "s1", "processID": "p1", "operationName": "op",
            "duration": 10_000,
            "tags": [{"key": "otel.status_code", "value": "ERROR"}],
        }],
    }]
    spans = _parse_jaeger_spans(traces)
    assert spans[0].status == "error"


def test_parse_child_of_reference_picked_over_follows_from():
    traces = [{
        "processes": {"p1": {"serviceName": "svc"}},
        "spans": [{
            "spanID": "child", "processID": "p1", "operationName": "op", "duration": 1,
            "references": [
                {"refType": "FOLLOWS_FROM", "spanID": "follow"},
                {"refType": "CHILD_OF", "spanID": "parent"},
            ],
        }],
    }]
    spans = _parse_jaeger_spans(traces)
    assert spans[0].parent_span_id == "parent"


def test_parse_events_captured_from_logs():
    traces = [{
        "processes": {"p1": {"serviceName": "svc"}},
        "spans": [{
            "spanID": "s1", "processID": "p1", "operationName": "op", "duration": 1,
            "logs": [
                {"timestamp": 1_700_000_000_000_000,
                 "fields": [{"key": "event", "value": "retry_started"},
                            {"key": "attempt", "value": 2}]},
            ],
        }],
    }]
    spans = _parse_jaeger_spans(traces)
    assert len(spans[0].events) == 1
    assert spans[0].events[0].get("event") == "retry_started"


def test_parse_process_tags_separate_from_span_tags():
    traces = [{
        "processes": {
            "p1": {"serviceName": "svc",
                   "tags": [{"key": "k8s.pod.name", "value": "pod-abc"}]}
        },
        "spans": [{
            "spanID": "s1", "processID": "p1", "operationName": "op", "duration": 1,
            "tags": [{"key": "http.method", "value": "POST"}],
        }],
    }]
    spans = _parse_jaeger_spans(traces)
    assert spans[0].tags == {"http.method": "POST"}
    assert spans[0].process_tags == {"k8s.pod.name": "pod-abc"}


def test_summary_from_trace():
    trace = {
        "processes": {"p1": {"serviceName": "api"}, "p2": {"serviceName": "db"}},
        "spans": [
            {"spanID": "root", "processID": "p1", "operationName": "GET",
             "duration": 100_000, "startTime": 1000, "references": []},
            {"spanID": "child", "processID": "p2", "operationName": "SELECT",
             "duration": 50_000, "references": [{"refType": "CHILD_OF", "spanID": "root"}],
             "tags": [{"key": "error", "value": True}]},
        ],
    }
    s = _summary_from_trace(trace)
    assert s is not None
    assert s.root_service == "api"
    assert s.span_count == 2
    assert s.error_count == 1
    assert set(s.services) == {"api", "db"}


# ── HTTP integration (mocked) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_services_filters_internal_services():
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.json = lambda: {"data": ["checkout", "jaeger-query", "inventory", "otel-collector"]}
    mock_resp.raise_for_status = lambda: None
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.agents.tracing.backends.jaeger.get_client", return_value=mock_client):
        backend = JaegerBackend("http://j:16686")
        services = await backend.list_services()

    assert services == ["checkout", "inventory"]


@pytest.mark.asyncio
async def test_get_trace_raises_not_found_on_empty():
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.json = lambda: {"data": []}
    mock_resp.raise_for_status = lambda: None
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.agents.tracing.backends.jaeger.get_client", return_value=mock_client):
        backend = JaegerBackend("http://j:16686")
        with pytest.raises(TraceNotFound):
            await backend.get_trace("missing-trace")


@pytest.mark.asyncio
async def test_find_traces_client_side_error_filter():
    """When has_error=True, client-side filter keeps only error-carrying."""
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.json = lambda: {"data": [
        {"traceID": "healthy", "processes": {"p1": {"serviceName": "svc"}},
         "spans": [{"spanID": "r", "processID": "p1", "operationName": "ok",
                    "duration": 1, "startTime": 0, "references": []}]},
        {"traceID": "errored", "processes": {"p1": {"serviceName": "svc"}},
         "spans": [{"spanID": "r", "processID": "p1", "operationName": "err",
                    "duration": 1, "startTime": 0, "references": [],
                    "tags": [{"key": "error", "value": True}]}]},
    ]}
    mock_resp.raise_for_status = lambda: None
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.agents.tracing.backends.jaeger.get_client", return_value=mock_client):
        backend = JaegerBackend("http://j:16686")
        res = await backend.find_traces(
            "svc",
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            has_error=True,
        )

    assert len(res) == 1 and res[0].trace_id == "errored"


@pytest.mark.asyncio
async def test_list_services_raises_unreachable_on_http_error():
    import httpx
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("src.agents.tracing.backends.jaeger.get_client", return_value=mock_client):
        backend = JaegerBackend("http://j:16686")
        with pytest.raises(BackendUnreachable):
            await backend.list_services()
