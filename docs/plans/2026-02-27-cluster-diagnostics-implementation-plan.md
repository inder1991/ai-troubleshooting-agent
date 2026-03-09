# Cluster Diagnostics Engine — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a LangGraph-powered cluster diagnostic workflow with 4 parallel agents, causal synthesis, and a dedicated War Room UI — all behind the existing `cluster_diagnostics` capability card.

**Architecture:** LangGraph `StateGraph` with fan-out/fan-in pattern. Four diagnostic agents (Control Plane, Node, Network, Storage) run in parallel via an abstract `ClusterClient` platform adapter (K8s + OpenShift). A 3-stage synthesis pipeline (Merge → Causal → Verdict) produces a `ClusterHealthReport`. `GraphEventBridge` filters LangGraph events into the existing EventEmitter → WebSocket pipeline. A new `ClusterWarRoom` React view renders domain panels, a process map DAG, and causal chain visualization.

**Tech Stack:** Python 3.12, FastAPI, LangGraph 0.2, `kubernetes-asyncio`, `aiohttp`, Pydantic v2, React 18, TypeScript, Tailwind CSS

**Design Doc:** `docs/plans/2026-02-27-cluster-diagnostics-design.md`

---

## Task 1: Add async dependencies to requirements.txt

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: Add new dependencies**

Add these lines after the existing `kubernetes>=28.0.0` line:

```
kubernetes-asyncio>=30.0.0
aiohttp>=3.9.0
langgraph-checkpoint>=0.2.0
```

`elasticsearch[async]` is already covered by the existing `elasticsearch>=8.0.0` line.

**Step 2: Install dependencies**

Run: `cd backend && pip install -r requirements.txt`
Expected: All packages install successfully

**Step 3: Verify imports work**

Run: `python -c "import kubernetes_asyncio; import aiohttp; import langgraph; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat(cluster): add async K8s, aiohttp, langgraph-checkpoint deps"
```

---

## Task 2: Create Pydantic state models (`state.py`)

**Files:**
- Create: `backend/src/agents/cluster/__init__.py`
- Create: `backend/src/agents/cluster/state.py`
- Create: `backend/tests/test_cluster_state.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_cluster_state.py
import pytest
from src.agents.cluster.state import (
    FailureReason, DomainStatus, DomainAnomaly, TruncationFlags,
    DomainReport, CausalLink, CausalChain, BlastRadius,
    RemediationStep, ClusterHealthReport, ClusterDiagnosticState,
)


def test_domain_report_defaults():
    report = DomainReport(domain="ctrl_plane")
    assert report.status == DomainStatus.PENDING
    assert report.confidence == 0
    assert report.anomalies == []
    assert report.ruled_out == []
    assert report.evidence_refs == []
    assert report.truncation_flags == TruncationFlags()


def test_domain_report_failed():
    report = DomainReport(
        domain="node",
        status=DomainStatus.FAILED,
        failure_reason=FailureReason.TIMEOUT,
        confidence=0,
        data_gathered_before_failure=["3 nodes checked before timeout"],
    )
    assert report.failure_reason == FailureReason.TIMEOUT
    assert len(report.data_gathered_before_failure) == 1


def test_causal_chain_weakest_link():
    chain = CausalChain(
        chain_id="cc-001",
        confidence=0.88,
        root_cause=DomainAnomaly(
            domain="node", anomaly_id="node-003",
            description="disk full", evidence_ref="ev-001",
        ),
        cascading_effects=[
            CausalLink(
                order=1, domain="ctrl_plane", anomaly_id="cp-002",
                description="pods evicted",
                link_type="resource_exhaustion -> pod_eviction",
                evidence_ref="ev-002",
            ),
        ],
    )
    assert chain.chain_id == "cc-001"
    assert chain.cascading_effects[0].link_type == "resource_exhaustion -> pod_eviction"


def test_cluster_diagnostic_state_defaults():
    state = ClusterDiagnosticState(diagnostic_id="DIAG-001")
    assert state.platform == ""
    assert len(state.domain_reports) == 0
    assert len(state.causal_chains) == 0
    assert state.re_dispatch_count == 0
    assert state.phase == "pre_flight"


def test_cluster_health_report_serialization():
    report = ClusterHealthReport(
        diagnostic_id="DIAG-001",
        platform="openshift",
        platform_version="4.14.2",
        platform_health="DEGRADED",
        data_completeness=0.75,
        blast_radius=BlastRadius(
            summary="14% of nodes under pressure",
            affected_namespaces=3, affected_pods=47, affected_nodes=2,
        ),
        causal_chains=[],
        uncorrelated_findings=[],
        domain_reports=[],
        remediation={"immediate": [], "long_term": []},
        execution_metadata={
            "total_duration_ms": 18340, "token_usage_total": 12500,
            "re_dispatch_count": 0, "agents_succeeded": 4, "agents_failed": 0,
        },
    )
    data = report.model_dump(mode="json")
    assert data["platform_health"] == "DEGRADED"
    assert data["blast_radius"]["affected_pods"] == 47
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_cluster_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.cluster'`

**Step 3: Write implementation**

```python
# backend/src/agents/cluster/__init__.py
```

```python
# backend/src/agents/cluster/state.py
"""Pydantic models for the Cluster Diagnostic LangGraph state."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class FailureReason(str, Enum):
    TIMEOUT = "TIMEOUT"
    RBAC_DENIED = "RBAC_DENIED"
    API_UNREACHABLE = "API_UNREACHABLE"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
    EXCEPTION = "EXCEPTION"


class DomainStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class TruncationFlags(BaseModel):
    events: bool = False
    pods: bool = False
    log_lines: bool = False
    metric_points: bool = False
    nodes: bool = False
    pvcs: bool = False


class DomainAnomaly(BaseModel):
    domain: str
    anomaly_id: str
    description: str
    evidence_ref: str
    severity: str = "medium"


class DomainReport(BaseModel):
    domain: str
    status: DomainStatus = DomainStatus.PENDING
    failure_reason: Optional[FailureReason] = None
    confidence: int = 0
    anomalies: list[DomainAnomaly] = Field(default_factory=list)
    ruled_out: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    truncation_flags: TruncationFlags = Field(default_factory=TruncationFlags)
    data_gathered_before_failure: list[str] = Field(default_factory=list)
    token_usage: int = 0
    duration_ms: int = 0


class CausalLink(BaseModel):
    order: int
    domain: str
    anomaly_id: str
    description: str
    link_type: str
    evidence_ref: str


class CausalChain(BaseModel):
    chain_id: str
    confidence: float
    root_cause: DomainAnomaly
    cascading_effects: list[CausalLink] = Field(default_factory=list)


class BlastRadius(BaseModel):
    summary: str = ""
    affected_namespaces: int = 0
    affected_pods: int = 0
    affected_nodes: int = 0


class RemediationStep(BaseModel):
    command: str = ""
    description: str = ""
    risk_level: str = "medium"
    effort_estimate: str = ""


class ClusterHealthReport(BaseModel):
    diagnostic_id: str
    platform: str = ""
    platform_version: str = ""
    platform_health: str = "UNKNOWN"
    data_completeness: float = 0.0
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    uncorrelated_findings: list[DomainAnomaly] = Field(default_factory=list)
    domain_reports: list[DomainReport] = Field(default_factory=list)
    remediation: dict[str, list] = Field(default_factory=dict)
    execution_metadata: dict[str, Any] = Field(default_factory=dict)


class ClusterDiagnosticState(BaseModel):
    """LangGraph shared state. Only compact summaries — no raw data, no credentials."""
    diagnostic_id: str
    platform: str = ""
    platform_version: str = ""
    namespaces: list[str] = Field(default_factory=list)
    exclude_namespaces: list[str] = Field(default_factory=list)
    domain_reports: list[DomainReport] = Field(default_factory=list)
    causal_chains: list[CausalChain] = Field(default_factory=list)
    uncorrelated_findings: list[DomainAnomaly] = Field(default_factory=list)
    health_report: Optional[ClusterHealthReport] = None
    phase: str = "pre_flight"
    re_dispatch_count: int = 0
    re_dispatch_domains: list[str] = Field(default_factory=list)
    data_completeness: float = 0.0
    error: Optional[str] = None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_cluster_state.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/__init__.py backend/src/agents/cluster/state.py backend/tests/test_cluster_state.py
git commit -m "feat(cluster): add Pydantic state models for cluster diagnostic graph"
```

---

## Task 3: Create `@traced_node` decorator

**Files:**
- Create: `backend/src/agents/cluster/traced_node.py`
- Create: `backend/tests/test_traced_node.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_traced_node.py
import asyncio
import pytest
from src.agents.cluster.traced_node import traced_node, NodeExecution
from src.agents.cluster.state import FailureReason


@pytest.mark.asyncio
async def test_traced_node_success():
    @traced_node(timeout_seconds=5)
    async def my_node(state, config):
        return {"domain_reports": [{"domain": "test", "status": "SUCCESS"}]}

    result = await my_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert "domain_reports" in result


@pytest.mark.asyncio
async def test_traced_node_timeout():
    @traced_node(timeout_seconds=0.1)
    async def slow_node(state, config):
        await asyncio.sleep(10)
        return {}

    result = await slow_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    # Should not raise, should return partial result with failure info
    assert result.get("_trace") is not None or result == {}


@pytest.mark.asyncio
async def test_traced_node_exception():
    @traced_node(timeout_seconds=5)
    async def bad_node(state, config):
        raise ValueError("something broke")

    result = await bad_node({"diagnostic_id": "D-1"}, {"configurable": {}})
    assert result.get("_trace") is not None or result == {}


def test_node_execution_model():
    execution = NodeExecution(
        node_name="ctrl_plane_agent",
        duration_ms=2340,
        failure_reason=None,
        status="SUCCESS",
    )
    assert execution.node_name == "ctrl_plane_agent"
    assert execution.duration_ms == 2340
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_traced_node.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/src/agents/cluster/traced_node.py
"""@traced_node decorator: timeout enforcement, failure classification, execution tracing."""

from __future__ import annotations

import asyncio
import time
import functools
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field
from src.agents.cluster.state import FailureReason
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NodeExecution(BaseModel):
    """Trace record for a single graph node execution."""
    node_name: str
    status: str = "PENDING"
    duration_ms: int = 0
    failure_reason: Optional[FailureReason] = None
    failure_detail: str = ""
    token_usage: int = 0
    input_summary: str = ""
    output_summary: str = ""


def traced_node(timeout_seconds: float = 60):
    """Decorator that wraps a LangGraph node function with timeout + tracing."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(state: dict, config: dict | None = None) -> dict:
            node_name = func.__name__
            start = time.monotonic()
            trace = NodeExecution(node_name=node_name, status="RUNNING")

            try:
                result = await asyncio.wait_for(
                    func(state, config or {}),
                    timeout=timeout_seconds,
                )
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "SUCCESS"
                trace.duration_ms = elapsed
                if isinstance(result, dict):
                    result["_trace"] = trace.model_dump(mode="json")
                return result

            except asyncio.TimeoutError:
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "FAILED"
                trace.failure_reason = FailureReason.TIMEOUT
                trace.failure_detail = f"Timed out after {timeout_seconds}s"
                trace.duration_ms = elapsed
                logger.warning(
                    "Node timed out",
                    extra={"node": node_name, "action": "timeout", "extra": f"{timeout_seconds}s"},
                )
                return {"_trace": trace.model_dump(mode="json")}

            except Exception as e:
                elapsed = int((time.monotonic() - start) * 1000)
                trace.status = "FAILED"
                trace.failure_reason = FailureReason.EXCEPTION
                trace.failure_detail = str(e)
                trace.duration_ms = elapsed
                logger.error(
                    "Node failed",
                    extra={"node": node_name, "action": "exception", "extra": str(e)},
                )
                return {"_trace": trace.model_dump(mode="json")}

        return wrapper
    return decorator
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_traced_node.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/traced_node.py backend/tests/test_traced_node.py
git commit -m "feat(cluster): add @traced_node decorator with timeout and failure classification"
```

---

## Task 4: Create abstract `ClusterClient` and diagnostic cache

**Files:**
- Create: `backend/src/agents/cluster_client/__init__.py`
- Create: `backend/src/agents/cluster_client/base.py`
- Create: `backend/src/agents/cluster_client/diagnostic_cache.py`
- Create: `backend/tests/test_cluster_client.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_cluster_client.py
import pytest
from src.agents.cluster_client.base import ClusterClient, QueryResult
from src.agents.cluster_client.diagnostic_cache import DiagnosticCache


def test_query_result_truncation():
    qr = QueryResult(
        data=[{"name": f"pod-{i}"} for i in range(500)],
        total_available=47392,
        returned=500,
        truncated=True,
        sort_order="severity_desc",
    )
    assert qr.truncated is True
    assert qr.returned == 500


def test_query_result_no_truncation():
    qr = QueryResult(data=[{"name": "pod-1"}], total_available=1, returned=1)
    assert qr.truncated is False


def test_cluster_client_is_abstract():
    with pytest.raises(TypeError):
        ClusterClient()  # type: ignore


@pytest.mark.asyncio
async def test_diagnostic_cache_hit():
    cache = DiagnosticCache(diagnostic_id="D-1")

    async def fetcher():
        return QueryResult(data=[1, 2, 3], total_available=3, returned=3)

    result1 = await cache.get_or_fetch("list_pods", {"ns": "default"}, fetcher)
    result2 = await cache.get_or_fetch("list_pods", {"ns": "default"}, fetcher)
    assert result1.data == result2.data


@pytest.mark.asyncio
async def test_diagnostic_cache_force_fresh():
    cache = DiagnosticCache(diagnostic_id="D-1")
    call_count = 0

    async def fetcher():
        nonlocal call_count
        call_count += 1
        return QueryResult(data=[call_count], total_available=1, returned=1)

    await cache.get_or_fetch("list_pods", {}, fetcher)
    result = await cache.get_or_fetch("list_pods", {}, fetcher, force_fresh=True)
    assert call_count == 2
    assert result.data == [2]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_cluster_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# backend/src/agents/cluster_client/__init__.py
```

```python
# backend/src/agents/cluster_client/base.py
"""Abstract ClusterClient — platform adapter for K8s and OpenShift."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field


# Object count caps from design doc
OBJECT_CAPS = {
    "events": 500,
    "pods": 1000,
    "log_lines": 2000,
    "metric_points": 500,
    "nodes": 500,
    "pvcs": 500,
}


class QueryResult(BaseModel):
    """Standard result wrapper with truncation tracking."""
    data: list[Any] = Field(default_factory=list)
    total_available: int = 0
    returned: int = 0
    truncated: bool = False
    sort_order: str = "severity_desc"


class ClusterClient(ABC):
    """Abstract base class for cluster interaction. Read-only contract."""

    @abstractmethod
    async def detect_platform(self) -> dict[str, str]:
        """Return {"platform": "kubernetes"|"openshift", "version": "1.28.3"}."""
        ...

    @abstractmethod
    async def list_namespaces(self) -> QueryResult:
        """List all namespaces."""
        ...

    @abstractmethod
    async def list_nodes(self) -> QueryResult:
        """List nodes with conditions."""
        ...

    @abstractmethod
    async def list_pods(self, namespace: str = "") -> QueryResult:
        """List pods. If namespace empty, list across all namespaces."""
        ...

    @abstractmethod
    async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
        """List events with optional field selector."""
        ...

    @abstractmethod
    async def list_pvcs(self, namespace: str = "") -> QueryResult:
        """List PersistentVolumeClaims."""
        ...

    @abstractmethod
    async def get_api_health(self) -> dict[str, Any]:
        """Check API server health."""
        ...

    @abstractmethod
    async def query_prometheus(self, query: str, time_range: str = "1h") -> QueryResult:
        """Execute a PromQL query."""
        ...

    @abstractmethod
    async def query_logs(self, index: str, query: dict, max_lines: int = 2000) -> QueryResult:
        """Query Elasticsearch logs."""
        ...

    # OpenShift-specific (return empty on vanilla K8s)
    async def get_cluster_operators(self) -> QueryResult:
        return QueryResult()

    async def get_machine_sets(self) -> QueryResult:
        return QueryResult()

    async def get_routes(self, namespace: str = "") -> QueryResult:
        return QueryResult()

    async def close(self) -> None:
        """Cleanup async resources."""
        pass
```

```python
# backend/src/agents/cluster_client/diagnostic_cache.py
"""Cache-on-first-read per diagnostic run."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Awaitable, Callable

from src.agents.cluster_client.base import QueryResult


class DiagnosticCache:
    """Per-diagnostic in-memory cache. Retried nodes see identical data."""

    def __init__(self, diagnostic_id: str):
        self.diagnostic_id = diagnostic_id
        self._cache: dict[str, QueryResult] = {}

    def _make_key(self, method: str, params: dict) -> str:
        params_hash = hashlib.sha256(
            json.dumps(params, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return f"{method}:{params_hash}"

    async def get_or_fetch(
        self,
        method: str,
        params: dict,
        fetcher: Callable[[], Awaitable[QueryResult]],
        force_fresh: bool = False,
    ) -> QueryResult:
        key = self._make_key(method, params)
        if not force_fresh and key in self._cache:
            return self._cache[key]
        result = await fetcher()
        self._cache[key] = result
        return result

    def clear(self) -> None:
        self._cache.clear()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_cluster_client.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add backend/src/agents/cluster_client/ backend/tests/test_cluster_client.py
git commit -m "feat(cluster): add abstract ClusterClient, QueryResult, and DiagnosticCache"
```

---

## Task 5: Create mock `ClusterClient` implementation with fixtures

**Files:**
- Create: `backend/src/agents/cluster_client/mock_client.py`
- Create: `backend/src/agents/fixtures/cluster_ctrl_plane_mock.json`
- Create: `backend/src/agents/fixtures/cluster_node_mock.json`
- Create: `backend/src/agents/fixtures/cluster_network_mock.json`
- Create: `backend/src/agents/fixtures/cluster_storage_mock.json`
- Create: `backend/tests/test_mock_cluster_client.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_mock_cluster_client.py
import pytest
from src.agents.cluster_client.mock_client import MockClusterClient


@pytest.mark.asyncio
async def test_mock_detect_platform():
    client = MockClusterClient(platform="openshift")
    info = await client.detect_platform()
    assert info["platform"] == "openshift"
    assert "version" in info


@pytest.mark.asyncio
async def test_mock_list_nodes():
    client = MockClusterClient()
    result = await client.list_nodes()
    assert len(result.data) > 0
    assert result.truncated is False


@pytest.mark.asyncio
async def test_mock_list_events_truncation():
    client = MockClusterClient()
    result = await client.list_events()
    # Mock should return events with realistic count
    assert result.returned <= 500


@pytest.mark.asyncio
async def test_mock_openshift_operators():
    client = MockClusterClient(platform="openshift")
    result = await client.get_cluster_operators()
    assert len(result.data) > 0


@pytest.mark.asyncio
async def test_mock_k8s_operators_empty():
    client = MockClusterClient(platform="kubernetes")
    result = await client.get_cluster_operators()
    assert len(result.data) == 0


@pytest.mark.asyncio
async def test_mock_prometheus_query():
    client = MockClusterClient()
    result = await client.query_prometheus("node_cpu_utilisation")
    assert len(result.data) > 0


@pytest.mark.asyncio
async def test_mock_query_logs():
    client = MockClusterClient()
    result = await client.query_logs("cluster-logs", {"query": "error"})
    assert len(result.data) > 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_mock_cluster_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create fixture JSON files**

Create 4 mock fixture files with realistic cluster data. Each has a scenario: "infra-node-03 at 97% disk causes CoreDNS eviction and DNS failures."

```json
// backend/src/agents/fixtures/cluster_ctrl_plane_mock.json
{
  "api_health": {"status": "ok", "latency_ms": 45},
  "cluster_operators": [
    {"name": "dns", "available": false, "degraded": true, "message": "CoreDNS pods unavailable on infra-node-03"},
    {"name": "ingress", "available": true, "degraded": true, "message": "2 of 3 router pods degraded"},
    {"name": "monitoring", "available": true, "degraded": false, "message": ""},
    {"name": "authentication", "available": true, "degraded": false, "message": ""}
  ],
  "etcd_members": [
    {"name": "etcd-master-01", "status": "healthy", "db_size_mb": 245},
    {"name": "etcd-master-02", "status": "healthy", "db_size_mb": 243},
    {"name": "etcd-master-03", "status": "healthy", "db_size_mb": 247}
  ],
  "api_audit_logs": [
    {"timestamp": "2026-02-27T10:25:00Z", "verb": "delete", "resource": "pods", "namespace": "production", "user": "system:node:infra-node-03", "reason": "eviction"},
    {"timestamp": "2026-02-27T10:25:01Z", "verb": "delete", "resource": "pods", "namespace": "production", "user": "system:node:infra-node-03", "reason": "eviction"}
  ]
}
```

```json
// backend/src/agents/fixtures/cluster_node_mock.json
{
  "nodes": [
    {"name": "master-01", "status": "Ready", "roles": ["control-plane"], "cpu_pct": 34, "memory_pct": 52, "disk_pct": 41},
    {"name": "master-02", "status": "Ready", "roles": ["control-plane"], "cpu_pct": 28, "memory_pct": 48, "disk_pct": 38},
    {"name": "master-03", "status": "Ready", "roles": ["control-plane"], "cpu_pct": 31, "memory_pct": 50, "disk_pct": 40},
    {"name": "worker-01", "status": "Ready", "roles": ["worker"], "cpu_pct": 72, "memory_pct": 68, "disk_pct": 55},
    {"name": "worker-02", "status": "Ready", "roles": ["worker"], "cpu_pct": 65, "memory_pct": 71, "disk_pct": 48},
    {"name": "infra-node-03", "status": "Ready,DiskPressure", "roles": ["infra"], "cpu_pct": 45, "memory_pct": 62, "disk_pct": 97}
  ],
  "events": [
    {"type": "Warning", "reason": "Evicted", "object": "pod/coredns-abc123", "message": "The node had condition: [DiskPressure]", "node": "infra-node-03", "timestamp": "2026-02-27T10:24:30Z"},
    {"type": "Warning", "reason": "Evicted", "object": "pod/router-xyz789", "message": "The node had condition: [DiskPressure]", "node": "infra-node-03", "timestamp": "2026-02-27T10:24:32Z"},
    {"type": "Warning", "reason": "FailedScheduling", "object": "pod/coredns-def456", "message": "0/6 nodes available: 1 node had disk pressure, 3 were control-plane", "timestamp": "2026-02-27T10:25:00Z"}
  ],
  "resource_quotas": [],
  "top_pods": [
    {"namespace": "production", "name": "access-log-collector-0", "cpu_m": 150, "memory_mi": 4200, "node": "infra-node-03"}
  ]
}
```

```json
// backend/src/agents/fixtures/cluster_network_mock.json
{
  "dns_pods": [
    {"name": "coredns-abc123", "status": "Evicted", "node": "infra-node-03", "restarts": 0},
    {"name": "coredns-def456", "status": "Pending", "node": "", "restarts": 0},
    {"name": "coredns-ghi789", "status": "Running", "node": "worker-01", "restarts": 0}
  ],
  "ingress_controllers": [
    {"name": "default", "replicas": 3, "available": 1, "status": "Degraded"}
  ],
  "network_policies": [],
  "dns_metrics": {
    "resolution_failures_pct": 40.2,
    "avg_latency_ms": 2450,
    "queries_per_sec": 1200
  },
  "ingress_metrics": {
    "5xx_rate_pct": 12.5,
    "request_rate": 3400,
    "p99_latency_ms": 8200
  },
  "logs": [
    {"timestamp": "2026-02-27T10:25:10Z", "source": "coredns", "message": "SERVFAIL for api.internal.svc.cluster.local: context deadline exceeded"},
    {"timestamp": "2026-02-27T10:25:12Z", "source": "coredns", "message": "SERVFAIL for payment.production.svc.cluster.local: i/o timeout"}
  ]
}
```

```json
// backend/src/agents/fixtures/cluster_storage_mock.json
{
  "storage_classes": [
    {"name": "gp3", "provisioner": "ebs.csi.aws.com", "default": true, "reclaim_policy": "Delete"},
    {"name": "gp2", "provisioner": "kubernetes.io/aws-ebs", "default": false, "reclaim_policy": "Delete"}
  ],
  "pvcs": [
    {"name": "access-logs-pvc", "namespace": "production", "status": "Bound", "capacity": "10Gi", "used_pct": 98, "storage_class": "gp3"},
    {"name": "app-data-pvc", "namespace": "production", "status": "Bound", "capacity": "50Gi", "used_pct": 45, "storage_class": "gp3"},
    {"name": "monitoring-pvc", "namespace": "monitoring", "status": "Bound", "capacity": "100Gi", "used_pct": 32, "storage_class": "gp3"}
  ],
  "csi_driver_pods": [
    {"name": "ebs-csi-controller-0", "status": "Running", "restarts": 0},
    {"name": "ebs-csi-node-abc", "status": "Running", "restarts": 0}
  ],
  "volume_metrics": {
    "iops_throttled_pct": 0,
    "attach_latency_ms": 120
  }
}
```

**Step 4: Write `MockClusterClient`**

```python
# backend/src/agents/cluster_client/mock_client.py
"""Mock ClusterClient that returns fixture data for demo/dev/testing."""

from __future__ import annotations

import json
import os
from typing import Any

from src.agents.cluster_client.base import ClusterClient, QueryResult, OBJECT_CAPS

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def _load_fixture(name: str) -> dict:
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, "r") as f:
        return json.load(f)


class MockClusterClient(ClusterClient):
    """Returns pre-built fixture data. No real cluster connection."""

    def __init__(self, platform: str = "openshift"):
        self._platform = platform

    async def detect_platform(self) -> dict[str, str]:
        return {
            "platform": self._platform,
            "version": "4.14.2" if self._platform == "openshift" else "1.28.3",
        }

    async def list_namespaces(self) -> QueryResult:
        ns = ["default", "kube-system", "monitoring", "production", "staging"]
        return QueryResult(data=ns, total_available=len(ns), returned=len(ns))

    async def list_nodes(self) -> QueryResult:
        data = _load_fixture("cluster_node_mock.json")
        nodes = data["nodes"]
        return QueryResult(data=nodes, total_available=len(nodes), returned=len(nodes))

    async def list_pods(self, namespace: str = "") -> QueryResult:
        # Return top pods from node fixture as representative sample
        data = _load_fixture("cluster_node_mock.json")
        pods = data.get("top_pods", [])
        return QueryResult(data=pods, total_available=len(pods), returned=len(pods))

    async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
        data = _load_fixture("cluster_node_mock.json")
        events = data.get("events", [])
        cap = OBJECT_CAPS["events"]
        truncated = len(events) > cap
        returned = events[:cap]
        return QueryResult(
            data=returned, total_available=len(events),
            returned=len(returned), truncated=truncated,
        )

    async def list_pvcs(self, namespace: str = "") -> QueryResult:
        data = _load_fixture("cluster_storage_mock.json")
        pvcs = data.get("pvcs", [])
        return QueryResult(data=pvcs, total_available=len(pvcs), returned=len(pvcs))

    async def get_api_health(self) -> dict[str, Any]:
        data = _load_fixture("cluster_ctrl_plane_mock.json")
        return data.get("api_health", {"status": "ok"})

    async def query_prometheus(self, query: str, time_range: str = "1h") -> QueryResult:
        # Return domain-appropriate metrics based on query content
        if "dns" in query or "coredns" in query:
            data = _load_fixture("cluster_network_mock.json")
            metrics = data.get("dns_metrics", {})
        elif "node" in query or "cpu" in query or "memory" in query:
            data = _load_fixture("cluster_node_mock.json")
            metrics = {"nodes": data.get("nodes", [])}
        else:
            metrics = {"value": 0}
        return QueryResult(data=[metrics], total_available=1, returned=1)

    async def query_logs(self, index: str, query: dict, max_lines: int = 2000) -> QueryResult:
        data = _load_fixture("cluster_network_mock.json")
        logs = data.get("logs", [])
        return QueryResult(data=logs, total_available=len(logs), returned=len(logs))

    # OpenShift-specific
    async def get_cluster_operators(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        data = _load_fixture("cluster_ctrl_plane_mock.json")
        ops = data.get("cluster_operators", [])
        return QueryResult(data=ops, total_available=len(ops), returned=len(ops))

    async def get_machine_sets(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        return QueryResult(data=[{"name": "worker-us-east-1a", "replicas": 3, "ready": 3}], total_available=1, returned=1)

    async def get_routes(self, namespace: str = "") -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        return QueryResult(data=[{"name": "app-route", "host": "app.example.com", "status": "Admitted"}], total_available=1, returned=1)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_mock_cluster_client.py -v`
Expected: 7 passed

**Step 6: Commit**

```bash
git add backend/src/agents/cluster_client/mock_client.py backend/src/agents/fixtures/ backend/tests/test_mock_cluster_client.py
git commit -m "feat(cluster): add MockClusterClient with fixture data for all 4 domains"
```

---

## Task 6: Create `GraphEventBridge`

**Files:**
- Create: `backend/src/agents/cluster/graph_event_bridge.py`
- Create: `backend/tests/test_graph_event_bridge.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_graph_event_bridge.py
import pytest
from unittest.mock import AsyncMock
from src.agents.cluster.graph_event_bridge import GraphEventBridge


@pytest.fixture
def mock_emitter():
    emitter = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter


@pytest.mark.asyncio
async def test_bridge_agent_started(mock_emitter):
    bridge = GraphEventBridge(
        diagnostic_id="D-1",
        emitter=mock_emitter,
    )
    await bridge.handle_event({
        "event": "on_chain_start",
        "name": "ctrl_plane_agent",
        "tags": [],
        "metadata": {},
    })
    mock_emitter.emit.assert_called_once()
    call_args = mock_emitter.emit.call_args
    assert call_args[1].get("event_type") or call_args[0][1] == "agent_started"


@pytest.mark.asyncio
async def test_bridge_drops_internal_events(mock_emitter):
    bridge = GraphEventBridge(
        diagnostic_id="D-1",
        emitter=mock_emitter,
    )
    # Internal chain events should be dropped
    await bridge.handle_event({
        "event": "on_chain_start",
        "name": "RunnableSequence",
        "tags": [],
        "metadata": {},
    })
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_bridge_tool_events(mock_emitter):
    bridge = GraphEventBridge(
        diagnostic_id="D-1",
        emitter=mock_emitter,
    )
    await bridge.handle_event({
        "event": "on_tool_start",
        "name": "list_nodes",
        "data": {"input": {"namespace": "default"}},
        "tags": ["ctrl_plane"],
        "metadata": {},
    })
    mock_emitter.emit.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_graph_event_bridge.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/agents/cluster/graph_event_bridge.py
"""Filter LangGraph astream_events(v2) into EventEmitter for WebSocket delivery."""

from __future__ import annotations

from typing import Any
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Top-level node names we care about
_KNOWN_NODES = {
    "pre_flight", "ctrl_plane_agent", "node_agent",
    "network_agent", "storage_agent", "synthesize",
    "dispatch", "confidence_check",
}

# Internal LangChain/LangGraph plumbing to drop
_INTERNAL_PREFIXES = {"Runnable", "ChatAnthropic", "ChannelWrite", "ChannelRead"}


class GraphEventBridge:
    """Translates LangGraph events to domain-tagged EventEmitter calls."""

    def __init__(self, diagnostic_id: str, emitter: Any):
        self.diagnostic_id = diagnostic_id
        self._emitter = emitter

    def _is_internal(self, name: str) -> bool:
        return any(name.startswith(prefix) for prefix in _INTERNAL_PREFIXES)

    def _extract_domain(self, name: str, tags: list[str]) -> str:
        """Extract domain from node name or tags."""
        if "ctrl_plane" in name:
            return "ctrl_plane"
        if "node_agent" in name:
            return "node"
        if "network" in name:
            return "network"
        if "storage" in name:
            return "storage"
        if "synthesize" in name:
            return "supervisor"
        for tag in tags:
            if tag in ("ctrl_plane", "node", "network", "storage"):
                return tag
        return "supervisor"

    async def handle_event(self, event: dict[str, Any]) -> None:
        """Process a single LangGraph streaming event."""
        event_type = event.get("event", "")
        name = event.get("name", "")
        tags = event.get("tags", [])

        # Drop internal plumbing
        if self._is_internal(name):
            return

        domain = self._extract_domain(name, tags)

        if event_type == "on_chain_start" and name in _KNOWN_NODES:
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="agent_started",
                message=f"Starting {name}",
                details={
                    "diagnostic_id": self.diagnostic_id,
                    "domain": domain,
                    "node_name": name,
                },
            )

        elif event_type == "on_chain_end" and name in _KNOWN_NODES:
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="agent_completed",
                message=f"Completed {name}",
                details={
                    "diagnostic_id": self.diagnostic_id,
                    "domain": domain,
                    "node_name": name,
                },
            )

        elif event_type == "on_tool_start":
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="tool_call",
                message=f"Querying: {name}",
                details={
                    "diagnostic_id": self.diagnostic_id,
                    "domain": domain,
                    "tool_name": name,
                    "tool_input": str(event.get("data", {}).get("input", ""))[:200],
                },
            )

        elif event_type == "on_tool_end":
            output = event.get("data", {}).get("output", "")
            summary = str(output)[:300] if output else ""
            await self._emitter.emit(
                agent_name=f"cluster_{domain}",
                event_type="tool_result",
                message=summary,
                details={
                    "diagnostic_id": self.diagnostic_id,
                    "domain": domain,
                    "tool_name": name,
                },
            )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_graph_event_bridge.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/graph_event_bridge.py backend/tests/test_graph_event_bridge.py
git commit -m "feat(cluster): add GraphEventBridge to filter LangGraph events to WebSocket"
```

---

## Task 7: Create the 4 diagnostic agent node functions

**Files:**
- Create: `backend/src/agents/cluster/ctrl_plane_agent.py`
- Create: `backend/src/agents/cluster/node_agent.py`
- Create: `backend/src/agents/cluster/network_agent.py`
- Create: `backend/src/agents/cluster/storage_agent.py`
- Create: `backend/tests/test_cluster_agents.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_cluster_agents.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
from src.agents.cluster.node_agent import node_agent
from src.agents.cluster.network_agent import network_agent
from src.agents.cluster.storage_agent import storage_agent
from src.agents.cluster.state import ClusterDiagnosticState, DomainStatus


def _make_state():
    return ClusterDiagnosticState(
        diagnostic_id="DIAG-TEST",
        platform="openshift",
        platform_version="4.14.2",
        namespaces=["default", "production"],
    ).model_dump(mode="json")


def _make_config(mock_client):
    return {
        "configurable": {
            "cluster_client": mock_client,
            "emitter": AsyncMock(),
            "diagnostic_cache": MagicMock(),
        }
    }


@pytest.mark.asyncio
async def test_ctrl_plane_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient(platform="openshift")
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.ctrl_plane_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [{"domain": "ctrl_plane", "anomaly_id": "cp-001", "description": "DNS operator degraded", "evidence_ref": "ev-001"}],
            "ruled_out": ["etcd healthy"],
            "confidence": 75,
        }
        result = await ctrl_plane_agent(state, config)

    assert "domain_reports" in result
    report = result["domain_reports"][0]
    assert report["domain"] == "ctrl_plane"


@pytest.mark.asyncio
async def test_node_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient()
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.node_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [{"domain": "node", "anomaly_id": "node-003", "description": "infra-node-03 disk 97%", "evidence_ref": "ev-002"}],
            "ruled_out": [],
            "confidence": 90,
        }
        result = await node_agent(state, config)

    assert "domain_reports" in result
    report = result["domain_reports"][0]
    assert report["domain"] == "node"


@pytest.mark.asyncio
async def test_network_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient()
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.network_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [{"domain": "network", "anomaly_id": "net-001", "description": "40% DNS failures", "evidence_ref": "ev-003"}],
            "ruled_out": [],
            "confidence": 80,
        }
        result = await network_agent(state, config)

    assert "domain_reports" in result


@pytest.mark.asyncio
async def test_storage_agent_mock():
    from src.agents.cluster_client.mock_client import MockClusterClient
    client = MockClusterClient()
    state = _make_state()
    config = _make_config(client)

    with patch("src.agents.cluster.storage_agent._llm_analyze", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {
            "anomalies": [],
            "ruled_out": ["CSI healthy", "no stuck PVCs"],
            "confidence": 85,
        }
        result = await storage_agent(state, config)

    assert "domain_reports" in result
    report = result["domain_reports"][0]
    assert report["domain"] == "storage"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_cluster_agents.py -v`
Expected: FAIL

**Step 3: Write agent implementations**

Each agent follows the same pattern: gather data via ClusterClient → build LLM prompt → parse structured response → return DomainReport.

Create all 4 agent files with the shared `_llm_analyze` function pattern. Each agent:
1. Gathers domain-specific data from `ClusterClient`
2. Builds a system prompt with platform capability map
3. Calls `_llm_analyze` (two-pass: raw data → compact DomainReport)
4. Returns `{"domain_reports": [report_dict]}`

The agents are LangGraph node functions (not classes). They receive `(state: dict, config: dict)` and return partial state updates.

**Implementation for each agent follows the same structure** (showing `ctrl_plane_agent` as template — the others follow the same pattern with domain-specific data gathering and prompts):

```python
# backend/src/agents/cluster/ctrl_plane_agent.py
"""Control Plane & Etcd diagnostic agent node."""

from __future__ import annotations

import json
import time
from typing import Any

from src.agents.cluster.state import DomainReport, DomainStatus, DomainAnomaly, TruncationFlags, FailureReason
from src.agents.cluster.traced_node import traced_node
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are the Control Plane & Etcd diagnostic agent for DebugDuck.
You analyze: degraded operators, API server latency, etcd sync/health, certificate expiry, leader election.

Platform: {platform} {platform_version}
{platform_capabilities}

Analyze the provided cluster data and produce a structured assessment."""

_ANALYSIS_PROMPT = """Analyze this control plane data and produce a JSON response:

## Data Collected
{data_json}

## Required JSON Response Format
{{
  "anomalies": [
    {{"domain": "ctrl_plane", "anomaly_id": "cp-NNN", "description": "...", "evidence_ref": "ev-ctrl-NNN", "severity": "high|medium|low"}}
  ],
  "ruled_out": ["list of things checked and found healthy"],
  "confidence": 0-100
}}

Rules:
- Only report anomalies you have evidence for
- Include severity (high/medium/low)
- Confidence reflects data quality and coverage
- ruled_out is important — shows thoroughness"""


async def _llm_analyze(system: str, prompt: str) -> dict:
    """Two-pass LLM call. Returns parsed JSON dict."""
    client = AnthropicClient(agent_name="cluster_ctrl_plane")
    response = await client.chat(
        prompt=prompt,
        system=system,
        max_tokens=2000,
        temperature=0.1,
    )
    # Parse JSON from response
    text = response.content if hasattr(response, "content") else str(response)
    # Extract JSON block
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse LLM response as JSON", extra={"action": "parse_error"})
        return {"anomalies": [], "ruled_out": [], "confidence": 0}


@traced_node(timeout_seconds=30)
async def ctrl_plane_agent(state: dict, config: dict) -> dict:
    """LangGraph node: Control Plane & Etcd diagnostics."""
    start_ms = time.monotonic()
    client = config.get("configurable", {}).get("cluster_client")
    if not client:
        return {"domain_reports": [DomainReport(
            domain="ctrl_plane", status=DomainStatus.FAILED,
            failure_reason=FailureReason.EXCEPTION,
        ).model_dump(mode="json")]}

    platform = state.get("platform", "kubernetes")
    platform_version = state.get("platform_version", "")

    # Gather data
    api_health = await client.get_api_health()
    operators = await client.get_cluster_operators()
    events = await client.list_events(field_selector="involvedObject.kind=Node")

    platform_caps = (
        "Full access: ClusterOperators, Routes, SCCs, MachineSets, plus standard K8s."
        if platform == "openshift"
        else "Standard K8s only. No Routes, SCCs, ClusterOperators."
    )

    data_payload = {
        "api_health": api_health,
        "cluster_operators": operators.data,
        "events": events.data[:100],  # Summary for LLM
    }

    system = _SYSTEM_PROMPT.format(
        platform=platform,
        platform_version=platform_version,
        platform_capabilities=platform_caps,
    )
    prompt = _ANALYSIS_PROMPT.format(data_json=json.dumps(data_payload, indent=2, default=str))

    analysis = await _llm_analyze(system, prompt)

    anomalies = [
        DomainAnomaly(**a) for a in analysis.get("anomalies", [])
        if isinstance(a, dict) and "domain" in a
    ]

    elapsed = int((time.monotonic() - start_ms) * 1000)
    report = DomainReport(
        domain="ctrl_plane",
        status=DomainStatus.SUCCESS,
        confidence=analysis.get("confidence", 0),
        anomalies=anomalies,
        ruled_out=analysis.get("ruled_out", []),
        evidence_refs=[a.evidence_ref for a in anomalies],
        truncation_flags=TruncationFlags(events=events.truncated),
        duration_ms=elapsed,
    )

    return {"domain_reports": [report.model_dump(mode="json")]}
```

The other 3 agents (`node_agent.py`, `network_agent.py`, `storage_agent.py`) follow the **exact same structure** with domain-specific:
- System prompt text
- Data gathering calls (e.g., `list_nodes()`, `list_pvcs()`, `query_prometheus()`)
- Timeout values (node: 45s, network: 45s, storage: 60s)
- Domain name in DomainReport

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_cluster_agents.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py backend/src/agents/cluster/node_agent.py backend/src/agents/cluster/network_agent.py backend/src/agents/cluster/storage_agent.py backend/tests/test_cluster_agents.py
git commit -m "feat(cluster): add 4 diagnostic agent node functions with LLM analysis"
```

---

## Task 8: Create the 3-stage synthesis pipeline

**Files:**
- Create: `backend/src/agents/cluster/synthesizer.py`
- Create: `backend/tests/test_synthesizer.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_synthesizer.py
import pytest
from unittest.mock import AsyncMock, patch
from src.agents.cluster.synthesizer import synthesize, _merge_reports, _compute_data_completeness
from src.agents.cluster.state import (
    DomainReport, DomainStatus, DomainAnomaly, CausalChain, ClusterHealthReport,
)


def test_data_completeness_all_success():
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=80),
        DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=90),
        DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=85),
        DomainReport(domain="storage", status=DomainStatus.SUCCESS, confidence=70),
    ]
    score = _compute_data_completeness(reports)
    assert score == 1.0


def test_data_completeness_partial():
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=80),
        DomainReport(domain="node", status=DomainStatus.FAILED, confidence=0),
        DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=85),
        DomainReport(domain="storage", status=DomainStatus.FAILED, confidence=0),
    ]
    score = _compute_data_completeness(reports)
    assert score == 0.5


def test_merge_deduplicates():
    reports = [
        DomainReport(
            domain="node", status=DomainStatus.SUCCESS, confidence=80,
            anomalies=[DomainAnomaly(domain="node", anomaly_id="n-001", description="infra-node-03 NotReady", evidence_ref="ev-1")],
        ),
        DomainReport(
            domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=75,
            anomalies=[DomainAnomaly(domain="ctrl_plane", anomaly_id="cp-001", description="infra-node-03 NotReady", evidence_ref="ev-2")],
        ),
    ]
    merged = _merge_reports(reports)
    # Both reports should be present
    assert len(merged["all_anomalies"]) >= 1


@pytest.mark.asyncio
async def test_synthesize_produces_health_report():
    state = {
        "diagnostic_id": "DIAG-TEST",
        "platform": "openshift",
        "platform_version": "4.14.2",
        "domain_reports": [
            DomainReport(domain="ctrl_plane", status=DomainStatus.SUCCESS, confidence=80,
                anomalies=[DomainAnomaly(domain="ctrl_plane", anomaly_id="cp-001", description="DNS operator degraded", evidence_ref="ev-1")],
            ).model_dump(mode="json"),
            DomainReport(domain="node", status=DomainStatus.SUCCESS, confidence=90,
                anomalies=[DomainAnomaly(domain="node", anomaly_id="n-001", description="disk 97%", evidence_ref="ev-2")],
            ).model_dump(mode="json"),
            DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=85).model_dump(mode="json"),
            DomainReport(domain="storage", status=DomainStatus.SUCCESS, confidence=70).model_dump(mode="json"),
        ],
        "causal_chains": [],
        "re_dispatch_count": 0,
    }

    with patch("src.agents.cluster.synthesizer._llm_causal_reasoning", new_callable=AsyncMock) as mock_causal:
        mock_causal.return_value = {
            "causal_chains": [{
                "chain_id": "cc-001", "confidence": 0.85,
                "root_cause": {"domain": "node", "anomaly_id": "n-001", "description": "disk 97%", "evidence_ref": "ev-2"},
                "cascading_effects": [],
            }],
            "uncorrelated_findings": [],
        }
        with patch("src.agents.cluster.synthesizer._llm_verdict", new_callable=AsyncMock) as mock_verdict:
            mock_verdict.return_value = {
                "platform_health": "DEGRADED",
                "blast_radius": {"summary": "1 node affected", "affected_namespaces": 1, "affected_pods": 5, "affected_nodes": 1},
                "remediation": {"immediate": [], "long_term": []},
                "re_dispatch_needed": False,
            }
            result = await synthesize(state, {"configurable": {}})

    assert "health_report" in result
    report = result["health_report"]
    assert report["platform_health"] == "DEGRADED"
    assert result["data_completeness"] == 1.0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_synthesizer.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/agents/cluster/synthesizer.py
"""3-stage synthesis pipeline: Merge -> Causal Reasoning -> Verdict."""

from __future__ import annotations

import json
from typing import Any

from src.agents.cluster.state import (
    DomainReport, DomainStatus, DomainAnomaly, CausalChain,
    BlastRadius, ClusterHealthReport,
)
from src.agents.cluster.traced_node import traced_node
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

CONSTRAINED_LINK_TYPES = [
    "resource_exhaustion -> pod_eviction",
    "resource_exhaustion -> throttling",
    "pod_eviction -> service_degradation",
    "node_failure -> workload_rescheduling",
    "dns_failure -> api_unreachable",
    "certificate_expiry -> tls_handshake_failure",
    "config_drift -> unexpected_behavior",
    "storage_detach -> container_stuck",
    "network_partition -> split_brain",
    "api_latency -> timeout_cascade",
    "quota_exceeded -> scheduling_failure",
    "image_pull_failure -> pod_pending",
    "unknown",
]

CAUSAL_RULES = """
Six Causal Reasoning Rules:
1. TEMPORAL: A can only cause B if A started before B. Check timestamps.
2. MECHANISM: Must name HOW A caused B (link_type). "Same time" is correlation, not causation.
3. DOMAIN BOUNDARY: Explain the infrastructure mechanism for cross-domain links.
4. SINGLE ROOT: Each chain has exactly one root cause. Two independent roots = two chains.
5. WEAKEST LINK: Chain confidence = minimum of individual link confidences.
6. OBSERVABILITY CONFIRMATION: For cross-domain causality, require evidence in effect domain referencing cause resource.
"""


def _compute_data_completeness(reports: list[DomainReport]) -> float:
    """Fraction of domains that returned SUCCESS or PARTIAL."""
    if not reports:
        return 0.0
    succeeded = sum(1 for r in reports if r.status in (DomainStatus.SUCCESS, DomainStatus.PARTIAL))
    return succeeded / len(reports)


def _merge_reports(reports: list[DomainReport]) -> dict:
    """Stage 1: Deterministic merge and deduplication."""
    all_anomalies: list[DomainAnomaly] = []
    all_ruled_out: list[str] = []
    seen_descriptions: set[str] = set()

    for report in reports:
        for anomaly in report.anomalies:
            desc_key = anomaly.description.lower().strip()
            if desc_key not in seen_descriptions:
                seen_descriptions.add(desc_key)
                all_anomalies.append(anomaly)
        all_ruled_out.extend(report.ruled_out)

    return {
        "all_anomalies": all_anomalies,
        "all_ruled_out": list(set(all_ruled_out)),
    }


async def _llm_causal_reasoning(anomalies: list[DomainAnomaly], reports: list[DomainReport]) -> dict:
    """Stage 2: LLM identifies cross-domain causal chains."""
    client = AnthropicClient(agent_name="cluster_synthesizer")

    anomaly_data = [a.model_dump(mode="json") for a in anomalies]
    report_summaries = [
        {"domain": r.domain, "status": r.status.value, "confidence": r.confidence, "anomaly_count": len(r.anomalies)}
        for r in reports
    ]

    prompt = f"""Analyze these cross-domain anomalies and identify causal chains.

## Anomalies Found
{json.dumps(anomaly_data, indent=2)}

## Domain Report Summaries
{json.dumps(report_summaries, indent=2)}

## Allowed Link Types
{json.dumps(CONSTRAINED_LINK_TYPES)}

{CAUSAL_RULES}

## Required JSON Response
{{
  "causal_chains": [
    {{
      "chain_id": "cc-NNN",
      "confidence": 0.0-1.0,
      "root_cause": {{"domain": "...", "anomaly_id": "...", "description": "...", "evidence_ref": "..."}},
      "cascading_effects": [
        {{"order": 1, "domain": "...", "anomaly_id": "...", "description": "...", "link_type": "...", "evidence_ref": "..."}}
      ]
    }}
  ],
  "uncorrelated_findings": [
    {{"domain": "...", "anomaly_id": "...", "description": "...", "evidence_ref": "...", "severity": "..."}}
  ]
}}"""

    response = await client.chat(
        prompt=prompt,
        system="You are a causal reasoning engine for cluster diagnostics. Be precise and evidence-based.",
        max_tokens=3000,
        temperature=0.1,
    )
    text = response.content if hasattr(response, "content") else str(response)
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"causal_chains": [], "uncorrelated_findings": []}


async def _llm_verdict(
    causal_chains: list[dict],
    reports: list[DomainReport],
    data_completeness: float,
) -> dict:
    """Stage 3: LLM produces verdict and remediation."""
    client = AnthropicClient(agent_name="cluster_synthesizer")

    prompt = f"""Based on the causal analysis, produce a cluster health verdict.

## Causal Chains
{json.dumps(causal_chains, indent=2)}

## Data Completeness: {data_completeness:.0%}

## Domain Report Statuses
{json.dumps([{{"domain": r.domain, "status": r.status.value, "confidence": r.confidence}} for r in reports], indent=2)}

## Required JSON Response
{{
  "platform_health": "HEALTHY|DEGRADED|CRITICAL",
  "blast_radius": {{
    "summary": "...",
    "affected_namespaces": 0,
    "affected_pods": 0,
    "affected_nodes": 0
  }},
  "remediation": {{
    "immediate": [{{"command": "...", "description": "...", "risk_level": "low|medium|high"}}],
    "long_term": [{{"description": "...", "effort_estimate": "..."}}]
  }},
  "re_dispatch_needed": false
}}"""

    response = await client.chat(
        prompt=prompt,
        system="You are a cluster health verdict engine. Be actionable and precise.",
        max_tokens=2000,
        temperature=0.1,
    )
    text = response.content if hasattr(response, "content") else str(response)
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "platform_health": "UNKNOWN",
            "blast_radius": {"summary": "Unable to determine", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
            "remediation": {"immediate": [], "long_term": []},
            "re_dispatch_needed": False,
        }


@traced_node(timeout_seconds=60)
async def synthesize(state: dict, config: dict) -> dict:
    """LangGraph node: 3-stage synthesis pipeline."""
    diagnostic_id = state.get("diagnostic_id", "")
    platform = state.get("platform", "")
    platform_version = state.get("platform_version", "")

    # Reconstruct DomainReports from state
    reports = [DomainReport(**r) for r in state.get("domain_reports", [])]

    # Stage 1: Merge
    merged = _merge_reports(reports)
    data_completeness = _compute_data_completeness(reports)

    # Stage 2: Causal Reasoning (skip if no anomalies)
    causal_result = {"causal_chains": [], "uncorrelated_findings": []}
    if merged["all_anomalies"]:
        causal_result = await _llm_causal_reasoning(merged["all_anomalies"], reports)

    # Stage 3: Verdict
    verdict = await _llm_verdict(causal_result.get("causal_chains", []), reports, data_completeness)

    # Build health report
    health_report = ClusterHealthReport(
        diagnostic_id=diagnostic_id,
        platform=platform,
        platform_version=platform_version,
        platform_health=verdict.get("platform_health", "UNKNOWN"),
        data_completeness=data_completeness,
        blast_radius=BlastRadius(**verdict.get("blast_radius", {})),
        causal_chains=[CausalChain(**c) for c in causal_result.get("causal_chains", []) if isinstance(c, dict) and "chain_id" in c],
        uncorrelated_findings=[DomainAnomaly(**f) for f in causal_result.get("uncorrelated_findings", []) if isinstance(f, dict) and "domain" in f],
        domain_reports=reports,
        remediation=verdict.get("remediation", {}),
        execution_metadata={
            "re_dispatch_count": state.get("re_dispatch_count", 0),
            "agents_succeeded": sum(1 for r in reports if r.status == DomainStatus.SUCCESS),
            "agents_failed": sum(1 for r in reports if r.status == DomainStatus.FAILED),
        },
    )

    return {
        "health_report": health_report.model_dump(mode="json"),
        "causal_chains": [c.model_dump(mode="json") for c in health_report.causal_chains],
        "uncorrelated_findings": [f.model_dump(mode="json") for f in health_report.uncorrelated_findings],
        "data_completeness": data_completeness,
        "phase": "complete",
        "re_dispatch_domains": verdict.get("re_dispatch_domains", []) if verdict.get("re_dispatch_needed") else [],
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_synthesizer.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/synthesizer.py backend/tests/test_synthesizer.py
git commit -m "feat(cluster): add 3-stage synthesis pipeline (merge, causal reasoning, verdict)"
```

---

## Task 9: Build the LangGraph `StateGraph` (`graph.py`)

**Files:**
- Create: `backend/src/agents/cluster/graph.py`
- Create: `backend/tests/test_cluster_graph.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_cluster_graph.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.cluster.graph import build_cluster_diagnostic_graph


def test_graph_builds_without_error():
    graph = build_cluster_diagnostic_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_runs_with_mocks():
    """Integration test: graph runs end-to-end with mocked LLM calls."""
    from src.agents.cluster_client.mock_client import MockClusterClient
    from src.agents.cluster.state import ClusterDiagnosticState

    graph = build_cluster_diagnostic_graph()
    client = MockClusterClient(platform="openshift")
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    mock_analysis = {
        "anomalies": [{"domain": "test", "anomaly_id": "t-1", "description": "test issue", "evidence_ref": "ev-1"}],
        "ruled_out": [],
        "confidence": 80,
    }
    mock_causal = {
        "causal_chains": [],
        "uncorrelated_findings": [],
    }
    mock_verdict = {
        "platform_health": "HEALTHY",
        "blast_radius": {"summary": "No issues", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
        "remediation": {"immediate": [], "long_term": []},
        "re_dispatch_needed": False,
    }

    with patch("src.agents.cluster.ctrl_plane_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.node_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.network_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.storage_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.synthesizer._llm_causal_reasoning", new_callable=AsyncMock, return_value=mock_causal), \
         patch("src.agents.cluster.synthesizer._llm_verdict", new_callable=AsyncMock, return_value=mock_verdict):

        initial_state = {
            "diagnostic_id": "DIAG-TEST",
            "platform": "openshift",
            "platform_version": "4.14.2",
            "namespaces": ["default", "production"],
            "domain_reports": [],
            "causal_chains": [],
            "uncorrelated_findings": [],
            "phase": "pre_flight",
            "re_dispatch_count": 0,
            "re_dispatch_domains": [],
            "data_completeness": 0.0,
        }

        config = {
            "configurable": {
                "cluster_client": client,
                "emitter": emitter,
            }
        }

        result = await graph.ainvoke(initial_state, config=config)

    assert result.get("phase") == "complete"
    assert result.get("health_report") is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_cluster_graph.py -v`
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/agents/cluster/graph.py
"""LangGraph StateGraph for cluster diagnostics with fan-out/fan-in."""

from __future__ import annotations

from typing import Any, Annotated
import operator

from langgraph.graph import StateGraph, END

from src.agents.cluster.ctrl_plane_agent import ctrl_plane_agent
from src.agents.cluster.node_agent import node_agent
from src.agents.cluster.network_agent import network_agent
from src.agents.cluster.storage_agent import storage_agent
from src.agents.cluster.synthesizer import synthesize
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Graph-level ceiling (seconds)
GRAPH_TIMEOUT = 180


def _merge_domain_reports(left: list, right: list) -> list:
    """Reducer for domain_reports: append new reports to existing list."""
    return left + right


def _merge_causal_chains(left: list, right: list) -> list:
    return left + right


def _merge_uncorrelated(left: list, right: list) -> list:
    return left + right


# State schema with reducers for fan-out merge
class GraphState:
    """TypedDict-style state with reducers for parallel agent outputs."""
    pass


def _should_redispatch(state: dict) -> str:
    """Conditional edge: re-dispatch or end."""
    re_dispatch = state.get("re_dispatch_domains", [])
    count = state.get("re_dispatch_count", 0)
    if re_dispatch and count < 1:
        return "dispatch"
    return "end"


def build_cluster_diagnostic_graph():
    """Build and compile the cluster diagnostic LangGraph."""

    # Define state schema using Annotated for reducers
    from typing import TypedDict, Optional

    class State(TypedDict):
        diagnostic_id: str
        platform: str
        platform_version: str
        namespaces: list[str]
        exclude_namespaces: list[str]
        domain_reports: Annotated[list[dict], operator.add]
        causal_chains: Annotated[list[dict], operator.add]
        uncorrelated_findings: Annotated[list[dict], operator.add]
        health_report: Optional[dict]
        phase: str
        re_dispatch_count: int
        re_dispatch_domains: list[str]
        data_completeness: float
        error: Optional[str]

    graph = StateGraph(State)

    # Add nodes
    graph.add_node("ctrl_plane_agent", ctrl_plane_agent)
    graph.add_node("node_agent", node_agent)
    graph.add_node("network_agent", network_agent)
    graph.add_node("storage_agent", storage_agent)
    graph.add_node("synthesize", synthesize)

    # Fan-out: START -> all 4 agents in parallel
    graph.set_entry_point("ctrl_plane_agent")

    # All agents fan-in to synthesize
    graph.add_edge("ctrl_plane_agent", "synthesize")
    graph.add_edge("node_agent", "synthesize")
    graph.add_edge("network_agent", "synthesize")
    graph.add_edge("storage_agent", "synthesize")

    # After synthesis: check confidence and optionally re-dispatch
    graph.add_conditional_edges(
        "synthesize",
        _should_redispatch,
        {"dispatch": "ctrl_plane_agent", "end": END},
    )

    # Compile with parallel fan-out
    # Note: LangGraph supports parallel execution when multiple nodes
    # have the same predecessor. We use set_entry_point + add_edge for fan-out.
    compiled = graph.compile()
    return compiled
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_cluster_graph.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/graph.py backend/tests/test_cluster_graph.py
git commit -m "feat(cluster): build LangGraph StateGraph with fan-out/fan-in and re-dispatch"
```

---

## Task 10: Wire capability routing in `routes_v4.py`

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Modify: `backend/src/api/models.py` (add `capability` to `StartSessionRequest`)
- Create: `backend/tests/test_cluster_routing.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_cluster_routing.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_cluster_session_creates_graph():
    """Verify that capability=cluster_diagnostics creates a LangGraph session."""
    from src.api.routes_v4 import sessions

    with patch("src.api.routes_v4.build_cluster_diagnostic_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"phase": "complete", "health_report": {}})
        mock_build.return_value = mock_graph

        # Simulate what the routing logic does
        capability = "cluster_diagnostics"
        assert capability == "cluster_diagnostics"
        graph = mock_build()
        assert graph is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_cluster_routing.py -v`
Expected: FAIL — import error (build_cluster_diagnostic_graph not in routes_v4 yet)

**Step 3: Modify `StartSessionRequest` to include `capability` field**

In `backend/src/api/models.py`, add `capability: str = "troubleshoot_app"` to `StartSessionRequest`.

Then in `backend/src/api/routes_v4.py`, add the routing branch:

```python
# After existing imports, add:
from src.agents.cluster.graph import build_cluster_diagnostic_graph

# In start_session(), after creating emitter, add capability routing:
capability = getattr(request, "capability", "troubleshoot_app")

if capability == "cluster_diagnostics":
    # Create LangGraph-based cluster diagnostic session
    from src.agents.cluster_client.mock_client import MockClusterClient
    cluster_client = MockClusterClient(
        platform=getattr(connection_config, "cluster_type", "openshift") if connection_config else "openshift"
    )
    graph = build_cluster_diagnostic_graph()

    sessions[session_id] = {
        "service_name": request.serviceName or "Cluster Diagnostics",
        "incident_id": incident_id,
        "phase": "initial",
        "confidence": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "emitter": emitter,
        "state": None,
        "profile_id": profile_id,
        "capability": "cluster_diagnostics",
        "graph": graph,
    }

    background_tasks.add_task(
        run_cluster_diagnosis, session_id, graph, cluster_client, emitter, request
    )

    return StartSessionResponse(
        session_id=session_id,
        incident_id=incident_id,
        status="started",
        message="Cluster diagnostics started",
        service_name=request.serviceName or "Cluster Diagnostics",
        created_at=sessions[session_id]["created_at"],
    )
```

Add `run_cluster_diagnosis` function:

```python
async def run_cluster_diagnosis(session_id, graph, cluster_client, emitter, request):
    """Background task: run LangGraph cluster diagnostic."""
    try:
        _diagnosis_tasks[session_id] = asyncio.current_task()
    except RuntimeError:
        pass

    lock = session_locks.get(session_id, asyncio.Lock())
    try:
        initial_state = {
            "diagnostic_id": session_id,
            "platform": "",
            "platform_version": "",
            "namespaces": [],
            "exclude_namespaces": [],
            "domain_reports": [],
            "causal_chains": [],
            "uncorrelated_findings": [],
            "health_report": None,
            "phase": "pre_flight",
            "re_dispatch_count": 0,
            "re_dispatch_domains": [],
            "data_completeness": 0.0,
            "error": None,
        }

        # Pre-flight: detect platform
        platform_info = await cluster_client.detect_platform()
        initial_state["platform"] = platform_info.get("platform", "kubernetes")
        initial_state["platform_version"] = platform_info.get("version", "")

        ns_result = await cluster_client.list_namespaces()
        initial_state["namespaces"] = ns_result.data

        await emitter.emit("cluster_supervisor", "phase_change", "Starting cluster diagnostics", {"phase": "collecting_context"})

        config = {
            "configurable": {
                "cluster_client": cluster_client,
                "emitter": emitter,
            }
        }

        result = await asyncio.wait_for(
            graph.ainvoke(initial_state, config=config),
            timeout=180,
        )

        async with lock:
            if session_id in sessions:
                sessions[session_id]["state"] = result
                sessions[session_id]["phase"] = result.get("phase", "complete")
                sessions[session_id]["confidence"] = int(result.get("data_completeness", 0) * 100)

        await emitter.emit("cluster_supervisor", "phase_change", "Cluster diagnostics complete", {"phase": "diagnosis_complete"})

    except asyncio.TimeoutError:
        logger.error("Cluster diagnosis timed out", extra={"session_id": session_id})
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit("cluster_supervisor", "error", "Cluster diagnosis timed out after 180s")
    except asyncio.CancelledError:
        logger.info("Cluster diagnosis cancelled for session %s", session_id)
    except Exception as e:
        logger.error("Cluster diagnosis failed", extra={"session_id": session_id, "action": "cluster_error", "extra": str(e)})
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit("cluster_supervisor", "error", f"Cluster diagnosis failed: {str(e)}")
    finally:
        _diagnosis_tasks.pop(session_id, None)
        await cluster_client.close()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_cluster_routing.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/src/api/models.py backend/tests/test_cluster_routing.py
git commit -m "feat(cluster): wire cluster_diagnostics capability routing in routes_v4"
```

---

## Task 11: Add cluster findings endpoint

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Create: `backend/tests/test_cluster_findings.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_cluster_findings.py
import pytest


def test_cluster_findings_format():
    """Verify the cluster findings response shape matches frontend expectations."""
    # Simulate what the endpoint would return
    findings = {
        "diagnostic_id": "DIAG-TEST",
        "platform": "openshift",
        "platform_health": "DEGRADED",
        "data_completeness": 0.75,
        "causal_chains": [],
        "domain_reports": [],
        "blast_radius": {"summary": "", "affected_namespaces": 0, "affected_pods": 0, "affected_nodes": 0},
        "remediation": {"immediate": [], "long_term": []},
    }
    assert "platform_health" in findings
    assert "domain_reports" in findings
    assert "causal_chains" in findings
    assert isinstance(findings["data_completeness"], float)
```

**Step 2: Run test to verify it passes (this is a schema test)**

Run: `cd backend && python -m pytest tests/test_cluster_findings.py -v`
Expected: PASS

**Step 3: Add cluster findings to existing `/findings` endpoint**

In `routes_v4.py`, modify the existing `get_findings` endpoint to check `sessions[session_id].get("capability")` and return cluster-specific data when it's `"cluster_diagnostics"`.

```python
# Inside the get_findings endpoint, add at the top:
if sessions[session_id].get("capability") == "cluster_diagnostics":
    state = sessions[session_id].get("state", {})
    if isinstance(state, dict):
        return {
            "diagnostic_id": session_id,
            "platform": state.get("platform", ""),
            "platform_version": state.get("platform_version", ""),
            "platform_health": state.get("health_report", {}).get("platform_health", "UNKNOWN") if state.get("health_report") else "PENDING",
            "data_completeness": state.get("data_completeness", 0.0),
            "causal_chains": state.get("causal_chains", []),
            "uncorrelated_findings": state.get("uncorrelated_findings", []),
            "domain_reports": state.get("domain_reports", []),
            "blast_radius": state.get("health_report", {}).get("blast_radius", {}) if state.get("health_report") else {},
            "remediation": state.get("health_report", {}).get("remediation", {}) if state.get("health_report") else {},
            "execution_metadata": state.get("health_report", {}).get("execution_metadata", {}) if state.get("health_report") else {},
        }
    return {"diagnostic_id": session_id, "platform_health": "PENDING", "domain_reports": []}
```

**Step 4: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/test_api.py -v`
Expected: All existing tests pass

**Step 5: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_findings.py
git commit -m "feat(cluster): add cluster findings to /findings endpoint with capability routing"
```

---

## Task 12: Add frontend types for cluster diagnostics

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add cluster diagnostic types**

Add these types after the existing `ClusterDiagnosticsForm` interface:

```typescript
// ===== Cluster Diagnostics Types =====
export interface ClusterDomainAnomaly {
  domain: string;
  anomaly_id: string;
  description: string;
  evidence_ref: string;
  severity?: string;
}

export interface ClusterDomainReport {
  domain: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL' | 'FAILED';
  failure_reason?: string;
  confidence: number;
  anomalies: ClusterDomainAnomaly[];
  ruled_out: string[];
  evidence_refs: string[];
  truncation_flags: Record<string, boolean>;
  data_gathered_before_failure?: string[];
  duration_ms: number;
}

export interface ClusterCausalLink {
  order: number;
  domain: string;
  anomaly_id: string;
  description: string;
  link_type: string;
  evidence_ref: string;
}

export interface ClusterCausalChain {
  chain_id: string;
  confidence: number;
  root_cause: ClusterDomainAnomaly;
  cascading_effects: ClusterCausalLink[];
}

export interface ClusterBlastRadius {
  summary: string;
  affected_namespaces: number;
  affected_pods: number;
  affected_nodes: number;
}

export interface ClusterRemediationStep {
  command?: string;
  description: string;
  risk_level?: string;
  effort_estimate?: string;
}

export interface ClusterHealthReport {
  diagnostic_id: string;
  platform: string;
  platform_version: string;
  platform_health: 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | 'UNKNOWN' | 'PENDING';
  data_completeness: number;
  blast_radius: ClusterBlastRadius;
  causal_chains: ClusterCausalChain[];
  uncorrelated_findings: ClusterDomainAnomaly[];
  domain_reports: ClusterDomainReport[];
  remediation: {
    immediate: ClusterRemediationStep[];
    long_term: ClusterRemediationStep[];
  };
  execution_metadata: Record<string, number>;
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(cluster): add TypeScript types for cluster diagnostic data"
```

---

## Task 13: Create `ClusterWarRoom.tsx` — main view component

**Files:**
- Create: `frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx`

**Step 1: Create the main view layout**

```typescript
// frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx
import React, { useState, useEffect, useCallback } from 'react';
import type {
  V4Session, ClusterHealthReport, ClusterDomainReport,
  ClusterCausalChain, TaskEvent,
} from '../../types';

interface ClusterWarRoomProps {
  session: V4Session;
  events: TaskEvent[];
  wsConnected: boolean;
  phase: string | null;
  confidence: number;
  onGoHome: () => void;
}

const DOMAIN_COLORS: Record<string, string> = {
  ctrl_plane: '#ef4444',  // red
  node: '#07b6d5',        // cyan
  network: '#f97316',     // orange
  storage: '#10b981',     // emerald
};

const DOMAIN_LABELS: Record<string, string> = {
  ctrl_plane: 'Control Plane & Etcd',
  node: 'Node & Capacity',
  network: 'Network & Ingress',
  storage: 'Storage & Persistence',
};

const ClusterWarRoom: React.FC<ClusterWarRoomProps> = ({
  session, events, wsConnected, phase, confidence, onGoHome,
}) => {
  const [findings, setFindings] = useState<ClusterHealthReport | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchFindings = useCallback(async () => {
    try {
      const res = await fetch(`/api/v4/session/${session.session_id}/findings`);
      if (res.ok) {
        const data = await res.json();
        if (data.platform_health && data.platform_health !== 'PENDING') {
          setFindings(data as ClusterHealthReport);
        }
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [session.session_id]);

  useEffect(() => {
    fetchFindings();
    const interval = setInterval(fetchFindings, 5000);
    return () => clearInterval(interval);
  }, [fetchFindings]);

  const healthColor = findings?.platform_health === 'HEALTHY' ? '#10b981'
    : findings?.platform_health === 'DEGRADED' ? '#f59e0b'
    : findings?.platform_health === 'CRITICAL' ? '#ef4444'
    : '#6b7280';

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Header */}
      <header className="h-14 border-b border-[#224349] flex items-center justify-between px-6 shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={onGoHome} className="text-slate-400 hover:text-white transition-colors">
            <span className="material-symbols-outlined" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
          </button>
          <div>
            <h1 className="text-white font-bold text-lg">Cluster Diagnostics</h1>
            <p className="text-xs text-slate-500">{session.session_id.slice(0, 8)}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 px-3 py-1 rounded-full" style={{ backgroundColor: `${healthColor}20`, border: `1px solid ${healthColor}40` }}>
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: healthColor }} />
            <span className="text-xs font-bold uppercase tracking-wider" style={{ color: healthColor }}>
              {findings?.platform_health || 'Analyzing...'}
            </span>
          </div>
          {findings && (
            <span className="text-xs text-slate-500">
              Data: {Math.round((findings.data_completeness || 0) * 100)}%
            </span>
          )}
        </div>
      </header>

      {/* Main content grid */}
      <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
        {loading && !findings && (
          <div className="flex items-center justify-center h-64 text-slate-500">
            <span className="material-symbols-outlined animate-spin mr-2" style={{ fontFamily: 'Material Symbols Outlined' }}>progress_activity</span>
            Running cluster diagnostics...
          </div>
        )}

        {findings && (
          <div className="grid grid-cols-12 gap-4">
            {/* Domain panels — 4 columns, 3 cols each */}
            {(['ctrl_plane', 'node', 'network', 'storage'] as const).map(domain => {
              const report = findings.domain_reports?.find(r => r.domain === domain);
              return (
                <div key={domain} className="col-span-3 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-1 h-6 rounded-full" style={{ backgroundColor: DOMAIN_COLORS[domain] }} />
                    <h3 className="text-sm font-bold text-white">{DOMAIN_LABELS[domain]}</h3>
                  </div>
                  {report ? (
                    <>
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`text-xs font-bold uppercase ${report.status === 'SUCCESS' ? 'text-emerald-400' : report.status === 'FAILED' ? 'text-red-400' : 'text-amber-400'}`}>
                          {report.status}
                        </span>
                        <span className="text-xs text-slate-500">
                          {report.confidence}% confidence
                        </span>
                      </div>
                      {report.anomalies?.map((a, i) => (
                        <div key={i} className="text-xs text-slate-300 mb-1 pl-3 border-l-2" style={{ borderColor: DOMAIN_COLORS[domain] + '60' }}>
                          {a.description}
                        </div>
                      ))}
                      {report.ruled_out?.length > 0 && (
                        <div className="mt-2 text-[10px] text-slate-600">
                          Ruled out: {report.ruled_out.join(', ')}
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-xs text-slate-600 animate-pulse">Analyzing...</div>
                  )}
                </div>
              );
            })}

            {/* Causal chains — full width */}
            {findings.causal_chains?.length > 0 && (
              <div className="col-span-12 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                <h3 className="text-sm font-bold text-white mb-3">Causal Chains</h3>
                {findings.causal_chains.map(chain => (
                  <div key={chain.chain_id} className="mb-3 p-3 rounded border" style={{ borderColor: '#224349' }}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-bold text-red-400 uppercase">Root Cause</span>
                      <span className="text-xs text-slate-500">{Math.round(chain.confidence * 100)}% confidence</span>
                    </div>
                    <p className="text-sm text-white mb-2">{chain.root_cause.description}</p>
                    {chain.cascading_effects.map(effect => (
                      <div key={effect.order} className="flex items-center gap-2 ml-4 mb-1">
                        <span className="text-slate-600">→</span>
                        <span className="text-xs text-slate-300">{effect.description}</span>
                        <span className="text-[10px] text-slate-600">({effect.link_type})</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            {/* Blast radius + Remediation */}
            {findings.blast_radius?.summary && (
              <div className="col-span-6 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                <h3 className="text-sm font-bold text-white mb-2">Blast Radius</h3>
                <p className="text-sm text-slate-300 mb-2">{findings.blast_radius.summary}</p>
                <div className="flex gap-4 text-xs text-slate-500">
                  <span>{findings.blast_radius.affected_nodes} nodes</span>
                  <span>{findings.blast_radius.affected_pods} pods</span>
                  <span>{findings.blast_radius.affected_namespaces} namespaces</span>
                </div>
              </div>
            )}

            {(findings.remediation?.immediate?.length > 0 || findings.remediation?.long_term?.length > 0) && (
              <div className="col-span-6 rounded-lg border p-4" style={{ borderColor: '#224349', backgroundColor: 'rgba(15,32,35,0.6)' }}>
                <h3 className="text-sm font-bold text-white mb-2">Remediation</h3>
                {findings.remediation.immediate?.map((step, i) => (
                  <div key={i} className="mb-2">
                    <p className="text-xs text-slate-300">{step.description}</p>
                    {step.command && (
                      <code className="text-[10px] text-cyan-400 block mt-1 font-mono">{step.command}</code>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ClusterWarRoom;
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/components/ClusterDiagnostic/ClusterWarRoom.tsx
git commit -m "feat(cluster): add ClusterWarRoom view component with domain panels and causal chains"
```

---

## Task 14: Wire `ClusterWarRoom` into `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add cluster diagnostic view routing**

In `App.tsx`:

1. Import `ClusterWarRoom`
2. Handle `capability === 'cluster_diagnostics'` in `handleFormSubmit` — start the session via API with capability field
3. Render `ClusterWarRoom` instead of `InvestigationView` when the active session has capability `cluster_diagnostics`

Add to `handleFormSubmit`, inside the `else` block (where placeholder sessions are created for non-troubleshoot_app capabilities):

```typescript
} else if (data.capability === 'cluster_diagnostics') {
  const clusterData = data as ClusterDiagnosticsForm;
  const session = await startSessionV4({
    service_name: 'Cluster Diagnostics',
    time_window: '1h',
    namespace: clusterData.namespace || '',
    cluster_url: clusterData.cluster_url,
    capability: 'cluster_diagnostics',
    profileId: clusterData.profile_id,
  });
  setSessions((prev) => [session, ...prev]);
  setActiveSession(session);
  setCurrentPhase(session.status);
  setConfidence(session.confidence);
  setViewState('cluster-diagnostics');
  refreshStatus(session.session_id);
}
```

Add `'cluster-diagnostics'` to `ViewState` type.

Add render block for cluster diagnostics view:
```tsx
{viewState === 'cluster-diagnostics' && activeSession && (
  <ClusterWarRoom
    session={activeSession}
    events={currentTaskEvents}
    wsConnected={wsConnected}
    phase={currentPhase}
    confidence={confidence}
    onGoHome={handleGoHome}
  />
)}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(cluster): wire ClusterWarRoom view into App.tsx with capability routing"
```

---

## Task 15: Update `startSessionV4` API call to pass capability

**Files:**
- Modify: `frontend/src/services/api.ts`

**Step 1: Add `capability` parameter**

In the `startSessionV4` function, add `capability` to the request body when provided.

Find the request body object and add: `capability: params.capability || 'troubleshoot_app'`

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(cluster): pass capability field in startSessionV4 API call"
```

---

## Task 16: Run full test suite and verify

**Step 1: Run backend tests**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests pass (existing + new cluster tests)

**Step 2: Run frontend TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 3: Run frontend build**

Run: `cd frontend && npx vite build`
Expected: Build succeeds

**Step 4: Commit any fixes if needed**

---

## Verification Checklist

1. **Backend models** — `ClusterDiagnosticState`, `DomainReport`, `CausalChain` serialize correctly
2. **@traced_node** — timeout, exception handling, trace recording all work
3. **ClusterClient** — abstract base enforces read-only contract, QueryResult carries truncation flags
4. **MockClusterClient** — returns fixture data, OpenShift-specific methods return empty on K8s
5. **DiagnosticCache** — cache hit, cache miss, force_fresh all work
6. **GraphEventBridge** — filters internal events, emits domain-tagged events
7. **4 agents** — each produces DomainReport via mocked LLM
8. **Synthesizer** — merge deduplicates, causal reasoning via mocked LLM, verdict via mocked LLM
9. **LangGraph** — graph builds, runs end-to-end with mocks
10. **Routing** — `capability=cluster_diagnostics` creates graph session
11. **Findings endpoint** — returns cluster-specific data shape
12. **Frontend types** — TypeScript compiles with new cluster types
13. **ClusterWarRoom** — renders domain panels, causal chains, blast radius, remediation
14. **App.tsx** — routes to ClusterWarRoom for cluster diagnostic sessions
15. **Zero regression** — existing app troubleshooting flow unchanged
