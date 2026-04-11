from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

DeployStatus = Literal["success", "failed", "in_progress", "aborted", "unknown"]
SyncHealth = Literal[
    "healthy", "degraded", "progressing", "suspended", "missing", "unknown"
]


class DeployEvent(BaseModel):
    """Normalized deploy event from any CI/CD source."""
    source: Literal["jenkins", "argocd"]
    source_id: str
    name: str
    status: DeployStatus
    started_at: datetime
    finished_at: datetime | None = None
    git_sha: str | None = None
    git_repo: str | None = None
    git_ref: str | None = None
    triggered_by: str | None = None
    url: str
    target: str | None = None


class Build(BaseModel):
    """Detailed Jenkins build state."""
    event: DeployEvent
    parameters: dict[str, str] = Field(default_factory=dict)
    log_tail: str = ""
    failed_stage: str | None = None


class SyncDiff(BaseModel):
    """ArgoCD sync diff."""
    event: DeployEvent
    health: SyncHealth
    out_of_sync_resources: list[dict] = Field(default_factory=list)
    manifest_diff: str = ""


class DeliveryItem(BaseModel):
    """Unified row for the Live Board — commit, build, or sync."""
    kind: Literal["commit", "build", "sync"]
    id: str
    title: str
    source: Literal["github", "jenkins", "argocd"]
    source_instance: str
    status: str
    author: str | None = None
    git_sha: str | None = None
    git_repo: str | None = None
    target: str | None = None
    timestamp: datetime
    duration_s: int | None = None
    url: str


ErrorKind = Literal["auth", "network", "timeout", "rate_limit", "parse", "unknown"]

_RETRIABLE_KINDS = {"network", "timeout", "rate_limit"}


class CICDClientError(Exception):
    """Structured error raised by CICDClient implementations."""

    def __init__(
        self,
        *,
        source: str,
        instance: str,
        kind: ErrorKind,
        message: str,
        retriable: bool | None = None,
    ) -> None:
        self.source = source
        self.instance = instance
        self.kind = kind
        self.message = message
        self.retriable = (
            retriable if retriable is not None else kind in _RETRIABLE_KINDS
        )
        super().__init__(f"[{source}/{instance}] {kind}: {message}")


@runtime_checkable
class CICDClient(Protocol):
    """Duck-typed interface all CI/CD clients satisfy."""

    source: Literal["jenkins", "argocd"]
    name: str

    async def list_deploy_events(
        self,
        since: datetime,
        until: datetime,
        target_filter: str | None = None,
    ) -> list[DeployEvent]: ...

    async def get_build_artifacts(
        self, event: DeployEvent
    ) -> Build | SyncDiff: ...

    async def health_check(self) -> bool: ...


@dataclass
class InstanceError:
    name: str
    source: Literal["jenkins", "argocd"]
    message: str = ""


@dataclass
class ResolveResult:
    jenkins: list[CICDClient] = field(default_factory=list)
    argocd: list[CICDClient] = field(default_factory=list)
    errors: list[InstanceError] = field(default_factory=list)
