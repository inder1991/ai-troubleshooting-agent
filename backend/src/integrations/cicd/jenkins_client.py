from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Literal

import aiohttp

from src.integrations.cicd.base import (
    Build, CICDClientError, DeployEvent, DeployStatus, SyncDiff,
)

_STATUS_MAP: dict[str | None, DeployStatus] = {
    "SUCCESS": "success",
    "FAILURE": "failed",
    "ABORTED": "aborted",
    "UNSTABLE": "failed",
    None: "in_progress",
}

_GIT_URL_RE = re.compile(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$")


def _normalize_repo(url: str | None) -> str | None:
    if not url:
        return None
    m = _GIT_URL_RE.search(url)
    return m.group(1) if m else None


class JenkinsClient:
    source: Literal["jenkins"] = "jenkins"

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str,
        instance_name: str,
        timeout_s: float = 10.0,
        max_concurrency: int = 5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.name = instance_name
        self._auth = aiohttp.BasicAuth(username, api_token)
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._sem = asyncio.Semaphore(max_concurrency)

    async def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession(
                auth=self._auth, timeout=self._timeout
            ) as s:
                async with s.get(url) as resp:
                    if resp.status == 401 or resp.status == 403:
                        raise CICDClientError(
                            source="jenkins", instance=self.name,
                            kind="auth", message=f"{resp.status}",
                        )
                    if resp.status >= 500:
                        raise CICDClientError(
                            source="jenkins", instance=self.name,
                            kind="network", message=f"{resp.status}",
                        )
                    resp.raise_for_status()
                    return await resp.json()
        except asyncio.TimeoutError as e:
            raise CICDClientError(
                source="jenkins", instance=self.name,
                kind="timeout", message=str(e),
            ) from e
        except aiohttp.ClientError as e:
            raise CICDClientError(
                source="jenkins", instance=self.name,
                kind="network", message=str(e),
            ) from e

    async def list_deploy_events(
        self,
        since: datetime,
        until: datetime,
        target_filter: str | None = None,
    ) -> list[DeployEvent]:
        jobs_payload = await self._get_json("/api/json?tree=jobs[name,url]")
        jobs = jobs_payload.get("jobs", [])

        async def fetch_job(job: dict[str, Any]) -> list[DeployEvent]:
            async with self._sem:
                job_name = job["name"]
                job_payload = await self._get_json(
                    f"/job/{job_name}/api/json?tree=builds[number,url]"
                )
                events: list[DeployEvent] = []
                for b in job_payload.get("builds", [])[:20]:
                    detail = await self._get_json(
                        f"/job/{job_name}/{b['number']}/api/json"
                    )
                    ev = self._parse_build(job_name, detail)
                    if since <= ev.started_at <= until:
                        events.append(ev)
                return events

        results = await asyncio.gather(
            *[fetch_job(j) for j in jobs], return_exceptions=False
        )
        return [ev for sub in results for ev in sub]

    def _parse_build(self, job_name: str, detail: dict[str, Any]) -> DeployEvent:
        ts = datetime.fromtimestamp(detail["timestamp"] / 1000, tz=timezone.utc)
        duration_ms = detail.get("duration", 0) or 0
        finished = (
            datetime.fromtimestamp((detail["timestamp"] + duration_ms) / 1000,
                                   tz=timezone.utc)
            if duration_ms
            else None
        )
        status = _STATUS_MAP.get(detail.get("result"), "unknown")
        git_sha: str | None = None
        git_repo: str | None = None
        triggered_by: str | None = None
        for action in detail.get("actions", []):
            rev = action.get("lastBuiltRevision") if isinstance(action, dict) else None
            if rev:
                git_sha = rev.get("SHA1")
            remotes = action.get("remoteUrls") if isinstance(action, dict) else None
            if remotes:
                git_repo = _normalize_repo(remotes[0])
            causes = action.get("causes") if isinstance(action, dict) else None
            if causes and isinstance(causes, list):
                triggered_by = causes[0].get("userName") or causes[0].get("userId")
        return DeployEvent(
            source="jenkins",
            source_id=f"{job_name}#{detail['number']}",
            name=job_name,
            status=status,
            started_at=ts,
            finished_at=finished,
            git_sha=git_sha,
            git_repo=git_repo,
            git_ref=None,
            triggered_by=triggered_by,
            url=detail.get("url", ""),
            target=None,
        )

    async def get_build_artifacts(self, event: DeployEvent) -> Build | SyncDiff:
        raise NotImplementedError  # Task 6

    async def health_check(self) -> bool:
        raise NotImplementedError  # Task 6
