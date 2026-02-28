# Live Investigation Steering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable SREs to steer investigations in real-time via slash commands, quick-action buttons, and natural language — parallel to the automated agent pipeline — with findings merging into a unified evidence pool and critic re-validation.

**Architecture:** InvestigationRouter with Fast Path (deterministic, ~50ms) and Smart Path (Haiku LLM, ~400ms), converging on a shared ToolDispatcher → EvidencePinFactory → State Merger → Conditional Critic Edge. See `docs/plans/2026-02-28-live-investigation-steering-design.md` for full design.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, pytest + pytest-asyncio, React 18, TypeScript, Tailwind CSS, WebSocket

---

## Task 1: Extend EvidencePin Schema

**Files:**
- Modify: `backend/src/models/schemas.py:639-647`
- Test: `backend/tests/test_evidence_pin_v2.py`

**Context:** The existing `EvidencePin` (line 639) has 6 fields. We need to extend it with `source`, `triggered_by`, `domain`, `validation_status`, `raw_output`, `severity`, `causal_role`, `namespace`, `service`, `resource_name`, `time_window`, and `id`. The existing EvidencePin is used by the V5 supervisor — we extend it non-destructively (new fields have defaults).

**Step 1: Write the failing test**

Create `backend/tests/test_evidence_pin_v2.py`:

```python
import pytest
from datetime import datetime, timezone
from src.models.schemas import EvidencePin, TimeWindow


class TestEvidencePinV2Fields:
    """Test the extended EvidencePin schema for live investigation steering."""

    def test_new_fields_have_defaults(self):
        """Existing V5 code that creates EvidencePin without new fields must still work."""
        pin = EvidencePin(
            claim="Memory spike to 92%",
            supporting_evidence=["container_memory=92%"],
            source_agent="metrics_agent",
            source_tool="prometheus",
            confidence=0.9,
            timestamp=datetime.now(timezone.utc),
            evidence_type="metric",
        )
        # New fields should have sensible defaults
        assert pin.source == "auto"
        assert pin.triggered_by == "automated_pipeline"
        assert pin.domain == "unknown"
        assert pin.validation_status == "pending_critic"
        assert pin.raw_output is None
        assert pin.severity is None
        assert pin.causal_role is None
        assert pin.namespace is None
        assert pin.service is None
        assert pin.resource_name is None
        assert pin.time_window is None
        assert pin.id is not None  # Auto-generated UUID

    def test_manual_pin_creation(self):
        """Manual pins from user investigation set source='manual'."""
        pin = EvidencePin(
            id="test-pin-001",
            claim="Pod auth-5b6q has 12 restarts",
            supporting_evidence=["restart_count=12", "reason=OOMKilled"],
            source_agent=None,
            source_tool="fetch_pod_logs",
            confidence=1.0,
            timestamp=datetime.now(timezone.utc),
            evidence_type="k8s_resource",
            source="manual",
            triggered_by="quick_action",
            domain="compute",
            validation_status="pending_critic",
            severity="high",
            namespace="payment-api",
            service="auth-service",
            resource_name="auth-5b6q",
        )
        assert pin.source == "manual"
        assert pin.triggered_by == "quick_action"
        assert pin.domain == "compute"

    def test_domain_literal_validation(self):
        """Domain must be one of the allowed values."""
        with pytest.raises(Exception):
            EvidencePin(
                claim="test",
                supporting_evidence=[],
                source_agent="test",
                source_tool="test",
                confidence=0.5,
                timestamp=datetime.now(timezone.utc),
                evidence_type="log",
                domain="invalid_domain",
            )

    def test_validation_status_literal(self):
        """validation_status must be pending_critic, validated, or rejected."""
        pin = EvidencePin(
            claim="test",
            supporting_evidence=[],
            source_agent="test",
            source_tool="test",
            confidence=0.5,
            timestamp=datetime.now(timezone.utc),
            evidence_type="log",
            validation_status="validated",
        )
        assert pin.validation_status == "validated"

    def test_source_agent_nullable_for_manual(self):
        """Manual pins may have source_agent=None."""
        pin = EvidencePin(
            claim="test",
            supporting_evidence=[],
            source_agent=None,
            source_tool="kubectl_logs",
            confidence=1.0,
            timestamp=datetime.now(timezone.utc),
            evidence_type="log",
            source="manual",
        )
        assert pin.source_agent is None

    def test_evidence_type_includes_k8s_resource(self):
        """evidence_type now includes 'k8s_resource' for describe results."""
        pin = EvidencePin(
            claim="test",
            supporting_evidence=[],
            source_agent="k8s_agent",
            source_tool="describe_resource",
            confidence=1.0,
            timestamp=datetime.now(timezone.utc),
            evidence_type="k8s_resource",
        )
        assert pin.evidence_type == "k8s_resource"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_evidence_pin_v2.py -v`
Expected: FAIL — EvidencePin doesn't have `source`, `domain`, etc.

**Step 3: Extend the EvidencePin model**

In `backend/src/models/schemas.py`, replace the existing EvidencePin class (line 639-646) with:

```python
class EvidencePin(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    claim: str = Field(..., min_length=1)
    supporting_evidence: list[str] = []
    source_agent: Optional[str] = None
    source_tool: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    timestamp: datetime
    evidence_type: Literal["log", "metric", "trace", "k8s_event", "k8s_resource", "code", "change"]

    # Live investigation steering fields
    source: Literal["auto", "manual"] = "auto"
    triggered_by: Literal["automated_pipeline", "user_chat", "quick_action"] = "automated_pipeline"
    raw_output: Optional[str] = None
    severity: Optional[Literal["critical", "high", "medium", "low", "info"]] = None
    causal_role: Optional[Literal["root_cause", "cascading_symptom", "correlated", "informational"]] = None
    domain: Literal["compute", "network", "storage", "control_plane", "security", "unknown"] = "unknown"
    validation_status: Literal["pending_critic", "validated", "rejected"] = "pending_critic"
    namespace: Optional[str] = None
    service: Optional[str] = None
    resource_name: Optional[str] = None
    time_window: Optional[TimeWindow] = None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_evidence_pin_v2.py -v`
Expected: All 6 tests PASS

**Step 5: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: Existing tests still pass (new fields have defaults)

**Step 6: Commit**

```bash
git add backend/src/models/schemas.py backend/tests/test_evidence_pin_v2.py
git commit -m "feat: extend EvidencePin with domain, validation_status, and manual source tracking"
```

---

## Task 2: ToolResult and EvidencePinFactory

**Files:**
- Create: `backend/src/tools/tool_result.py`
- Create: `backend/src/tools/evidence_pin_factory.py`
- Test: `backend/tests/test_tool_result.py`

**Context:** ToolResult is the intermediate data structure between raw tool execution and EvidencePin. EvidencePinFactory converts ToolResult → EvidencePin. These are used by every tool in the ToolExecutor.

**Step 1: Write the failing test**

Create `backend/tests/test_tool_result.py`:

```python
import pytest
from datetime import datetime, timezone
from src.tools.tool_result import ToolResult
from src.tools.evidence_pin_factory import EvidencePinFactory
from src.models.schemas import EvidencePin, TimeWindow


class TestToolResult:
    def test_successful_result(self):
        result = ToolResult(
            success=True,
            intent="fetch_pod_logs",
            raw_output="2026-02-28T10:00:00Z ERROR Connection timeout\n2026-02-28T10:00:01Z INFO Retrying",
            summary="Pod auth-5b6q: 1 error line found in 2 total lines",
            evidence_snippets=["2026-02-28T10:00:00Z ERROR Connection timeout"],
            evidence_type="log",
            domain="compute",
            severity="medium",
            error=None,
            metadata={"namespace": "payment-api", "pod": "auth-5b6q", "total_lines": 2},
        )
        assert result.success is True
        assert result.domain == "compute"
        assert len(result.evidence_snippets) == 1

    def test_failed_result(self):
        result = ToolResult(
            success=False,
            intent="fetch_pod_logs",
            raw_output="",
            summary="Pod not-found not found in namespace payment-api",
            evidence_snippets=[],
            evidence_type="log",
            domain="compute",
            severity=None,
            error="Pod 'not-found' not found in namespace 'payment-api'",
            metadata={"namespace": "payment-api", "pod": "not-found"},
        )
        assert result.success is False
        assert result.error is not None


class TestEvidencePinFactory:
    def _make_context(self):
        from src.tools.router_models import RouterContext
        return RouterContext(
            active_namespace="payment-api",
            active_service="auth-service",
            active_pod="auth-5b6q",
            time_window=TimeWindow(start="now-1h", end="now"),
            session_id="test-session",
            incident_id="INC-TEST-001",
        )

    def test_manual_pin_from_successful_result(self):
        result = ToolResult(
            success=True,
            intent="fetch_pod_logs",
            raw_output="ERROR Connection timeout",
            summary="Pod auth-5b6q: 1 error",
            evidence_snippets=["ERROR Connection timeout"],
            evidence_type="log",
            domain="compute",
            severity="medium",
            error=None,
            metadata={"pod": "auth-5b6q"},
        )
        pin = EvidencePinFactory.from_tool_result(result, "quick_action", self._make_context())

        assert isinstance(pin, EvidencePin)
        assert pin.source == "manual"
        assert pin.triggered_by == "quick_action"
        assert pin.domain == "compute"
        assert pin.validation_status == "pending_critic"
        assert pin.confidence == 1.0
        assert pin.namespace == "payment-api"
        assert pin.resource_name == "auth-5b6q"
        assert pin.raw_output == "ERROR Connection timeout"

    def test_auto_pin_from_pipeline(self):
        result = ToolResult(
            success=True,
            intent="search_logs",
            raw_output="...",
            summary="Found 50 errors",
            evidence_snippets=["err1"],
            evidence_type="log",
            domain="unknown",
            severity="high",
            error=None,
            metadata={},
        )
        pin = EvidencePinFactory.from_tool_result(result, "automated_pipeline", self._make_context())
        assert pin.source == "auto"

    def test_failed_result_gives_zero_confidence(self):
        result = ToolResult(
            success=False, intent="fetch_pod_logs", raw_output="", summary="Not found",
            evidence_snippets=[], evidence_type="log", domain="compute",
            severity=None, error="Not found", metadata={},
        )
        pin = EvidencePinFactory.from_tool_result(result, "user_chat", self._make_context())
        assert pin.confidence == 0.0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tool_result.py -v`
Expected: FAIL — modules don't exist

**Step 3: Create ToolResult model**

Create `backend/src/tools/tool_result.py`:

```python
from pydantic import BaseModel
from typing import Any, Optional


class ToolResult(BaseModel):
    """Intermediate result from a tool execution. Converted to EvidencePin by the factory."""
    success: bool
    intent: str
    raw_output: str
    summary: str
    evidence_snippets: list[str]
    evidence_type: str
    domain: str
    severity: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = {}
```

**Step 4: Create RouterContext model**

Create `backend/src/tools/router_models.py`:

```python
from pydantic import BaseModel, model_validator
from typing import Optional, Literal, Any
from src.models.schemas import TimeWindow


class RouterContext(BaseModel):
    """UI viewport state sent with every investigation request."""
    active_namespace: Optional[str] = None
    active_service: Optional[str] = None
    active_pod: Optional[str] = None
    time_window: TimeWindow
    session_id: str = ""
    incident_id: str = ""
    discovered_services: list[str] = []
    discovered_namespaces: list[str] = []
    pod_names: list[str] = []
    active_findings_summary: str = ""
    last_agent_phase: str = ""
    elk_index: Optional[str] = None


class QuickActionPayload(BaseModel):
    intent: str
    params: dict[str, Any]


class InvestigateRequest(BaseModel):
    command: Optional[str] = None
    query: Optional[str] = None
    quick_action: Optional[QuickActionPayload] = None
    context: RouterContext

    @model_validator(mode="after")
    def exactly_one_input(self) -> "InvestigateRequest":
        provided = sum(1 for v in [self.command, self.query, self.quick_action] if v is not None)
        if provided != 1:
            raise ValueError("Exactly one of command, query, or quick_action must be provided")
        return self


class InvestigateResponse(BaseModel):
    pin_id: str
    intent: str
    params: dict[str, Any]
    path_used: Literal["fast", "smart"]
    status: Literal["executing", "error"]
    error: Optional[str] = None
```

**Step 5: Create EvidencePinFactory**

Create `backend/src/tools/evidence_pin_factory.py`:

```python
from datetime import datetime, timezone
from uuid import uuid4
from typing import Literal

from src.models.schemas import EvidencePin
from src.tools.tool_result import ToolResult
from src.tools.router_models import RouterContext


class EvidencePinFactory:
    @staticmethod
    def from_tool_result(
        result: ToolResult,
        triggered_by: Literal["automated_pipeline", "user_chat", "quick_action"],
        context: RouterContext,
    ) -> EvidencePin:
        source = "manual" if triggered_by in ("user_chat", "quick_action") else "auto"
        return EvidencePin(
            id=str(uuid4()),
            claim=result.summary,
            source=source,
            source_agent=None,
            source_tool=result.intent,
            triggered_by=triggered_by,
            evidence_type=result.evidence_type,
            supporting_evidence=result.evidence_snippets,
            raw_output=result.raw_output,
            confidence=1.0 if result.success else 0.0,
            severity=result.severity,
            causal_role=None,
            domain=result.domain,
            validation_status="pending_critic",
            namespace=context.active_namespace,
            service=context.active_service,
            resource_name=result.metadata.get("pod") or result.metadata.get("name"),
            timestamp=datetime.now(timezone.utc),
            time_window=context.time_window,
        )
```

**Step 6: Ensure `backend/src/tools/__init__.py` exists**

Check if it exists. If not, create empty `backend/src/tools/__init__.py`.

**Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_result.py -v`
Expected: All 5 tests PASS

**Step 8: Commit**

```bash
git add backend/src/tools/tool_result.py backend/src/tools/router_models.py backend/src/tools/evidence_pin_factory.py backend/tests/test_tool_result.py
git commit -m "feat: add ToolResult, RouterContext, InvestigateRequest, and EvidencePinFactory"
```

---

## Task 3: ToolExecutor — fetch_pod_logs and describe_resource

**Files:**
- Create: `backend/src/tools/tool_executor.py`
- Test: `backend/tests/test_tool_executor.py`

**Context:** The ToolExecutor dispatches tool calls by intent name. Each handler takes params and returns a ToolResult. We start with the two most critical K8s tools. The K8s client pattern is already used in `backend/src/agents/k8s_agent.py` — we reuse the same connection approach.

**Step 1: Write the failing test**

Create `backend/tests/test_tool_executor.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.tools.tool_executor import ToolExecutor
from src.tools.tool_result import ToolResult


def _make_config():
    """Minimal connection config for testing."""
    return {
        "cluster_url": "https://k8s.test.local",
        "cluster_token": "test-token",
        "namespace": "payment-api",
        "verify_ssl": False,
    }


class TestFetchPodLogs:
    @pytest.mark.asyncio
    async def test_successful_log_fetch(self):
        executor = ToolExecutor(_make_config())

        mock_api = AsyncMock()
        mock_api.read_namespaced_pod_log = AsyncMock(return_value=(
            "2026-02-28T10:00:00Z INFO Starting service\n"
            "2026-02-28T10:00:01Z ERROR Connection refused to db:5432\n"
            "2026-02-28T10:00:02Z INFO Retrying connection\n"
        ))
        executor._k8s_core_api = mock_api

        result = await executor.execute("fetch_pod_logs", {
            "namespace": "payment-api",
            "pod": "auth-5b6q",
            "tail_lines": 200,
        })

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.intent == "fetch_pod_logs"
        assert result.domain == "compute"
        assert result.evidence_type == "log"
        assert "1 error" in result.summary.lower() or "error" in result.summary.lower()
        assert len(result.evidence_snippets) >= 1
        assert "Connection refused" in result.evidence_snippets[0]

    @pytest.mark.asyncio
    async def test_pod_not_found(self):
        from kubernetes.client.exceptions import ApiException
        executor = ToolExecutor(_make_config())

        mock_api = AsyncMock()
        mock_api.read_namespaced_pod_log = AsyncMock(
            side_effect=ApiException(status=404, reason="Not Found")
        )
        executor._k8s_core_api = mock_api

        result = await executor.execute("fetch_pod_logs", {
            "namespace": "payment-api",
            "pod": "nonexistent",
        })

        assert result.success is False
        assert "not found" in result.summary.lower()
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_previous_container_logs(self):
        executor = ToolExecutor(_make_config())

        mock_api = AsyncMock()
        mock_api.read_namespaced_pod_log = AsyncMock(return_value="FATAL OOMKilled\n")
        executor._k8s_core_api = mock_api

        result = await executor.execute("fetch_pod_logs", {
            "namespace": "payment-api",
            "pod": "auth-5b6q",
            "previous": True,
        })

        assert result.success is True
        assert result.severity == "critical"
        mock_api.read_namespaced_pod_log.assert_called_once()
        call_kwargs = mock_api.read_namespaced_pod_log.call_args
        assert call_kwargs.kwargs.get("previous") is True or call_kwargs[1].get("previous") is True


class TestDescribeResource:
    @pytest.mark.asyncio
    async def test_describe_pod(self):
        executor = ToolExecutor(_make_config())

        mock_pod = MagicMock()
        mock_pod.metadata.name = "auth-5b6q"
        mock_pod.metadata.namespace = "payment-api"
        mock_pod.status.phase = "Running"
        mock_pod.status.conditions = []
        mock_pod.status.container_statuses = [
            MagicMock(ready=True, restart_count=0, name="auth",
                      last_state=MagicMock(terminated=None))
        ]

        mock_api = AsyncMock()
        mock_api.read_namespaced_pod = AsyncMock(return_value=mock_pod)
        executor._k8s_core_api = mock_api

        result = await executor.execute("describe_resource", {
            "kind": "pod",
            "name": "auth-5b6q",
            "namespace": "payment-api",
        })

        assert result.success is True
        assert result.domain == "compute"
        assert result.evidence_type == "k8s_resource"

    @pytest.mark.asyncio
    async def test_describe_service_maps_to_network_domain(self):
        executor = ToolExecutor(_make_config())

        mock_svc = MagicMock()
        mock_svc.metadata.name = "auth-svc"
        mock_svc.spec.type = "ClusterIP"
        mock_svc.spec.ports = [MagicMock(port=8080, target_port=8080, protocol="TCP")]

        mock_api = AsyncMock()
        mock_api.read_namespaced_service = AsyncMock(return_value=mock_svc)
        executor._k8s_core_api = mock_api

        result = await executor.execute("describe_resource", {
            "kind": "service",
            "name": "auth-svc",
            "namespace": "payment-api",
        })

        assert result.domain == "network"

    @pytest.mark.asyncio
    async def test_unsupported_kind(self):
        executor = ToolExecutor(_make_config())
        result = await executor.execute("describe_resource", {
            "kind": "customresource",
            "name": "foo",
            "namespace": "bar",
        })
        assert result.success is False
        assert "unsupported" in result.summary.lower() or "unsupported" in result.error.lower()


class TestUnknownIntent:
    @pytest.mark.asyncio
    async def test_unknown_intent_raises(self):
        executor = ToolExecutor(_make_config())
        with pytest.raises(KeyError):
            await executor.execute("nonexistent_tool", {})
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_tool_executor.py -v`
Expected: FAIL — `src.tools.tool_executor` doesn't exist

**Step 3: Implement ToolExecutor**

Create `backend/src/tools/tool_executor.py`:

```python
"""
ToolExecutor: Dispatches investigation tool calls by intent name.
Each handler takes params dict → returns ToolResult.
"""
import json
from typing import Any, Callable, Awaitable
from kubernetes.client.exceptions import ApiException

from src.tools.tool_result import ToolResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Domain mapping for K8s resource kinds
_KIND_TO_DOMAIN = {
    "pod": "compute", "deployment": "compute", "node": "compute",
    "configmap": "compute", "replicaset": "compute",
    "service": "network", "ingress": "network",
    "pvc": "storage", "persistentvolumeclaim": "storage",
}

# Error keywords for log severity classification
_CRITICAL_KEYWORDS = ("fatal", "panic")
_HIGH_KEYWORDS = ("oom", "killed", "segfault")
_MEDIUM_KEYWORDS = ("error", "exception", "timeout", "refused", "fail")


class ToolExecutor:
    """Stateless tool dispatcher. Each method: params → ToolResult."""

    def __init__(self, connection_config: dict):
        self._config = connection_config
        self._k8s_core_api = None
        self._k8s_apps_api = None
        self._k8s_networking_api = None

    # ── Dispatch ──────────────────────────────────────────────────────────

    HANDLERS: dict[str, str] = {
        "fetch_pod_logs": "_fetch_pod_logs",
        "describe_resource": "_describe_resource",
        "query_prometheus": "_query_prometheus",
        "search_logs": "_search_logs",
        "check_pod_status": "_check_pod_status",
        "get_events": "_get_events",
    }

    async def execute(self, intent: str, params: dict[str, Any]) -> ToolResult:
        handler_name = self.HANDLERS[intent]  # KeyError if unknown
        handler = getattr(self, handler_name)
        return await handler(params)

    # ── fetch_pod_logs ────────────────────────────────────────────────────

    async def _fetch_pod_logs(self, params: dict) -> ToolResult:
        namespace = params["namespace"]
        pod = params["pod"]
        container = params.get("container")
        previous = params.get("previous", False)
        tail_lines = params.get("tail_lines", 200)

        api = self._k8s_core_api
        try:
            log_text = await api.read_namespaced_pod_log(
                name=pod, namespace=namespace,
                container=container or "",
                previous=previous,
                tail_lines=tail_lines,
                timestamps=True,
            )
        except ApiException as e:
            if e.status == 404:
                msg = f"Pod '{pod}' not found in namespace '{namespace}'"
            elif e.status == 400 and "previous terminated" in str(e.body or ""):
                msg = f"Pod '{pod}' has no previous container (never crashed)"
            else:
                msg = f"Failed to fetch logs: {e.reason}"
            return ToolResult(
                success=False, intent="fetch_pod_logs", raw_output="",
                summary=msg, evidence_snippets=[], evidence_type="log",
                domain="compute", severity=None, error=msg,
                metadata={"namespace": namespace, "pod": pod},
            )

        lines = log_text.strip().split("\n") if log_text.strip() else []
        error_lines = [l for l in lines if any(kw in l.lower() for kw in _MEDIUM_KEYWORDS)]

        severity = self._classify_log_severity(error_lines)

        if error_lines:
            summary = f"Pod {pod}: {len(error_lines)} error lines found in {len(lines)} total lines"
        elif previous:
            summary = f"Pod {pod}: previous container logs retrieved ({len(lines)} lines, no errors)"
        else:
            summary = f"Pod {pod}: logs retrieved ({len(lines)} lines, no errors detected)"

        return ToolResult(
            success=True, intent="fetch_pod_logs", raw_output=log_text,
            summary=summary, evidence_snippets=error_lines[:10],
            evidence_type="log", domain="compute", severity=severity, error=None,
            metadata={"namespace": namespace, "pod": pod, "container": container,
                      "previous": previous, "total_lines": len(lines),
                      "error_lines": len(error_lines)},
        )

    # ── describe_resource ─────────────────────────────────────────────────

    async def _describe_resource(self, params: dict) -> ToolResult:
        kind = params["kind"].lower()
        name = params["name"]
        namespace = params.get("namespace")

        api = self._k8s_core_api
        domain = _KIND_TO_DOMAIN.get(kind, "unknown")

        # Map kind → API method
        namespaced_methods = {
            "pod": api.read_namespaced_pod,
            "service": api.read_namespaced_service,
            "configmap": api.read_namespaced_config_map,
            "pvc": api.read_namespaced_persistent_volume_claim,
        }
        cluster_methods = {
            "node": api.read_node,
        }

        method = namespaced_methods.get(kind) or cluster_methods.get(kind)
        if not method:
            msg = f"Unsupported resource kind: {kind}"
            return ToolResult(
                success=False, intent="describe_resource", raw_output="",
                summary=msg, evidence_snippets=[], evidence_type="k8s_resource",
                domain=domain, severity=None, error=msg, metadata={"kind": kind, "name": name},
            )

        try:
            if kind in namespaced_methods:
                resource = await method(name=name, namespace=namespace)
            else:
                resource = await method(name=name)
        except ApiException as e:
            msg = f"{kind}/{name} not found: {e.reason}"
            return ToolResult(
                success=False, intent="describe_resource", raw_output="",
                summary=msg, evidence_snippets=[], evidence_type="k8s_resource",
                domain=domain, severity=None, error=msg,
                metadata={"kind": kind, "name": name, "namespace": namespace},
            )

        raw = self._resource_to_text(resource, kind)
        signals = self._extract_resource_signals(resource, kind)

        return ToolResult(
            success=True, intent="describe_resource", raw_output=raw,
            summary=signals["summary"], evidence_snippets=signals["key_lines"],
            evidence_type="k8s_resource", domain=domain,
            severity="high" if signals["has_issues"] else "info", error=None,
            metadata={"kind": kind, "name": name, "namespace": namespace},
        )

    # ── Placeholder handlers (implemented in Task 4) ──────────────────────

    async def _query_prometheus(self, params: dict) -> ToolResult:
        raise NotImplementedError("Implemented in Task 4")

    async def _search_logs(self, params: dict) -> ToolResult:
        raise NotImplementedError("Implemented in Task 4")

    async def _check_pod_status(self, params: dict) -> ToolResult:
        raise NotImplementedError("Implemented in Task 4")

    async def _get_events(self, params: dict) -> ToolResult:
        raise NotImplementedError("Implemented in Task 4")

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _classify_log_severity(error_lines: list[str]) -> str:
        combined = " ".join(error_lines).lower()
        if any(kw in combined for kw in _CRITICAL_KEYWORDS):
            return "critical"
        if any(kw in combined for kw in _HIGH_KEYWORDS):
            return "high"
        if error_lines:
            return "medium"
        return "info"

    @staticmethod
    def _resource_to_text(resource, kind: str) -> str:
        """Serialize K8s resource to human-readable text."""
        try:
            from kubernetes.client import ApiClient
            return json.dumps(ApiClient().sanitize_for_serialization(resource), indent=2)
        except Exception:
            return str(resource)

    @staticmethod
    def _extract_resource_signals(resource, kind: str) -> dict:
        """Extract key signals from a K8s resource for summary."""
        key_lines = []
        has_issues = False
        summary_parts = []

        if kind == "pod":
            name = getattr(resource.metadata, "name", "unknown")
            phase = getattr(resource.status, "phase", "Unknown")
            summary_parts.append(f"Pod {name}: {phase}")
            for cs in (resource.status.container_statuses or []):
                if not cs.ready:
                    has_issues = True
                    key_lines.append(f"Container {cs.name}: NOT READY, restarts={cs.restart_count}")
                if cs.last_state and cs.last_state.terminated:
                    reason = cs.last_state.terminated.reason or "Unknown"
                    has_issues = True
                    key_lines.append(f"Container {cs.name}: last terminated with {reason}")
        elif kind == "service":
            name = getattr(resource.metadata, "name", "unknown")
            svc_type = getattr(resource.spec, "type", "ClusterIP")
            summary_parts.append(f"Service {name}: type={svc_type}")
        else:
            name = getattr(resource.metadata, "name", "unknown")
            summary_parts.append(f"{kind.title()} {name}")

        return {
            "summary": ", ".join(summary_parts) or f"{kind}/{getattr(resource.metadata, 'name', 'unknown')}",
            "key_lines": key_lines,
            "has_issues": has_issues,
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_tool_executor.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add backend/src/tools/tool_executor.py backend/tests/test_tool_executor.py
git commit -m "feat: add ToolExecutor with fetch_pod_logs and describe_resource handlers"
```

---

## Task 4: ToolExecutor — query_prometheus, search_logs, check_pod_status, get_events

**Files:**
- Modify: `backend/src/tools/tool_executor.py`
- Test: `backend/tests/test_tool_executor_extended.py`

**Context:** Implement the remaining 4 Phase 1 tools. `query_prometheus` and `search_logs` reuse existing client patterns from MetricsAgent and LogAgent. `check_pod_status` and `get_events` reuse K8s API patterns from K8sAgent.

**Step 1: Write failing tests**

Create `backend/tests/test_tool_executor_extended.py`:

```python
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

from src.tools.tool_executor import ToolExecutor


def _make_config():
    return {
        "cluster_url": "https://k8s.test.local",
        "cluster_token": "test-token",
        "prometheus_url": "http://prometheus:9090",
        "elasticsearch_url": "http://es:9200",
        "namespace": "payment-api",
        "verify_ssl": False,
    }


class TestQueryPrometheus:
    @pytest.mark.asyncio
    async def test_successful_query(self):
        executor = ToolExecutor(_make_config())
        mock_prom = AsyncMock()
        mock_prom.query_range = AsyncMock(return_value={
            "data": {
                "resultType": "matrix",
                "result": [{
                    "metric": {"__name__": "container_memory_working_set_bytes", "pod": "auth-5b6q"},
                    "values": [[1709100000, "104857600"], [1709100060, "209715200"], [1709100120, "524288000"]],
                }],
            },
        })
        executor._prom_client = mock_prom

        result = await executor.execute("query_prometheus", {
            "query": "container_memory_working_set_bytes{pod='auth-5b6q'}",
            "range_minutes": 60,
        })

        assert result.success is True
        assert result.evidence_type == "metric"
        assert result.metadata["series_count"] == 1

    @pytest.mark.asyncio
    async def test_empty_result(self):
        executor = ToolExecutor(_make_config())
        mock_prom = AsyncMock()
        mock_prom.query_range = AsyncMock(return_value={"data": {"result": []}})
        executor._prom_client = mock_prom

        result = await executor.execute("query_prometheus", {
            "query": "nonexistent_metric",
        })
        assert result.success is True
        assert "no data" in result.summary.lower()


class TestSearchLogs:
    @pytest.mark.asyncio
    async def test_successful_search(self):
        executor = ToolExecutor(_make_config())
        mock_es = AsyncMock()
        mock_es.search = AsyncMock(return_value={
            "hits": {
                "total": {"value": 3},
                "hits": [
                    {"_source": {"@timestamp": "2026-02-28T10:00:00Z", "message": "Connection timeout", "level": "ERROR"}},
                    {"_source": {"@timestamp": "2026-02-28T10:00:01Z", "message": "Retrying", "level": "WARN"}},
                    {"_source": {"@timestamp": "2026-02-28T10:00:02Z", "message": "Connection refused", "level": "ERROR"}},
                ],
            },
        })
        executor._es_client = mock_es

        result = await executor.execute("search_logs", {
            "query": "Connection",
            "index": "app-logs-*",
            "since_minutes": 60,
        })

        assert result.success is True
        assert result.evidence_type == "log"
        assert result.metadata["total"] == 3

    @pytest.mark.asyncio
    async def test_no_results(self):
        executor = ToolExecutor(_make_config())
        mock_es = AsyncMock()
        mock_es.search = AsyncMock(return_value={"hits": {"total": {"value": 0}, "hits": []}})
        executor._es_client = mock_es

        result = await executor.execute("search_logs", {"query": "nonexistent"})
        assert result.success is True
        assert result.metadata["total"] == 0


class TestCheckPodStatus:
    @pytest.mark.asyncio
    async def test_healthy_pods(self):
        executor = ToolExecutor(_make_config())
        mock_api = AsyncMock()

        mock_pod = MagicMock()
        mock_pod.metadata.name = "auth-5b6q"
        mock_pod.status.phase = "Running"
        mock_pod.status.container_statuses = [
            MagicMock(ready=True, restart_count=0, last_state=MagicMock(terminated=None))
        ]

        mock_api.list_namespaced_pod = AsyncMock(return_value=MagicMock(items=[mock_pod]))
        executor._k8s_core_api = mock_api

        result = await executor.execute("check_pod_status", {"namespace": "payment-api"})
        assert result.success is True
        assert result.metadata["unhealthy"] == 0
        assert result.severity == "info"

    @pytest.mark.asyncio
    async def test_unhealthy_pod(self):
        executor = ToolExecutor(_make_config())
        mock_api = AsyncMock()

        mock_pod = MagicMock()
        mock_pod.metadata.name = "auth-crash"
        mock_pod.status.phase = "CrashLoopBackOff"
        mock_cs = MagicMock(ready=False, restart_count=5, name="auth")
        mock_cs.last_state.terminated.reason = "OOMKilled"
        mock_pod.status.container_statuses = [mock_cs]

        mock_api.list_namespaced_pod = AsyncMock(return_value=MagicMock(items=[mock_pod]))
        executor._k8s_core_api = mock_api

        result = await executor.execute("check_pod_status", {"namespace": "payment-api"})
        assert result.severity == "critical"
        assert result.metadata["unhealthy"] == 1


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_warning_events(self):
        executor = ToolExecutor(_make_config())
        mock_api = AsyncMock()

        mock_event = MagicMock()
        mock_event.last_timestamp = datetime.now(timezone.utc)
        mock_event.type = "Warning"
        mock_event.reason = "OOMKilling"
        mock_event.message = "Pod exceeded memory limit"
        mock_event.count = 3
        mock_event.involved_object.name = "auth-5b6q"

        mock_api.list_namespaced_event = AsyncMock(return_value=MagicMock(items=[mock_event]))
        executor._k8s_core_api = mock_api

        result = await executor.execute("get_events", {
            "namespace": "payment-api",
            "since_minutes": 60,
        })

        assert result.success is True
        assert result.evidence_type == "k8s_event"
        assert result.metadata["warning_count"] == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_tool_executor_extended.py -v`
Expected: FAIL — NotImplementedError

**Step 3: Implement the 4 handlers in `backend/src/tools/tool_executor.py`**

Replace the placeholder methods with full implementations. Add `_prom_client` and `_es_client` fields to `__init__`. Implement:

- `_query_prometheus`: Uses `self._prom_client.query_range()`, computes stats (series_count, latest_value, max_value, avg_value, stddev), detects spikes (>2 stddev), infers domain from PromQL content.
- `_search_logs`: Uses `self._es_client.search()` with `query_string`, extracts hits, formats messages with timestamps.
- `_check_pod_status`: Uses `self._k8s_core_api.list_namespaced_pod()`, reports phase/restarts/OOM/readiness per pod.
- `_get_events`: Uses `self._k8s_core_api.list_namespaced_event()`, filters by time and optional involved_object, counts warnings.

Follow the exact implementation from the design doc Section 6 (the code is already provided there verbatim). Adapt the method signatures to use `self._prom_client` / `self._es_client` / `self._k8s_core_api`.

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_tool_executor_extended.py tests/test_tool_executor.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/tools/tool_executor.py backend/tests/test_tool_executor_extended.py
git commit -m "feat: add query_prometheus, search_logs, check_pod_status, get_events to ToolExecutor"
```

---

## Task 5: InvestigationRouter — Fast Path + Smart Path

**Files:**
- Create: `backend/src/tools/investigation_router.py`
- Test: `backend/tests/test_investigation_router.py`

**Context:** The router receives an InvestigateRequest, determines Fast or Smart path, resolves intent + params, dispatches to ToolExecutor, wraps result in EvidencePin, and returns. Fast Path uses regex for slash commands and direct passthrough for quick_action. Smart Path calls Haiku with RouterContext for intent classification.

**Step 1: Write failing tests**

Create `backend/tests/test_investigation_router.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.tools.investigation_router import InvestigationRouter
from src.tools.router_models import (
    InvestigateRequest, QuickActionPayload, RouterContext, InvestigateResponse,
)
from src.tools.tool_result import ToolResult
from src.models.schemas import TimeWindow, EvidencePin


def _make_context(**overrides):
    defaults = dict(
        active_namespace="payment-api",
        active_service="auth-service",
        time_window=TimeWindow(start="now-1h", end="now"),
        session_id="test-session",
        incident_id="INC-TEST",
    )
    defaults.update(overrides)
    return RouterContext(**defaults)


class TestFastPathQuickAction:
    @pytest.mark.asyncio
    async def test_quick_action_bypasses_llm(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=ToolResult(
            success=True, intent="fetch_pod_logs", raw_output="log text",
            summary="Pod auth: 1 error", evidence_snippets=["ERROR"],
            evidence_type="log", domain="compute", severity="medium",
            error=None, metadata={"pod": "auth-5b6q"},
        ))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        request = InvestigateRequest(
            quick_action=QuickActionPayload(intent="fetch_pod_logs", params={"pod": "auth-5b6q", "namespace": "payment-api"}),
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.path_used == "fast"
        assert response.intent == "fetch_pod_logs"
        assert isinstance(pin, EvidencePin)
        assert pin.source == "manual"
        assert pin.triggered_by == "quick_action"


class TestFastPathSlashCommand:
    @pytest.mark.asyncio
    async def test_slash_logs_parsed(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=ToolResult(
            success=True, intent="fetch_pod_logs", raw_output="...",
            summary="Pod auth: ok", evidence_snippets=[],
            evidence_type="log", domain="compute", severity="info",
            error=None, metadata={"pod": "auth-5b6q"},
        ))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        request = InvestigateRequest(
            command="/logs namespace=payment-api pod=auth-5b6q",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.path_used == "fast"
        assert response.intent == "fetch_pod_logs"
        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args
        assert call_args[0][0] == "fetch_pod_logs"
        assert call_args[0][1]["pod"] == "auth-5b6q"

    @pytest.mark.asyncio
    async def test_slash_command_uses_context_defaults(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=ToolResult(
            success=True, intent="fetch_pod_logs", raw_output="...",
            summary="ok", evidence_snippets=[], evidence_type="log",
            domain="compute", severity="info", error=None, metadata={},
        ))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=None)

        # No namespace in command — should use context
        request = InvestigateRequest(
            command="/logs pod=auth-5b6q",
            context=_make_context(active_namespace="payment-api"),
        )
        response, pin = await router.route(request)

        call_params = mock_executor.execute.call_args[0][1]
        assert call_params["namespace"] == "payment-api"

    @pytest.mark.asyncio
    async def test_unknown_slash_command(self):
        router = InvestigationRouter(tool_executor=AsyncMock(), llm_client=None)

        request = InvestigateRequest(
            command="/nonexistent foo=bar",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.status == "error"
        assert pin is None


class TestSmartPath:
    @pytest.mark.asyncio
    async def test_natural_language_uses_llm(self):
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value=ToolResult(
            success=True, intent="fetch_pod_logs", raw_output="...",
            summary="ok", evidence_snippets=[], evidence_type="log",
            domain="compute", severity="info", error=None, metadata={},
        ))

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            text='{"intent": "fetch_pod_logs", "params": {"pod": "auth-5b6q", "namespace": "payment-api"}}'
        ))

        router = InvestigationRouter(tool_executor=mock_executor, llm_client=mock_llm)

        request = InvestigateRequest(
            query="check the auth pod logs",
            context=_make_context(),
        )
        response, pin = await router.route(request)

        assert response.path_used == "smart"
        assert response.intent == "fetch_pod_logs"
        mock_llm.chat.assert_called_once()


class TestPydanticValidation:
    def test_exactly_one_input_required(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvestigateRequest(
                command="/logs pod=x",
                query="check logs",
                context=_make_context(),
            )

    def test_no_input_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InvestigateRequest(context=_make_context())
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_investigation_router.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement InvestigationRouter**

Create `backend/src/tools/investigation_router.py`:

```python
"""
InvestigationRouter: Fast Path (slash commands, buttons) + Smart Path (NL → Haiku LLM).
Both paths converge on ToolExecutor.execute() → EvidencePinFactory.from_tool_result().
"""
import json
import re
from typing import Optional

from src.tools.tool_executor import ToolExecutor
from src.tools.tool_result import ToolResult
from src.tools.evidence_pin_factory import EvidencePinFactory
from src.tools.router_models import InvestigateRequest, InvestigateResponse, RouterContext
from src.tools.tool_registry import TOOL_REGISTRY, SLASH_COMMAND_MAP
from src.models.schemas import EvidencePin
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InvestigationRouter:
    def __init__(self, tool_executor: ToolExecutor, llm_client=None):
        self._executor = tool_executor
        self._llm = llm_client

    async def route(self, request: InvestigateRequest) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        """Route an investigation request to the correct tool. Returns (response, pin)."""

        if request.quick_action:
            return await self._fast_path_quick_action(request)
        elif request.command:
            return await self._fast_path_slash_command(request)
        elif request.query:
            return await self._smart_path(request)
        else:
            # Should never happen due to Pydantic validator
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="fast", status="error",
                error="No input provided",
            ), None

    # ── Fast Path: Quick Action Button ────────────────────────────────────

    async def _fast_path_quick_action(self, request: InvestigateRequest) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        qa = request.quick_action
        params = self._apply_context_defaults(qa.intent, qa.params, request.context)

        try:
            result = await self._executor.execute(qa.intent, params)
        except KeyError:
            return InvestigateResponse(
                pin_id="", intent=qa.intent, params=params, path_used="fast",
                status="error", error=f"Unknown tool: {qa.intent}",
            ), None

        pin = EvidencePinFactory.from_tool_result(result, "quick_action", request.context)

        return InvestigateResponse(
            pin_id=pin.id, intent=qa.intent, params=params,
            path_used="fast", status="executing",
        ), pin

    # ── Fast Path: Slash Command ──────────────────────────────────────────

    async def _fast_path_slash_command(self, request: InvestigateRequest) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        command = request.command.strip()
        parsed = self._parse_slash_command(command)

        if not parsed:
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="fast",
                status="error", error=f"Unknown command: {command.split()[0]}",
            ), None

        intent, params = parsed
        params = self._apply_context_defaults(intent, params, request.context)

        try:
            result = await self._executor.execute(intent, params)
        except KeyError:
            return InvestigateResponse(
                pin_id="", intent=intent, params=params, path_used="fast",
                status="error", error=f"Unknown tool: {intent}",
            ), None

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", request.context)

        return InvestigateResponse(
            pin_id=pin.id, intent=intent, params=params,
            path_used="fast", status="executing",
        ), pin

    # ── Smart Path: Natural Language → Haiku LLM ─────────────────────────

    async def _smart_path(self, request: InvestigateRequest) -> tuple[InvestigateResponse, Optional[EvidencePin]]:
        if not self._llm:
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="smart",
                status="error", error="LLM client not configured for smart path",
            ), None

        system_prompt = self._build_smart_prompt(request.context)
        try:
            llm_response = await self._llm.chat(
                user_message=request.query,
                system_prompt=system_prompt,
            )
            parsed = json.loads(llm_response.text)
            intent = parsed["intent"]
            params = parsed.get("params", {})
        except (json.JSONDecodeError, KeyError) as e:
            return InvestigateResponse(
                pin_id="", intent="", params={}, path_used="smart",
                status="error", error=f"Failed to parse LLM response: {e}",
            ), None

        params = self._apply_context_defaults(intent, params, request.context)

        try:
            result = await self._executor.execute(intent, params)
        except KeyError:
            return InvestigateResponse(
                pin_id="", intent=intent, params=params, path_used="smart",
                status="error", error=f"Unknown tool: {intent}",
            ), None

        pin = EvidencePinFactory.from_tool_result(result, "user_chat", request.context)

        return InvestigateResponse(
            pin_id=pin.id, intent=intent, params=params,
            path_used="smart", status="executing",
        ), pin

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_slash_command(command: str) -> Optional[tuple[str, dict]]:
        """Parse '/logs namespace=x pod=y' into (intent, {namespace: x, pod: y})."""
        parts = command.strip().split()
        if not parts or not parts[0].startswith("/"):
            return None

        slash = parts[0]  # e.g., "/logs"
        intent = SLASH_COMMAND_MAP.get(slash)
        if not intent:
            return None

        params = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                # Convert boolean strings
                if value.lower() in ("true", "false"):
                    params[key] = value.lower() == "true"
                else:
                    try:
                        params[key] = int(value)
                    except ValueError:
                        params[key] = value
            else:
                # Positional — ignore for now
                pass

        return intent, params

    @staticmethod
    def _apply_context_defaults(intent: str, params: dict, context: RouterContext) -> dict:
        """Fill missing params from RouterContext using tool registry defaults."""
        tool_def = next((t for t in TOOL_REGISTRY if t["intent"] == intent), None)
        if not tool_def:
            return params

        for param_def in tool_def.get("params_schema", []):
            name = param_def["name"]
            ctx_field = param_def.get("default_from_context")
            if name not in params and ctx_field:
                ctx_value = getattr(context, ctx_field, None)
                if ctx_value is not None:
                    params[name] = ctx_value

        return params

    @staticmethod
    def _build_smart_prompt(context: RouterContext) -> str:
        tool_descriptions = "\n".join(
            f"- {t['intent']}: {t['description']} (params: {', '.join(p['name'] for p in t.get('params_schema', []))})"
            for t in TOOL_REGISTRY
        )
        return f"""You are an investigation router. Parse the user's request into a tool call.

Current context:
- Active namespace: {context.active_namespace}
- Active service: {context.active_service}
- Active pod: {context.active_pod}
- Known pods: {', '.join(context.pod_names[:20])}
- Time window: {context.time_window.start} to {context.time_window.end}

Available tools:
{tool_descriptions}

Use the active context to fill any missing parameters.
Output ONLY valid JSON: {{"intent": "tool_name", "params": {{...}}}}
"""
```

**Step 4: Create tool registry data**

Create `backend/src/tools/tool_registry.py`:

```python
"""
Tool registry: defines all available investigation tools, their parameters, and slash commands.
This is the single source of truth — the frontend reads it via GET /tools, the router uses
it for slash command mapping and context defaults.
"""

TOOL_REGISTRY = [
    {
        "intent": "fetch_pod_logs",
        "label": "Get Pod Logs",
        "icon": "terminal",
        "slash_command": "/logs",
        "category": "logs",
        "description": "Fetch logs from a running or previously crashed pod",
        "params_schema": [
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
            {"name": "pod", "type": "select", "required": True, "default_from_context": "active_pod", "options": []},
            {"name": "container", "type": "select", "required": False, "options": []},
            {"name": "previous", "type": "boolean", "required": False},
            {"name": "tail_lines", "type": "number", "required": False},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "query_prometheus",
        "label": "Run PromQL",
        "icon": "monitoring",
        "slash_command": "/promql",
        "category": "metrics",
        "description": "Execute a Prometheus query and pin the result",
        "params_schema": [
            {"name": "query", "type": "string", "required": True},
            {"name": "range_minutes", "type": "number", "required": False},
        ],
        "requires_context": [],
    },
    {
        "intent": "describe_resource",
        "label": "Describe Resource",
        "icon": "info",
        "slash_command": "/describe",
        "category": "cluster",
        "description": "kubectl describe for any K8s/OpenShift resource",
        "params_schema": [
            {"name": "kind", "type": "select", "required": True, "options": ["pod", "deployment", "service", "node", "configmap", "ingress", "pvc"]},
            {"name": "name", "type": "string", "required": True},
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "get_events",
        "label": "Cluster Events",
        "icon": "event_note",
        "slash_command": "/events",
        "category": "cluster",
        "description": "Fetch Kubernetes events filtered by namespace and time",
        "params_schema": [
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
            {"name": "since_minutes", "type": "number", "required": False},
            {"name": "involved_object", "type": "string", "required": False},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "search_logs",
        "label": "Search ELK Logs",
        "icon": "search",
        "slash_command": "/search",
        "category": "logs",
        "description": "Search Elasticsearch for log patterns across services",
        "params_schema": [
            {"name": "query", "type": "string", "required": True},
            {"name": "index", "type": "string", "required": False, "default_from_context": "elk_index"},
            {"name": "level", "type": "select", "required": False, "options": ["ERROR", "WARN", "INFO", "DEBUG"]},
            {"name": "since_minutes", "type": "number", "required": False},
        ],
        "requires_context": [],
    },
    {
        "intent": "check_pod_status",
        "label": "Pod Health",
        "icon": "health_and_safety",
        "slash_command": "/pods",
        "category": "cluster",
        "description": "Check pod status, restart counts, and OOM kills",
        "params_schema": [
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
            {"name": "label_selector", "type": "string", "required": False},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "re_investigate_service",
        "label": "Investigate Service",
        "icon": "radar",
        "slash_command": "/investigate",
        "category": "cluster",
        "description": "Run the full agent pipeline against a different service",
        "params_schema": [
            {"name": "service", "type": "string", "required": True},
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
        ],
        "requires_context": ["namespace"],
    },
]

# Derived: slash command → intent mapping
SLASH_COMMAND_MAP = {t["slash_command"]: t["intent"] for t in TOOL_REGISTRY}
```

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_investigation_router.py -v`
Expected: All 8 tests PASS

**Step 6: Commit**

```bash
git add backend/src/tools/investigation_router.py backend/src/tools/tool_registry.py backend/tests/test_investigation_router.py
git commit -m "feat: add InvestigationRouter with Fast Path (slash commands, buttons) and Smart Path (Haiku LLM)"
```

---

## Task 6: API Endpoint — POST /investigate and GET /tools

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Modify: `backend/src/api/models.py`
- Test: `backend/tests/test_investigate_endpoint.py`

**Context:** Add two new endpoints to the existing v4 router. `POST /investigate` receives InvestigateRequest, dispatches via InvestigationRouter, merges the EvidencePin into session state, and emits WebSocket events. `GET /tools` returns the tool registry for the frontend.

**Step 1: Write failing tests**

Create `backend/tests/test_investigate_endpoint.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(autouse=True)
def _clear_sessions():
    from src.api.routes_v4 import sessions, supervisors, session_locks
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    yield
    sessions.clear()
    supervisors.clear()
    session_locks.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def seeded_session(client):
    """Create a session to test against."""
    with patch("src.api.routes_v4.SupervisorAgent"):
        resp = client.post("/api/v4/session/start", json={
            "serviceName": "auth-service",
            "namespace": "payment-api",
            "capability": "troubleshoot_app",
        })
    assert resp.status_code == 200
    return resp.json()["session_id"]


class TestInvestigateEndpoint:
    def test_quick_action_returns_200(self, client, seeded_session):
        with patch("src.api.routes_v4._get_investigation_router") as mock_get:
            mock_router = AsyncMock()
            from src.tools.router_models import InvestigateResponse
            from src.models.schemas import EvidencePin, TimeWindow
            from datetime import datetime, timezone

            mock_pin = EvidencePin(
                id="pin-001", claim="Pod ok", source_agent=None,
                source_tool="fetch_pod_logs", confidence=1.0,
                timestamp=datetime.now(timezone.utc), evidence_type="log",
                source="manual", domain="compute",
            )
            mock_router.route = AsyncMock(return_value=(
                InvestigateResponse(
                    pin_id="pin-001", intent="fetch_pod_logs",
                    params={"pod": "auth"}, path_used="fast", status="executing",
                ),
                mock_pin,
            ))
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{seeded_session}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {
                    "active_namespace": "payment-api",
                    "time_window": {"start": "now-1h", "end": "now"},
                },
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["pin_id"] == "pin-001"
        assert data["path_used"] == "fast"

    def test_invalid_session_returns_400(self, client):
        resp = client.post("/api/v4/session/not-a-uuid/investigate", json={
            "quick_action": {"intent": "test", "params": {}},
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 400

    def test_exactly_one_input_validation(self, client, seeded_session):
        resp = client.post(f"/api/v4/session/{seeded_session}/investigate", json={
            "command": "/logs pod=x",
            "query": "check logs",
            "context": {"time_window": {"start": "now-1h", "end": "now"}},
        })
        assert resp.status_code == 422  # Pydantic validation error


class TestToolsEndpoint:
    def test_get_tools_returns_registry(self, client, seeded_session):
        resp = client.get(f"/api/v4/session/{seeded_session}/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert len(data["tools"]) >= 6
        # Each tool has required fields
        for tool in data["tools"]:
            assert "intent" in tool
            assert "label" in tool
            assert "slash_command" in tool
            assert "params_schema" in tool
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_investigate_endpoint.py -v`
Expected: FAIL — endpoints don't exist

**Step 3: Add endpoints to routes_v4.py**

Add to the imports in `backend/src/api/routes_v4.py`:

```python
from src.tools.router_models import InvestigateRequest, InvestigateResponse
from src.tools.tool_registry import TOOL_REGISTRY
```

Add a helper to get/create the router for a session:

```python
# Investigation routers per session
_investigation_routers: Dict[str, Any] = {}

def _get_investigation_router(session_id: str):
    """Get or create InvestigationRouter for a session."""
    if session_id not in _investigation_routers:
        from src.tools.investigation_router import InvestigationRouter
        from src.tools.tool_executor import ToolExecutor
        config = sessions[session_id].get("connection_config", {})
        executor = ToolExecutor(config)
        llm = AnthropicClient(agent_name="investigation_router")
        _investigation_routers[session_id] = InvestigationRouter(
            tool_executor=executor, llm_client=llm,
        )
    return _investigation_routers[session_id]
```

Add the endpoints:

```python
@router.post("/session/{session_id}/investigate")
async def investigate(session_id: str, request: InvestigateRequest):
    """Manual investigation: slash command, quick action, or natural language."""
    _validate_session_id(session_id)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    investigation_router = _get_investigation_router(session_id)
    response, pin = await investigation_router.route(request)

    if pin:
        # Merge pin into session state under lock
        async with session_locks.setdefault(session_id, asyncio.Lock()):
            state = sessions[session_id]
            if "evidence_pins" not in state:
                state["evidence_pins"] = []
            state["evidence_pins"].append(pin.model_dump(mode="json"))

        # Emit WebSocket event
        try:
            await manager.send_message(session_id, {
                "type": "task_event",
                "data": {
                    "session_id": session_id,
                    "agent_name": "investigation_router",
                    "event_type": "evidence_pin_added",
                    "message": pin.claim,
                    "timestamp": pin.timestamp.isoformat(),
                    "details": {
                        "pin_id": pin.id,
                        "domain": pin.domain,
                        "severity": pin.severity,
                        "validation_status": pin.validation_status,
                        "evidence_type": pin.evidence_type,
                        "source_tool": pin.source_tool,
                        "raw_output": pin.raw_output,
                    },
                },
            })
        except Exception as e:
            logger.warning("WebSocket broadcast failed for evidence pin", extra={"error": str(e)})

    return response.model_dump()


@router.get("/session/{session_id}/tools")
async def get_tools(session_id: str):
    """Return available investigation tools for this session."""
    _validate_session_id(session_id)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Enrich tool options from session state (discovered pods, namespaces, etc.)
    state = sessions.get(session_id, {})
    enriched = []
    for tool in TOOL_REGISTRY:
        tool_copy = {**tool}
        # Future: populate select options from session state
        enriched.append(tool_copy)

    return {"tools": enriched}
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_investigate_endpoint.py -v`
Expected: All 4 tests PASS

**Step 5: Run full test suite for regressions**

Run: `cd backend && python -m pytest tests/ --timeout=30 2>&1 | tail -20`
Expected: No regressions

**Step 6: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_investigate_endpoint.py
git commit -m "feat: add POST /investigate and GET /tools API endpoints"
```

---

## Task 7: Frontend — TypeScript Types and API Service

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`

**Context:** Add TypeScript types for EvidencePin, InvestigateRequest/Response, ToolDefinition, and RouterContext. Add API functions for `postInvestigate()` and `getTools()`.

**Step 1: Add types to `frontend/src/types/index.ts`**

Append to the end of the file:

```typescript
// ── Live Investigation Steering ──────────────────────────────────────

export interface RouterContext {
  active_namespace: string | null;
  active_service: string | null;
  active_pod: string | null;
  time_window: { start: string; end: string };
  session_id: string;
  incident_id: string;
  discovered_services: string[];
  discovered_namespaces: string[];
  pod_names: string[];
  active_findings_summary: string;
  last_agent_phase: string;
  elk_index?: string;
}

export interface QuickActionPayload {
  intent: string;
  params: Record<string, unknown>;
}

export interface InvestigateRequest {
  command?: string;
  query?: string;
  quick_action?: QuickActionPayload;
  context: RouterContext;
}

export interface InvestigateResponse {
  pin_id: string;
  intent: string;
  params: Record<string, unknown>;
  path_used: 'fast' | 'smart';
  status: 'executing' | 'error';
  error?: string;
}

export type EvidencePinDomain = 'compute' | 'network' | 'storage' | 'control_plane' | 'security' | 'unknown';
export type ValidationStatus = 'pending_critic' | 'validated' | 'rejected';
export type CausalRole = 'root_cause' | 'cascading_symptom' | 'correlated' | 'informational';

export interface EvidencePinV2 {
  id: string;
  claim: string;
  source: 'auto' | 'manual';
  source_agent: string | null;
  source_tool: string;
  triggered_by: 'automated_pipeline' | 'user_chat' | 'quick_action';
  evidence_type: string;
  supporting_evidence: string[];
  raw_output: string | null;
  confidence: number;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info' | null;
  causal_role: CausalRole | null;
  domain: EvidencePinDomain;
  validation_status: ValidationStatus;
  namespace: string | null;
  service: string | null;
  resource_name: string | null;
  timestamp: string;
  time_window: { start: string; end: string } | null;
}

export interface ToolParam {
  name: string;
  type: 'string' | 'select' | 'number' | 'boolean';
  required: boolean;
  default_from_context?: string;
  options?: string[];
  placeholder?: string;
}

export interface ToolDefinition {
  intent: string;
  label: string;
  icon: string;
  slash_command: string;
  category: 'logs' | 'metrics' | 'cluster' | 'network' | 'security' | 'code';
  description: string;
  params_schema: ToolParam[];
  requires_context: string[];
}
```

**Step 2: Add API functions to `frontend/src/services/api.ts`**

```typescript
import type { InvestigateRequest, InvestigateResponse, ToolDefinition } from '../types';

export const postInvestigate = async (
  sessionId: string,
  request: InvestigateRequest
): Promise<InvestigateResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/investigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Investigation request failed'));
  }
  return response.json();
};

export const getTools = async (sessionId: string): Promise<{ tools: ToolDefinition[] }> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/session/${sessionId}/tools`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to get tools'));
  }
  return response.json();
};
```

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat: add TypeScript types and API functions for live investigation steering"
```

---

## Task 8: Frontend — Quick Action Toolbar Component

**Files:**
- Create: `frontend/src/components/Chat/QuickActionToolbar.tsx`
- Create: `frontend/src/components/Chat/ToolParamForm.tsx`
- Create: `frontend/src/hooks/useInvestigationTools.ts`

**Context:** The toolbar sits at the top of the ChatDrawer. It fetches tools from `GET /tools`, renders buttons, and shows inline forms for tools needing user input. Uses the existing project patterns: Tailwind dark theme, Material Symbols icons, `useChatUI()` for context.

**Step 1: Create the useInvestigationTools hook**

Create `frontend/src/hooks/useInvestigationTools.ts`:

```typescript
import { useState, useEffect, useCallback } from 'react';
import { getTools, postInvestigate } from '../services/api';
import type { ToolDefinition, InvestigateRequest, InvestigateResponse, RouterContext } from '../types';

export function useInvestigationTools(sessionId: string | null) {
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    getTools(sessionId).then((data) => setTools(data.tools)).catch(() => {});
  }, [sessionId]);

  const executeAction = useCallback(
    async (request: InvestigateRequest): Promise<InvestigateResponse | null> => {
      if (!sessionId) return null;
      setLoading(true);
      try {
        return await postInvestigate(sessionId, request);
      } catch {
        return null;
      } finally {
        setLoading(false);
      }
    },
    [sessionId]
  );

  return { tools, loading, executeAction };
}
```

**Step 2: Create ToolParamForm component**

Create `frontend/src/components/Chat/ToolParamForm.tsx`:

```typescript
import React, { useState, useMemo } from 'react';
import type { ToolDefinition, ToolParam, RouterContext } from '../../types';

interface ToolParamFormProps {
  tool: ToolDefinition;
  context: RouterContext;
  onExecute: (params: Record<string, unknown>) => void;
  onCancel: () => void;
}

export const ToolParamForm: React.FC<ToolParamFormProps> = ({ tool, context, onExecute, onCancel }) => {
  const initialParams = useMemo(() => {
    const params: Record<string, unknown> = {};
    for (const p of tool.params_schema) {
      if (p.default_from_context) {
        const ctxValue = (context as Record<string, unknown>)[p.default_from_context];
        if (ctxValue) params[p.name] = ctxValue;
      }
    }
    return params;
  }, [tool, context]);

  const [params, setParams] = useState<Record<string, unknown>>(initialParams);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onExecute(params);
  };

  const updateParam = (name: string, value: unknown) => {
    setParams((prev) => ({ ...prev, [name]: value }));
  };

  const canSubmit = tool.params_schema
    .filter((p) => p.required)
    .every((p) => params[p.name] !== undefined && params[p.name] !== '');

  return (
    <form onSubmit={handleSubmit} className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 space-y-2">
      <div className="text-xs font-medium text-cyan-400 mb-2">{tool.label}</div>
      {tool.params_schema.map((p) => (
        <ParamField key={p.name} param={p} value={params[p.name]} onChange={(v) => updateParam(p.name, v)} />
      ))}
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel}
          className="px-3 py-1 text-xs text-slate-400 hover:text-white transition-colors">
          Cancel
        </button>
        <button type="submit" disabled={!canSubmit}
          className="px-3 py-1 text-xs bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white rounded transition-colors">
          Run
        </button>
      </div>
    </form>
  );
};

const ParamField: React.FC<{
  param: ToolParam;
  value: unknown;
  onChange: (v: unknown) => void;
}> = ({ param, value, onChange }) => {
  if (param.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-xs text-slate-300">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)}
          className="rounded border-slate-600 bg-slate-800" />
        {param.name}
      </label>
    );
  }
  if (param.type === 'select' && param.options?.length) {
    return (
      <label className="flex flex-col gap-1 text-xs text-slate-300">
        <span>{param.name}{param.required ? ' *' : ''}</span>
        <select value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}
          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-white">
          <option value="">Select...</option>
          {param.options.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    );
  }
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-300">
      <span>{param.name}{param.required ? ' *' : ''}</span>
      <input type={param.type === 'number' ? 'number' : 'text'}
        value={String(value ?? '')}
        placeholder={param.placeholder}
        onChange={(e) => onChange(param.type === 'number' ? Number(e.target.value) : e.target.value)}
        className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-white placeholder-slate-500" />
    </label>
  );
};
```

**Step 3: Create QuickActionToolbar component**

Create `frontend/src/components/Chat/QuickActionToolbar.tsx`:

```typescript
import React, { useState, useCallback } from 'react';
import { ToolParamForm } from './ToolParamForm';
import type { ToolDefinition, RouterContext, QuickActionPayload } from '../../types';

interface QuickActionToolbarProps {
  tools: ToolDefinition[];
  context: RouterContext;
  onExecute: (payload: QuickActionPayload) => void;
  loading: boolean;
}

const ICON_MAP: Record<string, string> = {
  terminal: 'terminal',
  monitoring: 'monitoring',
  info: 'info',
  event_note: 'event_note',
  search: 'search',
  health_and_safety: 'health_and_safety',
  radar: 'radar',
};

export const QuickActionToolbar: React.FC<QuickActionToolbarProps> = ({
  tools, context, onExecute, loading,
}) => {
  const [activeTool, setActiveTool] = useState<ToolDefinition | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const handleClick = useCallback((tool: ToolDefinition) => {
    // If all required params have context defaults, execute immediately
    const needsInput = tool.params_schema.some(
      (p) => p.required && !p.default_from_context
    );
    if (!needsInput) {
      const params: Record<string, unknown> = {};
      for (const p of tool.params_schema) {
        if (p.default_from_context) {
          const v = (context as Record<string, unknown>)[p.default_from_context];
          if (v) params[p.name] = v;
        }
      }
      onExecute({ intent: tool.intent, params });
    } else {
      setActiveTool(tool);
    }
  }, [context, onExecute]);

  const handleFormExecute = useCallback((params: Record<string, unknown>) => {
    if (!activeTool) return;
    onExecute({ intent: activeTool.intent, params });
    setActiveTool(null);
  }, [activeTool, onExecute]);

  const isDisabled = useCallback((tool: ToolDefinition) => {
    return tool.requires_context.some((req) => {
      const val = (context as Record<string, unknown>)[`active_${req}`];
      return !val;
    });
  }, [context]);

  if (collapsed) {
    return (
      <button onClick={() => setCollapsed(false)}
        className="w-full py-1 text-xs text-slate-500 hover:text-cyan-400 transition-colors">
        Show Quick Actions
      </button>
    );
  }

  return (
    <div className="border-b border-slate-800 p-2 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider">Quick Actions</span>
        <button onClick={() => setCollapsed(true)} className="text-slate-600 hover:text-slate-400">
          <span className="material-symbols-outlined text-sm">expand_less</span>
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tools.map((tool) => (
          <button key={tool.intent} onClick={() => handleClick(tool)}
            disabled={loading || isDisabled(tool)}
            title={isDisabled(tool) ? `Requires: ${tool.requires_context.join(', ')}` : tool.description}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded border transition-colors
              ${isDisabled(tool)
                ? 'border-slate-700 text-slate-600 cursor-not-allowed opacity-40'
                : 'border-slate-700 text-slate-300 hover:border-cyan-600 hover:text-cyan-400'
              }`}>
            <span className="material-symbols-outlined text-sm">{ICON_MAP[tool.icon] || tool.icon}</span>
            {tool.label}
          </button>
        ))}
      </div>
      {activeTool && (
        <ToolParamForm
          tool={activeTool}
          context={context}
          onExecute={handleFormExecute}
          onCancel={() => setActiveTool(null)}
        />
      )}
    </div>
  );
};
```

**Step 4: Commit**

```bash
git add frontend/src/hooks/useInvestigationTools.ts frontend/src/components/Chat/QuickActionToolbar.tsx frontend/src/components/Chat/ToolParamForm.tsx
git commit -m "feat: add QuickActionToolbar, ToolParamForm, and useInvestigationTools hook"
```

---

## Task 9: Frontend — Integrate Toolbar into ChatDrawer + Slash Command Autocomplete

**Files:**
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx`

**Context:** Wire the QuickActionToolbar into ChatDrawer. Add slash command autocomplete to the chat input. Add the ghost text UX for slash commands.

**Step 1: Add imports and hook**

At the top of ChatDrawer.tsx, add:

```typescript
import { QuickActionToolbar } from './QuickActionToolbar';
import { useInvestigationTools } from '../../hooks/useInvestigationTools';
import type { RouterContext, QuickActionPayload } from '../../types';
```

**Step 2: Build RouterContext from available state**

Inside the ChatDrawer component, construct the RouterContext from props/context:

```typescript
const routerContext: RouterContext = useMemo(() => ({
  active_namespace: /* from topology selection or session */ namespace ?? null,
  active_service: selectedService ?? null,
  active_pod: null,
  time_window: { start: 'now-1h', end: 'now' },
  session_id: sessionId ?? '',
  incident_id: '',
  discovered_services: [],
  discovered_namespaces: [],
  pod_names: [],
  active_findings_summary: '',
  last_agent_phase: '',
}), [namespace, selectedService, sessionId]);
```

**Step 3: Add toolbar to render**

Insert `<QuickActionToolbar>` at the top of the drawer body, above the messages list:

```tsx
<QuickActionToolbar
  tools={tools}
  context={routerContext}
  onExecute={handleQuickActionExecute}
  loading={toolsLoading}
/>
```

**Step 4: Add slash command autocomplete**

Add state for autocomplete and filter logic when input starts with `/`. Show a dropdown above the input with matching commands. On selection, inject the command template with ghost text (context defaults pre-filled as placeholder).

**Step 5: Handle the `/` input → autocomplete → ghost text flow**

When user types `/` → show dropdown filtered by typed text. On select → replace input with `/logs namespace=payment-api pod=` where context defaults are pre-filled and remaining params are empty with cursor positioned.

**Step 6: Commit**

```bash
git add frontend/src/components/Chat/ChatDrawer.tsx
git commit -m "feat: integrate QuickActionToolbar and slash command autocomplete into ChatDrawer"
```

---

## Task 10: Frontend — EvidencePin Cards with Validation Status Animation

**Files:**
- Create: `frontend/src/components/cards/EvidencePinCard.tsx`
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx`

**Context:** Render EvidencePinV2 objects in the Evidence column. Cards show amber pulse when `validation_status === "pending_critic"`, snap to green/red on update, and display domain badge + causal role badge. Reuses existing card patterns (AgentFindingCard styling).

**Step 1: Create EvidencePinCard**

Create `frontend/src/components/cards/EvidencePinCard.tsx` following the existing AgentFindingCard pattern:

- Amber pulsing border when `pending_critic` (reuse `pulse-red` animation from `index.css`, create `pulse-amber`)
- Green border when `validated`
- Faded opacity when `rejected`
- Domain badge (top-right): compute/network/storage/control_plane/security
- CausalRoleBadge (existing component) when `causal_role` is set
- Expandable "View Raw" section showing `raw_output`
- Severity badge using existing `severityColor` mapping

**Step 2: Add CSS animation for amber pulse**

In `frontend/src/index.css`, add alongside existing `pulse-red`:

```css
@keyframes pulse-amber {
  0%, 100% { border-color: rgba(245, 158, 11, 0.3); }
  50% { border-color: rgba(245, 158, 11, 0.8); }
}
.animate-pulse-amber {
  animation: pulse-amber 2s ease-in-out infinite;
}
```

**Step 3: Add manual evidence pins section in EvidenceFindings**

In EvidenceFindings.tsx, add a new VineCard section that renders EvidencePinCard for all pins where `source === "manual"`. Position it after the root cause patterns section.

**Step 4: Handle WebSocket `evidence_pin_added` and `evidence_pin_updated` events**

In InvestigationView.tsx (or App.tsx), handle the new event types:
- `evidence_pin_added`: Add pin to local state → re-render with amber pulse
- `evidence_pin_updated`: Update pin's `validation_status` and `causal_role` → re-render with final state

**Step 5: Commit**

```bash
git add frontend/src/components/cards/EvidencePinCard.tsx frontend/src/components/Investigation/EvidenceFindings.tsx frontend/src/index.css
git commit -m "feat: add EvidencePinCard with validation status animations and integrate into EvidenceFindings"
```

---

## Task 11: Backend — Critic Delta Revalidation

**Files:**
- Modify: `backend/src/agents/critic_agent.py`
- Modify: `backend/src/api/routes_v4.py`
- Test: `backend/tests/test_critic_delta.py`

**Context:** After a manual EvidencePin is merged, trigger the CriticAgent to delta-validate the new pin against existing evidence. Update the pin's `validation_status` and `causal_role`, then emit `evidence_pin_updated` via WebSocket.

**Step 1: Write failing test**

Create `backend/tests/test_critic_delta.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.models.schemas import EvidencePin


class TestCriticDeltaRevalidation:
    @pytest.mark.asyncio
    async def test_validates_manual_pin(self):
        from src.agents.critic_agent import CriticAgent

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=MagicMock(
            text='{"validation_status": "validated", "causal_role": "cascading_symptom", "confidence": 0.85, "reasoning": "Log errors correlate with metrics spike", "contradictions": []}'
        ))

        critic = CriticAgent(llm_client=mock_llm)

        new_pin = EvidencePin(
            id="pin-manual-001", claim="Pod auth-5b6q: 5 error lines",
            source_agent=None, source_tool="fetch_pod_logs",
            confidence=1.0, timestamp=datetime.now(timezone.utc),
            evidence_type="log", source="manual", domain="compute",
        )
        existing_pins = [
            EvidencePin(
                id="pin-auto-001", claim="Memory spike to 92%",
                source_agent="metrics_agent", source_tool="prometheus",
                confidence=0.9, timestamp=datetime.now(timezone.utc),
                evidence_type="metric", source="auto", domain="compute",
                validation_status="validated", causal_role="root_cause",
            ),
        ]

        result = await critic.validate_delta(new_pin, existing_pins, [])

        assert result["validation_status"] in ("validated", "rejected")
        assert result["causal_role"] is not None
```

**Step 2: Implement `validate_delta` on CriticAgent**

Add a `validate_delta(new_pin, existing_pins, causal_chains)` method that sends the new pin + existing evidence summary to the LLM with a prompt asking: "Does this new evidence support, contradict, or add to the existing findings? Assign a causal_role and validation_status."

**Step 3: Wire into routes_v4.py**

After merging the pin in the `/investigate` endpoint, dispatch an async task to run critic delta revalidation. On completion, update the pin in session state and emit `evidence_pin_updated` WebSocket event.

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_critic_delta.py -v`

**Step 5: Commit**

```bash
git add backend/src/agents/critic_agent.py backend/src/api/routes_v4.py backend/tests/test_critic_delta.py
git commit -m "feat: add critic delta revalidation for manual evidence pins"
```

---

## Task 12: Integration Test — End-to-End Flow

**Files:**
- Test: `backend/tests/test_investigation_integration.py`

**Context:** Full end-to-end test: create session → POST /investigate with quick_action → verify EvidencePin created → verify WebSocket event emitted → verify critic revalidation triggered.

**Step 1: Write integration test**

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture(autouse=True)
def _clear():
    from src.api.routes_v4 import sessions, supervisors, session_locks, _investigation_routers
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    _investigation_routers.clear()
    yield
    sessions.clear()
    supervisors.clear()
    session_locks.clear()
    _investigation_routers.clear()


class TestInvestigationIntegration:
    def test_full_flow_quick_action(self):
        client = TestClient(app)

        # 1. Create session
        with patch("src.api.routes_v4.SupervisorAgent"):
            resp = client.post("/api/v4/session/start", json={
                "serviceName": "auth-service",
                "namespace": "payment-api",
                "capability": "troubleshoot_app",
            })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # 2. Get available tools
        resp = client.get(f"/api/v4/session/{session_id}/tools")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert any(t["intent"] == "fetch_pod_logs" for t in tools)

        # 3. Execute investigation via quick action (mocked executor)
        with patch("src.api.routes_v4._get_investigation_router") as mock_get:
            from src.tools.router_models import InvestigateResponse
            from src.models.schemas import EvidencePin
            from datetime import datetime, timezone

            pin = EvidencePin(
                id="pin-test", claim="Pod auth: 3 errors",
                source_agent=None, source_tool="fetch_pod_logs",
                confidence=1.0, timestamp=datetime.now(timezone.utc),
                evidence_type="log", source="manual", domain="compute",
                validation_status="pending_critic",
            )
            mock_router = AsyncMock()
            mock_router.route = AsyncMock(return_value=(
                InvestigateResponse(
                    pin_id="pin-test", intent="fetch_pod_logs",
                    params={"pod": "auth"}, path_used="fast", status="executing",
                ), pin,
            ))
            mock_get.return_value = mock_router

            resp = client.post(f"/api/v4/session/{session_id}/investigate", json={
                "quick_action": {"intent": "fetch_pod_logs", "params": {"pod": "auth"}},
                "context": {
                    "active_namespace": "payment-api",
                    "time_window": {"start": "now-1h", "end": "now"},
                },
            })

        assert resp.status_code == 200
        assert resp.json()["pin_id"] == "pin-test"
        assert resp.json()["path_used"] == "fast"
```

**Step 2: Run test**

Run: `cd backend && python -m pytest tests/test_investigation_integration.py -v`

**Step 3: Commit**

```bash
git add backend/tests/test_investigation_integration.py
git commit -m "test: add end-to-end integration test for investigation steering flow"
```

---

## Summary

| Task | Component | New Files | Modified Files |
|------|-----------|-----------|----------------|
| 1 | EvidencePin schema extension | `test_evidence_pin_v2.py` | `schemas.py` |
| 2 | ToolResult + EvidencePinFactory | `tool_result.py`, `router_models.py`, `evidence_pin_factory.py`, `test_tool_result.py` | — |
| 3 | ToolExecutor (logs, describe) | `tool_executor.py`, `test_tool_executor.py` | — |
| 4 | ToolExecutor (prometheus, ELK, pods, events) | `test_tool_executor_extended.py` | `tool_executor.py` |
| 5 | InvestigationRouter | `investigation_router.py`, `tool_registry.py`, `test_investigation_router.py` | — |
| 6 | API endpoints | `test_investigate_endpoint.py` | `routes_v4.py` |
| 7 | Frontend types + API | — | `types/index.ts`, `api.ts` |
| 8 | QuickActionToolbar + ToolParamForm | `QuickActionToolbar.tsx`, `ToolParamForm.tsx`, `useInvestigationTools.ts` | — |
| 9 | ChatDrawer integration + slash autocomplete | — | `ChatDrawer.tsx` |
| 10 | EvidencePinCard + animations | `EvidencePinCard.tsx` | `EvidenceFindings.tsx`, `index.css` |
| 11 | Critic delta revalidation | `test_critic_delta.py` | `critic_agent.py`, `routes_v4.py` |
| 12 | Integration test | `test_investigation_integration.py` | — |
