"""Unit tests for GitHubClient helper."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.integrations.github_client import GitHubClient, GitHubClientError


def _mock_response(status_code: int = 200, json_data=None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_data if json_data is not None else [])
    resp.raise_for_status = MagicMock()
    resp.text = ""
    return resp


def _commit(sha: str, author: str, date: str, message: str) -> dict:
    return {
        "sha": sha,
        "commit": {
            "author": {"name": author, "date": date},
            "message": message,
        },
    }


@pytest.mark.asyncio
async def test_get_commits_parses_payload():
    payload = [
        _commit("abcdef1234567890", "alice", "2026-04-10T10:00:00Z", "fix: null pointer"),
        _commit("1234567890abcdef", "bob", "2026-04-10T11:00:00Z", "chore: bump deps"),
    ]

    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_mock_response(200, payload))
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.github_client.httpx.AsyncClient", return_value=fake_ctx):
        client = GitHubClient(token="t")
        result = await client.get_commits("acme/widgets", since_hours=24)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["sha"] == "abcdef12"
    assert result[0]["author"] == "alice"
    assert result[0]["date"] == "2026-04-10T10:00:00Z"
    assert "fix: null pointer" in result[0]["message"]


@pytest.mark.asyncio
async def test_get_commits_falls_back_when_window_empty():
    commits_payload = [
        _commit("aaaa0000bbbb1111", "carol", "2026-04-09T10:00:00Z", "feat: thing"),
        _commit("cccc2222dddd3333", "dan", "2026-04-09T11:00:00Z", "refactor"),
    ]
    responses = [_mock_response(200, []), _mock_response(200, commits_payload)]

    fake_client = MagicMock()
    fake_client.get = AsyncMock(side_effect=responses)
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.github_client.httpx.AsyncClient", return_value=fake_ctx):
        client = GitHubClient(token="t")
        result = await client.get_commits("acme/widgets", since_hours=24)

    assert len(result) == 2
    assert fake_client.get.await_count == 2


@pytest.mark.asyncio
async def test_get_commit_diff_truncates_large_patches():
    big_patch = "x" * 3000
    payload = {
        "commit": {
            "message": "big refactor",
            "author": {"name": "eve"},
        },
        "files": [
            {
                "filename": "src/a.py",
                "status": "modified",
                "additions": 10,
                "deletions": 5,
                "patch": big_patch,
            }
        ],
    }

    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_mock_response(200, payload))
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.github_client.httpx.AsyncClient", return_value=fake_ctx):
        client = GitHubClient(token="t")
        result = await client.get_commit_diff("acme/widgets", "deadbeef")

    assert result["commit_sha"] == "deadbeef"
    assert result["author"] == "eve"
    assert len(result["files"]) == 1
    patch_out = result["files"][0]["patch"]
    assert len(patch_out) <= 1500 + len("\n... (truncated)")
    assert patch_out.endswith("... (truncated)")


@pytest.mark.asyncio
async def test_get_commits_raises_on_401():
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_mock_response(401))
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.github_client.httpx.AsyncClient", return_value=fake_ctx):
        client = GitHubClient(token="")
        with pytest.raises(GitHubClientError, match="authentication required"):
            await client.get_commits("acme/widgets", since_hours=24)


@pytest.mark.asyncio
async def test_get_commits_raises_on_404():
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_mock_response(404))
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.github_client.httpx.AsyncClient", return_value=fake_ctx):
        client = GitHubClient(token="t")
        with pytest.raises(GitHubClientError, match="not found"):
            await client.get_commits("acme/widgets", since_hours=24)


@pytest.mark.asyncio
async def test_get_commits_raises_on_connect_error():
    fake_client = MagicMock()
    fake_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.github_client.httpx.AsyncClient", return_value=fake_ctx):
        client = GitHubClient(token="t")
        with pytest.raises(GitHubClientError, match="connection failed"):
            await client.get_commits("acme/widgets", since_hours=24)


@pytest.mark.asyncio
async def test_get_commit_diff_raises_on_404():
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=_mock_response(404))
    fake_ctx = MagicMock()
    fake_ctx.__aenter__ = AsyncMock(return_value=fake_client)
    fake_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.github_client.httpx.AsyncClient", return_value=fake_ctx):
        client = GitHubClient(token="t")
        with pytest.raises(GitHubClientError):
            await client.get_commit_diff("acme/widgets", "deadbeef")
