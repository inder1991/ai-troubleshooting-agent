"""ElkLogReconstructor — retry-aware chain reconstruction tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.tracing.elk_reconstructor import (
    ElkLogReconstructor,
    _hops_from_hits,
    _score_confidence,
)


# ── Pure-logic ───────────────────────────────────────────────────────────


def test_empty_hits_returns_zero():
    res = _hops_from_hits([], "abc")
    assert res.hops == []
    assert res.confidence == 0


def test_error_hop_marked_error():
    hits = [{"_source": {"service": "svc", "@timestamp": "2026-04-18T10:00:00Z",
                         "message": "boom", "level": "ERROR"}}]
    res = _hops_from_hits(hits, "abc")
    assert res.hops[0].status == "error"


def test_timeout_detected_in_message():
    hits = [{"_source": {"service": "svc", "@timestamp": "...",
                         "message": "request timed out", "level": "INFO"}}]
    res = _hops_from_hits(hits, "abc")
    assert res.hops[0].status == "timeout"


def test_retry_clusters_marked_but_not_first():
    """Consecutive ERRORs from same service → all but first are flagged retries."""
    hits = [
        {"_source": {"service": "db", "@timestamp": "T1", "message": "fail1", "level": "ERROR"}},
        {"_source": {"service": "db", "@timestamp": "T2", "message": "fail2", "level": "ERROR"}},
        {"_source": {"service": "db", "@timestamp": "T3", "message": "fail3", "level": "ERROR"}},
    ]
    res = _hops_from_hits(hits, "abc")
    assert res.hops[0].is_retry_of_previous is False  # first is the actual failure
    assert res.hops[1].is_retry_of_previous is True
    assert res.hops[2].is_retry_of_previous is True


def test_retry_cluster_breaks_on_different_service():
    hits = [
        {"_source": {"service": "api", "@timestamp": "T1", "message": "err", "level": "ERROR"}},
        {"_source": {"service": "db", "@timestamp": "T2", "message": "err", "level": "ERROR"}},
    ]
    res = _hops_from_hits(hits, "abc")
    assert all(h.is_retry_of_previous is False for h in res.hops)


def test_service_extraction_from_kubernetes_shape():
    hits = [{
        "_source": {
            "kubernetes": {"container": {"name": "checkout-api"}},
            "@timestamp": "T", "message": "m", "level": "INFO",
        }
    }]
    res = _hops_from_hits(hits, "abc")
    assert res.hops[0].service_name == "checkout-api"


def test_service_extraction_from_service_name_field():
    hits = [{"_source": {"service.name": "inventory", "@timestamp": "T",
                         "message": "m", "level": "INFO"}}]
    res = _hops_from_hits(hits, "abc")
    assert res.hops[0].service_name == "inventory"


def test_confidence_increases_with_diversity_and_errors():
    low = _score_confidence([], 0)
    assert low == 0

    # 2 hops, 1 service, no errors — low
    from src.agents.tracing.elk_reconstructor import ReconstructedHop
    tiny = [ReconstructedHop(service_name="a", timestamp="T", message="m", level="INFO", status="ok"),
            ReconstructedHop(service_name="a", timestamp="T", message="m", level="INFO", status="ok")]
    conf1 = _score_confidence(tiny, 1)

    # 20 hops, 3 services, with error — much higher
    big = [ReconstructedHop(service_name=f"s{i%3}", timestamp="T", message="m",
                            level="INFO" if i != 10 else "ERROR",
                            status="ok" if i != 10 else "error")
           for i in range(20)]
    conf2 = _score_confidence(big, 3)

    assert conf2 > conf1


# ── HTTP (mocked) ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconstruct_includes_time_window_in_query():
    captured = {}
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.json = lambda: {"hits": {"hits": []}}
    mock_resp.raise_for_status = lambda: None

    async def fake_post(*a, **kw):
        captured["body"] = kw.get("json")
        return mock_resp

    mock_client.post = fake_post

    with patch("src.agents.tracing.elk_reconstructor.get_client", return_value=mock_client):
        r = ElkLogReconstructor("http://es:9200")
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=15)
        await r.reconstruct("abc-123", start=start, end=end)

    assert "body" in captured
    must = captured["body"]["query"]["bool"]["must"]
    assert any("range" in m and "@timestamp" in m["range"] for m in must), \
        "query body must include a time-window range filter"


@pytest.mark.asyncio
async def test_reconstruct_queries_multiple_correlation_fields():
    captured = {}
    mock_client = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.json = lambda: {"hits": {"hits": []}}
    mock_resp.raise_for_status = lambda: None

    async def fake_post(*a, **kw):
        captured["body"] = kw.get("json")
        return mock_resp

    mock_client.post = fake_post

    with patch("src.agents.tracing.elk_reconstructor.get_client", return_value=mock_client):
        r = ElkLogReconstructor("http://es:9200")
        await r.reconstruct(
            "tid",
            start=datetime.now(timezone.utc) - timedelta(minutes=5),
            end=datetime.now(timezone.utc),
        )

    shoulds = captured["body"]["query"]["bool"]["should"]
    fields = set()
    for s in shoulds:
        if "match" in s:
            fields.update(s["match"].keys())

    # We must cover at least the OTel + common conventions.
    assert "trace_id" in fields
    assert "traceId" in fields
    assert "otel.trace_id" in fields
    assert "correlation_id" in fields
