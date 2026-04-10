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

<!-- REMAINING TASKS: 5–27 — appended in subsequent plan updates -->
