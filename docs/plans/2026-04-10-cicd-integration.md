# CI/CD Integration (Jenkins + ArgoCD) — Phase A Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship Phase A (read-path) of the CI/CD integration — shared `CICDClient` library (Jenkins + ArgoCD), ChangeAgent enrichment, `troubleshoot_pipeline` capability, and a real-time Live Board at `/cicd`.

**Architecture:** Three layers — (1) `CICDClient` Protocol + Jenkins/ArgoCD implementations in `backend/src/integrations/cicd/`, (2) consumers (`ChangeAgent` pre-fetch, new `PipelineAgent`, `/cicd/stream` endpoint), (3) frontend Live Board with 10s poll + drawer. Normalization at the client boundary so agents only see `DeployEvent`. See `docs/plans/2026-04-10-cicd-integration-design.md` for full context.

**Tech Stack:** Python 3.11 / FastAPI / pydantic / aiohttp / pytest / React 18 / TypeScript / Vite / React Query / Tailwind.

**Scope boundaries:** Phase A only. `trigger_action` method lands as Protocol stub (for Phase B). No webhooks. No remediation. No WebSocket push.

**TDD discipline:** Every task writes the failing test first, runs it to confirm it fails, then minimal implementation, then re-runs to confirm green, then commits. One behavior per test. Frequent commits.

---

## Task Map

**Backend — CICD package (Tasks 1–9)**
1. Package skeleton + `DeployEvent` / `Build` / `SyncDiff` / `DeliveryItem` models
2. `CICDClientError` exception hierarchy
3. `CICDClient` Protocol + `ResolveResult` / `InstanceError`
4. TTL cache
5. `JenkinsClient.list_deploy_events`
6. `JenkinsClient.get_build_artifacts` + `health_check`
7. `ArgoCDClient` REST mode
8. `ArgoCDClient` kubeconfig mode + `probe_crds`
9. `resolve_cicd_clients` with auto-discovery + failure isolation

**Backend — Integrations wiring (Tasks 10–12)**
10. Register `jenkins` / `argocd` service types in integrations store
11. Probe endpoints for Jenkins + ArgoCD
12. Audit hook for all CICDClient reads

**Backend — Agents (Tasks 13–15)**
13. ChangeAgent pre-fetch enrichment
14. `PipelineAgent` ReAct implementation
15. Supervisor + schema wiring for `troubleshoot_pipeline`

**Backend — API (Tasks 16–17)**
16. `GET /api/v4/cicd/stream` endpoint
17. `GET /api/v4/cicd/commit/{owner}/{repo}/{sha}` endpoint

**Frontend — Types & routing (Tasks 18–19)**
18. Shared types + `troubleshoot_pipeline` capability
19. Router entries + sidebar "Delivery" + "Pipeline"

**Frontend — Live Board (Tasks 20–25)**
20. `SplitFlapCell` component
21. `DeliveryRow` component
22. `DeliveryFilters` component
23. `DeliveryDrawer` component (Commit / Diff / Related tabs)
24. `CICDLiveBoard` page with polling + filter/drawer state
25. Home page compact widget (top 8 rows)

**Frontend — Settings (Task 26)**
26. Jenkins + ArgoCD forms in `IntegrationSettings`

**Integration / Smoke (Task 27)**
27. Manual verification checklist

---

## Conventions Used Throughout

- Python tests: `pytest backend/tests/path -v`
- Frontend tests: `npm test -- path` (Vitest)
- Commit format: `feat(cicd): ...`, `test(cicd): ...`, `refactor(cicd): ...`
- All async code uses `aiohttp.ClientSession` passed as a parameter where possible (easier mocking)
- All new Python files start with `from __future__ import annotations`
- Every task ends with a commit. Do not batch multiple tasks into a single commit.

---

## Task 1: Package skeleton + core models

**Files:**
- Create: `backend/src/integrations/cicd/__init__.py`
- Create: `backend/src/integrations/cicd/base.py`
- Create: `backend/tests/integrations/cicd/__init__.py`
- Create: `backend/tests/integrations/cicd/test_models.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_models.py
from __future__ import annotations
from datetime import datetime, timezone

from backend.src.integrations.cicd.base import (
    DeployEvent, Build, SyncDiff, DeliveryItem,
)


def test_deploy_event_roundtrips_required_fields():
    event = DeployEvent(
        source="jenkins",
        source_id="checkout-api#1847",
        name="checkout-api",
        status="success",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 4, 10, 14, 1, tzinfo=timezone.utc),
        git_sha="abc123",
        git_repo="acme/checkout-api",
        git_ref="main",
        triggered_by="ci-bot",
        url="https://jenkins.example/job/checkout-api/1847/",
        target="prod",
    )
    dumped = event.model_dump()
    assert dumped["source"] == "jenkins"
    assert dumped["status"] == "success"
    assert DeployEvent.model_validate(dumped) == event


def test_delivery_item_accepts_commit_kind_without_duration():
    item = DeliveryItem(
        kind="commit",
        id="abc123",
        title="fix: null guard on cart",
        source="github",
        source_instance="acme-github",
        status="committed",
        author="gunjan",
        git_sha="abc123",
        git_repo="acme/checkout-api",
        target="main",
        timestamp=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        duration_s=None,
        url="https://github.com/acme/checkout-api/commit/abc123",
    )
    assert item.kind == "commit"
    assert item.duration_s is None
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.src.integrations.cicd`

**Step 3: Write minimal implementation**

```python
# backend/src/integrations/cicd/__init__.py
"""CI/CD integration package (Jenkins + ArgoCD)."""
```

```python
# backend/src/integrations/cicd/base.py
from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

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
    parameters: dict[str, str] = {}
    log_tail: str = ""
    failed_stage: str | None = None


class SyncDiff(BaseModel):
    """ArgoCD sync diff."""
    event: DeployEvent
    health: SyncHealth
    out_of_sync_resources: list[dict] = []
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
```

```python
# backend/tests/integrations/cicd/__init__.py
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_models.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/__init__.py backend/src/integrations/cicd/base.py backend/tests/integrations/cicd/__init__.py backend/tests/integrations/cicd/test_models.py
git commit -m "feat(cicd): add core models (DeployEvent, Build, SyncDiff, DeliveryItem)"
```

---

## Task 2: CICDClientError hierarchy

**Files:**
- Modify: `backend/src/integrations/cicd/base.py` (append)
- Create: `backend/tests/integrations/cicd/test_errors.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_errors.py
from __future__ import annotations

import pytest

from backend.src.integrations.cicd.base import CICDClientError


def test_cicd_client_error_carries_structured_fields():
    err = CICDClientError(
        source="jenkins",
        instance="prod-jenkins",
        kind="auth",
        message="401 Unauthorized",
        retriable=False,
    )
    assert err.source == "jenkins"
    assert err.instance == "prod-jenkins"
    assert err.kind == "auth"
    assert err.retriable is False
    assert "401" in str(err)


def test_cicd_client_error_defaults_retriable_for_network_kind():
    err = CICDClientError(
        source="argocd", instance="prod", kind="network", message="conn reset",
    )
    assert err.retriable is True


def test_cicd_client_error_is_raisable():
    with pytest.raises(CICDClientError) as exc_info:
        raise CICDClientError(
            source="jenkins", instance="x", kind="timeout", message="t/o",
        )
    assert exc_info.value.kind == "timeout"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_errors.py -v`
Expected: FAIL — `ImportError: cannot import name 'CICDClientError'`

**Step 3: Write minimal implementation**

Append to `backend/src/integrations/cicd/base.py`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_errors.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/base.py backend/tests/integrations/cicd/test_errors.py
git commit -m "feat(cicd): add CICDClientError with retriable classification"
```

---

## Task 3: CICDClient Protocol + ResolveResult

**Files:**
- Modify: `backend/src/integrations/cicd/base.py` (append)
- Create: `backend/tests/integrations/cicd/test_protocol.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_protocol.py
from __future__ import annotations

from datetime import datetime, timezone

from backend.src.integrations.cicd.base import (
    CICDClient, DeployEvent, InstanceError, ResolveResult,
)


class _FakeClient:
    source = "jenkins"
    name = "fake"

    async def list_deploy_events(self, since, until, target_filter=None):
        return []

    async def get_build_artifacts(self, event):
        return None

    async def health_check(self):
        return True


def test_fake_client_satisfies_protocol():
    # runtime_checkable Protocol — isinstance check should pass
    client: CICDClient = _FakeClient()
    assert isinstance(client, CICDClient)


def test_resolve_result_holds_clients_and_errors():
    result = ResolveResult(
        clients=[_FakeClient()],
        errors=[InstanceError(instance="broken", kind="auth", message="401")],
    )
    assert len(result.clients) == 1
    assert result.errors[0].instance == "broken"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_protocol.py -v`
Expected: FAIL — `ImportError: cannot import name 'CICDClient'`

**Step 3: Write minimal implementation**

Append to `backend/src/integrations/cicd/base.py`:

```python
from dataclasses import dataclass, field


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
    instance: str
    kind: str
    message: str = ""


@dataclass
class ResolveResult:
    clients: list[CICDClient] = field(default_factory=list)
    errors: list[InstanceError] = field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_protocol.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/base.py backend/tests/integrations/cicd/test_protocol.py
git commit -m "feat(cicd): add CICDClient Protocol and ResolveResult"
```

---

## Task 4: TTL cache

**Files:**
- Create: `backend/src/integrations/cicd/cache.py`
- Create: `backend/tests/integrations/cicd/test_cache.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_cache.py
from __future__ import annotations

import asyncio
import pytest

from backend.src.integrations.cicd.cache import TTLCache


@pytest.mark.asyncio
async def test_ttl_cache_returns_cached_value_within_ttl():
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=60)
    calls = {"n": 0}

    async def load():
        calls["n"] += 1
        return 42

    assert await cache.get_or_set("k", load) == 42
    assert await cache.get_or_set("k", load) == 42
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_ttl_cache_reloads_after_ttl_expires(monkeypatch):
    cache: TTLCache[str, int] = TTLCache(ttl_seconds=1)
    now = {"t": 1000.0}
    monkeypatch.setattr("backend.src.integrations.cicd.cache.time.monotonic",
                        lambda: now["t"])
    calls = {"n": 0}

    async def load():
        calls["n"] += 1
        return calls["n"]

    assert await cache.get_or_set("k", load) == 1
    now["t"] += 2.0
    assert await cache.get_or_set("k", load) == 2
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_ttl_cache_isolates_keys():
    cache: TTLCache[str, str] = TTLCache(ttl_seconds=60)

    async def load_a():
        return "A"

    async def load_b():
        return "B"

    assert await cache.get_or_set("a", load_a) == "A"
    assert await cache.get_or_set("b", load_b) == "B"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/integrations/cicd/cache.py
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    """Minimal async TTL cache. Single-flight safety via per-key lock."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[K, tuple[float, V]] = {}
        self._locks: dict[K, asyncio.Lock] = {}

    async def get_or_set(self, key: K, loader: Callable[[], Awaitable[V]]) -> V:
        now = time.monotonic()
        entry = self._store.get(key)
        if entry is not None and (now - entry[0]) < self._ttl:
            return entry[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            entry = self._store.get(key)
            now = time.monotonic()
            if entry is not None and (now - entry[0]) < self._ttl:
                return entry[1]
            value = await loader()
            self._store[key] = (time.monotonic(), value)
            return value
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_cache.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/cache.py backend/tests/integrations/cicd/test_cache.py
git commit -m "feat(cicd): add TTL cache for list queries"
```

---

## Task 5: JenkinsClient.list_deploy_events

**Files:**
- Create: `backend/src/integrations/cicd/jenkins_client.py`
- Create: `backend/tests/integrations/cicd/test_jenkins_client.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_jenkins_client.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.integrations.cicd.base import CICDClientError
from backend.src.integrations.cicd.jenkins_client import JenkinsClient


JOBS_PAYLOAD = {
    "jobs": [
        {"name": "checkout-api", "url": "https://j.example/job/checkout-api/"},
    ]
}
JOB_PAYLOAD = {
    "builds": [
        {"number": 1847, "url": "https://j.example/job/checkout-api/1847/"},
    ]
}
BUILD_PAYLOAD = {
    "number": 1847,
    "result": "SUCCESS",
    "timestamp": 1775995200000,  # 2026-04-10T14:00:00Z
    "duration": 60000,
    "url": "https://j.example/job/checkout-api/1847/",
    "actions": [
        {"_class": "hudson.plugins.git.util.BuildData",
         "lastBuiltRevision": {"SHA1": "abc123"},
         "remoteUrls": ["https://github.com/acme/checkout-api.git"]},
        {"_class": "hudson.model.CauseAction",
         "causes": [{"userName": "ci-bot"}]},
    ],
}


def _mk_client(mock_get):
    client = JenkinsClient(
        base_url="https://j.example",
        username="u",
        api_token="t",
        instance_name="prod",
    )
    client._get_json = mock_get  # type: ignore[assignment]
    return client


@pytest.mark.asyncio
async def test_list_deploy_events_parses_builds_within_window():
    mock_get = AsyncMock(side_effect=[JOBS_PAYLOAD, JOB_PAYLOAD, BUILD_PAYLOAD])
    client = _mk_client(mock_get)

    since = datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)
    events = await client.list_deploy_events(since, until)

    assert len(events) == 1
    ev = events[0]
    assert ev.source == "jenkins"
    assert ev.name == "checkout-api"
    assert ev.status == "success"
    assert ev.git_sha == "abc123"
    assert ev.git_repo == "acme/checkout-api"
    assert ev.triggered_by == "ci-bot"


@pytest.mark.asyncio
async def test_list_deploy_events_skips_builds_outside_window():
    old_build = {**BUILD_PAYLOAD, "timestamp": 0}
    mock_get = AsyncMock(side_effect=[JOBS_PAYLOAD, JOB_PAYLOAD, old_build])
    client = _mk_client(mock_get)
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert events == []


@pytest.mark.asyncio
async def test_list_deploy_events_raises_auth_error_on_401():
    async def raise_auth(*a, **kw):
        raise CICDClientError(
            source="jenkins", instance="prod", kind="auth", message="401",
        )
    client = _mk_client(AsyncMock(side_effect=raise_auth))

    with pytest.raises(CICDClientError) as exc_info:
        await client.list_deploy_events(
            datetime(2026, 4, 10, tzinfo=timezone.utc),
            datetime(2026, 4, 11, tzinfo=timezone.utc),
        )
    assert exc_info.value.kind == "auth"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_jenkins_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/integrations/cicd/jenkins_client.py
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Literal

import aiohttp

from backend.src.integrations.cicd.base import (
    Build, CICDClientError, DeployEvent, DeployStatus, SyncDiff,
)

_STATUS_MAP: dict[str, DeployStatus] = {
    "SUCCESS": "success",
    "FAILURE": "failed",
    "ABORTED": "aborted",
    "UNSTABLE": "failed",
    None: "in_progress",  # type: ignore[dict-item]
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
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_jenkins_client.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/jenkins_client.py backend/tests/integrations/cicd/test_jenkins_client.py
git commit -m "feat(cicd): JenkinsClient.list_deploy_events with git metadata parsing"
```

---

## Task 6: JenkinsClient.get_build_artifacts + health_check

**Files:**
- Modify: `backend/src/integrations/cicd/jenkins_client.py`
- Modify: `backend/tests/integrations/cicd/test_jenkins_client.py`

**Step 1: Write the failing test**

Append to `test_jenkins_client.py`:

```python
@pytest.mark.asyncio
async def test_get_build_artifacts_returns_log_tail_and_failed_stage():
    from backend.src.integrations.cicd.base import DeployEvent
    from datetime import datetime, timezone

    event = DeployEvent(
        source="jenkins",
        source_id="checkout-api#1847",
        name="checkout-api",
        status="failed",
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        url="https://j.example/job/checkout-api/1847/",
    )

    detail = {
        **BUILD_PAYLOAD,
        "result": "FAILURE",
        "actions": [
            {"parameters": [{"name": "ENV", "value": "prod"}]},
        ],
    }
    log_text = "\n".join(f"line {i}" for i in range(250)) + "\n[Pipeline] stage 'deploy' FAILED"

    mock_get = AsyncMock(side_effect=[detail])
    client = _mk_client(mock_get)

    async def fake_log(path: str) -> str:
        assert path.endswith("/consoleText")
        return log_text

    client._get_text = fake_log  # type: ignore[assignment]

    build = await client.get_build_artifacts(event)
    assert build.event.source_id == "checkout-api#1847"
    assert build.parameters == {"ENV": "prod"}
    assert "line 249" in build.log_tail
    assert build.log_tail.count("\n") <= 210  # bounded
    assert build.failed_stage == "deploy"


@pytest.mark.asyncio
async def test_health_check_returns_true_on_200():
    mock_get = AsyncMock(return_value={"mode": "NORMAL"})
    client = _mk_client(mock_get)
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_health_check_returns_false_on_auth_error():
    async def fail(*a, **kw):
        raise CICDClientError(
            source="jenkins", instance="prod", kind="auth", message="401",
        )
    client = _mk_client(AsyncMock(side_effect=fail))
    assert await client.health_check() is False
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_jenkins_client.py -v`
Expected: FAIL — `NotImplementedError`

**Step 3: Write minimal implementation**

Replace the two stub methods in `jenkins_client.py` and add `_get_text`:

```python
    async def _get_text(self, path: str) -> str:
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession(
                auth=self._auth, timeout=self._timeout
            ) as s:
                async with s.get(url) as resp:
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

    async def get_build_artifacts(self, event: DeployEvent) -> Build | SyncDiff:
        job_name, _, num = event.source_id.partition("#")
        detail = await self._get_json(f"/job/{job_name}/{num}/api/json")
        log = await self._get_text(f"/job/{job_name}/{num}/consoleText")
        params: dict[str, str] = {}
        for action in detail.get("actions", []):
            for p in (action.get("parameters") or []) if isinstance(action, dict) else []:
                params[p["name"]] = str(p.get("value", ""))
        tail_lines = log.splitlines()[-200:]
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
        try:
            await self._get_json("/api/json?tree=mode")
            return True
        except CICDClientError:
            return False
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_jenkins_client.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/jenkins_client.py backend/tests/integrations/cicd/test_jenkins_client.py
git commit -m "feat(cicd): JenkinsClient artifacts + health_check with log-tail parsing"
```

---

## Task 7: ArgoCDClient REST mode

**Files:**
- Create: `backend/src/integrations/cicd/argocd_client.py`
- Create: `backend/tests/integrations/cicd/test_argocd_client.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_argocd_client.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.src.integrations.cicd.argocd_client import ArgoCDClient


APPS_PAYLOAD = {
    "items": [
        {
            "metadata": {"name": "checkout-api", "namespace": "argocd"},
            "spec": {
                "source": {"repoURL": "https://github.com/acme/checkout-api"},
                "destination": {"namespace": "prod"},
            },
            "status": {
                "sync": {"status": "Synced", "revision": "abc123"},
                "health": {"status": "Healthy"},
                "operationState": {
                    "startedAt": "2026-04-10T14:02:00Z",
                    "finishedAt": "2026-04-10T14:02:11Z",
                    "phase": "Succeeded",
                    "syncResult": {"revision": "abc123"},
                },
            },
        }
    ]
}


@pytest.mark.asyncio
async def test_list_deploy_events_parses_argocd_sync():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=APPS_PAYLOAD)  # type: ignore

    since = datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc)
    until = datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)
    events = await client.list_deploy_events(since, until)

    assert len(events) == 1
    ev = events[0]
    assert ev.source == "argocd"
    assert ev.name == "checkout-api"
    assert ev.status == "success"
    assert ev.git_sha == "abc123"
    assert ev.git_repo == "acme/checkout-api"
    assert ev.target == "prod"


@pytest.mark.asyncio
async def test_list_deploy_events_filters_by_target_namespace():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value=APPS_PAYLOAD)  # type: ignore
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
        target_filter="staging",
    )
    assert events == []


@pytest.mark.asyncio
async def test_health_check_returns_true_on_valid_list():
    client = ArgoCDClient.from_rest(
        base_url="https://argo.example", token="t", instance_name="prod",
    )
    client._get_json = AsyncMock(return_value={"items": []})  # type: ignore
    assert await client.health_check() is True
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_argocd_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/integrations/cicd/argocd_client.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal

import aiohttp

from backend.src.integrations.cicd.base import (
    CICDClientError, DeployEvent, DeployStatus, SyncDiff, SyncHealth,
)

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
    url = url.rstrip("/").removesuffix(".git")
    parts = url.split("/")
    return "/".join(parts[-2:]) if len(parts) >= 2 else None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class ArgoCDClient:
    source: Literal["argocd"] = "argocd"

    def __init__(
        self,
        mode: Literal["rest", "kubeconfig"],
        instance_name: str,
        base_url: str | None = None,
        token: str | None = None,
        cluster_client: Any = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.mode = mode
        self.name = instance_name
        self.base_url = (base_url or "").rstrip("/")
        self._token = token
        self._cluster = cluster_client
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)

    @classmethod
    def from_rest(cls, base_url: str, token: str, instance_name: str) -> "ArgoCDClient":
        return cls(mode="rest", base_url=base_url, token=token,
                   instance_name=instance_name)

    @classmethod
    def from_kubeconfig(cls, cluster_client: Any, instance_name: str = "in-cluster") -> "ArgoCDClient":
        return cls(mode="kubeconfig", cluster_client=cluster_client,
                   instance_name=instance_name)

    @classmethod
    async def probe_crds(cls, cluster_client: Any) -> bool:
        try:
            return await cluster_client.has_crd("applications.argoproj.io")
        except Exception:
            return False

    async def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as s:
                async with s.get(url, headers=headers) as resp:
                    if resp.status in (401, 403):
                        raise CICDClientError(
                            source="argocd", instance=self.name,
                            kind="auth", message=f"{resp.status}",
                        )
                    if resp.status == 429:
                        raise CICDClientError(
                            source="argocd", instance=self.name,
                            kind="rate_limit", message="429",
                        )
                    resp.raise_for_status()
                    return await resp.json()
        except asyncio.TimeoutError as e:
            raise CICDClientError(
                source="argocd", instance=self.name,
                kind="timeout", message=str(e),
            ) from e
        except aiohttp.ClientError as e:
            raise CICDClientError(
                source="argocd", instance=self.name,
                kind="network", message=str(e),
            ) from e

    async def _fetch_apps(self) -> list[dict[str, Any]]:
        if self.mode == "rest":
            payload = await self._get_json("/api/v1/applications")
            return payload.get("items", [])
        # kubeconfig mode
        return await self._cluster.list_custom_resource(
            group="argoproj.io", version="v1alpha1", plural="applications",
        )

    async def list_deploy_events(
        self,
        since: datetime,
        until: datetime,
        target_filter: str | None = None,
    ) -> list[DeployEvent]:
        apps = await self._fetch_apps()
        events: list[DeployEvent] = []
        for app in apps:
            meta = app.get("metadata", {})
            spec = app.get("spec", {})
            status = app.get("status", {})
            op = status.get("operationState") or {}
            started = _parse_iso(op.get("startedAt"))
            if not started or not (since <= started <= until):
                continue
            dest_ns = (spec.get("destination") or {}).get("namespace")
            if target_filter and dest_ns != target_filter:
                continue
            phase = op.get("phase", "")
            events.append(DeployEvent(
                source="argocd",
                source_id=f"{meta.get('name')}@{(op.get('syncResult') or {}).get('revision', 'unknown')}",
                name=meta.get("name", "unknown"),
                status=_PHASE_MAP.get(phase, "unknown"),
                started_at=started,
                finished_at=_parse_iso(op.get("finishedAt")),
                git_sha=(op.get("syncResult") or {}).get("revision")
                        or (status.get("sync") or {}).get("revision"),
                git_repo=_normalize_repo((spec.get("source") or {}).get("repoURL")),
                git_ref=(spec.get("source") or {}).get("targetRevision"),
                triggered_by=None,
                url=f"{self.base_url}/applications/{meta.get('name')}"
                    if self.mode == "rest" else "",
                target=dest_ns,
            ))
        return events

    async def get_build_artifacts(self, event: DeployEvent) -> SyncDiff:
        apps = await self._fetch_apps()
        target = next(
            (a for a in apps if a.get("metadata", {}).get("name") == event.name),
            None,
        )
        if target is None:
            raise CICDClientError(
                source="argocd", instance=self.name,
                kind="parse", message=f"app {event.name} not found",
            )
        status = target.get("status", {})
        health = (status.get("health") or {}).get("status", "Unknown")
        return SyncDiff(
            event=event,
            health=_HEALTH_MAP.get(health, "unknown"),
            out_of_sync_resources=[
                r for r in status.get("resources", [])
                if r.get("status") != "Synced"
            ],
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
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_argocd_client.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/argocd_client.py backend/tests/integrations/cicd/test_argocd_client.py
git commit -m "feat(cicd): ArgoCDClient REST mode with sync event parsing"
```

---

## Task 8: ArgoCDClient kubeconfig mode + probe_crds

**Files:**
- Modify: `backend/tests/integrations/cicd/test_argocd_client.py`

(Implementation already covers kubeconfig mode via `_fetch_apps`; this task adds coverage.)

**Step 1: Write the failing test**

Append:

```python
class _FakeCluster:
    def __init__(self, apps, has_crd=True):
        self.apps = apps
        self._has_crd = has_crd

    async def list_custom_resource(self, group, version, plural):
        assert group == "argoproj.io"
        assert plural == "applications"
        return self.apps

    async def has_crd(self, name: str) -> bool:
        return self._has_crd


@pytest.mark.asyncio
async def test_kubeconfig_mode_reads_applications_from_cluster():
    cluster = _FakeCluster(apps=APPS_PAYLOAD["items"])
    client = ArgoCDClient.from_kubeconfig(cluster_client=cluster)
    events = await client.list_deploy_events(
        datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc),
    )
    assert len(events) == 1
    assert events[0].source == "argocd"


@pytest.mark.asyncio
async def test_probe_crds_returns_true_when_crd_present():
    cluster = _FakeCluster(apps=[], has_crd=True)
    assert await ArgoCDClient.probe_crds(cluster) is True


@pytest.mark.asyncio
async def test_probe_crds_returns_false_on_cluster_exception():
    class Broken:
        async def has_crd(self, name):
            raise RuntimeError("rbac denied")
    assert await ArgoCDClient.probe_crds(Broken()) is False
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_argocd_client.py -v`
Expected: All 3 new tests PASS if Task 7 code is correct (kubeconfig code path is already wired). If the kubeconfig branch has a bug, fix it before moving on.

**Step 3/4: Fix and re-verify as needed**

**Step 5: Commit**

```bash
git add backend/tests/integrations/cicd/test_argocd_client.py
git commit -m "test(cicd): ArgoCDClient kubeconfig mode + probe_crds coverage"
```

---

## Task 9: resolve_cicd_clients with auto-discovery

**Files:**
- Create: `backend/src/integrations/cicd/resolver.py`
- Create: `backend/tests/integrations/cicd/test_resolver.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_resolver.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.integrations.cicd.base import CICDClientError
from backend.src.integrations.cicd.resolver import resolve_cicd_clients


class _FakeEntry:
    def __init__(self, name, url="https://x", creds=None):
        self.name = name
        self.url = url
        self.credentials = creds or {"username": "u", "api_token": "t"}


@pytest.mark.asyncio
async def test_resolver_returns_empty_when_nothing_configured():
    with patch(
        "backend.src.integrations.cicd.resolver.gi_store"
    ) as store:
        store.get_by_service_type = MagicMock(return_value=[])
        result = await resolve_cicd_clients(ctx=None)
    assert result.clients == []
    assert result.errors == []


@pytest.mark.asyncio
async def test_resolver_isolates_failing_jenkins_instance():
    entries = [_FakeEntry("good"), _FakeEntry("bad")]
    with patch("backend.src.integrations.cicd.resolver.gi_store") as store, \
         patch("backend.src.integrations.cicd.resolver.JenkinsClient") as JC:
        store.get_by_service_type = MagicMock(
            side_effect=lambda t: entries if t == "jenkins" else []
        )
        good = MagicMock()
        good.health_check = AsyncMock(return_value=True)
        good.source = "jenkins"
        good.name = "good"
        def make(url, creds, instance_name, **kw):
            if instance_name == "bad":
                raise CICDClientError(
                    source="jenkins", instance="bad",
                    kind="auth", message="401",
                )
            return good
        JC.side_effect = lambda **kw: make(**kw)
        result = await resolve_cicd_clients(ctx=None)
    assert len(result.clients) == 1
    assert result.clients[0].name == "good"
    assert len(result.errors) == 1
    assert result.errors[0].instance == "bad"
    assert result.errors[0].kind == "auth"


@pytest.mark.asyncio
async def test_resolver_auto_discovers_argocd_when_cluster_has_crds():
    with patch("backend.src.integrations.cicd.resolver.gi_store") as store, \
         patch("backend.src.integrations.cicd.resolver.ArgoCDClient") as AC:
        store.get_by_service_type = MagicMock(return_value=[])
        AC.probe_crds = AsyncMock(return_value=True)
        discovered = MagicMock(source="argocd", name="in-cluster")
        AC.from_kubeconfig = MagicMock(return_value=discovered)
        cluster = MagicMock()
        result = await resolve_cicd_clients(ctx={"cluster_integration": cluster})
    assert any(c.name == "in-cluster" for c in result.clients)


@pytest.mark.asyncio
async def test_resolver_skips_auto_discovery_when_argocd_already_configured():
    with patch("backend.src.integrations.cicd.resolver.gi_store") as store, \
         patch("backend.src.integrations.cicd.resolver.ArgoCDClient") as AC:
        store.get_by_service_type = MagicMock(
            side_effect=lambda t: [_FakeEntry("manual")] if t == "argocd" else []
        )
        configured = MagicMock(source="argocd", name="manual")
        configured.health_check = AsyncMock(return_value=True)
        AC.from_rest = MagicMock(return_value=configured)
        AC.probe_crds = AsyncMock(return_value=True)
        AC.from_kubeconfig = MagicMock()
        cluster = MagicMock()
        result = await resolve_cicd_clients(ctx={"cluster_integration": cluster})
    assert [c.name for c in result.clients] == ["manual"]
    AC.from_kubeconfig.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_resolver.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/integrations/cicd/resolver.py
from __future__ import annotations

from typing import Any

from backend.src.integrations.cicd.argocd_client import ArgoCDClient
from backend.src.integrations.cicd.base import (
    CICDClientError, InstanceError, ResolveResult,
)
from backend.src.integrations.cicd.jenkins_client import JenkinsClient
from backend.src.integrations.store import gi_store  # existing module


async def resolve_cicd_clients(ctx: dict[str, Any] | None) -> ResolveResult:
    clients: list[Any] = []
    errors: list[InstanceError] = []

    for entry in gi_store.get_by_service_type("jenkins"):
        try:
            creds = entry.credentials or {}
            c = JenkinsClient(
                base_url=entry.url,
                username=creds.get("username", ""),
                api_token=creds.get("api_token", ""),
                instance_name=entry.name,
            )
            if await c.health_check():
                clients.append(c)
            else:
                errors.append(InstanceError(
                    instance=entry.name, kind="health_check_failed",
                ))
        except CICDClientError as e:
            errors.append(InstanceError(
                instance=entry.name, kind=e.kind, message=e.message,
            ))

    for entry in gi_store.get_by_service_type("argocd"):
        try:
            creds = entry.credentials or {}
            c = ArgoCDClient.from_rest(
                base_url=entry.url,
                token=creds.get("token", ""),
                instance_name=entry.name,
            )
            if await c.health_check():
                clients.append(c)
            else:
                errors.append(InstanceError(
                    instance=entry.name, kind="health_check_failed",
                ))
        except CICDClientError as e:
            errors.append(InstanceError(
                instance=entry.name, kind=e.kind, message=e.message,
            ))

    cluster = ctx.get("cluster_integration") if ctx else None
    if cluster and not any(getattr(c, "source", None) == "argocd" for c in clients):
        try:
            if await ArgoCDClient.probe_crds(cluster):
                clients.append(ArgoCDClient.from_kubeconfig(cluster))
        except Exception:  # defensive — probe must never crash resolver
            pass

    return ResolveResult(clients=clients, errors=errors)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_resolver.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/resolver.py backend/tests/integrations/cicd/test_resolver.py
git commit -m "feat(cicd): resolver with auto-discovery and failure isolation"
```

---

## Task 10: Register jenkins/argocd service types

**Files:**
- Modify: `backend/src/integrations/store.py`
- Modify: `backend/src/integrations/models.py` (if service_type enum lives there)
- Create: `backend/tests/integrations/test_cicd_service_types.py`

**Context:** The existing integrations store exposes `gi_store.get_by_service_type(kind)`. Confirm the current enum/list of supported service types and add `"jenkins"` and `"argocd"` following the exact pattern used for `"elk"` / `"github"`.

**Step 1: Write the failing test**

```python
# backend/tests/integrations/test_cicd_service_types.py
from __future__ import annotations

from backend.src.integrations.store import SUPPORTED_SERVICE_TYPES


def test_jenkins_is_registered_service_type():
    assert "jenkins" in SUPPORTED_SERVICE_TYPES


def test_argocd_is_registered_service_type():
    assert "argocd" in SUPPORTED_SERVICE_TYPES
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/test_cicd_service_types.py -v`
Expected: FAIL — `AssertionError` (or `ImportError` if constant doesn't exist yet; if it doesn't, expose it as part of this task).

**Step 3: Write minimal implementation**

Edit `backend/src/integrations/store.py` — locate the existing enum/tuple/set of allowed service types and add the two new entries. If no public constant exists, add one:

```python
SUPPORTED_SERVICE_TYPES = {
    "jira", "confluence", "github", "elk", "remedy",
    "prometheus", "jenkins", "argocd",
}
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/test_cicd_service_types.py -v`
Expected: PASS (2 tests)

Also run: `pytest backend/tests/integrations/ -v` to make sure existing integration tests didn't regress.

**Step 5: Commit**

```bash
git add backend/src/integrations/store.py backend/tests/integrations/test_cicd_service_types.py
git commit -m "feat(integrations): register jenkins and argocd as service types"
```

---

## Task 11: Probe endpoints for Jenkins + ArgoCD

**Files:**
- Modify: `backend/src/integrations/probe.py`
- Create: `backend/tests/integrations/test_cicd_probe.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/test_cicd_probe.py
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.src.integrations.probe import probe_integration


@pytest.mark.asyncio
async def test_probe_jenkins_returns_ok_on_success():
    with patch("backend.src.integrations.probe.JenkinsClient") as JC:
        instance = JC.return_value
        instance.health_check = AsyncMock(return_value=True)
        result = await probe_integration(
            service_type="jenkins",
            url="https://j.example",
            credentials={"username": "u", "api_token": "t"},
        )
    assert result.ok is True


@pytest.mark.asyncio
async def test_probe_jenkins_returns_error_on_auth_failure():
    from backend.src.integrations.cicd.base import CICDClientError
    with patch("backend.src.integrations.probe.JenkinsClient") as JC:
        instance = JC.return_value
        instance.health_check = AsyncMock(side_effect=CICDClientError(
            source="jenkins", instance="probe", kind="auth", message="401",
        ))
        result = await probe_integration(
            service_type="jenkins",
            url="https://j.example",
            credentials={"username": "u", "api_token": "bad"},
        )
    assert result.ok is False
    assert "401" in (result.error or "")


@pytest.mark.asyncio
async def test_probe_argocd_rest_returns_ok():
    with patch("backend.src.integrations.probe.ArgoCDClient") as AC:
        instance = AC.from_rest.return_value
        instance.health_check = AsyncMock(return_value=True)
        result = await probe_integration(
            service_type="argocd",
            url="https://argo.example",
            credentials={"token": "t"},
        )
    assert result.ok is True
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/test_cicd_probe.py -v`
Expected: FAIL — existing probe doesn't know `jenkins` / `argocd` types.

**Step 3: Write minimal implementation**

Add two branches to `probe.py`:

```python
from backend.src.integrations.cicd.base import CICDClientError
from backend.src.integrations.cicd.jenkins_client import JenkinsClient
from backend.src.integrations.cicd.argocd_client import ArgoCDClient


async def _probe_jenkins(url, credentials):
    try:
        client = JenkinsClient(
            base_url=url,
            username=credentials.get("username", ""),
            api_token=credentials.get("api_token", ""),
            instance_name="probe",
        )
        ok = await client.health_check()
        return ProbeResult(ok=ok, error=None if ok else "health check failed")
    except CICDClientError as e:
        return ProbeResult(ok=False, error=str(e))


async def _probe_argocd(url, credentials):
    try:
        client = ArgoCDClient.from_rest(
            base_url=url,
            token=credentials.get("token", ""),
            instance_name="probe",
        )
        ok = await client.health_check()
        return ProbeResult(ok=ok, error=None if ok else "health check failed")
    except CICDClientError as e:
        return ProbeResult(ok=False, error=str(e))
```

Wire them into the dispatch in `probe_integration`:

```python
    if service_type == "jenkins":
        return await _probe_jenkins(url, credentials)
    if service_type == "argocd":
        return await _probe_argocd(url, credentials)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/test_cicd_probe.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/integrations/probe.py backend/tests/integrations/test_cicd_probe.py
git commit -m "feat(integrations): probe endpoints for jenkins and argocd"
```

---

## Task 12: Audit hook for CICDClient reads

**Files:**
- Modify: `backend/src/integrations/cicd/jenkins_client.py`
- Modify: `backend/src/integrations/cicd/argocd_client.py`
- Create: `backend/tests/integrations/cicd/test_audit_hook.py`

**Goal:** Every `list_deploy_events` / `get_build_artifacts` / `health_check` records an audit event `{action: "read", source, instance, method, caller}` via the existing `integrations/audit_store.py`. Landing this now so Phase B write actions plug into the same store without refactor.

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_audit_hook.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.integrations.cicd.jenkins_client import JenkinsClient


@pytest.mark.asyncio
async def test_jenkins_list_emits_audit_read_record():
    client = JenkinsClient("https://j", "u", "t", "prod")
    client._get_json = AsyncMock(return_value={"jobs": []})
    with patch("backend.src.integrations.cicd.jenkins_client.audit_store") as a:
        await client.list_deploy_events(
            datetime(2026, 4, 10, tzinfo=timezone.utc),
            datetime(2026, 4, 11, tzinfo=timezone.utc),
        )
        a.record.assert_called_once()
        call = a.record.call_args.kwargs
        assert call["action"] == "read"
        assert call["source"] == "jenkins"
        assert call["instance"] == "prod"
        assert call["method"] == "list_deploy_events"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_audit_hook.py -v`
Expected: FAIL — `ImportError: cannot import name 'audit_store'`

**Step 3: Write minimal implementation**

At top of `jenkins_client.py`:

```python
from backend.src.integrations import audit_store  # type: ignore
```

Wrap `list_deploy_events` body entry:

```python
    async def list_deploy_events(self, since, until, target_filter=None):
        audit_store.record(
            action="read", source="jenkins", instance=self.name,
            method="list_deploy_events", caller=None,
        )
        # ... existing body
```

Do the same in `get_build_artifacts` and `health_check`. Mirror in `argocd_client.py`.

If `audit_store.record` does not exist yet, add a minimal function in the existing `audit_store` module:

```python
def record(*, action, source, instance, method, caller=None, severity="info"):
    logger.info(
        "integration_audit",
        extra={"action": action, "source": source, "instance": instance,
               "method": method, "caller": caller, "severity": severity},
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_audit_hook.py -v`
Expected: PASS

Also re-run: `pytest backend/tests/integrations/cicd/ -v`
Expected: All previous tests still green.

**Step 5: Commit**

```bash
git add backend/src/integrations/cicd/jenkins_client.py backend/src/integrations/cicd/argocd_client.py backend/src/integrations/audit_store.py backend/tests/integrations/cicd/test_audit_hook.py
git commit -m "feat(cicd): audit hook for all CICDClient read operations"
```

---

## Task 13: ChangeAgent pre-fetch enrichment

**Files:**
- Modify: `backend/src/agents/change_agent.py`
- Create: `backend/tests/test_change_agent_cicd_enrichment.py`

**Goal:** Phase 0 pre-fetch fans out to `resolve_cicd_clients` and appends a `ci_cd_events` context block for the triage prompt. When the resolver returns no clients, the block is omitted entirely (no confusing empty section for the LLM).

**Step 1: Write the failing test**

```python
# backend/tests/test_change_agent_cicd_enrichment.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.integrations.cicd.base import DeployEvent, ResolveResult


def _event(name="checkout-api", status="failed"):
    return DeployEvent(
        source="jenkins",
        source_id=f"{name}#1",
        name=name,
        status=status,
        started_at=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
        url="https://j/x/1/",
    )


@pytest.mark.asyncio
async def test_change_agent_prefetch_includes_cicd_events():
    fake_client = MagicMock()
    fake_client.list_deploy_events = AsyncMock(return_value=[_event()])
    with patch(
        "backend.src.agents.change_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[fake_client], errors=[])),
    ):
        from backend.src.agents.change_agent import _prefetch_cicd_events
        events = await _prefetch_cicd_events(
            ctx={},
            incident_start=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
            namespace="prod",
        )
    assert len(events) == 1
    assert events[0].name == "checkout-api"


@pytest.mark.asyncio
async def test_change_agent_prefetch_returns_empty_when_no_clients():
    with patch(
        "backend.src.agents.change_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[], errors=[])),
    ):
        from backend.src.agents.change_agent import _prefetch_cicd_events
        events = await _prefetch_cicd_events(
            ctx={},
            incident_start=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
            namespace="prod",
        )
    assert events == []


@pytest.mark.asyncio
async def test_change_agent_prefetch_tolerates_one_client_failing():
    good = MagicMock()
    good.list_deploy_events = AsyncMock(return_value=[_event("svc-a")])
    bad = MagicMock()
    bad.list_deploy_events = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(
        "backend.src.agents.change_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[good, bad], errors=[])),
    ):
        from backend.src.agents.change_agent import _prefetch_cicd_events
        events = await _prefetch_cicd_events(
            ctx={},
            incident_start=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc),
            namespace="prod",
        )
    assert len(events) == 1
    assert events[0].name == "svc-a"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_change_agent_cicd_enrichment.py -v`
Expected: FAIL — `ImportError: cannot import name '_prefetch_cicd_events'`

**Step 3: Write minimal implementation**

Add to `change_agent.py`:

```python
from datetime import timedelta

from backend.src.integrations.cicd.resolver import resolve_cicd_clients


async def _prefetch_cicd_events(ctx, incident_start, namespace):
    """Fan out to all resolved CI/CD clients. Per-client failures are swallowed."""
    result = await resolve_cicd_clients(ctx)
    if not result.clients:
        return []
    since = incident_start - timedelta(hours=2)
    until = incident_start + timedelta(minutes=30)
    import asyncio
    coros = [
        c.list_deploy_events(since, until, target_filter=namespace)
        for c in result.clients
    ]
    outputs = await asyncio.gather(*coros, return_exceptions=True)
    events = []
    for out in outputs:
        if isinstance(out, Exception):
            continue
        events.extend(out)
    return events
```

Then wire it into the existing Phase 0 pre-fetch block: call `_prefetch_cicd_events` in parallel with existing GitHub/k8s pre-fetch (`asyncio.gather`) and, when non-empty, include the result as `ci_cd_events` in the triage context dict. Keep the key absent when the list is empty.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_change_agent_cicd_enrichment.py -v`
Expected: PASS (3 tests)

Run existing ChangeAgent tests to confirm no regression:
Run: `pytest backend/tests/ -k change_agent -v`

**Step 5: Commit**

```bash
git add backend/src/agents/change_agent.py backend/tests/test_change_agent_cicd_enrichment.py
git commit -m "feat(change-agent): pre-fetch CI/CD events for triage context"
```

---

## Task 14: PipelineAgent implementation

**Files:**
- Create: `backend/src/agents/pipeline_agent.py`
- Create: `backend/tests/agents/test_pipeline_agent.py`

**Goal:** Thin `ReActAgent` with three tools: `list_recent_deploys`, `get_deploy_details`, `search_logs`. Max 4 iterations. Returns a finding with deeplink chips.

**Step 1: Write the failing test**

```python
# backend/tests/agents/test_pipeline_agent.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.integrations.cicd.base import Build, DeployEvent, ResolveResult


def _event():
    return DeployEvent(
        source="jenkins", source_id="svc#1", name="svc",
        status="failed",
        started_at=datetime(2026, 4, 10, 14, tzinfo=timezone.utc),
        url="https://j/svc/1",
    )


@pytest.mark.asyncio
async def test_pipeline_agent_produces_finding_from_deploy_event():
    from backend.src.agents.pipeline_agent import PipelineAgent

    fake_client = MagicMock()
    fake_client.source = "jenkins"
    fake_client.name = "prod"
    fake_client.list_deploy_events = AsyncMock(return_value=[_event()])
    fake_client.get_build_artifacts = AsyncMock(return_value=Build(
        event=_event(), parameters={}, log_tail="error: boom",
        failed_stage="deploy",
    ))

    with patch(
        "backend.src.agents.pipeline_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[fake_client], errors=[])),
    ):
        agent = PipelineAgent(llm=AsyncMock())
        agent.llm.invoke = AsyncMock(side_effect=[
            {"action": "list_recent_deploys", "args": {"hours": 2}},
            {"action": "get_deploy_details", "args": {"event_id": "svc#1"}},
            {"action": "finish",
             "args": {"finding": "Deploy svc#1 failed at stage 'deploy'",
                      "root_cause": "error: boom"}},
        ])
        finding = await agent.run(inputs={
            "instance": "prod", "name": "svc", "window_hours": 2,
        })

    assert "svc#1" in finding["finding"]
    assert finding["root_cause"]


@pytest.mark.asyncio
async def test_pipeline_agent_stops_after_max_iterations():
    from backend.src.agents.pipeline_agent import PipelineAgent

    with patch(
        "backend.src.agents.pipeline_agent.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[], errors=[])),
    ):
        agent = PipelineAgent(llm=AsyncMock(), max_iterations=4)
        agent.llm.invoke = AsyncMock(return_value={
            "action": "list_recent_deploys", "args": {"hours": 1},
        })
        finding = await agent.run(inputs={
            "instance": "prod", "name": "svc", "window_hours": 1,
        })
    assert finding["terminated_reason"] == "max_iterations"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/agents/test_pipeline_agent.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/agents/pipeline_agent.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.src.integrations.cicd.resolver import resolve_cicd_clients


class PipelineAgent:
    """Minimal ReAct agent with three CI/CD tools."""

    def __init__(self, llm: Any, max_iterations: int = 4) -> None:
        self.llm = llm
        self.max_iterations = max_iterations

    async def run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        ctx: dict[str, Any] = {"inputs": inputs, "observations": []}
        for _ in range(self.max_iterations):
            step = await self.llm.invoke(ctx)
            action = step.get("action")
            args = step.get("args", {})
            if action == "finish":
                return {
                    "finding": args.get("finding", ""),
                    "root_cause": args.get("root_cause"),
                    "terminated_reason": "finished",
                }
            obs = await self._run_tool(action, args, inputs)
            ctx["observations"].append({"action": action, "args": args, "obs": obs})
        return {
            "finding": "Unable to conclude within iteration budget.",
            "root_cause": None,
            "terminated_reason": "max_iterations",
        }

    async def _run_tool(self, action: str, args: dict, inputs: dict) -> Any:
        result = await resolve_cicd_clients(ctx=None)
        clients = [
            c for c in result.clients if c.name == inputs.get("instance")
        ] or result.clients
        if action == "list_recent_deploys":
            hours = int(args.get("hours", 2))
            until = datetime.now(tz=timezone.utc)
            since = until - timedelta(hours=hours)
            out: list[dict] = []
            for c in clients:
                try:
                    evs = await c.list_deploy_events(since, until)
                    out.extend(e.model_dump() for e in evs)
                except Exception:
                    continue
            return out
        if action == "get_deploy_details":
            event_id = args.get("event_id", "")
            for c in clients:
                try:
                    evs = await c.list_deploy_events(
                        datetime.now(tz=timezone.utc) - timedelta(hours=24),
                        datetime.now(tz=timezone.utc),
                    )
                    match = next((e for e in evs if e.source_id == event_id), None)
                    if match is None:
                        continue
                    art = await c.get_build_artifacts(match)
                    return art.model_dump()
                except Exception:
                    continue
            return None
        if action == "search_logs":
            return {"error": "search_logs not wired to live source in Phase A"}
        return {"error": f"unknown action {action}"}
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/agents/test_pipeline_agent.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/pipeline_agent.py backend/tests/agents/test_pipeline_agent.py
git commit -m "feat(agents): PipelineAgent ReAct loop with 3 CI/CD tools"
```

---

## Task 15: Supervisor + schema wiring for troubleshoot_pipeline

**Files:**
- Modify: `backend/src/agents/supervisor.py`
- Modify: `backend/src/models/schemas.py`
- Create: `backend/tests/test_supervisor_pipeline_capability.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_supervisor_pipeline_capability.py
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


def test_capability_enum_includes_troubleshoot_pipeline():
    from backend.src.models.schemas import CapabilityType
    assert "troubleshoot_pipeline" in {c.value for c in CapabilityType}


@pytest.mark.asyncio
async def test_supervisor_routes_troubleshoot_pipeline_to_pipeline_agent():
    from backend.src.agents import supervisor

    with patch.object(supervisor, "PipelineAgent") as PA:
        instance = PA.return_value
        instance.run = AsyncMock(return_value={"finding": "ok"})
        result = await supervisor.dispatch(
            capability="troubleshoot_pipeline",
            inputs={"instance": "prod", "name": "svc", "window_hours": 2},
        )
    assert result["finding"] == "ok"
    PA.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_supervisor_pipeline_capability.py -v`
Expected: FAIL — unknown capability / enum missing.

**Step 3: Write minimal implementation**

- In `schemas.py`, add `TROUBLESHOOT_PIPELINE = "troubleshoot_pipeline"` to the `CapabilityType` enum.
- In `supervisor.py`, add route:

```python
from backend.src.agents.pipeline_agent import PipelineAgent

async def dispatch(capability: str, inputs: dict):
    if capability == "troubleshoot_pipeline":
        agent = PipelineAgent(llm=get_llm())
        return await agent.run(inputs)
    # ... existing routing
```

(If `dispatch` is not the existing entry point, wire it into the existing one — route by the new capability string.)

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_supervisor_pipeline_capability.py -v`
Expected: PASS (2 tests)

Run full supervisor tests for regression check.

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/src/models/schemas.py backend/tests/test_supervisor_pipeline_capability.py
git commit -m "feat(supervisor): route troubleshoot_pipeline capability to PipelineAgent"
```

---

## Task 16: GET /api/v4/cicd/stream endpoint

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Create: `backend/tests/integrations/cicd/test_stream_endpoint.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_stream_endpoint.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.src.integrations.cicd.base import DeployEvent, ResolveResult


def _event(name="svc-a", ts=datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc)):
    return DeployEvent(
        source="jenkins", source_id=f"{name}#1", name=name,
        status="success", started_at=ts, url="https://j/x/1/",
    )


@pytest.fixture
def client():
    from backend.src.api.main import app  # adjust if actual app object path differs
    return TestClient(app)


def test_stream_endpoint_merges_sources_sorted_desc(client):
    old = _event("svc-a", datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc))
    new = _event("svc-b", datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc))
    fake = MagicMock()
    fake.source = "jenkins"
    fake.name = "prod"
    fake.list_deploy_events = AsyncMock(return_value=[old, new])
    with patch(
        "backend.src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[fake], errors=[])),
    ), patch(
        "backend.src.api.routes_v4.list_recent_github_commits",
        AsyncMock(return_value=[]),
    ):
        resp = client.get("/api/v4/cicd/stream?since=2026-04-10T12:00:00Z")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == ["svc-b#1", "svc-a#1"]


def test_stream_endpoint_returns_partial_on_source_failure(client):
    good = MagicMock(); good.source = "jenkins"; good.name = "g"
    good.list_deploy_events = AsyncMock(return_value=[_event()])
    bad = MagicMock(); bad.source = "argocd"; bad.name = "b"
    bad.list_deploy_events = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(
        "backend.src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[good, bad], errors=[])),
    ), patch(
        "backend.src.api.routes_v4.list_recent_github_commits",
        AsyncMock(return_value=[]),
    ):
        resp = client.get("/api/v4/cicd/stream?since=2026-04-10T12:00:00Z")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert len(body["source_errors"]) == 1


def test_stream_endpoint_empty_when_nothing_configured(client):
    with patch(
        "backend.src.api.routes_v4.resolve_cicd_clients",
        AsyncMock(return_value=ResolveResult(clients=[], errors=[])),
    ), patch(
        "backend.src.api.routes_v4.list_recent_github_commits",
        AsyncMock(return_value=[]),
    ):
        resp = client.get("/api/v4/cicd/stream?since=2026-04-10T12:00:00Z")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_stream_endpoint.py -v`
Expected: FAIL — `/api/v4/cicd/stream` not registered.

**Step 3: Write minimal implementation**

Add to `routes_v4.py`:

```python
import asyncio
from datetime import datetime

from fastapi import Query

from backend.src.integrations.cicd.resolver import resolve_cicd_clients
from backend.src.integrations.cicd.base import DeliveryItem
from backend.src.integrations.github_client import list_recent_github_commits  # existing


def _event_to_delivery_item(ev, source_instance: str) -> DeliveryItem:
    kind = "sync" if ev.source == "argocd" else "build"
    duration = None
    if ev.finished_at:
        duration = int((ev.finished_at - ev.started_at).total_seconds())
    return DeliveryItem(
        kind=kind, id=ev.source_id, title=ev.name,
        source=ev.source, source_instance=source_instance,
        status=ev.status, author=ev.triggered_by,
        git_sha=ev.git_sha, git_repo=ev.git_repo,
        target=ev.target, timestamp=ev.started_at,
        duration_s=duration, url=ev.url,
    )


def _commit_to_delivery_item(c) -> DeliveryItem:
    return DeliveryItem(
        kind="commit", id=c.sha, title=c.message_first_line,
        source="github", source_instance=c.repo,
        status="committed", author=c.author,
        git_sha=c.sha, git_repo=c.repo, target=c.branch,
        timestamp=c.timestamp, duration_s=None, url=c.url,
    )


@router.get("/cicd/stream")
async def cicd_stream(since: datetime = Query(...), limit: int = 100):
    until = datetime.now(tz=since.tzinfo or timezone.utc)
    resolved = await resolve_cicd_clients(ctx=None)

    async def safe_list(client):
        try:
            return ("ok", client.name, await client.list_deploy_events(since, until))
        except Exception as e:
            return ("err", client.name, str(e))

    deploy_results = await asyncio.gather(
        *[safe_list(c) for c in resolved.clients]
    )
    commits = []
    try:
        commits = await list_recent_github_commits(since=since, limit=50)
    except Exception:
        pass

    items: list[DeliveryItem] = []
    source_errors = [
        {"instance": e.instance, "kind": e.kind, "message": e.message}
        for e in resolved.errors
    ]
    for status, instance, data in deploy_results:
        if status == "err":
            source_errors.append(
                {"instance": instance, "kind": "runtime", "message": data}
            )
            continue
        for ev in data:
            items.append(_event_to_delivery_item(ev, instance))
    for c in commits:
        items.append(_commit_to_delivery_item(c))

    items.sort(key=lambda i: i.timestamp, reverse=True)
    return {
        "items": [i.model_dump() for i in items[:limit]],
        "source_errors": source_errors,
        "server_ts": datetime.now(tz=timezone.utc).isoformat(),
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_stream_endpoint.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/integrations/cicd/test_stream_endpoint.py
git commit -m "feat(api): GET /api/v4/cicd/stream unified deploy+commit feed"
```

---

## Task 17: GET /api/v4/cicd/commit/{owner}/{repo}/{sha}

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Create: `backend/tests/integrations/cicd/test_commit_endpoint.py`

**Step 1: Write the failing test**

```python
# backend/tests/integrations/cicd/test_commit_endpoint.py
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.src.api.main import app
    return TestClient(app)


def test_commit_detail_endpoint_returns_commit_and_files(client):
    fake = {
        "sha": "abc123",
        "message": "fix: null guard",
        "author": "gunjan",
        "timestamp": "2026-04-10T14:00:00Z",
        "files": [
            {"filename": "src/cart.ts", "status": "modified",
             "additions": 4, "deletions": 1, "patch": "@@ ... @@"},
        ],
        "url": "https://github.com/acme/checkout-api/commit/abc123",
    }
    with patch(
        "backend.src.api.routes_v4.get_github_commit_detail",
        AsyncMock(return_value=fake),
    ):
        resp = client.get("/api/v4/cicd/commit/acme/checkout-api/abc123")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sha"] == "abc123"
    assert len(body["files"]) == 1


def test_commit_detail_endpoint_returns_429_on_rate_limit(client):
    with patch(
        "backend.src.api.routes_v4.get_github_commit_detail",
        AsyncMock(side_effect=Exception("API rate limit exceeded")),
    ):
        resp = client.get("/api/v4/cicd/commit/acme/checkout-api/abc123")
    assert resp.status_code in (429, 502)
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integrations/cicd/test_commit_endpoint.py -v`
Expected: FAIL — endpoint missing.

**Step 3: Write minimal implementation**

Add to `routes_v4.py`:

```python
from fastapi import HTTPException

from backend.src.integrations.github_client import get_github_commit_detail  # existing


@router.get("/cicd/commit/{owner}/{repo}/{sha}")
async def cicd_commit_detail(owner: str, repo: str, sha: str):
    try:
        return await get_github_commit_detail(owner=owner, repo=repo, sha=sha)
    except Exception as e:
        msg = str(e)
        if "rate limit" in msg.lower():
            raise HTTPException(status_code=429, detail="GitHub rate limit reached")
        raise HTTPException(status_code=502, detail=msg)
```

If `get_github_commit_detail` does not yet exist in the codebase, add a minimal wrapper using the existing GitHub integration token path.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/integrations/cicd/test_commit_endpoint.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/integrations/cicd/test_commit_endpoint.py
git commit -m "feat(api): GET /api/v4/cicd/commit/{owner}/{repo}/{sha} commit detail"
```

---

## Task 18: Frontend shared types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Write the failing test**

```typescript
// frontend/src/types/__tests__/cicd-types.test.ts
import type { DeliveryItem, CICDStreamResponse, CapabilityType } from "../index";

test("DeliveryItem type accepts commit kind", () => {
  const item: DeliveryItem = {
    kind: "commit",
    id: "abc",
    title: "fix: null guard",
    source: "github",
    source_instance: "acme",
    status: "committed",
    author: "gunjan",
    git_sha: "abc",
    git_repo: "acme/checkout-api",
    target: "main",
    timestamp: "2026-04-10T14:00:00Z",
    duration_s: null,
    url: "https://github.com/acme/checkout-api/commit/abc",
  };
  expect(item.kind).toBe("commit");
});

test("CapabilityType includes troubleshoot_pipeline", () => {
  const cap: CapabilityType = "troubleshoot_pipeline";
  expect(cap).toBe("troubleshoot_pipeline");
});

test("CICDStreamResponse shape", () => {
  const r: CICDStreamResponse = {
    items: [],
    source_errors: [],
    server_ts: "2026-04-10T14:00:00Z",
  };
  expect(r.items).toEqual([]);
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- cicd-types`
Expected: FAIL — missing exports.

**Step 3: Write minimal implementation**

Append to `frontend/src/types/index.ts`:

```typescript
export type DeliveryKind = "commit" | "build" | "sync";
export type DeliverySource = "github" | "jenkins" | "argocd";

export interface DeliveryItem {
  kind: DeliveryKind;
  id: string;
  title: string;
  source: DeliverySource;
  source_instance: string;
  status: string;
  author: string | null;
  git_sha: string | null;
  git_repo: string | null;
  target: string | null;
  timestamp: string;      // ISO
  duration_s: number | null;
  url: string;
}

export interface SourceError {
  instance: string;
  kind: string;
  message?: string;
}

export interface CICDStreamResponse {
  items: DeliveryItem[];
  source_errors: SourceError[];
  server_ts: string;
}

export interface CommitDetail {
  sha: string;
  message: string;
  author: string;
  timestamp: string;
  files: CommitFile[];
  url: string;
}

export interface CommitFile {
  filename: string;
  status: "added" | "modified" | "removed" | "renamed";
  additions: number;
  deletions: number;
  patch: string;
}
```

Extend the existing `CapabilityType` union to include `"troubleshoot_pipeline"`.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- cicd-types`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/types/__tests__/cicd-types.test.ts
git commit -m "feat(types): DeliveryItem, CICDStreamResponse, troubleshoot_pipeline capability"
```

---

## Task 19: Router entries + sidebar "Delivery" + "Pipeline"

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/contexts/NavigationContext.tsx`
- Modify: `frontend/src/components/Layout/SidebarNav.tsx`
- Create: `frontend/src/pages/CICDPage.tsx` (placeholder — Task 24 fills it)

**Step 1: Write the failing test**

```typescript
// frontend/src/router/__tests__/cicd-route.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router-dom";
import { routes } from "../../router";

test("router has /cicd route", () => {
  const flat = JSON.stringify(routes);
  expect(flat).toContain("/cicd");
});

test("sidebar includes Delivery entry", async () => {
  const { SidebarNav } = await import("../../components/Layout/SidebarNav");
  render(
    <MemoryRouter>
      <SidebarNav />
    </MemoryRouter>
  );
  expect(screen.getByText(/Delivery/i)).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- cicd-route`
Expected: FAIL — no `/cicd` route, no `Delivery` in sidebar.

**Step 3: Write minimal implementation**

Create placeholder page:

```tsx
// frontend/src/pages/CICDPage.tsx
export default function CICDPage() {
  return <div data-testid="cicd-page">Delivery Live Board</div>;
}
```

Add to `router.tsx` (inside existing routes array):

```tsx
{
  path: "/cicd",
  lazy: async () => ({
    Component: (await import("./pages/CICDPage")).default,
  }),
},
{
  path: "/diagnostics/pipeline",
  lazy: async () => ({
    Component: (await import("./pages/InvestigationRoute")).default,
  }),
},
```

Update `NavigationContext.tsx` nav entries list to include `{ id: "delivery", label: "Delivery", path: "/cicd", icon: "rocket_launch" }` between Sessions and Diagnostics, and add `{ id: "pipeline", label: "Pipeline", path: "/diagnostics/pipeline" }` under the Diagnostics children.

Update `SidebarNav.tsx` to render the new top-level entry (should be automatic if it reads from context).

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- cicd-route`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add frontend/src/router.tsx frontend/src/contexts/NavigationContext.tsx frontend/src/components/Layout/SidebarNav.tsx frontend/src/pages/CICDPage.tsx frontend/src/router/__tests__/cicd-route.test.tsx
git commit -m "feat(routing): /cicd route + Delivery sidebar entry + Pipeline capability"
```

---

## Task 20: SplitFlapCell component

**Files:**
- Create: `frontend/src/components/CICD/SplitFlapCell.tsx`
- Create: `frontend/src/components/CICD/__tests__/SplitFlapCell.test.tsx`

**Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { SplitFlapCell } from "../SplitFlapCell";

test("renders the current value", () => {
  render(<SplitFlapCell value="SUCCESS" />);
  expect(screen.getByText("SUCCESS")).toBeInTheDocument();
});

test("applies flipping class when value changes", () => {
  const { rerender, container } = render(<SplitFlapCell value="RUNNING" />);
  rerender(<SplitFlapCell value="SUCCESS" />);
  const el = container.querySelector("[data-testid='split-flap']");
  expect(el?.className).toMatch(/flipping|animate/);
});

test("applies status color class", () => {
  render(<SplitFlapCell value="FAILED" status="failed" />);
  const el = screen.getByText("FAILED");
  expect(el.className).toMatch(/red|danger|failed/i);
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- SplitFlapCell`
Expected: FAIL — missing component.

**Step 3: Write minimal implementation**

```tsx
// frontend/src/components/CICD/SplitFlapCell.tsx
import { useEffect, useRef, useState } from "react";

type Props = {
  value: string;
  status?: "success" | "failed" | "in_progress" | "unknown" | string;
};

const STATUS_CLASSES: Record<string, string> = {
  success: "text-emerald-400",
  failed: "text-red-400",
  in_progress: "text-amber-400",
  healthy: "text-emerald-400",
  degraded: "text-red-400",
  progressing: "text-amber-400",
};

export function SplitFlapCell({ value, status }: Props) {
  const prev = useRef(value);
  const [flipping, setFlipping] = useState(false);

  useEffect(() => {
    if (prev.current !== value) {
      setFlipping(true);
      prev.current = value;
      const t = setTimeout(() => setFlipping(false), 400);
      return () => clearTimeout(t);
    }
  }, [value]);

  const colorClass = status ? STATUS_CLASSES[status] ?? "text-slate-300" : "text-slate-300";

  return (
    <span
      data-testid="split-flap"
      className={`inline-block font-mono tracking-wider ${colorClass} ${
        flipping ? "animate-flip" : ""
      }`}
    >
      {value}
    </span>
  );
}
```

Add keyframes in `index.css`:

```css
@keyframes flip {
  0% { transform: rotateX(0); }
  50% { transform: rotateX(-90deg); opacity: 0.2; }
  100% { transform: rotateX(0); }
}
.animate-flip { animation: flip 400ms ease-out; }
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- SplitFlapCell`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add frontend/src/components/CICD/SplitFlapCell.tsx frontend/src/components/CICD/__tests__/SplitFlapCell.test.tsx frontend/src/index.css
git commit -m "feat(cicd-ui): SplitFlapCell with flip animation on value change"
```

---

## Task 21: DeliveryRow component

**Files:**
- Create: `frontend/src/components/CICD/DeliveryRow.tsx`
- Create: `frontend/src/components/CICD/__tests__/DeliveryRow.test.tsx`

**Step 1: Write the failing test**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { DeliveryRow } from "../DeliveryRow";
import type { DeliveryItem } from "../../../types";

const base: DeliveryItem = {
  kind: "build", id: "svc#1", title: "checkout-api #1847",
  source: "jenkins", source_instance: "prod", status: "success",
  author: "ci-bot", git_sha: "abc", git_repo: "acme/checkout-api",
  target: "build", timestamp: "2026-04-10T14:01:44Z", duration_s: 60,
  url: "https://j/x/1",
};

test("renders kind pill with correct color class for BUILD", () => {
  render(<DeliveryRow item={base} onClick={() => {}} />);
  const pill = screen.getByText(/BUILD/);
  expect(pill.className).toMatch(/amber|yellow/);
});

test("COMMIT pill uses slate", () => {
  render(<DeliveryRow item={{ ...base, kind: "commit" }} onClick={() => {}} />);
  expect(screen.getByText(/COMMIT/).className).toMatch(/slate|gray/);
});

test("SYNC pill uses cyan", () => {
  render(<DeliveryRow item={{ ...base, kind: "sync" }} onClick={() => {}} />);
  expect(screen.getByText(/SYNC/).className).toMatch(/cyan|sky/);
});

test("clicking row fires onClick with item", () => {
  const spy = vi.fn();
  render(<DeliveryRow item={base} onClick={spy} />);
  fireEvent.click(screen.getByRole("row"));
  expect(spy).toHaveBeenCalledWith(base);
});

test("FAILED row renders Investigate button", () => {
  render(<DeliveryRow item={{ ...base, status: "failed" }} onClick={() => {}} />);
  expect(screen.getByRole("button", { name: /investigate/i })).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- DeliveryRow`
Expected: FAIL — component missing.

**Step 3: Write minimal implementation**

```tsx
// frontend/src/components/CICD/DeliveryRow.tsx
import { Link } from "react-router-dom";
import type { DeliveryItem } from "../../types";
import { SplitFlapCell } from "./SplitFlapCell";

const KIND_PILL: Record<DeliveryItem["kind"], string> = {
  commit: "bg-slate-700 text-slate-100",
  build: "bg-amber-600/20 text-amber-300",
  sync: "bg-cyan-600/20 text-cyan-300",
};

type Props = { item: DeliveryItem; onClick: (item: DeliveryItem) => void };

export function DeliveryRow({ item, onClick }: Props) {
  const failed = item.status === "failed" || item.status === "degraded";
  const investigateHref = failed
    ? `/investigations/new?capability=troubleshoot_app&name=${encodeURIComponent(item.title)}&target=${item.target ?? ""}`
    : null;

  return (
    <div
      role="row"
      onClick={() => onClick(item)}
      className="grid grid-cols-[80px_1fr_100px_120px_140px_120px_100px_120px] gap-2 items-center px-3 py-2 hover:bg-slate-800/60 cursor-pointer border-b border-slate-800"
    >
      <span className={`px-2 py-0.5 rounded text-xs font-semibold tracking-wider ${KIND_PILL[item.kind]}`}>
        {item.kind.toUpperCase()}
      </span>
      <span className="truncate text-slate-100">{item.title}</span>
      <span className="text-slate-400 text-xs uppercase">{item.source}</span>
      <span className="text-slate-400 text-xs">{item.target ?? "—"}</span>
      <SplitFlapCell value={item.status.toUpperCase()} status={item.status} />
      <span className="text-slate-400 text-xs">{item.author ?? "—"}</span>
      <span className="text-slate-500 text-xs font-mono">
        {new Date(item.timestamp).toLocaleTimeString()}
      </span>
      <span>
        {investigateHref && (
          <Link
            to={investigateHref}
            role="button"
            className="text-cyan-400 text-xs hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            Investigate ↗
          </Link>
        )}
      </span>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- DeliveryRow`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add frontend/src/components/CICD/DeliveryRow.tsx frontend/src/components/CICD/__tests__/DeliveryRow.test.tsx
git commit -m "feat(cicd-ui): DeliveryRow with kind pills and Investigate link"
```

---

## Task 22: DeliveryFilters component

**Files:**
- Create: `frontend/src/components/CICD/DeliveryFilters.tsx`
- Create: `frontend/src/components/CICD/__tests__/DeliveryFilters.test.tsx`

**Step 1: Write the failing test**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { DeliveryFilters } from "../DeliveryFilters";

test("renders default All filters", () => {
  render(<DeliveryFilters value={{ kind: "all", status: "all" }} onChange={() => {}} />);
  expect(screen.getByRole("button", { name: /all/i })).toBeInTheDocument();
});

test("clicking Failed emits new filter", () => {
  const spy = vi.fn();
  render(<DeliveryFilters value={{ kind: "all", status: "all" }} onChange={spy} />);
  fireEvent.click(screen.getByRole("button", { name: /failed/i }));
  expect(spy).toHaveBeenCalledWith(expect.objectContaining({ status: "failed" }));
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- DeliveryFilters`
Expected: FAIL.

**Step 3: Write minimal implementation**

```tsx
// frontend/src/components/CICD/DeliveryFilters.tsx
export type FilterValue = {
  kind: "all" | "deploys" | "commits";
  status: "all" | "failed" | "in_progress" | "success";
};

type Props = { value: FilterValue; onChange: (v: FilterValue) => void };

const KIND_OPTS: FilterValue["kind"][] = ["all", "deploys", "commits"];
const STATUS_OPTS: FilterValue["status"][] = ["all", "failed", "in_progress", "success"];

export function DeliveryFilters({ value, onChange }: Props) {
  return (
    <div className="flex gap-4 items-center px-3 py-2 border-b border-slate-800">
      <div className="flex gap-1">
        {KIND_OPTS.map((k) => (
          <button
            key={k}
            onClick={() => onChange({ ...value, kind: k })}
            className={`px-2 py-1 text-xs rounded ${value.kind === k ? "bg-cyan-600 text-white" : "text-slate-400 hover:bg-slate-800"}`}
          >
            {k[0].toUpperCase() + k.slice(1)}
          </button>
        ))}
      </div>
      <div className="flex gap-1">
        {STATUS_OPTS.map((s) => (
          <button
            key={s}
            onClick={() => onChange({ ...value, status: s })}
            className={`px-2 py-1 text-xs rounded ${value.status === s ? "bg-cyan-600 text-white" : "text-slate-400 hover:bg-slate-800"}`}
          >
            {s.replace("_", " ")}
          </button>
        ))}
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- DeliveryFilters`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add frontend/src/components/CICD/DeliveryFilters.tsx frontend/src/components/CICD/__tests__/DeliveryFilters.test.tsx
git commit -m "feat(cicd-ui): DeliveryFilters kind/status chips"
```

---

## Task 23: DeliveryDrawer component

**Files:**
- Create: `frontend/src/components/CICD/DeliveryDrawer.tsx`
- Create: `frontend/src/components/CICD/__tests__/DeliveryDrawer.test.tsx`

**Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DeliveryDrawer } from "../DeliveryDrawer";
import type { DeliveryItem } from "../../../types";

const item: DeliveryItem = {
  kind: "build", id: "svc#1", title: "svc",
  source: "jenkins", source_instance: "prod", status: "failed",
  author: "ci-bot", git_sha: "abc123", git_repo: "acme/checkout-api",
  target: "prod", timestamp: "2026-04-10T14:00:00Z", duration_s: 60,
  url: "https://j/x/1",
};

function renderWithClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

test("drawer fetches commit detail on open", async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      sha: "abc123", message: "fix: null guard", author: "gunjan",
      timestamp: "2026-04-10T14:00:00Z", url: "https://x", files: [],
    }),
  }) as any;

  renderWithClient(<DeliveryDrawer item={item} allItems={[item]} onClose={() => {}} />);
  await waitFor(() => {
    expect(screen.getByText(/fix: null guard/)).toBeInTheDocument();
  });
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/v4/cicd/commit/acme/checkout-api/abc123"),
  );
});

test("Related tab lists items matching git_sha from current feed", async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      sha: "abc123", message: "fix", author: "g",
      timestamp: "2026-04-10T14:00:00Z", url: "https://x", files: [],
    }),
  }) as any;

  const other: DeliveryItem = { ...item, id: "svc#2", kind: "sync", source: "argocd" };
  renderWithClient(<DeliveryDrawer item={item} allItems={[item, other]} onClose={() => {}} />);
  await waitFor(() => screen.getByText(/fix/));
  screen.getByRole("tab", { name: /related/i }).click();
  await waitFor(() => expect(screen.getAllByText(/svc/)).not.toHaveLength(0));
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- DeliveryDrawer`
Expected: FAIL.

**Step 3: Write minimal implementation**

```tsx
// frontend/src/components/CICD/DeliveryDrawer.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { DeliveryItem, CommitDetail } from "../../types";

type Props = {
  item: DeliveryItem;
  allItems: DeliveryItem[];
  onClose: () => void;
};

type Tab = "commit" | "diff" | "related";

export function DeliveryDrawer({ item, allItems, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("commit");
  const commitKey = item.git_repo && item.git_sha
    ? `/api/v4/cicd/commit/${item.git_repo}/${item.git_sha}`
    : null;

  const { data: commit, isLoading, error } = useQuery<CommitDetail>({
    queryKey: ["commit", commitKey],
    queryFn: async () => {
      const res = await fetch(commitKey!);
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json();
    },
    enabled: !!commitKey,
  });

  const related = item.git_sha
    ? allItems.filter((i) => i.git_sha === item.git_sha && i.id !== item.id)
    : [];

  return (
    <aside className="fixed right-0 top-0 h-screen w-[480px] bg-slate-900 border-l border-slate-700 shadow-xl flex flex-col">
      <header className="p-4 border-b border-slate-800 flex items-center justify-between">
        <h2 className="text-slate-100 font-semibold truncate">{item.title}</h2>
        <button onClick={onClose} className="text-slate-400 hover:text-white">×</button>
      </header>
      <nav className="flex border-b border-slate-800">
        {(["commit", "diff", "related"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            onClick={() => setTab(t)}
            className={`flex-1 px-3 py-2 text-sm ${tab === t ? "text-cyan-400 border-b-2 border-cyan-400" : "text-slate-400"}`}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>
      <div className="flex-1 overflow-y-auto p-4 text-sm">
        {tab === "commit" && (
          isLoading ? <p className="text-slate-400">Loading…</p>
          : error ? <p className="text-red-400">Failed to load commit</p>
          : commit ? (
            <div>
              <p className="text-slate-100 font-semibold">{commit.message}</p>
              <p className="text-slate-400 text-xs mt-1">
                {commit.author} · {new Date(commit.timestamp).toLocaleString()}
              </p>
              <a href={commit.url} className="text-cyan-400 text-xs mt-2 inline-block"
                 target="_blank" rel="noopener noreferrer">Open on GitHub ↗</a>
            </div>
          ) : <p className="text-slate-500">No commit linked.</p>
        )}
        {tab === "diff" && (
          commit?.files?.length ? (
            <div className="space-y-3">
              {commit.files.map((f) => (
                <div key={f.filename}>
                  <div className="text-slate-300 text-xs font-mono">
                    {f.filename} <span className="text-emerald-400">+{f.additions}</span>{" "}
                    <span className="text-red-400">-{f.deletions}</span>
                  </div>
                  <pre className="text-[10px] bg-slate-950 p-2 rounded mt-1 overflow-x-auto">{f.patch}</pre>
                </div>
              ))}
            </div>
          ) : <p className="text-slate-500">No file changes to show.</p>
        )}
        {tab === "related" && (
          related.length ? (
            <ul className="space-y-1">
              {related.map((r) => (
                <li key={r.id} className="text-slate-300 text-xs">
                  <span className="uppercase text-slate-500 mr-2">{r.kind}</span>
                  {r.title} <span className="text-slate-500">· {r.status}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-slate-500">No related items in the current feed.</p>
        )}
      </div>
    </aside>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- DeliveryDrawer`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add frontend/src/components/CICD/DeliveryDrawer.tsx frontend/src/components/CICD/__tests__/DeliveryDrawer.test.tsx
git commit -m "feat(cicd-ui): DeliveryDrawer with Commit/Diff/Related tabs"
```

---

## Task 24: CICDLiveBoard page with polling

**Files:**
- Modify: `frontend/src/pages/CICDPage.tsx`
- Create: `frontend/src/components/CICD/CICDLiveBoard.tsx`
- Create: `frontend/src/components/CICD/__tests__/CICDLiveBoard.test.tsx`

**Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { CICDLiveBoard } from "../CICDLiveBoard";

const payload = {
  items: [
    { kind: "sync", id: "a", title: "svc-a", source: "argocd", source_instance: "p",
      status: "healthy", author: null, git_sha: "abc", git_repo: "acme/x",
      target: "prod", timestamp: "2026-04-10T14:02:11Z", duration_s: null, url: "" },
    { kind: "build", id: "b", title: "svc-b #1", source: "jenkins", source_instance: "p",
      status: "success", author: "ci-bot", git_sha: "abc", git_repo: "acme/x",
      target: "build", timestamp: "2026-04-10T14:01:44Z", duration_s: 60, url: "" },
  ],
  source_errors: [],
  server_ts: "2026-04-10T14:02:12Z",
};

function wrap(ui: React.ReactNode) {
  const q = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={q}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

test("renders rows sorted newest first", async () => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => payload }) as any;
  wrap(<CICDLiveBoard />);
  await waitFor(() => expect(screen.getByText("svc-a")).toBeInTheDocument());
  const rows = screen.getAllByRole("row");
  expect(rows[0].textContent).toContain("svc-a");
  expect(rows[1].textContent).toContain("svc-b");
});

test("renders source_errors warning chip when present", async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ ...payload, source_errors: [{ instance: "bad", kind: "auth" }] }),
  }) as any;
  wrap(<CICDLiveBoard />);
  await waitFor(() => expect(screen.getByText(/source issues/i)).toBeInTheDocument());
});

test("renders empty state when no items and no sources configured", async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [], source_errors: [], server_ts: "" }),
  }) as any;
  wrap(<CICDLiveBoard />);
  await waitFor(() =>
    expect(screen.getByText(/no deploys or commits/i)).toBeInTheDocument()
  );
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- CICDLiveBoard`
Expected: FAIL.

**Step 3: Write minimal implementation**

```tsx
// frontend/src/components/CICD/CICDLiveBoard.tsx
import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CICDStreamResponse, DeliveryItem } from "../../types";
import { DeliveryRow } from "./DeliveryRow";
import { DeliveryFilters, type FilterValue } from "./DeliveryFilters";
import { DeliveryDrawer } from "./DeliveryDrawer";

export function CICDLiveBoard() {
  const [filter, setFilter] = useState<FilterValue>({ kind: "all", status: "all" });
  const [selected, setSelected] = useState<DeliveryItem | null>(null);

  const since = useMemo(
    () => new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
    [],
  );

  const { data, isLoading } = useQuery<CICDStreamResponse>({
    queryKey: ["cicd-stream", since],
    queryFn: async () => {
      const res = await fetch(`/api/v4/cicd/stream?since=${since}&limit=100`);
      if (!res.ok) throw new Error(String(res.status));
      return res.json();
    },
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });

  const items = data?.items ?? [];
  const filtered = items.filter((i) => {
    if (filter.kind === "deploys" && !(i.kind === "build" || i.kind === "sync")) return false;
    if (filter.kind === "commits" && i.kind !== "commit") return false;
    if (filter.status !== "all" && i.status !== filter.status) return false;
    return true;
  });

  return (
    <div className="h-full flex flex-col bg-slate-950">
      <header className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <h1 className="text-slate-100 text-lg font-semibold">Delivery</h1>
        {data?.source_errors?.length ? (
          <span className="text-amber-400 text-xs">
            ⚠ {data.source_errors.length} source issues
          </span>
        ) : null}
      </header>
      <DeliveryFilters value={filter} onChange={setFilter} />
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <p className="text-slate-500 p-4">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="text-slate-500 p-4">No deploys or commits in the last 24 hours.</p>
        ) : (
          filtered.map((i) => (
            <DeliveryRow key={i.id} item={i} onClick={setSelected} />
          ))
        )}
      </div>
      {selected && (
        <DeliveryDrawer
          item={selected}
          allItems={items}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
```

Update `CICDPage.tsx`:

```tsx
import { CICDLiveBoard } from "../components/CICD/CICDLiveBoard";
export default function CICDPage() {
  return <CICDLiveBoard />;
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- CICDLiveBoard`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add frontend/src/components/CICD/CICDLiveBoard.tsx frontend/src/components/CICD/__tests__/CICDLiveBoard.test.tsx frontend/src/pages/CICDPage.tsx
git commit -m "feat(cicd-ui): CICDLiveBoard with 10s polling, filter, drawer"
```

---

## Task 25: Home page compact widget (top 8 rows)

**Files:**
- Modify: `frontend/src/components/Home/HomePage.tsx`
- Create: `frontend/src/components/CICD/CICDHomeWidget.tsx`
- Create: `frontend/src/components/CICD/__tests__/CICDHomeWidget.test.tsx`

**Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { CICDHomeWidget } from "../CICDHomeWidget";

function wrap(ui: React.ReactNode) {
  const q = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={q}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

test("shows at most 8 rows", async () => {
  const items = Array.from({ length: 20 }, (_, i) => ({
    kind: "build", id: `b${i}`, title: `svc-${i}`,
    source: "jenkins", source_instance: "p", status: "success",
    author: null, git_sha: null, git_repo: null, target: null,
    timestamp: `2026-04-10T14:${String(i).padStart(2, "0")}:00Z`,
    duration_s: null, url: "",
  }));
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items, source_errors: [], server_ts: "" }),
  }) as any;
  wrap(<CICDHomeWidget />);
  await waitFor(() => expect(screen.getByText(/svc-19/)).toBeInTheDocument());
  expect(screen.queryByText(/svc-11/)).not.toBeInTheDocument();
});

test("links to /cicd when user clicks See all", async () => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [], source_errors: [], server_ts: "" }),
  }) as any;
  wrap(<CICDHomeWidget />);
  const link = await screen.findByRole("link", { name: /see all/i });
  expect(link).toHaveAttribute("href", "/cicd");
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- CICDHomeWidget`
Expected: FAIL.

**Step 3: Write minimal implementation**

```tsx
// frontend/src/components/CICD/CICDHomeWidget.tsx
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { CICDStreamResponse } from "../../types";
import { DeliveryRow } from "./DeliveryRow";

export function CICDHomeWidget() {
  const since = new Date(Date.now() - 6 * 3600 * 1000).toISOString();
  const { data } = useQuery<CICDStreamResponse>({
    queryKey: ["cicd-home", since],
    queryFn: async () => {
      const res = await fetch(`/api/v4/cicd/stream?since=${since}&limit=8`);
      if (!res.ok) throw new Error(String(res.status));
      return res.json();
    },
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  });

  const items = (data?.items ?? []).slice(0, 8);

  return (
    <section className="border border-slate-800 rounded-lg overflow-hidden">
      <header className="flex items-center justify-between px-3 py-2 border-b border-slate-800">
        <h3 className="text-slate-100 text-sm font-semibold">Delivery — last 6h</h3>
        <Link to="/cicd" className="text-cyan-400 text-xs hover:underline">See all ↗</Link>
      </header>
      <div className="max-h-72 overflow-y-auto">
        {items.length === 0 ? (
          <p className="text-slate-500 text-xs p-3">No recent delivery activity.</p>
        ) : (
          items.map((i) => <DeliveryRow key={i.id} item={i} onClick={() => {}} />)
        )}
      </div>
    </section>
  );
}
```

Import and place `<CICDHomeWidget />` in `HomePage.tsx` in the existing home grid.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- CICDHomeWidget`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add frontend/src/components/CICD/CICDHomeWidget.tsx frontend/src/components/CICD/__tests__/CICDHomeWidget.test.tsx frontend/src/components/Home/HomePage.tsx
git commit -m "feat(cicd-ui): Home page compact delivery widget (top 8 rows)"
```

---

## Task 26: Jenkins + ArgoCD forms in IntegrationSettings

**Files:**
- Modify: `frontend/src/components/Settings/IntegrationSettings.tsx`
- Create: `frontend/src/components/Settings/__tests__/cicd-forms.test.tsx`

**Step 1: Write the failing test**

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { IntegrationSettings } from "../IntegrationSettings";

test("renders Jenkins form fields", () => {
  render(<IntegrationSettings />);
  fireEvent.click(screen.getByRole("button", { name: /add jenkins/i }));
  expect(screen.getByLabelText(/base url/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/api token/i)).toBeInTheDocument();
});

test("renders ArgoCD form fields", () => {
  render(<IntegrationSettings />);
  fireEvent.click(screen.getByRole("button", { name: /add argocd/i }));
  expect(screen.getByLabelText(/base url/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/token/i)).toBeInTheDocument();
});

test("Test Connection calls probe endpoint", async () => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) }) as any;
  render(<IntegrationSettings />);
  fireEvent.click(screen.getByRole("button", { name: /add jenkins/i }));
  fireEvent.change(screen.getByLabelText(/base url/i), { target: { value: "https://j" } });
  fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "u" } });
  fireEvent.change(screen.getByLabelText(/api token/i), { target: { value: "t" } });
  fireEvent.click(screen.getByRole("button", { name: /test connection/i }));
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/v4/integrations/probe"),
    expect.objectContaining({ method: "POST" }),
  );
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- cicd-forms`
Expected: FAIL.

**Step 3: Write minimal implementation**

Add two form variants to `IntegrationSettings.tsx` following the existing pattern used for `github`/`elk` forms. Use the existing probe POST path. Ensure each form has:

- Jenkins: `base_url`, `username`, `api_token`
- ArgoCD: `base_url`, `token`
- "Test Connection" → `POST /api/v4/integrations/probe { service_type, url, credentials }`
- "Save" → POST to the existing integrations save endpoint

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- cicd-forms`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add frontend/src/components/Settings/IntegrationSettings.tsx frontend/src/components/Settings/__tests__/cicd-forms.test.tsx
git commit -m "feat(settings): Jenkins and ArgoCD integration forms"
```

---

## Task 27: Manual verification checklist

**Files:**
- Create: `docs/plans/2026-04-10-cicd-integration-smoke.md`

This task has no automated tests — it is the final human-in-the-loop gate before handoff.

**Step 1: Write the checklist**

```markdown
# CI/CD Phase A — Smoke Verification

Run these before declaring Phase A complete.

## Prerequisites
- [ ] Backend: `pytest backend/tests/integrations/cicd/ backend/tests/test_change_agent_cicd_enrichment.py backend/tests/agents/test_pipeline_agent.py backend/tests/integrations/test_cicd_*.py -v` — all green
- [ ] Frontend: `cd frontend && npm test -- CICD DeliveryRow DeliveryFilters DeliveryDrawer SplitFlapCell cicd-forms cicd-route cicd-types` — all green
- [ ] `npm run build` — clean

## Configured sources path
- [ ] Settings → Integrations → Add Jenkins → real URL/username/token → "Test Connection" returns OK → Save
- [ ] Settings → Integrations → Add ArgoCD (REST) → real URL/token → Test Connection OK → Save
- [ ] Navigate to `/cicd` → board renders with live rows from both sources, newest first
- [ ] Status cell animates on first load AND on an in-progress → terminal transition
- [ ] Kind filter: "Deploys" hides COMMIT rows; "Commits" hides BUILD/SYNC rows
- [ ] Status filter: "Failed" leaves only failed rows
- [ ] Click a BUILD row → drawer opens with Commit tab populated from the GitHub commit detail endpoint
- [ ] Diff tab shows file patches
- [ ] Related tab shows any other rows with the same `git_sha`

## Auto-discovery path
- [ ] On a k8s cluster where ArgoCD is installed and the kube context has read access to `applications.argoproj.io` CRDs AND no ArgoCD is manually configured:
  - [ ] `/cicd` shows ArgoCD sync rows
  - [ ] Configuring ArgoCD manually in Settings replaces auto-discovered instance (auto-discovery is skipped)

## Failure isolation
- [ ] Misconfigure Jenkins credentials → `/cicd` still shows ArgoCD rows + warning chip "⚠ N source issues" in header
- [ ] Everything unconfigured → empty state links to Settings → Integrations

## ChangeAgent enrichment
- [ ] Start a `troubleshoot_app` session against a namespace with a recent failed Jenkins build
- [ ] WarRoom shows an AgentFindingCard from ChangeAgent that references the build with a deeplink chip

## Pipeline capability
- [ ] Sidebar Diagnostics → Pipeline → form asks for instance, name, window
- [ ] Submit → PipelineAgent produces a finding in WarRoom within ≤4 iterations

## Home widget
- [ ] Home page shows top-8 Delivery widget
- [ ] "See all ↗" navigates to `/cicd`
```

**Step 2: Commit**

```bash
git add docs/plans/2026-04-10-cicd-integration-smoke.md
git commit -m "docs(cicd): Phase A smoke verification checklist"
```

---

## Completion

After Task 27 passes, announce:

> "I'm using the finishing-a-development-branch skill to complete this work."

Then use superpowers:finishing-a-development-branch to present the 4 merge/PR/keep/discard options.

---

## Plan Summary

**27 tasks covering Phase A end-to-end:**
- Tasks 1–9 — `backend/src/integrations/cicd/` package (models, clients, resolver)
- Tasks 10–12 — integrations framework wiring (store, probe, audit)
- Tasks 13–15 — agent layer (ChangeAgent enrichment, PipelineAgent, supervisor routing)
- Tasks 16–17 — API endpoints (`/cicd/stream`, `/cicd/commit/...`)
- Tasks 18–25 — frontend (types, routing, SplitFlapCell, row, filters, drawer, board, home widget)
- Task 26 — Settings forms
- Task 27 — manual verification

Every task is TDD: failing test → minimal code → green → commit. No batching.

Phase B (remediation write-path + webhooks) is explicitly out of scope; the `trigger_action` method stub and audit hook are in place so Phase B is purely additive.



