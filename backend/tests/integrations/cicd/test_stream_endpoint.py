from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.integrations.cicd.base import DeployEvent, InstanceError, ResolveResult


def _event(name="svc-a", ts=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
           source="jenkins", status="success"):
    return DeployEvent(
        source=source,
        source_id=f"{name}#1",
        name=name,
        status=status,
        started_at=ts,
        url=f"https://j/{name}/1/",
    )


def _client_stub(name: str, source: str, events: list):
    c = MagicMock()
    c.source = source
    c.name = name
    c.list_deploy_events = AsyncMock(return_value=events)
    return c


@pytest.fixture
def http():
    from src.api.main import app
    return TestClient(app)


def test_stream_endpoint_merges_sources_sorted_desc(http):
    old = _event("svc-a", datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc))
    new = _event("svc-b", datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc))
    fake = _client_stub("prod-jenkins", "jenkins", [old, new])
    with patch(
        "src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[fake], argocd=[], errors=[])),
    ):
        resp = http.get("/api/v4/cicd/stream?cluster_id=c1&since=2026-04-10T12:00:00Z")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == ["svc-b#1", "svc-a#1"]


def test_stream_endpoint_returns_partial_on_source_failure(http):
    good = _client_stub("g", "jenkins", [_event()])
    bad = MagicMock()
    bad.source = "argocd"; bad.name = "b"
    bad.list_deploy_events = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(
        "src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[good], argocd=[bad], errors=[])),
    ):
        resp = http.get("/api/v4/cicd/stream?cluster_id=c1&since=2026-04-10T12:00:00Z")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert len(body["source_errors"]) == 1
    err = body["source_errors"][0]
    assert err["name"] == "b"
    assert err["source"] == "argocd"


def test_stream_endpoint_surfaces_resolver_errors(http):
    with patch(
        "src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(
            jenkins=[], argocd=[],
            errors=[InstanceError(name="bad-jenkins", source="jenkins", message="auth failed")],
        )),
    ):
        resp = http.get("/api/v4/cicd/stream?cluster_id=c1&since=2026-04-10T12:00:00Z")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["source_errors"] == [
        {"name": "bad-jenkins", "source": "jenkins", "message": "auth failed"},
    ]


def test_stream_endpoint_empty_when_nothing_configured(http):
    with patch(
        "src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[], argocd=[], errors=[])),
    ):
        resp = http.get("/api/v4/cicd/stream?cluster_id=c1&since=2026-04-10T12:00:00Z")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_stream_endpoint_mixes_commits_when_git_repo_provided(http):
    fake = _client_stub("prod", "jenkins", [_event()])
    commits = [
        {"sha": "deadbeef12", "author": "alice",
         "date": "2026-04-10T13:30:00Z",
         "message": "fix: null guard in checkout handler"},
    ]
    with patch(
        "src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(jenkins=[fake], argocd=[], errors=[])),
    ), patch(
        "src.api.routes_v4.GitHubClient"
    ) as GH:
        GH.return_value.get_commits = AsyncMock(return_value=commits)
        resp = http.get(
            "/api/v4/cicd/stream?cluster_id=c1"
            "&since=2026-04-10T12:00:00Z&git_repo=acme/checkout-api"
        )
    assert resp.status_code == 200
    body = resp.json()
    ids = [i["id"] for i in body["items"]]
    assert "svc-a#1" in ids
    assert "deadbeef12" in ids


def test_stream_endpoint_requires_cluster_id(http):
    resp = http.get("/api/v4/cicd/stream?since=2026-04-10T12:00:00Z")
    assert resp.status_code == 422  # missing required query param
