from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

import aiohttp

from src.integrations.cicd.audit_hook import record_cicd_read
from src.integrations.cicd.base import (
    Build, CICDClientError, DeployEvent, DeployStatus, SyncDiff,
)

logger = logging.getLogger(__name__)

_MAX_BUILDS_PER_JOB = 50  # bound per-job work; newest-first, break on age
_LOG_TAIL_LINES = 200  # console log tail size for Build.log_tail

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
    """Jenkins CI/CD client (Phase A — read-path).

    NOTE: currently opens a fresh aiohttp.ClientSession per request.
    This is intentional for Phase A simplicity. A shared-session refactor
    is planned before Phase B, tracked as part of the resolver wiring.
    """

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

    async def _get_text(self, path: str) -> str:
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession(
                auth=self._auth, timeout=self._timeout
            ) as s:
                async with s.get(url) as resp:
                    if resp.status in (401, 403):
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
                    return await resp.text()
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
        record_cicd_read(self.source, self.name, "list_deploy_events")
        jobs_payload = await self._get_json("/api/json?tree=jobs[name,url]")
        jobs = jobs_payload.get("jobs", [])

        # TODO(phase-b): URL-encode job_name here too (see get_build_artifacts);
        # keeping as-is in this commit to scope the review fix narrowly.
        async def fetch_job(job: dict[str, Any]) -> list[DeployEvent]:
            async with self._sem:
                job_name = job["name"]
                job_payload = await self._get_json(
                    f"/job/{job_name}/api/json?tree=builds[number,url]"
                )
                events: list[DeployEvent] = []
                for b in job_payload.get("builds", [])[:_MAX_BUILDS_PER_JOB]:
                    detail = await self._get_json(
                        f"/job/{job_name}/{b['number']}/api/json"
                    )
                    ev = self._parse_build(job_name, detail)
                    if ev.started_at < since:
                        break  # newest-first — all remaining builds are older than window
                    if ev.started_at <= until:
                        events.append(ev)
                return events

        results = await asyncio.gather(
            *[fetch_job(j) for j in jobs], return_exceptions=True
        )
        events: list[DeployEvent] = []
        for job, result in zip(jobs, results):
            if isinstance(result, Exception):
                logger.warning(
                    "jenkins list_deploy_events: job %s failed: %s",
                    job.get("name"), result,
                )
                continue
            events.extend(result)
        return events

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
        for action in detail.get("actions") or []:
            if not isinstance(action, dict):
                continue
            rev = action.get("lastBuiltRevision")
            if rev and git_sha is None:
                git_sha = rev.get("SHA1")
            remotes = action.get("remoteUrls")
            if remotes and git_repo is None:
                git_repo = _normalize_repo(remotes[0])
            causes = action.get("causes")
            if causes and isinstance(causes, list) and triggered_by is None:
                first_cause = causes[0] if isinstance(causes[0], dict) else {}
                triggered_by = first_cause.get("userName") or first_cause.get("userId")
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
        """Fetch build detail + console log tail for a given DeployEvent.

        `failed_stage` is extracted by regex matching on
        ``[Pipeline] stage '<name>' FAILED`` markers in the log tail. This is
        an intentional convention: teams are expected to emit these markers
        from a shared Jenkins pipeline library step on stage failure. We do
        NOT attempt to parse raw Jenkins console output — if the marker is
        absent, ``failed_stage`` will be ``None``.
        """
        record_cicd_read(self.source, self.name, "get_build_artifacts")
        job_name, sep, num = event.source_id.partition("#")
        if not sep or not num:
            raise CICDClientError(
                source="jenkins",
                instance=self.name,
                kind="unknown",
                message=f"invalid source_id {event.source_id!r}: expected 'job#build'",
            )
        # Preserve '/' for folder-plugin nested job paths (e.g. folder/subjob).
        encoded_job = quote(job_name, safe="/")
        detail = await self._get_json(f"/job/{encoded_job}/{num}/api/json")
        log = await self._get_text(f"/job/{encoded_job}/{num}/consoleText")
        params: dict[str, str] = {}
        for action in detail.get("actions") or []:
            if not isinstance(action, dict):
                continue
            for p in action.get("parameters") or []:
                if isinstance(p, dict) and "name" in p:
                    params[p["name"]] = str(p.get("value", ""))
        tail_lines = log.splitlines()[-_LOG_TAIL_LINES:]
        log_tail = "\n".join(tail_lines)
        failed_stage: str | None = None
        m = re.search(r"\[Pipeline\] stage ['\"]?([^'\"]+)['\"]? FAILED", log_tail)
        if m:
            failed_stage = m.group(1)
        return Build(
            event=event, parameters=params, log_tail=log_tail,
            failed_stage=failed_stage,
        )

    async def health_check(self) -> bool:
        record_cicd_read(self.source, self.name, "health_check")
        try:
            await self._get_json("/api/json?tree=mode")
            return True
        except CICDClientError:
            return False
