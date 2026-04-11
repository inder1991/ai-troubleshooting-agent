from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Literal

import aiohttp

from src.integrations.cicd.base import (
    CICDClientError,
    DeployEvent,
    DeployStatus,
    SyncDiff,
    SyncHealth,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 10.0
_DEFAULT_MAX_CONCURRENCY = 5

_PHASE_MAP: dict[str, DeployStatus] = {
    "Succeeded": "success",
    "Failed": "failed",
    "Error": "failed",
    "Running": "in_progress",
    "Terminating": "aborted",
}

_HEALTH_MAP: dict[str, SyncHealth] = {
    "Healthy": "healthy",
    "Degraded": "degraded",
    "Progressing": "progressing",
    "Suspended": "suspended",
    "Missing": "missing",
}


def _normalize_repo(url: str | None) -> str | None:
    if not url:
        return None
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class ArgoCDClient:
    """ArgoCD CI/CD client (Phase A — read-path).

    Supports two connection modes:
      - ``rest``: hits the ArgoCD HTTP API with a bearer token.
      - ``kubeconfig``: reads Application CRs directly via a cluster client
        (see Task 8 for coverage).

    NOTE: currently opens a fresh ``aiohttp.ClientSession`` per request to
    mirror ``JenkinsClient``. A shared-session refactor is planned before
    Phase B.
    """

    source: Literal["argocd"] = "argocd"

    def __init__(
        self,
        mode: Literal["rest", "kubeconfig"],
        instance_name: str,
        base_url: str | None = None,
        token: str | None = None,
        cluster_client: Any = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self.mode = mode
        self.name = instance_name
        self.base_url = (base_url or "").rstrip("/")
        self._token = token
        self._cluster = cluster_client
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._sem = asyncio.Semaphore(max_concurrency)

    @classmethod
    def from_rest(
        cls, base_url: str, token: str, instance_name: str,
    ) -> "ArgoCDClient":
        return cls(
            mode="rest",
            base_url=base_url,
            token=token,
            instance_name=instance_name,
        )

    @classmethod
    def from_kubeconfig(
        cls, cluster_client: Any, instance_name: str = "in-cluster",
    ) -> "ArgoCDClient":
        return cls(
            mode="kubeconfig",
            cluster_client=cluster_client,
            instance_name=instance_name,
        )

    @classmethod
    async def probe_crds(cls, cluster_client: Any) -> bool:
        try:
            return await cluster_client.has_crd("applications.argoproj.io")
        except Exception:
            return False

    async def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = (
            {"Authorization": f"Bearer {self._token}"} if self._token else {}
        )
        try:
            async with self._sem:
                # TODO(phase-b): share a single ClientSession across calls.
                async with aiohttp.ClientSession(timeout=self._timeout) as s:
                    async with s.get(url, headers=headers) as resp:
                        if resp.status in (401, 403):
                            raise CICDClientError(
                                source="argocd",
                                instance=self.name,
                                kind="auth",
                                message=f"{resp.status}",
                            )
                        if resp.status == 429:
                            raise CICDClientError(
                                source="argocd",
                                instance=self.name,
                                kind="rate_limit",
                                message="429",
                            )
                        if resp.status >= 500:
                            raise CICDClientError(
                                source="argocd",
                                instance=self.name,
                                kind="network",
                                message=f"{resp.status}",
                            )
                        resp.raise_for_status()
                        return await resp.json()
        except asyncio.TimeoutError as e:
            raise CICDClientError(
                source="argocd",
                instance=self.name,
                kind="timeout",
                message=str(e),
            ) from e
        except aiohttp.ClientError as e:
            raise CICDClientError(
                source="argocd",
                instance=self.name,
                kind="network",
                message=str(e),
            ) from e

    async def _fetch_apps(self) -> list[dict[str, Any]]:
        if self.mode == "rest":
            payload = await self._get_json("/api/v1/applications")
            items = (payload or {}).get("items") or []
            return items if isinstance(items, list) else []
        # kubeconfig mode — exercised by Task 8.
        result = await self._cluster.list_custom_resource(
            group="argoproj.io", version="v1alpha1", plural="applications",
        )
        return result or []

    async def list_deploy_events(
        self,
        since: datetime,
        until: datetime,
        target_filter: str | None = None,
    ) -> list[DeployEvent]:
        apps = await self._fetch_apps()
        events: list[DeployEvent] = []
        for app in apps or []:
            if not isinstance(app, dict):
                continue
            meta = app.get("metadata") or {}
            spec = app.get("spec") or {}
            status = app.get("status") or {}
            op = status.get("operationState") or {}
            if not op:
                continue
            started = _parse_iso(op.get("startedAt"))
            if not started or not (since <= started <= until):
                continue
            destination = spec.get("destination") or {}
            dest_ns = destination.get("namespace")
            if target_filter and dest_ns != target_filter:
                continue
            source_spec = spec.get("source") or {}
            sync_result = op.get("syncResult") or {}
            sync_status = status.get("sync") or {}
            phase = op.get("phase", "")
            name = meta.get("name") or "unknown"
            revision = (
                sync_result.get("revision")
                or sync_status.get("revision")
            )
            events.append(
                DeployEvent(
                    source="argocd",
                    source_id=f"{name}@{sync_result.get('revision') or 'unknown'}",
                    name=name,
                    status=_PHASE_MAP.get(phase, "unknown"),
                    started_at=started,
                    finished_at=_parse_iso(op.get("finishedAt")),
                    git_sha=revision,
                    git_repo=_normalize_repo(source_spec.get("repoURL")),
                    git_ref=source_spec.get("targetRevision"),
                    triggered_by=None,
                    url=(
                        f"{self.base_url}/applications/{name}"
                        if self.mode == "rest"
                        else ""
                    ),
                    target=dest_ns,
                )
            )
        return events

    async def get_build_artifacts(self, event: DeployEvent) -> SyncDiff:
        apps = await self._fetch_apps()
        target: dict[str, Any] | None = None
        for a in apps or []:
            if not isinstance(a, dict):
                continue
            meta = a.get("metadata") or {}
            if meta.get("name") == event.name:
                target = a
                break
        if target is None:
            raise CICDClientError(
                source="argocd",
                instance=self.name,
                kind="parse",
                message=f"app {event.name} not found",
            )
        status = target.get("status") or {}
        health_obj = status.get("health") or {}
        health = health_obj.get("status", "Unknown")
        resources = status.get("resources") or []
        out_of_sync = [
            r
            for r in resources
            if isinstance(r, dict) and r.get("status") != "Synced"
        ]
        return SyncDiff(
            event=event,
            health=_HEALTH_MAP.get(health, "unknown"),
            out_of_sync_resources=out_of_sync,
            manifest_diff="",
        )

    async def health_check(self) -> bool:
        try:
            await self._fetch_apps()
            return True
        except CICDClientError:
            return False
        except Exception:
            return False
