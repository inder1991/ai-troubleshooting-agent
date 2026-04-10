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

<!-- REMAINING TASKS: 10–27 — appended next -->

