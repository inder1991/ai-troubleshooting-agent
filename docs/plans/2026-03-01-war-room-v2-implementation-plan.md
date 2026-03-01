# War Room v2 — Platform Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Transform the diagnostics workflow from a single-root-cause tool into a complete SRE investigation platform with multi-root-cause Causal Forest, operational recommendations, Surgical Telescope resource inspector, NeuralChart metrics visualization, click-anywhere ResourceEntity drill-down, and enriched backend schema.

**Architecture:** 15 tasks organized in dependency order — data layer first (backend models, parser, LTTB, API endpoints, synthesizer, route wiring), then frontend foundation (types, parser, context, chart wrapper), then features (Causal Forest, recommendations, Telescope, chart integration), and finally layout pivot and end-to-end wiring. Each task is independently testable.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, pytest, React 18, TypeScript, Tailwind CSS, Recharts, react-syntax-highlighter, react-window

**Design Doc:** `docs/plans/2026-03-01-war-room-v2-platform-upgrade-design.md`

**Branch:** `feature/war-room-v2` (from `main`)

---

## Task 1: Backend Data Models — ResourceRef, CausalTree, OperationalRecommendation

**Files:**
- Modify: `backend/src/models/schemas.py`
- Create: `backend/tests/test_war_room_models.py`

**Context:** All new Pydantic models that power the War Room v2 features. These are the data contracts between backend synthesis and frontend rendering. Existing models (Finding, EvidencePin, etc.) are unchanged. New models are additive.

**Changes:**

1. Add `ResourceRef` model after `EvidencePin` (around line 661):

```python
class ResourceRef(BaseModel):
    """A reference to a Kubernetes/OpenShift resource for click-anywhere drill-down."""
    type: str  # pod, deployment, service, configmap, pvc, node, ingress,
               # replicaset, deploymentconfig, route, buildconfig, imagestream
    name: str
    namespace: Optional[str] = None
    status: Optional[str] = None    # Running, CrashLoopBackOff — for hover tooltip
    age: Optional[str] = None       # "2d", "15m" — for hover tooltip
```

2. Add `CommandStep` model:

```python
class CommandStep(BaseModel):
    """A single command in an operational recommendation."""
    order: int
    description: str
    command: str
    command_type: Literal["kubectl", "oc", "helm", "shell"]
    is_dry_run: bool = False
    dry_run_command: Optional[str] = None
    validation_command: Optional[str] = None
```

3. Add `OperationalRecommendation` model:

```python
class OperationalRecommendation(BaseModel):
    """A copy-paste ready operational command recommendation."""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    title: str
    urgency: Literal["immediate", "short_term", "preventive"]
    category: Literal["scale", "rollback", "restart", "config_patch", "network", "storage"]
    commands: list[CommandStep]
    rollback_commands: list[CommandStep] = Field(default_factory=list)
    risk_level: Literal["safe", "caution", "destructive"]
    prerequisites: list[str] = Field(default_factory=list)
    expected_outcome: str = ""
    resource_refs: list[ResourceRef] = Field(default_factory=list)
```

4. Add `CausalTree` model:

```python
class CausalTree(BaseModel):
    """An independent root cause with its cascading symptoms and recommendations."""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    root_cause: Finding
    severity: Literal["critical", "warning", "info"]
    blast_radius: Optional[dict] = None  # Uses BlastRadiusData shape
    cascading_symptoms: list[Finding] = Field(default_factory=list)
    correlated_signals: list[CorrelatedSignalGroup] = Field(default_factory=list)
    operational_recommendations: list[OperationalRecommendation] = Field(default_factory=list)
    triage_status: Literal["untriaged", "acknowledged", "mitigated", "resolved"] = "untriaged"
    resource_refs: list[ResourceRef] = Field(default_factory=list)
```

5. Add `resource_refs` field to existing `Finding` model (line ~103):

```python
class Finding(BaseModel):
    # ... existing fields ...
    resource_refs: list["ResourceRef"] = Field(default_factory=list)
```

6. Add `resource_refs` field to existing `EvidencePin` model (line ~639):

```python
class EvidencePin(BaseModel):
    # ... existing fields ...
    resource_refs: list["ResourceRef"] = Field(default_factory=list)
```

**Tests** (`backend/tests/test_war_room_models.py`):

```python
import pytest
from backend.src.models.schemas import (
    ResourceRef, CommandStep, OperationalRecommendation,
    CausalTree, Finding, Breadcrumb, EvidencePin,
)
from datetime import datetime


class TestResourceRef:
    def test_minimal(self):
        ref = ResourceRef(type="pod", name="auth-5b6q")
        assert ref.type == "pod"
        assert ref.namespace is None

    def test_full(self):
        ref = ResourceRef(type="pod", name="auth-5b6q", namespace="payment-api", status="Running", age="2d")
        assert ref.namespace == "payment-api"
        assert ref.status == "Running"

    def test_openshift_types(self):
        ref = ResourceRef(type="deploymentconfig", name="auth-dc")
        assert ref.type == "deploymentconfig"


class TestCommandStep:
    def test_basic(self):
        step = CommandStep(order=1, description="Scale up", command="kubectl scale deploy/auth --replicas=3", command_type="kubectl")
        assert step.is_dry_run is False
        assert step.dry_run_command is None

    def test_with_dry_run(self):
        step = CommandStep(
            order=1, description="Scale up", command="kubectl scale deploy/auth --replicas=3",
            command_type="kubectl", is_dry_run=True,
            dry_run_command="kubectl scale deploy/auth --replicas=3 --dry-run=client -o yaml",
            validation_command="kubectl get deploy auth -o jsonpath='{.spec.replicas}'"
        )
        assert step.is_dry_run is True


class TestOperationalRecommendation:
    def test_minimal(self):
        rec = OperationalRecommendation(
            title="Scale auth deployment", urgency="immediate", category="scale",
            commands=[CommandStep(order=1, description="Scale", command="kubectl scale deploy/auth --replicas=3", command_type="kubectl")],
            risk_level="safe",
        )
        assert rec.urgency == "immediate"
        assert len(rec.id) > 0  # UUID auto-generated

    def test_with_rollback(self):
        rec = OperationalRecommendation(
            title="Rollback", urgency="immediate", category="rollback",
            commands=[CommandStep(order=1, description="Rollback", command="kubectl rollout undo deploy/auth", command_type="kubectl")],
            rollback_commands=[CommandStep(order=1, description="Undo", command="kubectl rollout undo deploy/auth", command_type="kubectl")],
            risk_level="caution", prerequisites=["Confirm no active traffic"],
            expected_outcome="Pod restarts with previous image",
        )
        assert rec.risk_level == "caution"
        assert len(rec.rollback_commands) == 1


class TestCausalTree:
    def _make_finding(self, summary="OOM in auth pod"):
        return Finding(
            finding_id="f1", agent_name="k8s_agent", category="resource",
            summary=summary, confidence_score=85, severity="critical",
            breadcrumbs=[Breadcrumb(agent_name="k8s_agent", action="check", source_type="k8s_event", source_reference="pod/auth", raw_evidence="OOM", timestamp=datetime.now())],
            negative_findings=[],
        )

    def test_minimal(self):
        tree = CausalTree(root_cause=self._make_finding(), severity="critical")
        assert tree.triage_status == "untriaged"
        assert len(tree.id) > 0

    def test_with_symptoms_and_recommendations(self):
        tree = CausalTree(
            root_cause=self._make_finding("OOM"),
            severity="critical",
            cascading_symptoms=[self._make_finding("Pod restart")],
            operational_recommendations=[
                OperationalRecommendation(
                    title="Increase memory", urgency="immediate", category="scale",
                    commands=[CommandStep(order=1, description="Patch", command="kubectl patch deploy/auth -p '{...}'", command_type="kubectl")],
                    risk_level="safe",
                )
            ],
            resource_refs=[ResourceRef(type="pod", name="auth-5b6q", namespace="payment-api")],
        )
        assert len(tree.cascading_symptoms) == 1
        assert len(tree.operational_recommendations) == 1
        assert len(tree.resource_refs) == 1


class TestResourceRefsOnExistingModels:
    def test_finding_has_resource_refs(self):
        f = Finding(
            finding_id="f1", agent_name="k8s_agent", category="resource",
            summary="test", confidence_score=85, severity="critical",
            breadcrumbs=[], negative_findings=[],
            resource_refs=[ResourceRef(type="pod", name="auth")],
        )
        assert len(f.resource_refs) == 1

    def test_finding_resource_refs_default_empty(self):
        f = Finding(
            finding_id="f1", agent_name="k8s_agent", category="resource",
            summary="test", confidence_score=85, severity="critical",
            breadcrumbs=[], negative_findings=[],
        )
        assert f.resource_refs == []

    def test_evidence_pin_has_resource_refs(self):
        pin = EvidencePin(
            claim="test", source_tool="fetch_pod_logs", confidence=0.8,
            timestamp=datetime.now(), evidence_type="log",
            resource_refs=[ResourceRef(type="service", name="auth-svc", namespace="default")],
        )
        assert len(pin.resource_refs) == 1
```

**Commit:** `feat: add War Room v2 data models (ResourceRef, CausalTree, OperationalRecommendation)`

---

## Task 2: @[kind:ns/name] Resource Reference Parser (Backend)

**Files:**
- Create: `backend/src/utils/resource_ref_parser.py`
- Create: `backend/tests/test_resource_ref_parser.py`

**Context:** LLM agents are prompted to use `@[kind:namespace/name]` inline references. This utility extracts them from text and returns `ResourceRef` objects. It also auto-populates `resource_refs` lists on models that contain text fields. Used as a post-processing step after LLM synthesis.

**Changes:**

```python
"""Parse @[kind:namespace/name] inline resource references from LLM-generated text."""
import re
from backend.src.models.schemas import ResourceRef

# Matches @[kind:namespace/name] or @[kind:name]
_RESOURCE_REF_PATTERN = re.compile(
    r'@\[([a-z_]+):(?:([a-z0-9][a-z0-9._-]*)/)?'
    r'([a-z0-9][a-z0-9._-]*)\]',
    re.IGNORECASE,
)

_VALID_KINDS = frozenset({
    "pod", "deployment", "service", "configmap", "pvc", "node", "ingress",
    "replicaset", "namespace", "secret", "statefulset", "daemonset", "job", "cronjob",
    # OpenShift
    "deploymentconfig", "route", "buildconfig", "imagestream",
})


def extract_resource_refs(text: str, default_namespace: str | None = None) -> list[ResourceRef]:
    """Extract all @[kind:namespace/name] references from text.

    Args:
        text: LLM-generated text containing inline references.
        default_namespace: Fallback namespace when short format @[kind:name] is used.

    Returns:
        Deduplicated list of ResourceRef objects.
    """
    seen: set[tuple[str, str, str | None]] = set()
    refs: list[ResourceRef] = []

    for match in _RESOURCE_REF_PATTERN.finditer(text):
        kind = match.group(1).lower()
        namespace = match.group(2) or default_namespace
        name = match.group(3)

        if kind not in _VALID_KINDS:
            continue

        key = (kind, name, namespace)
        if key in seen:
            continue
        seen.add(key)

        refs.append(ResourceRef(type=kind, name=name, namespace=namespace))

    return refs


def strip_resource_ref_syntax(text: str) -> str:
    """Remove @[kind:ns/name] syntax, leaving just the resource name.

    Example: 'Pod @[pod:default/auth-5b6q] crashed' → 'Pod auth-5b6q crashed'
    """
    def _replace(match: re.Match) -> str:
        return match.group(3)  # Just the name

    return _RESOURCE_REF_PATTERN.sub(_replace, text)
```

**Tests** (`backend/tests/test_resource_ref_parser.py`):

```python
import pytest
from backend.src.utils.resource_ref_parser import extract_resource_refs, strip_resource_ref_syntax


class TestExtractResourceRefs:
    def test_fully_qualified(self):
        text = "Pod @[pod:payment-api/auth-5b6q] is crashing"
        refs = extract_resource_refs(text)
        assert len(refs) == 1
        assert refs[0].type == "pod"
        assert refs[0].name == "auth-5b6q"
        assert refs[0].namespace == "payment-api"

    def test_short_format_with_default_ns(self):
        text = "Check @[service:auth-svc]"
        refs = extract_resource_refs(text, default_namespace="default")
        assert len(refs) == 1
        assert refs[0].namespace == "default"

    def test_short_format_no_default_ns(self):
        text = "Check @[service:auth-svc]"
        refs = extract_resource_refs(text)
        assert refs[0].namespace is None

    def test_multiple_refs(self):
        text = "Pod @[pod:ns/auth-5b6q] crashed due to @[pvc:ns/auth-data-vol] exhaustion"
        refs = extract_resource_refs(text)
        assert len(refs) == 2
        assert {r.type for r in refs} == {"pod", "pvc"}

    def test_deduplication(self):
        text = "@[pod:ns/auth] and again @[pod:ns/auth]"
        refs = extract_resource_refs(text)
        assert len(refs) == 1

    def test_invalid_kind_ignored(self):
        text = "@[invalid_kind:ns/name]"
        refs = extract_resource_refs(text)
        assert len(refs) == 0

    def test_openshift_types(self):
        text = "@[deploymentconfig:myns/auth-dc] and @[route:myns/auth-route]"
        refs = extract_resource_refs(text)
        assert len(refs) == 2
        assert {r.type for r in refs} == {"deploymentconfig", "route"}

    def test_no_refs(self):
        refs = extract_resource_refs("No resource references here")
        assert refs == []

    def test_mixed_case_kind(self):
        text = "@[Pod:ns/auth]"
        refs = extract_resource_refs(text)
        assert len(refs) == 1
        assert refs[0].type == "pod"


class TestStripResourceRefSyntax:
    def test_strips_to_name(self):
        text = "Pod @[pod:payment-api/auth-5b6q] is crashing"
        result = strip_resource_ref_syntax(text)
        assert result == "Pod auth-5b6q is crashing"

    def test_strips_multiple(self):
        text = "@[pod:ns/auth] uses @[pvc:ns/vol]"
        result = strip_resource_ref_syntax(text)
        assert result == "auth uses vol"

    def test_no_refs_unchanged(self):
        text = "No references"
        assert strip_resource_ref_syntax(text) == text
```

**Commit:** `feat: add @[kind:ns/name] resource reference parser`

---

## Task 3: LTTB Downsampling Utility (Backend)

**Files:**
- Create: `backend/src/utils/lttb.py`
- Create: `backend/tests/test_lttb.py`

**Context:** Largest Triangle Three Buckets downsampling. Never send more than 150 data points per time-series line to the frontend. Pure Python, no external dependency. Applied in `ToolExecutor._query_prometheus()` and `EvidencePinFactory.from_tool_result()`.

**Changes:**

```python
"""LTTB (Largest Triangle Three Buckets) downsampling for time-series data.

Hard rule: Never send more than 150 data points per line to the frontend.
"""
from __future__ import annotations

MAX_POINTS = 150


def lttb_downsample(
    data: list[tuple[float, float]],
    threshold: int = MAX_POINTS,
) -> list[tuple[float, float]]:
    """Downsample time-series data using LTTB algorithm.

    Args:
        data: List of (timestamp, value) tuples, sorted by timestamp.
        threshold: Maximum number of output points.

    Returns:
        Downsampled list of (timestamp, value) tuples.
    """
    length = len(data)
    if threshold >= length or threshold < 3:
        return list(data)

    sampled: list[tuple[float, float]] = []

    # Always keep first point
    sampled.append(data[0])

    # Bucket size (excluding first and last points)
    bucket_size = (length - 2) / (threshold - 2)

    a = 0  # Index of previously selected point

    for i in range(1, threshold - 1):
        # Calculate bucket boundaries
        bucket_start = int((i - 1) * bucket_size) + 1
        bucket_end = int(i * bucket_size) + 1
        bucket_end = min(bucket_end, length - 1)

        # Calculate next bucket average for triangle area calculation
        next_bucket_start = int(i * bucket_size) + 1
        next_bucket_end = int((i + 1) * bucket_size) + 1
        next_bucket_end = min(next_bucket_end, length)

        avg_x = sum(data[j][0] for j in range(next_bucket_start, next_bucket_end)) / max(1, next_bucket_end - next_bucket_start)
        avg_y = sum(data[j][1] for j in range(next_bucket_start, next_bucket_end)) / max(1, next_bucket_end - next_bucket_start)

        # Find point in current bucket with largest triangle area
        max_area = -1.0
        max_idx = bucket_start

        point_a = data[a]

        for j in range(bucket_start, bucket_end):
            # Triangle area using cross product
            area = abs(
                (point_a[0] - avg_x) * (data[j][1] - point_a[1])
                - (point_a[0] - data[j][0]) * (avg_y - point_a[1])
            ) * 0.5

            if area > max_area:
                max_area = area
                max_idx = j

        sampled.append(data[max_idx])
        a = max_idx

    # Always keep last point
    sampled.append(data[-1])

    return sampled
```

**Tests** (`backend/tests/test_lttb.py`):

```python
import pytest
import math
from backend.src.utils.lttb import lttb_downsample, MAX_POINTS


class TestLTTBDownsample:
    def test_below_threshold_returns_copy(self):
        data = [(float(i), float(i * 2)) for i in range(50)]
        result = lttb_downsample(data)
        assert len(result) == 50

    def test_at_threshold_returns_copy(self):
        data = [(float(i), float(i)) for i in range(150)]
        result = lttb_downsample(data)
        assert len(result) == 150

    def test_above_threshold_downsamples(self):
        data = [(float(i), float(i)) for i in range(500)]
        result = lttb_downsample(data)
        assert len(result) == MAX_POINTS

    def test_preserves_first_and_last(self):
        data = [(float(i), math.sin(i * 0.1)) for i in range(300)]
        result = lttb_downsample(data, threshold=50)
        assert result[0] == data[0]
        assert result[-1] == data[-1]

    def test_custom_threshold(self):
        data = [(float(i), float(i)) for i in range(1000)]
        result = lttb_downsample(data, threshold=20)
        assert len(result) == 20

    def test_threshold_too_small_returns_all(self):
        data = [(float(i), float(i)) for i in range(100)]
        result = lttb_downsample(data, threshold=2)
        assert len(result) == 100

    def test_empty_data(self):
        assert lttb_downsample([]) == []

    def test_single_point(self):
        data = [(1.0, 2.0)]
        assert lttb_downsample(data) == [(1.0, 2.0)]

    def test_preserves_spikes(self):
        """LTTB should preferentially keep points that form large triangles (spikes)."""
        # Flat line with one spike
        data = [(float(i), 0.0) for i in range(200)]
        data[100] = (100.0, 1000.0)  # Spike
        result = lttb_downsample(data, threshold=20)
        values = [v for _, v in result]
        assert max(values) == 1000.0, "LTTB should preserve the spike"

    def test_output_sorted_by_timestamp(self):
        data = [(float(i), math.sin(i * 0.05)) for i in range(500)]
        result = lttb_downsample(data, threshold=50)
        timestamps = [t for t, _ in result]
        assert timestamps == sorted(timestamps)
```

**Commit:** `feat: add LTTB downsampling utility for time-series data`

---

## Task 4: Resource API Endpoints (Backend)

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Modify: `backend/src/tools/tool_executor.py`
- Create: `backend/tests/test_resource_endpoints.py`

**Context:** Two new endpoints for the Surgical Telescope drawer. The first returns YAML + events (fast, always fetched on drawer open). The second returns logs (lazy, only on LOGS tab click). Uses the existing lazy-init K8s clients from `ToolExecutor`.

**Changes to `routes_v4.py`** — add after the `/promql/query` endpoint:

```python
@router_v4.get("/session/{session_id}/resource/{namespace}/{kind}/{name}")
async def get_resource(session_id: str, namespace: str, kind: str, name: str):
    """Fetch K8s resource YAML and events for the Surgical Telescope drawer."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    config = session.get("connection_config", {})
    executor = ToolExecutor(config=config)

    # Fetch resource YAML
    yaml_result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: executor.get_resource_yaml(kind, name, namespace)
    )

    # Fetch events for this resource
    events_result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: executor.get_resource_events(kind, name, namespace)
    )

    return {
        "yaml": yaml_result.get("yaml", ""),
        "events": events_result.get("events", []),
        "error": yaml_result.get("error") or events_result.get("error"),
    }


@router_v4.get("/session/{session_id}/resource/{namespace}/{kind}/{name}/logs")
async def get_resource_logs(
    session_id: str, namespace: str, kind: str, name: str,
    tail_lines: int = 500, container: str | None = None,
):
    """Fetch pod logs lazily — only called when LOGS tab is clicked."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if kind != "pod":
        return {"logs": "", "error": f"Logs only available for pods, not {kind}"}

    tail_lines = max(1, min(tail_lines, 5000))
    config = session.get("connection_config", {})
    executor = ToolExecutor(config=config)

    logs_result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: executor.get_pod_logs(name, namespace, tail_lines, container)
    )

    return {
        "logs": logs_result.get("logs", ""),
        "error": logs_result.get("error"),
    }
```

**Changes to `tool_executor.py`** — add three new public methods:

```python
def get_resource_yaml(self, kind: str, name: str, namespace: str) -> dict:
    """Get resource YAML as string. Used by Telescope drawer."""
    try:
        api = self._get_api_for_kind(kind)
        method_name, is_cluster_scoped, _ = self._KIND_TO_API_METHOD.get(
            kind, (None, False, "core")
        )
        if not method_name:
            return {"yaml": "", "error": f"Unsupported kind: {kind}"}

        read_method = f"read_{'namespaced_' if not is_cluster_scoped else ''}{kind}"
        reader = getattr(api, read_method, None)
        if not reader:
            return {"yaml": "", "error": f"No API method for kind: {kind}"}

        if is_cluster_scoped:
            resource = reader(name)
        else:
            resource = reader(name, namespace)

        from kubernetes.client import ApiClient
        yaml_str = ApiClient().sanitize_for_serialization(resource)
        import json
        return {"yaml": json.dumps(yaml_str, indent=2, default=str)}
    except Exception as e:
        logger.error("Failed to get resource YAML", extra={"kind": kind, "name": name, "error": str(e)})
        return {"yaml": "", "error": "Failed to fetch resource"}

def get_resource_events(self, kind: str, name: str, namespace: str) -> dict:
    """Get K8s events for a specific resource. Used by Telescope drawer."""
    try:
        api = self._get_k8s_core_api()
        field_selector = f"involvedObject.name={name},involvedObject.kind={kind.capitalize()}"
        events = api.list_namespaced_event(namespace, field_selector=field_selector)
        return {
            "events": [
                {
                    "type": e.type or "Normal",
                    "reason": e.reason or "",
                    "message": e.message or "",
                    "count": getattr(e, 'count', 1) or 1,
                    "first_timestamp": e.first_timestamp.isoformat() if e.first_timestamp else "",
                    "last_timestamp": e.last_timestamp.isoformat() if e.last_timestamp else "",
                    "source_component": e.source.component if e.source else "",
                }
                for e in events.items
            ]
        }
    except Exception as e:
        logger.error("Failed to get resource events", extra={"kind": kind, "name": name, "error": str(e)})
        return {"events": [], "error": "Failed to fetch events"}

def get_pod_logs(self, pod_name: str, namespace: str, tail_lines: int = 500, container: str | None = None) -> dict:
    """Get pod logs. Used by Telescope LOGS tab."""
    try:
        api = self._get_k8s_core_api()
        kwargs: dict = {"tail_lines": tail_lines}
        if container:
            kwargs["container"] = container
        logs = api.read_namespaced_pod_log(pod_name, namespace, **kwargs)
        return {"logs": logs or ""}
    except Exception as e:
        logger.error("Failed to get pod logs", extra={"pod": pod_name, "error": str(e)})
        return {"logs": "", "error": "Failed to fetch logs"}
```

Also add a helper to resolve the correct API object for a given kind:

```python
def _get_api_for_kind(self, kind: str) -> object:
    """Return the correct K8s API client for the given resource kind."""
    _, _, api_group = self._KIND_TO_API_METHOD.get(kind, (None, False, "core"))
    if api_group == "apps":
        return self._get_k8s_apps_api()
    elif api_group == "networking":
        return self._get_k8s_networking_api()
    else:
        return self._get_k8s_core_api()
```

**Tests** (`backend/tests/test_resource_endpoints.py`):

Test the ToolExecutor methods with mocked K8s clients. Test the API endpoints with FastAPI TestClient and mocked session/executor.

```python
import pytest
from unittest.mock import MagicMock, patch
from backend.src.tools.tool_executor import ToolExecutor


class TestGetResourceYaml:
    def test_returns_yaml_for_pod(self):
        executor = ToolExecutor(config={})
        mock_api = MagicMock()
        mock_api.read_namespaced_pod.return_value = MagicMock()
        executor._k8s_core_api = mock_api
        result = executor.get_resource_yaml("pod", "auth-5b6q", "default")
        assert "error" not in result or result["error"] is None

    def test_unsupported_kind(self):
        executor = ToolExecutor(config={})
        result = executor.get_resource_yaml("unknown_kind", "name", "ns")
        assert result["error"] is not None

    def test_api_failure_returns_generic_error(self):
        executor = ToolExecutor(config={})
        mock_api = MagicMock()
        mock_api.read_namespaced_pod.side_effect = Exception("connection refused")
        executor._k8s_core_api = mock_api
        result = executor.get_resource_yaml("pod", "auth", "default")
        assert result["error"] == "Failed to fetch resource"
        assert "connection refused" not in result["error"]


class TestGetResourceEvents:
    def test_returns_events(self):
        executor = ToolExecutor(config={})
        mock_api = MagicMock()
        mock_event = MagicMock()
        mock_event.type = "Warning"
        mock_event.reason = "BackOff"
        mock_event.message = "Back-off restarting"
        mock_event.count = 5
        mock_event.first_timestamp = None
        mock_event.last_timestamp = None
        mock_event.source = MagicMock(component="kubelet")
        mock_api.list_namespaced_event.return_value = MagicMock(items=[mock_event])
        executor._k8s_core_api = mock_api
        result = executor.get_resource_events("pod", "auth", "default")
        assert len(result["events"]) == 1
        assert result["events"][0]["reason"] == "BackOff"


class TestGetPodLogs:
    def test_returns_logs(self):
        executor = ToolExecutor(config={})
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log.return_value = "2024-01-01 ERROR something"
        executor._k8s_core_api = mock_api
        result = executor.get_pod_logs("auth-5b6q", "default")
        assert "ERROR" in result["logs"]

    def test_with_container(self):
        executor = ToolExecutor(config={})
        mock_api = MagicMock()
        mock_api.read_namespaced_pod_log.return_value = "logs"
        executor._k8s_core_api = mock_api
        executor.get_pod_logs("auth", "default", container="sidecar")
        mock_api.read_namespaced_pod_log.assert_called_once_with("auth", "default", tail_lines=500, container="sidecar")
```

**Commit:** `feat: add resource API endpoints for Surgical Telescope`

---

## Task 5: LTTB Integration + Prometheus Downsampling (Backend)

**Files:**
- Modify: `backend/src/tools/tool_executor.py` (integrate LTTB into `_query_prometheus`)
- Modify: `backend/src/tools/evidence_pin_factory.py` (enforce 150-point cap on time_series metadata)
- Modify: `backend/src/api/routes_v4.py` (replace 30-point cap with LTTB in `/promql/query` and `/findings`)
- Modify: `backend/tests/test_tool_executor.py`

**Context:** Currently time-series data is capped at 30 points via naive slicing (`points[-30:]`). Replace with LTTB downsampling capped at 150 points for visual fidelity.

**Changes:**

1. In `tool_executor.py` `_query_prometheus()` — after aggregating values, downsample:
```python
from backend.src.utils.lttb import lttb_downsample

# After building the values list from Prometheus result:
if len(all_values) > 150:
    ts_tuples = [(float(ts), float(val)) for ts, val in all_values]
    downsampled = lttb_downsample(ts_tuples)
    all_values = [(ts, val) for ts, val in downsampled]
```

2. In `routes_v4.py` `get_findings()` — replace `points[-30:]` (line ~760) with:
```python
from backend.src.utils.lttb import lttb_downsample, MAX_POINTS

# Replace: capped = points[-30:] if len(points) > 30 else points
ts_tuples = [(dp.timestamp.timestamp(), dp.value) for dp in points]
downsampled = lttb_downsample(ts_tuples, MAX_POINTS)
ts_data_raw[key] = [{"timestamp": datetime.fromtimestamp(ts).isoformat(), "value": val} for ts, val in downsampled]
```

3. In `routes_v4.py` `proxy_promql_query()` — apply LTTB to response:
```python
# After getting response data, before returning:
if result_data:
    for series in result_data:
        values = series.get("values", [])
        if len(values) > MAX_POINTS:
            ts_tuples = [(float(v[0]), float(v[1])) for v in values]
            downsampled = lttb_downsample(ts_tuples, MAX_POINTS)
            series["values"] = [[ts, str(val)] for ts, val in downsampled]
```

**Tests:** Add tests verifying downsampling is applied when data exceeds 150 points. Add tests verifying data under 150 points is returned as-is.

**Commit:** `feat: integrate LTTB downsampling into Prometheus queries and findings`

---

## Task 6: Causal Forest in V4Findings Response (Backend)

**Files:**
- Modify: `backend/src/models/schemas.py` (add `causal_forest` to `DiagnosticState`)
- Modify: `backend/src/api/routes_v4.py` (add `causal_forest` to findings response)
- Modify: `backend/src/api/routes_v4.py` (add triage status update endpoint)
- Create: `backend/tests/test_causal_forest_response.py`

**Context:** The `causal_forest` field is the primary view for War Room v2. It's populated by the synthesizer (Task not in scope here — the synthesizer prompt is a separate concern that will evolve over time). For now, wire the data model through the API. Also add a PATCH endpoint for triage status updates.

**Changes:**

1. Add `causal_forest` to `DiagnosticState` (schemas.py):
```python
class DiagnosticState(BaseModel):
    # ... existing fields ...
    causal_forest: list[CausalTree] = Field(default_factory=list)
```

2. Add `causal_forest` to findings response in `get_findings()`:
```python
# In the return dict:
"causal_forest": [ct.model_dump(mode="json") for ct in state.causal_forest] if state.causal_forest else [],
```

Also add to the empty-state return (when `state` is None):
```python
"causal_forest": [],
```

3. Add triage status PATCH endpoint:
```python
class TriageStatusUpdate(BaseModel):
    status: Literal["untriaged", "acknowledged", "mitigated", "resolved"]

@router_v4.patch("/session/{session_id}/causal-tree/{tree_id}/triage")
async def update_triage_status(session_id: str, tree_id: str, update: TriageStatusUpdate):
    """Update triage status of a CausalTree."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    if not state or not state.causal_forest:
        raise HTTPException(status_code=404, detail="No causal forest data")

    for tree in state.causal_forest:
        if tree.id == tree_id:
            tree.triage_status = update.status
            return {"status": "updated", "tree_id": tree_id, "triage_status": update.status}

    raise HTTPException(status_code=404, detail=f"CausalTree {tree_id} not found")
```

**Tests:**
- Test causal_forest appears in findings response (empty by default)
- Test causal_forest serialization with populated data
- Test triage status PATCH updates correctly
- Test triage status PATCH with invalid tree_id returns 404

**Commit:** `feat: wire causal_forest through V4Findings API response`

---

## Task 7: Frontend TypeScript Types + API Methods

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`

**Context:** Add TypeScript interfaces matching the new backend models, and API methods for the new endpoints. No tests — TypeScript type safety + `npx tsc --noEmit` is the verification.

**Changes to `types/index.ts`** — add after the `EvidencePinV2` interface (around line 971):

```typescript
// ── War Room v2 Types ──────────────────────────────────────────────────

export interface ResourceRef {
  type: string;
  name: string;
  namespace: string | null;
  status: string | null;
  age: string | null;
}

export interface CommandStep {
  order: number;
  description: string;
  command: string;
  command_type: 'kubectl' | 'oc' | 'helm' | 'shell';
  is_dry_run: boolean;
  dry_run_command: string | null;
  validation_command: string | null;
}

export interface OperationalRecommendation {
  id: string;
  title: string;
  urgency: 'immediate' | 'short_term' | 'preventive';
  category: 'scale' | 'rollback' | 'restart' | 'config_patch' | 'network' | 'storage';
  commands: CommandStep[];
  rollback_commands: CommandStep[];
  risk_level: 'safe' | 'caution' | 'destructive';
  prerequisites: string[];
  expected_outcome: string;
  resource_refs: ResourceRef[];
}

export type TriageStatus = 'untriaged' | 'acknowledged' | 'mitigated' | 'resolved';

export interface CausalTree {
  id: string;
  root_cause: Finding;
  severity: 'critical' | 'warning' | 'info';
  blast_radius: BlastRadiusData | null;
  cascading_symptoms: Finding[];
  correlated_signals: CorrelatedSignalGroup[];
  operational_recommendations: OperationalRecommendation[];
  triage_status: TriageStatus;
  resource_refs: ResourceRef[];
}

export interface TelescopeResource {
  yaml: string;
  events: K8sEvent[];
  error?: string;
}

export interface TelescopeResourceLogs {
  logs: string;
  error?: string;
}
```

Add `resource_refs` to existing `Finding` interface:
```typescript
export interface Finding {
  // ... existing fields ...
  resource_refs?: ResourceRef[];
}
```

Add `causal_forest` to `V4Findings`:
```typescript
export interface V4Findings {
  // ... existing fields ...
  causal_forest?: CausalTree[];
}
```

**Changes to `api.ts`** — add new methods:

```typescript
export async function getResource(
  sessionId: string, namespace: string, kind: string, name: string
): Promise<TelescopeResource> {
  const resp = await fetch(
    `${API_BASE}/session/${sessionId}/resource/${namespace}/${kind}/${name}`
  );
  if (!resp.ok) throw new Error(`Failed to fetch resource: ${resp.statusText}`);
  return resp.json();
}

export async function getResourceLogs(
  sessionId: string, namespace: string, kind: string, name: string,
  tailLines: number = 500, container?: string,
): Promise<TelescopeResourceLogs> {
  const params = new URLSearchParams({ tail_lines: String(tailLines) });
  if (container) params.set('container', container);
  const resp = await fetch(
    `${API_BASE}/session/${sessionId}/resource/${namespace}/${kind}/${name}/logs?${params}`
  );
  if (!resp.ok) throw new Error(`Failed to fetch logs: ${resp.statusText}`);
  return resp.json();
}

export async function updateTriageStatus(
  sessionId: string, treeId: string, status: TriageStatus,
): Promise<void> {
  const resp = await fetch(
    `${API_BASE}/session/${sessionId}/causal-tree/${treeId}/triage`,
    { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) },
  );
  if (!resp.ok) throw new Error(`Failed to update triage: ${resp.statusText}`);
}
```

**Verification:** `npx tsc --noEmit` passes.

**Commit:** `feat: add War Room v2 TypeScript types and API methods`

---

## Task 8: parseResourceEntities() Utility (Frontend)

**Files:**
- Create: `frontend/src/utils/parseResourceEntities.tsx`

**Context:** Converts `@[kind:namespace/name]` tokens in any text string into clickable `<ResourceEntity>` components. Called everywhere text is rendered: finding cards, causal tree descriptions, recommendations, chat messages, evidence pin claims.

**Changes:**

```tsx
import React from 'react';

// Matches @[kind:namespace/name] or @[kind:name]
const RESOURCE_REF_REGEX = /@\[([a-z_]+):(?:([a-z0-9][a-z0-9._-]*)\/)?([a-z0-9][a-z0-9._-]*)\]/gi;

interface ResourceEntityInlineProps {
  kind: string;
  name: string;
  namespace: string | null;
  onClick?: (kind: string, name: string, namespace: string | null) => void;
}

const KIND_ICONS: Record<string, string> = {
  pod: 'deployed_code',
  deployment: 'layers',
  service: 'router',
  node: 'dns',
  configmap: 'settings',
  pvc: 'storage',
  ingress: 'language',
  route: 'language',
  namespace: 'folder',
  deploymentconfig: 'swap_horiz',
  replicaset: 'layers',
  secret: 'lock',
  statefulset: 'layers',
};

const ResourceEntityInline: React.FC<ResourceEntityInlineProps> = ({ kind, name, namespace, onClick }) => {
  const icon = KIND_ICONS[kind] || 'deployed_code';

  return (
    <button
      type="button"
      onClick={() => onClick?.(kind, name, namespace)}
      className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-cyan-400
                 border-b border-dashed border-cyan-500/40 hover:bg-cyan-950/30
                 hover:border-cyan-400/60 transition-colors cursor-pointer"
      title={`${kind}: ${namespace ? `${namespace}/` : ''}${name}`}
    >
      <span
        className="text-[11px] text-cyan-500/80"
        style={{ fontFamily: 'Material Symbols Outlined' }}
      >
        {icon}
      </span>
      <span className="text-[11px] font-mono">{name}</span>
    </button>
  );
};

/**
 * Parse text containing @[kind:namespace/name] tokens into React elements.
 *
 * @param text - Text to parse (e.g., "Pod @[pod:ns/auth-5b6q] is crashing")
 * @param onEntityClick - Callback when a resource entity is clicked
 * @param defaultNamespace - Fallback namespace for short-form @[kind:name]
 * @returns Array of React nodes (strings and ResourceEntityInline components)
 */
export function parseResourceEntities(
  text: string,
  onEntityClick?: (kind: string, name: string, namespace: string | null) => void,
  defaultNamespace?: string | null,
): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;

  // Reset regex state
  RESOURCE_REF_REGEX.lastIndex = 0;

  let match: RegExpExecArray | null;
  while ((match = RESOURCE_REF_REGEX.exec(text)) !== null) {
    // Add text before match
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const kind = match[1].toLowerCase();
    const namespace = match[2] || defaultNamespace || null;
    const name = match[3];

    nodes.push(
      <ResourceEntityInline
        key={`${kind}-${namespace}-${name}-${match.index}`}
        kind={kind}
        name={name}
        namespace={namespace}
        onClick={onEntityClick}
      />
    );

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes.length > 0 ? nodes : [text];
}
```

**Verification:** `npx tsc --noEmit` passes.

**Commit:** `feat: add parseResourceEntities utility for inline resource references`

---

## Task 9: TelescopeContext + TelescopeDrawer Shell (Frontend)

**Files:**
- Create: `frontend/src/contexts/TelescopeContext.tsx`
- Create: `frontend/src/components/Investigation/TelescopeDrawer.tsx`
- Modify: `frontend/src/components/Investigation/InvestigationView.tsx` (wrap with TelescopeProvider)

**Context:** TelescopeContext wraps the entire 3-column grid AND footer so any component can call `openTelescope()`. The TelescopeDrawer is a fixed right-edge panel (`w-[450px]`, `z-[100]`). This task creates the shell with YAML tab only; LOGS and EVENTS tabs are added in Task 13.

**TelescopeContext:**

```tsx
import React, { createContext, useContext, useState, useCallback } from 'react';

export interface TelescopeTarget {
  kind: string;
  name: string;
  namespace: string;
}

interface TelescopeContextValue {
  isOpen: boolean;
  target: TelescopeTarget | null;
  defaultTab: 'yaml' | 'logs' | 'events';
  breadcrumbs: TelescopeTarget[];
  openTelescope: (target: TelescopeTarget, defaultTab?: 'yaml' | 'logs' | 'events') => void;
  closeTelescope: () => void;
  pushBreadcrumb: (target: TelescopeTarget) => void;
  popBreadcrumb: () => void;
}

const TelescopeCtx = createContext<TelescopeContextValue | null>(null);

export const useTelescopeContext = () => {
  const ctx = useContext(TelescopeCtx);
  if (!ctx) throw new Error('useTelescopeContext must be used within TelescopeProvider');
  return ctx;
};

export const TelescopeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [target, setTarget] = useState<TelescopeTarget | null>(null);
  const [defaultTab, setDefaultTab] = useState<'yaml' | 'logs' | 'events'>('yaml');
  const [breadcrumbs, setBreadcrumbs] = useState<TelescopeTarget[]>([]);

  const openTelescope = useCallback((t: TelescopeTarget, tab: 'yaml' | 'logs' | 'events' = 'yaml') => {
    setTarget(t);
    setDefaultTab(tab);
    setBreadcrumbs([t]);
    setIsOpen(true);
  }, []);

  const closeTelescope = useCallback(() => {
    setIsOpen(false);
    setTarget(null);
    setBreadcrumbs([]);
  }, []);

  const pushBreadcrumb = useCallback((t: TelescopeTarget) => {
    setTarget(t);
    setBreadcrumbs(prev => [...prev, t]);
  }, []);

  const popBreadcrumb = useCallback(() => {
    setBreadcrumbs(prev => {
      if (prev.length <= 1) return prev;
      const next = prev.slice(0, -1);
      setTarget(next[next.length - 1]);
      return next;
    });
  }, []);

  return (
    <TelescopeCtx.Provider value={{ isOpen, target, defaultTab, breadcrumbs, openTelescope, closeTelescope, pushBreadcrumb, popBreadcrumb }}>
      {children}
    </TelescopeCtx.Provider>
  );
};
```

**TelescopeDrawer** — shell with YAML tab, breadcrumb, live state indicator:

```tsx
import React, { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useTelescopeContext } from '../../contexts/TelescopeContext';
import { useChatUI } from '../../contexts/ChatContext';
import { getResource } from '../../services/api';
import type { TelescopeResource } from '../../types';

const TelescopeDrawer: React.FC = () => {
  const { isOpen, target, defaultTab, breadcrumbs, closeTelescope, popBreadcrumb } = useTelescopeContext();
  const { sessionId } = useChatUI();
  const [activeTab, setActiveTab] = useState<'yaml' | 'logs' | 'events'>(defaultTab);
  const [data, setData] = useState<TelescopeResource | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { setActiveTab(defaultTab); }, [defaultTab]);

  useEffect(() => {
    if (!isOpen || !target || !sessionId) return;
    setLoading(true);
    getResource(sessionId, target.namespace, target.kind, target.name)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [isOpen, target, sessionId]);

  if (!isOpen || !target) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ x: 450 }} animate={{ x: 0 }} exit={{ x: 450 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className="fixed right-0 top-0 bottom-0 w-[450px] z-[100] bg-[#0a1a1f] border-l border-slate-700/50 shadow-2xl flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/50">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" title="Viewing real-time cluster state" />
            <span className="text-[10px] font-bold text-slate-300 tracking-wider uppercase">TELESCOPE</span>
          </div>
          <button onClick={closeTelescope} className="p-1 rounded hover:bg-slate-800 transition-colors">
            <span className="material-symbols-outlined text-slate-400 text-[18px]">close</span>
          </button>
        </div>

        {/* Breadcrumbs */}
        <div className="flex items-center gap-1 px-4 py-2 text-[10px] text-slate-400 overflow-x-auto border-b border-slate-800/30">
          {breadcrumbs.map((bc, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span className="text-slate-600">/</span>}
              <button
                onClick={() => { /* popBreadcrumb back to this level */ }}
                className={`hover:text-cyan-400 transition-colors ${i === breadcrumbs.length - 1 ? 'text-cyan-400 font-medium' : ''}`}
              >
                {bc.namespace}/{bc.kind}/{bc.name}
              </button>
            </React.Fragment>
          ))}
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center gap-1 px-4 py-2 border-b border-slate-800/30">
          {(['yaml', 'logs', 'events'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1 rounded text-[10px] font-bold tracking-wider uppercase transition-colors
                ${activeTab === tab
                  ? 'bg-cyan-950/40 text-cyan-400 border border-cyan-700/40'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/40'}`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <span className="text-[10px] text-slate-500 animate-pulse">Loading...</span>
            </div>
          ) : activeTab === 'yaml' ? (
            <YAMLTab yaml={data?.yaml || ''} />
          ) : activeTab === 'logs' ? (
            <div className="p-4 text-[10px] text-slate-500">Click LOGS tab to load</div>
          ) : (
            <EventsTab events={data?.events || []} />
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

// Inline YAMLTab — uses react-syntax-highlighter
const YAMLTab: React.FC<{ yaml: string }> = ({ yaml }) => {
  if (!yaml) return <div className="p-4 text-[10px] text-slate-500">No YAML data</div>;
  return (
    <pre className="text-[10px] font-mono leading-5 p-4 text-slate-300 overflow-auto whitespace-pre-wrap">
      {yaml}
    </pre>
  );
};

// Inline EventsTab
const EventsTab: React.FC<{ events: Array<{ type: string; reason: string; message: string; count: number; last_timestamp: string }> }> = ({ events }) => {
  if (!events.length) return <div className="p-4 text-[10px] text-slate-500">No events</div>;
  return (
    <div className="divide-y divide-slate-800/30">
      {events.map((e, i) => (
        <div key={i} className={`px-4 py-2 ${e.type === 'Warning' ? 'border-l-2 border-amber-500/60' : 'border-l-2 border-slate-700/40'}`}>
          <div className="flex items-center gap-2">
            <span className={`text-[9px] font-bold ${e.type === 'Warning' ? 'text-amber-400' : 'text-slate-500'}`}>{e.reason}</span>
            {e.count > 1 && <span className="text-[9px] text-slate-600">x{e.count}</span>}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">{e.message}</div>
        </div>
      ))}
    </div>
  );
};

export default TelescopeDrawer;
```

**Changes to InvestigationView.tsx** — wrap with TelescopeProvider:

Replace the `<TopologySelectionProvider>` wrapper to also include `TelescopeProvider`:

```tsx
import { TelescopeProvider } from '../../contexts/TelescopeContext';

// In the return — wrap everything (grid + footer) with TelescopeProvider:
<TelescopeProvider>
  <TopologySelectionProvider>
    <div className="grid grid-cols-12 flex-1 overflow-hidden">
      {/* ... columns ... */}
    </div>
  </TopologySelectionProvider>

  {/* TelescopeDrawer v2 (replaces old SurgicalTelescope) */}
  <TelescopeDrawerV2 />

  {/* ... RemediationProgressBar, AttestationGate, ChatDrawer, LedgerTriggerTab ... */}
</TelescopeProvider>
```

**Verification:** `npx tsc --noEmit` passes. Drawer opens on `openTelescope()` call with YAML content.

**Commit:** `feat: add TelescopeContext and TelescopeDrawer shell with YAML/Events tabs`

---

## Task 10: NeuralChart Wrapper Component (Frontend)

**Files:**
- Create: `frontend/src/components/Investigation/charts/NeuralChart.tsx`
- Modify: `frontend/package.json` (add `recharts` dependency)

**Context:** Recharts wrapper with SVG glow filters, War Room tooltip, no dots on lines, deep memoization. Output standard SVG so Tailwind classes apply directly.

**Install:** `npm install recharts`

**NeuralChart Component:**

```tsx
import React, { useMemo } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts';

interface NeuralChartLine {
  dataKey: string;
  color: 'cyan' | 'amber' | 'red' | 'slate';
  label?: string;
}

interface NeuralChartProps {
  data: Array<Record<string, number | string>>;
  lines: NeuralChartLine[];
  height?: number;
  showGrid?: boolean;
  thresholdValue?: number;
  xAxisKey?: string;
}

const COLOR_MAP: Record<string, string> = {
  cyan: '#07b6d5',
  amber: '#f59e0b',
  red: '#ef4444',
  slate: '#64748b',
};

const GLOW_FILTER_ID = 'neural-glow';

const WarRoomTooltip: React.FC<{ active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }> = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#0f2023]/95 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 shadow-xl">
      <div className="text-[9px] text-slate-500 font-mono mb-1">{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2 text-[10px] font-mono">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-slate-400">{p.name}:</span>
          <span className="text-slate-200 font-medium">{typeof p.value === 'number' ? p.value.toFixed(2) : p.value}</span>
        </div>
      ))}
    </div>
  );
};

const NeuralChart: React.FC<NeuralChartProps> = React.memo(({
  data,
  lines,
  height = 120,
  showGrid = true,
  thresholdValue,
  xAxisKey = 'timestamp',
}) => {
  // Deep memoize data to prevent SVG filter repainting
  const stableData = useMemo(() => data, [JSON.stringify(data)]);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={stableData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        {/* SVG glow filter */}
        <defs>
          <filter id={GLOW_FILTER_ID} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {showGrid && (
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.15)" />
        )}

        <XAxis
          dataKey={xAxisKey}
          tick={{ fontSize: 9, fill: '#64748b' }}
          axisLine={{ stroke: '#334155' }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 9, fill: '#64748b' }}
          axisLine={{ stroke: '#334155' }}
          tickLine={false}
          width={40}
        />

        <Tooltip content={<WarRoomTooltip />} />

        {thresholdValue !== undefined && (
          <ReferenceLine
            y={thresholdValue}
            stroke="#f59e0b"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
        )}

        {lines.map(line => (
          <Line
            key={line.dataKey}
            type="monotone"
            dataKey={line.dataKey}
            stroke={COLOR_MAP[line.color]}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 3, fill: COLOR_MAP[line.color] }}
            name={line.label || line.dataKey}
            filter={`url(#${GLOW_FILTER_ID})`}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
});

NeuralChart.displayName = 'NeuralChart';

export default NeuralChart;
```

**Verification:** `npx tsc --noEmit` passes. Component renders without errors.

**Commit:** `feat: add NeuralChart Recharts wrapper with SVG glow filters`

---

## Task 11: CausalForestView Component (Frontend)

**Files:**
- Create: `frontend/src/components/Investigation/CausalForestView.tsx`
- Create: `frontend/src/components/Investigation/cards/CausalTreeCard.tsx`

**Context:** Center column renders each `CausalTree` as an independent, collapsible card. Color-coded severity border, blast radius badge, expandable tree of root → cascading symptoms, triage toggle, attached operational recommendations. All resource names rendered via `parseResourceEntities()`.

**CausalTreeCard:**

```tsx
import React, { useState, useCallback } from 'react';
import type { CausalTree, TriageStatus } from '../../../types';
import { updateTriageStatus } from '../../../services/api';
import { parseResourceEntities } from '../../../utils/parseResourceEntities';
import { useTelescopeContext } from '../../../contexts/TelescopeContext';
import CausalRoleBadge from './CausalRoleBadge';

interface CausalTreeCardProps {
  tree: CausalTree;
  sessionId: string;
  onTriageUpdate?: (treeId: string, status: TriageStatus) => void;
}

const SEVERITY_BORDER: Record<string, string> = {
  critical: 'border-l-red-500',
  warning: 'border-l-amber-500',
  info: 'border-l-slate-500',
};

const TRIAGE_SEQUENCE: TriageStatus[] = ['untriaged', 'acknowledged', 'mitigated', 'resolved'];
const TRIAGE_COLORS: Record<TriageStatus, string> = {
  untriaged: 'text-red-400 bg-red-950/30',
  acknowledged: 'text-amber-400 bg-amber-950/30',
  mitigated: 'text-cyan-400 bg-cyan-950/30',
  resolved: 'text-emerald-400 bg-emerald-950/30',
};

const CausalTreeCard: React.FC<CausalTreeCardProps> = ({ tree, sessionId, onTriageUpdate }) => {
  const [expanded, setExpanded] = useState(true);
  const [triage, setTriage] = useState<TriageStatus>(tree.triage_status);
  const { openTelescope } = useTelescopeContext();

  const handleEntityClick = useCallback((kind: string, name: string, namespace: string | null) => {
    openTelescope({ kind, name, namespace: namespace || 'default' });
  }, [openTelescope]);

  const cycleTriage = useCallback(async () => {
    const currentIdx = TRIAGE_SEQUENCE.indexOf(triage);
    const nextStatus = TRIAGE_SEQUENCE[(currentIdx + 1) % TRIAGE_SEQUENCE.length];
    setTriage(nextStatus);
    onTriageUpdate?.(tree.id, nextStatus);
    try {
      await updateTriageStatus(sessionId, tree.id, nextStatus);
    } catch { /* optimistic update, revert on failure if needed */ }
  }, [triage, tree.id, sessionId, onTriageUpdate]);

  const blastCount = tree.blast_radius
    ? (tree.blast_radius.upstream_affected?.length || 0) + (tree.blast_radius.downstream_affected?.length || 0)
    : 0;

  return (
    <div className={`rounded-lg border border-slate-800/50 border-l-[3px] ${SEVERITY_BORDER[tree.severity]} bg-slate-900/30`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="material-symbols-outlined text-[16px] text-slate-500">{expanded ? 'expand_more' : 'chevron_right'}</span>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] font-medium text-slate-200 truncate">
              {parseResourceEntities(tree.root_cause.summary, handleEntityClick)}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {blastCount > 0 && (
            <span className="text-[9px] text-amber-400 bg-amber-950/30 px-1.5 py-0.5 rounded font-mono">
              {blastCount} affected
            </span>
          )}
          <button onClick={(e) => { e.stopPropagation(); cycleTriage(); }} className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${TRIAGE_COLORS[triage]}`}>
            {triage}
          </button>
        </div>
      </div>

      {/* Expandable body */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Root cause details */}
          <div className="text-[10px] text-slate-400">
            {parseResourceEntities(tree.root_cause.description || tree.root_cause.summary, handleEntityClick)}
          </div>

          {/* Cascading symptoms */}
          {tree.cascading_symptoms.length > 0 && (
            <div className="space-y-1">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Cascading Symptoms</span>
              {tree.cascading_symptoms.map((s, i) => (
                <div key={i} className="flex items-start gap-2 pl-3 border-l border-slate-700/40">
                  <CausalRoleBadge role="cascading_failure" />
                  <span className="text-[10px] text-slate-400">
                    {parseResourceEntities(s.summary, handleEntityClick)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Operational recommendations rendered here — Task 12 will add */}
          {tree.operational_recommendations.length > 0 && (
            <div className="text-[9px] text-slate-500">
              {tree.operational_recommendations.length} recommendation(s) — render in Task 12
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CausalTreeCard;
```

**CausalForestView:**

```tsx
import React from 'react';
import type { CausalTree, TriageStatus } from '../../types';
import CausalTreeCard from './cards/CausalTreeCard';

interface CausalForestViewProps {
  forest: CausalTree[];
  sessionId: string;
  onTriageUpdate?: (treeId: string, status: TriageStatus) => void;
}

const CausalForestView: React.FC<CausalForestViewProps> = ({ forest, sessionId, onTriageUpdate }) => {
  if (!forest.length) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-4">
        <span className="material-symbols-outlined text-[16px] text-cyan-500">account_tree</span>
        <span className="text-[10px] font-black text-slate-300 tracking-[0.1em] uppercase">Causal Forest</span>
        <span className="text-[9px] text-slate-500 font-mono">{forest.length} root cause{forest.length !== 1 ? 's' : ''}</span>
      </div>
      {forest.map(tree => (
        <CausalTreeCard key={tree.id} tree={tree} sessionId={sessionId} onTriageUpdate={onTriageUpdate} />
      ))}
    </div>
  );
};

export default CausalForestView;
```

**Verification:** `npx tsc --noEmit` passes.

**Commit:** `feat: add CausalForestView and CausalTreeCard components`

---

## Task 12: Operational Recommendation Cards (Frontend)

**Files:**
- Create: `frontend/src/components/Investigation/cards/RecommendationCard.tsx`
- Modify: `frontend/src/components/Investigation/cards/CausalTreeCard.tsx` (replace placeholder)

**Context:** Nested inside each CausalTreeCard. Urgency badge, risk indicator, command blocks with one-click copy, dry-run toggle, rollback section, validation command. Placeholder UX: `<...>` syntax detected via regex, rendered as pulsing text block.

**RecommendationCard:**

Key features:
- Urgency badge (red IMMEDIATE, amber SHORT TERM, slate PREVENTIVE)
- Risk indicator (green SAFE, amber CAUTION, red DESTRUCTIVE)
- Command blocks with monospace font and copy button
- Dry-run toggle showing `--dry-run=client -o yaml` variant
- Collapsible rollback section
- `<...>` placeholder detection with pulsing amber highlight
- Validation command section

**Changes to CausalTreeCard.tsx:** Replace the placeholder comment with:

```tsx
import RecommendationCard from './RecommendationCard';

// In expanded section, replace the placeholder:
{tree.operational_recommendations.map(rec => (
  <RecommendationCard key={rec.id} recommendation={rec} />
))}
```

**Verification:** `npx tsc --noEmit` passes.

**Commit:** `feat: add RecommendationCard with copy-paste commands and placeholder detection`

---

## Task 13: TelescopeDrawer LOGS Tab — LogViewerTab (Frontend)

**Files:**
- Create: `frontend/src/components/Investigation/telescope/LogViewerTab.tsx`
- Modify: `frontend/src/components/Investigation/TelescopeDrawer.tsx` (integrate LOGS tab)

**Context:** The LOGS tab is lazily loaded — logs API call only fires when user clicks LOGS tab. Features: severity color-coding, JSON unpacking with `[+]` expander, sticky filter bar, auto-scroll with human override (`onWheel`), virtualization via `react-window` if > 5,000 lines.

**Install:** `npm install react-window` (already in package.json per exploration)

**LogViewerTab:**

Key features:
- Severity parsing: ERROR = red bg + left border, WARN = amber text, INFO/DEBUG = ghosted slate
- JSON detection: lines starting with `{` → `[+]` expander → inline pretty-print
- Sticky filter bar: regex search, severity toggles, auto-scroll toggle
- Auto-scroll disengages on `onWheel` (Human Override)
- Uses `getResourceLogs()` API call on mount
- Virtualized rendering via react-window FixedSizeList when lines > 5000

**Changes to TelescopeDrawer.tsx:**

Replace the LOGS tab placeholder:
```tsx
import LogViewerTab from './telescope/LogViewerTab';

// In content section:
activeTab === 'logs' ? (
  <LogViewerTab
    namespace={target.namespace}
    kind={target.kind}
    name={target.name}
    sessionId={sessionId}
  />
) : ...
```

**Verification:** `npx tsc --noEmit` passes. LOGS tab loads logs on click, not on drawer open.

**Commit:** `feat: add LogViewerTab with severity coloring, JSON unpacking, and virtualization`

---

## Task 14: NeuralChart Integration Points (Frontend)

**Files:**
- Modify: `frontend/src/components/Investigation/Navigator.tsx` (metric anomaly cards)
- Modify: `frontend/src/components/Investigation/cards/CausalTreeCard.tsx` (correlated signals)

**Context:** Integrate NeuralChart into two key locations where time-series data is available. The Navigator column shows metric anomaly charts at 80px height. The CausalTreeCard shows correlated signal overlays at 80px.

**Changes to Navigator.tsx:**

In the metrics validation dock section, replace sparkline display with NeuralChart for metric anomalies that have time_series_data:

```tsx
import NeuralChart from './charts/NeuralChart';

// In metric anomaly rendering:
{findings?.time_series_data?.[anomaly.metric_name] && (
  <NeuralChart
    height={80}
    data={findings.time_series_data[anomaly.metric_name].map(p => ({
      timestamp: new Date(p.timestamp).toLocaleTimeString(),
      value: p.value,
    }))}
    lines={[{ dataKey: 'value', color: anomaly.severity === 'critical' ? 'red' : 'amber' }]}
    showGrid={false}
  />
)}
```

**Changes to CausalTreeCard.tsx:**

After cascading symptoms, render correlated signals with NeuralChart if time_series is available:

```tsx
{tree.correlated_signals.length > 0 && (
  <div className="space-y-1">
    <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Correlated Signals</span>
    {tree.correlated_signals.map((sig, i) => (
      <div key={i} className="text-[10px] text-slate-400">
        <span className="text-cyan-400">{sig.group_name}</span>: {sig.narrative}
      </div>
    ))}
  </div>
)}
```

**Verification:** `npx tsc --noEmit` passes.

**Commit:** `feat: integrate NeuralChart into Navigator metrics and CausalTree signals`

---

## Task 15: Layout Pivot + End-to-End Wiring (Frontend)

**Files:**
- Modify: `frontend/src/components/Investigation/InvestigationView.tsx`
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx`
- Modify: `frontend/src/index.css` (new animations for Telescope, Causal Forest)

**Context:** Final wiring. The Causal Forest occupies the center column (col-5). EvidenceFindings renders CausalForestView at the top when `causal_forest` data is available. TelescopeProvider wraps the entire layout including footer. Z-index layering: TelescopeDrawer at z-100, CommandBar (footer) at z-50 or lower.

**Changes to InvestigationView.tsx:**

1. Import `TelescopeProvider` and new `TelescopeDrawer`:
```tsx
import { TelescopeProvider } from '../../contexts/TelescopeContext';
import TelescopeDrawerV2 from './TelescopeDrawer';
```

2. Wrap entire return with `<TelescopeProvider>` (including footer/chat):
```tsx
return (
  <TelescopeProvider>
    <div className="flex flex-col h-full">
      {/* ... error banner, freshness ... */}
      <TopologySelectionProvider>
        <div className="grid grid-cols-12 flex-1 overflow-hidden">
          {/* Left col-3, Center col-5, Right col-4 — unchanged */}
        </div>
      </TopologySelectionProvider>

      <TelescopeDrawerV2 />

      <RemediationProgressBar ... />
      {/* ... rest ... */}
      <ChatDrawer />
      <LedgerTriggerTab />
    </div>
  </TelescopeProvider>
);
```

3. Remove old `<SurgicalTelescope />` import and render (the old one was for code diffs).

**Changes to EvidenceFindings.tsx:**

At the top of the scrollable evidence stack, render CausalForestView when data is available:

```tsx
import CausalForestView from './CausalForestView';

// In the render, above error patterns:
{findings?.causal_forest && findings.causal_forest.length > 0 && (
  <CausalForestView forest={findings.causal_forest} sessionId={sessionId} />
)}
```

**Changes to index.css:**

Add telescope slide animation and causal tree severity animations:

```css
/* Telescope drawer backdrop */
.telescope-backdrop {
  backdrop-filter: blur(4px);
}

/* Causal tree severity glow */
@keyframes severity-glow-red {
  0%, 100% { box-shadow: inset 3px 0 8px -4px rgba(239, 68, 68, 0.3); }
  50% { box-shadow: inset 3px 0 12px -4px rgba(239, 68, 68, 0.5); }
}

.animate-severity-glow-red {
  animation: severity-glow-red 3s ease-in-out infinite;
}
```

**Verification:**
1. `npx tsc --noEmit` — no TypeScript errors
2. `cd backend && python3 -m pytest --tb=short -q` — all tests pass
3. Manual: CausalForest renders in center column when data exists
4. Manual: Click ResourceEntity → TelescopeDrawer opens from right at z-100
5. Manual: LOGS tab → lazy-loads logs on click
6. Manual: Triage toggle cycles through statuses

**Commit:** `feat: layout pivot, end-to-end wiring, z-index layering for War Room v2`

---

## Verification Checklist

After all 15 tasks:

1. `cd backend && python3 -m pytest --tb=short -q` — all tests pass (existing + new model, parser, LTTB, endpoint tests)
2. `cd frontend && npx tsc --noEmit` — no TypeScript errors
3. Manual: Start investigation → Causal Forest renders with severity-coded cards
4. Manual: Click triage toggle → cycles untriaged → acknowledged → mitigated → resolved
5. Manual: Click resource name in finding → TelescopeDrawer opens with YAML
6. Manual: Switch to LOGS tab → logs lazy-loaded, severity color-coded
7. Manual: Switch to EVENTS tab → grouped by reason
8. Manual: Operational recommendations → copy button works, dry-run toggle works
9. Manual: `<PREVIOUS_TAG>` placeholder → renders as pulsing amber block
10. Manual: NeuralChart in Navigator → SVG glow, no dots, tooltip on hover
11. Manual: Breadcrumb in Telescope → click resource inside YAML → pushes breadcrumb

---

## Dependency Graph

```
Task 1: Data Models ──────────────────────┐
Task 2: Resource Ref Parser ──────────────┤
Task 3: LTTB Utility ────────────────┐    │
                                     │    │
Task 4: Resource API Endpoints ──────┤    │
Task 5: LTTB Integration ───────────-┘    │
Task 6: V4Findings Enhancement ──────────-┘
                                     │
Task 7: Frontend Types + API ────────┤
Task 8: parseResourceEntities ───────┤
                                     │
Task 9: TelescopeContext + Drawer ───┤
Task 10: NeuralChart Wrapper ────────┤
                                     │
Task 11: CausalForestView ──────────-┤
Task 12: RecommendationCard ─────────┤
Task 13: LogViewerTab ───────────────┤
Task 14: NeuralChart Integration ────┤
                                     │
Task 15: Layout Pivot + Wiring ──────┘
```

Tasks 1-6 (backend) can proceed sequentially. Tasks 7-10 (frontend foundation) can proceed after Task 6. Tasks 11-14 (frontend features) depend on 7-10. Task 15 (final wiring) depends on everything.
