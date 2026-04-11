"""Minimal GitHub REST client used by ChangeAgent and related tooling.

Extracted from the ad-hoc HTTP code that previously lived inside
``src.agents.change_agent``. Returns typed dicts (not JSON strings), so
callers can format however they wish.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx

from src.utils.logger import get_logger

logger = get_logger(__name__)


class GitHubClientError(Exception):
    """Raised when the GitHub API returns an error or is unreachable."""


class GitHubClient:
    """Small async helper around the GitHub REST API.

    Only implements the two operations ChangeAgent needs today:
    listing recent commits and fetching a single commit's diff.
    """

    def __init__(self, token: str = "") -> None:
        self._token = token or os.getenv("GITHUB_TOKEN", "")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    @staticmethod
    def _format_commit(c: dict) -> dict:
        return {
            "sha": c["sha"][:8],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"],
            "message": c["commit"]["message"][:200],
        }

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    async def get_commits(
        self, owner_repo: str, since_hours: int = 24
    ) -> list[dict]:
        """Return recent commits for ``owner/repo``.

        If no commits land in the ``since_hours`` window, falls back to
        the last 10 commits so callers still see something.
        """
        since_iso = (
            datetime.now(timezone.utc) - timedelta(hours=since_hours)
        ).isoformat()
        url = f"https://api.github.com/repos/{owner_repo}/commits"
        headers = self._headers()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    url,
                    headers=headers,
                    params={"per_page": 20, "since": since_iso},
                )
                if resp.status_code == 401:
                    raise GitHubClientError(
                        "authentication required — set GITHUB_TOKEN"
                    )
                if resp.status_code == 404:
                    raise GitHubClientError(
                        f"repository not found — {owner_repo}"
                    )
                resp.raise_for_status()
                commits = resp.json()

                if not commits:
                    resp = await client.get(
                        url, headers=headers, params={"per_page": 10}
                    )
                    resp.raise_for_status()
                    commits = resp.json()
                    if commits:
                        logger.info(
                            "No commits in last %dh for %s, falling back to last %d",
                            since_hours,
                            owner_repo,
                            len(commits),
                        )
        except httpx.HTTPStatusError as exc:
            raise GitHubClientError(
                f"{exc.response.status_code} {exc.response.text[:200]}"
            ) from exc
        except httpx.ConnectError as exc:
            raise GitHubClientError("connection failed") from exc
        except httpx.TimeoutException as exc:
            raise GitHubClientError("request timed out") from exc

        return [self._format_commit(c) for c in commits]

    async def get_commit_diff(
        self, owner_repo: str, commit_sha: str
    ) -> dict:
        """Return file-level diff for a single commit.

        Limits output to 15 files and truncates any single patch longer
        than 1500 chars (matches the historical ChangeAgent behavior).
        """
        url = f"https://api.github.com/repos/{owner_repo}/commits/{commit_sha}"
        headers = self._headers()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 401:
                    raise GitHubClientError(
                        "authentication required — set GITHUB_TOKEN"
                    )
                if resp.status_code == 404:
                    raise GitHubClientError(
                        f"commit not found: {commit_sha}"
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise GitHubClientError(
                f"{exc.response.status_code}"
            ) from exc
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise GitHubClientError(
                "connection failed or timed out"
            ) from exc

        files_out: list[dict] = []
        for f in (data.get("files") or [])[:15]:
            patch = f.get("patch", "") or ""
            if len(patch) > 1500:
                patch = patch[:1500] + "\n... (truncated)"
            files_out.append(
                {
                    "filename": f.get("filename", ""),
                    "status": f.get("status", ""),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                    "patch": patch,
                }
            )

        return {
            "commit_sha": commit_sha,
            "message": (data.get("commit", {}) or {}).get("message", "")[:200],
            "author": (
                (data.get("commit", {}) or {}).get("author", {}) or {}
            ).get("name", ""),
            "files": files_out,
        }
