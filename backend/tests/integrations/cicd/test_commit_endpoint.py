from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.integrations.github_client import GitHubClientError


@pytest.fixture
def http():
    from src.api.main import app
    return TestClient(app)


def test_commit_detail_returns_commit_and_files(http):
    fake = {
        "commit_sha": "abc123",
        "message": "fix: null guard",
        "author": "gunjan",
        "files": [
            {"filename": "src/cart.ts", "status": "modified",
             "additions": 4, "deletions": 1, "patch": "@@ ... @@"},
        ],
    }
    with patch("src.api.routes_v4.GitHubClient") as GH:
        GH.return_value.get_commit_diff = AsyncMock(return_value=fake)
        resp = http.get("/api/v4/cicd/commit/acme/checkout-api/abc123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["commit_sha"] == "abc123"
    assert len(body["files"]) == 1
    assert body["files"][0]["filename"] == "src/cart.ts"


def test_commit_detail_returns_429_on_rate_limit(http):
    with patch("src.api.routes_v4.GitHubClient") as GH:
        GH.return_value.get_commit_diff = AsyncMock(
            side_effect=GitHubClientError("API rate limit exceeded"),
        )
        resp = http.get("/api/v4/cicd/commit/acme/checkout-api/abc123")
    assert resp.status_code == 429


def test_commit_detail_returns_404_on_not_found(http):
    with patch("src.api.routes_v4.GitHubClient") as GH:
        GH.return_value.get_commit_diff = AsyncMock(
            side_effect=GitHubClientError("repository not found"),
        )
        resp = http.get("/api/v4/cicd/commit/acme/checkout-api/abc123")
    assert resp.status_code == 404


def test_commit_detail_returns_502_on_generic_failure(http):
    with patch("src.api.routes_v4.GitHubClient") as GH:
        GH.return_value.get_commit_diff = AsyncMock(
            side_effect=GitHubClientError("connection failed"),
        )
        resp = http.get("/api/v4/cicd/commit/acme/checkout-api/abc123")
    assert resp.status_code == 502
