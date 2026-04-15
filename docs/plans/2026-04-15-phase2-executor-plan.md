# Phase 2 — Orchestrator + WorkflowExecutor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a flag-gated, deterministic workflow execution layer that runs static DAGs of Phase-1 agent contracts, persists runs, and streams events over SSE. No change to existing investigation flow.

**Architecture:** Three layers — `ContractRegistry` (Phase 1, pure metadata) → `WorkflowExecutor` (Phase 2, scheduler + state) → `AgentRunnerRegistry` (Phase 2, name+version → callable). REST at `/api/v4/workflows*` and `/api/v4/runs*`, all gated by `WORKFLOWS_ENABLED` (default OFF). SQLite persistence for workflows, versions, runs, step-runs, events.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, jsonschema, `asyncio`, SQLite (stdlib). SSE via `sse-starlette` (add to requirements).

**Design source:** `docs/plans/2026-04-15-phase2-executor-design.md` — READ BEFORE STARTING.

---

## Ground rules (apply to every task)

- TDD: every task is failing test → minimal impl → passing test → commit.
- Imports: use `src.*` (never `backend.src.*`) — locked in Phase 1 fix.
- All code under `backend/src/workflows/` except the API router (`backend/src/api/routes_workflows.py`) and runner-side adapters.
- Every new route in `routes_workflows.py` uses `Depends(require_workflows_flag)` (parallel to Phase 1's `require_flag`).
- **Non-impact invariants (verify before every commit that touches backend):**
  - `git diff main..HEAD -- backend/src/agents/supervisor.py` empty.
  - `git diff main..HEAD -- backend/src/api/routes_v4.py` empty.
  - `git diff main..HEAD -- backend/src/models/schemas.py` empty.
  - `git diff main..HEAD -- frontend/src/components/Investigation/` empty.

---

## Task 0: Branch bookkeeping + dependency prep

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: Confirm branch**

```bash
git rev-parse --abbrev-ref HEAD
```
Expected: `feature/phase2-executor`.

**Step 2: Add SSE dependency**

Append to `backend/requirements.txt`:
```
sse-starlette>=2.0
```

**Step 3: Install**

```bash
pip3 install --break-system-packages 'sse-starlette>=2.0'
```

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore(phase2): add sse-starlette dependency"
```

---

## Task 1: Feature flag `WORKFLOWS_ENABLED`

**Files:**
- Modify: `backend/src/config.py`
- Create: `backend/tests/test_workflows_feature_flag.py`

**Step 1: Failing test**

```python
# backend/tests/test_workflows_feature_flag.py
from importlib import reload


def test_workflows_flag_default_off():
    from src.config import settings
    assert settings.WORKFLOWS_ENABLED is False


def test_workflows_flag_respects_env(monkeypatch):
    monkeypatch.setenv("WORKFLOWS_ENABLED", "true")
    from src import config
    reload(config)
    assert config.settings.WORKFLOWS_ENABLED is True
    monkeypatch.delenv("WORKFLOWS_ENABLED", raising=False)
    reload(config)
```

**Step 2: Run — expect FAIL** (`AttributeError: WORKFLOWS_ENABLED`).

```bash
python3 -m pytest backend/tests/test_workflows_feature_flag.py -v
```

**Step 3: Implement**

In `backend/src/config.py`, add to the `Settings` class:
```python
WORKFLOWS_ENABLED: bool = Field(default=False, description="Phase 2: expose /v4/workflows* endpoints")
```

**Step 4: Run — expect PASS.**

**Step 5: Commit**

```bash
git add backend/src/config.py backend/tests/test_workflows_feature_flag.py
git commit -m "feat(config): add WORKFLOWS_ENABLED flag (default off)"
```

---

## Task 2: Pydantic DAG models (authored form)

**Files:**
- Create: `backend/src/workflows/__init__.py` (empty)
- Create: `backend/src/workflows/models.py`
- Create: `backend/tests/test_workflow_models.py`

**Step 1: Failing tests** (write ~6 tests covering):

- `Ref` accepts `{"from": "input", "path": "service"}`; rejects unknown `from`.
- `Ref` accepts `{"from": "node", "node_id": "a", "path": "output.x"}`; rejects when `from=node` without `node_id`.
- `Transform` accepts every op in the frozen set (`coalesce, concat, eq, in, exists, and, or, not`); rejects `"custom_op"`.
- `StepSpec` requires `id`, `agent`, `agent_version`; `on_failure` defaults to `"fail"`; rejects unknown `on_failure`.
- `StepSpec.id` matches `^[a-z][a-z0-9_]*$`.
- `WorkflowDag` rejects duplicate step ids.

**Step 2: Run — expect FAIL** (module doesn't exist).

**Step 3: Implement `models.py`**

```python
from __future__ import annotations
from typing import Any, Literal, Union
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FROZEN_OPS = {"coalesce", "concat", "eq", "in", "exists", "and", "or", "not"}
STEP_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class RefNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: Literal["node"] = Field(alias="from")
    node_id: str
    path: str


class RefInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: Literal["input"] = Field(alias="from")
    path: str


class RefEnv(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_: Literal["env"] = Field(alias="from")
    path: str


Ref = Union[RefNode, RefInput, RefEnv]


class Literal_(BaseModel):
    model_config = ConfigDict(extra="forbid")
    literal: Any


class Transform(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str
    args: list[Any]

    @field_validator("op")
    @classmethod
    def _op_in_frozen(cls, v: str) -> str:
        if v not in FROZEN_OPS:
            raise ValueError(f"unknown op {v!r}; allowed: {sorted(FROZEN_OPS)}")
        return v


Expr = Union[dict, Literal_, Transform]  # ref dict, literal, or transform


class StepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    agent: str
    agent_version: int | Literal["latest"] = "latest"
    inputs: dict[str, Any] = Field(default_factory=dict)
    when: dict | None = None
    on_failure: Literal["fail", "continue", "fallback"] = "fail"
    fallback_step_id: str | None = None
    parallel_group: str | None = None
    concurrency_group: str | None = None
    timeout_seconds_override: float | None = None
    retry_on_override: list[str] | None = None

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not STEP_ID_RE.match(v):
            raise ValueError(f"invalid step id {v!r}")
        return v

    @model_validator(mode="after")
    def _fallback_requires_id(self) -> "StepSpec":
        if self.on_failure == "fallback" and not self.fallback_step_id:
            raise ValueError("on_failure='fallback' requires fallback_step_id")
        return self


class WorkflowDag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs_schema: dict = Field(default_factory=lambda: {"type": "object"})
    steps: list[StepSpec]

    @model_validator(mode="after")
    def _unique_ids(self) -> "WorkflowDag":
        ids = [s.id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step ids")
        return self
```

**Step 4: Run — expect PASS.**

**Step 5: Commit**

```bash
git add backend/src/workflows/__init__.py backend/src/workflows/models.py backend/tests/test_workflow_models.py
git commit -m "feat(workflows): Pydantic models for DAG + frozen transform ops"
```

---

## Task 3: Ref/transform AST evaluator

**Files:**
- Create: `backend/src/workflows/evaluator.py`
- Create: `backend/tests/test_workflow_evaluator.py`

**Purpose:** Given a compiled mapping AST + a state dict (`{"input": {...}, "nodes": {id: {"status": ..., "output": ...}}}`), produce resolved Python values. Raises `SkippedRefError` if ref targets a SKIPPED node; raises `MissingRefError` if node not yet present or path missing.

**Step 1: Tests**

- resolves `{"literal": 7}` → `7`.
- resolves `{"ref": {"from": "input", "path": "x.y"}}` against `{"input": {"x": {"y": 42}}}` → `42`.
- resolves `{"ref": {"from": "node", "node_id": "a", "path": "output.svc"}}` → value.
- raises `SkippedRefError` when node status is SKIPPED.
- raises `MissingRefError` when node missing or path missing.
- `coalesce(null_ref, literal("def"))` → `"def"`.
- `eq(literal(1), literal(1))` → `True`.
- `and(eq(...), not(...))` works.

**Step 2: Implement**

```python
from __future__ import annotations
from typing import Any


class SkippedRefError(Exception): ...
class MissingRefError(Exception): ...


def _get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise MissingRefError(f"missing path segment {part!r}")
            cur = cur[part]
        elif isinstance(cur, list):
            cur = cur[int(part)]
        else:
            raise MissingRefError(f"cannot descend into {type(cur).__name__} at {part!r}")
    return cur


def evaluate(expr: Any, state: dict) -> Any:
    if isinstance(expr, dict) and "literal" in expr:
        return expr["literal"]
    if isinstance(expr, dict) and "ref" in expr:
        r = expr["ref"]
        src = r["from"]
        if src == "input":
            return _get_path(state.get("input", {}), r["path"])
        if src == "env":
            return _get_path(state.get("env", {}), r["path"])
        if src == "node":
            node_id = r["node_id"]
            nodes = state.get("nodes", {})
            if node_id not in nodes:
                raise MissingRefError(f"node {node_id!r} has not run")
            node = nodes[node_id]
            if node.get("status") == "SKIPPED":
                raise SkippedRefError(f"node {node_id!r} was skipped")
            if node.get("status") != "SUCCESS":
                raise MissingRefError(f"node {node_id!r} status={node.get('status')}")
            return _get_path({"output": node.get("output")}, r["path"])
    if isinstance(expr, dict) and "op" in expr:
        op = expr["op"]
        args = expr["args"]
        if op == "coalesce":
            for a in args:
                try:
                    v = evaluate(a, state)
                    if v is not None:
                        return v
                except (MissingRefError, SkippedRefError):
                    continue
            return None
        if op == "concat":
            return "".join(str(evaluate(a, state)) for a in args)
        if op == "eq":
            return evaluate(args[0], state) == evaluate(args[1], state)
        if op == "in":
            return evaluate(args[0], state) in evaluate(args[1], state)
        if op == "exists":
            try:
                evaluate(args[0], state)
                return True
            except (MissingRefError, SkippedRefError):
                return False
        if op == "and":
            return all(evaluate(a, state) for a in args)
        if op == "or":
            return any(evaluate(a, state) for a in args)
        if op == "not":
            return not evaluate(args[0], state)
        raise ValueError(f"unknown op {op}")
    # dict of resolved mapping (step.inputs leaf case)
    if isinstance(expr, dict):
        return {k: evaluate(v, state) for k, v in expr.items()}
    # list → resolve each
    if isinstance(expr, list):
        return [evaluate(x, state) for x in expr]
    # anything else passed through (shouldn't happen with well-formed AST)
    return expr
```

**Step 3–5:** Run tests → pass → commit.

```bash
git add backend/src/workflows/evaluator.py backend/tests/test_workflow_evaluator.py
git commit -m "feat(workflows): ref/transform AST evaluator with skip/missing semantics"
```

---

## Task 4: Compiler (save-time validation)

**Files:**
- Create: `backend/src/workflows/compiler.py`
- Create: `backend/tests/test_workflow_compiler.py`

**Purpose:** Given a `WorkflowDag` + `ContractRegistry`, produce a `CompiledWorkflow` (topo order, resolved `agent_version`, validated refs against upstream output schemas, cycle detection). Raises `CompileError` with precise paths.

**Step 1: Tests**

- Happy-path 3-step linear DAG compiles; `topo_order == ["a", "b", "c"]`.
- Cycle rejected.
- Unknown `agent` rejected with step id in message.
- `agent_version` override loosening timeout (`timeout_seconds_override > contract.timeout_seconds`) rejected.
- `retry_on_override` not subset of contract → rejected.
- Ref to nonexistent node id → rejected.
- Ref to downstream node (breaks topo) → rejected.
- Ref path missing from upstream's output schema → rejected.
- `"latest"` → highest non-deprecated version.
- `on_failure=fallback` without matching `fallback_step_id` → rejected (already in model, but end-to-end check).
- Fallback dependency-subset rule: fallback step's refs must be subset of primary's.
- `MAX_TOTAL_STEPS_PER_RUN` (env, default 200) enforced.

**Step 2: Implement**

```python
from __future__ import annotations
from dataclasses import dataclass, field
import os
from typing import Any
import jsonschema

from src.contracts.registry import ContractRegistry
from src.workflows.models import WorkflowDag, StepSpec, FROZEN_OPS


class CompileError(ValueError):
    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path


@dataclass
class CompiledStep:
    id: str
    agent: str
    agent_version: int
    inputs: dict  # raw AST, already reference-validated
    when: dict | None
    on_failure: str
    fallback_step_id: str | None
    parallel_group: str | None
    concurrency_group: str | None
    timeout_seconds: float
    retry_on: list[str]
    upstream_ids: list[str]


@dataclass
class CompiledWorkflow:
    topo_order: list[str]
    steps: dict[str, CompiledStep]
    inputs_schema: dict


def _extract_ref_paths(expr: Any, acc: list[tuple[str, Any]]) -> None:
    """Recursively collect ('ref'|'op'|'literal', value) refs."""
    if isinstance(expr, dict):
        if "ref" in expr:
            acc.append(("ref", expr["ref"]))
        elif "op" in expr:
            for a in expr.get("args", []):
                _extract_ref_paths(a, acc)
        elif "literal" in expr:
            pass
        else:
            for v in expr.values():
                _extract_ref_paths(v, acc)
    elif isinstance(expr, list):
        for v in expr:
            _extract_ref_paths(v, acc)


def _path_exists_in_schema(schema: dict, path: str) -> bool:
    """Best-effort: walk JSON-Schema `properties` and `items` along dotted path."""
    cur = schema
    for part in path.split("."):
        if cur.get("type") == "object" and "properties" in cur:
            props = cur["properties"]
            if part not in props:
                return False
            cur = props[part]
        elif cur.get("type") == "array" and "items" in cur:
            cur = cur["items"]
        else:
            # Unknown / permissive schema → accept
            return True
    return True


def compile_dag(dag: WorkflowDag, contracts: ContractRegistry) -> CompiledWorkflow:
    max_steps = int(os.environ.get("MAX_TOTAL_STEPS_PER_RUN", "200"))
    if len(dag.steps) > max_steps:
        raise CompileError("steps", f"exceeds MAX_TOTAL_STEPS_PER_RUN ({max_steps})")

    # 1. Resolve agent versions; validate contract + override rules
    resolved: dict[str, CompiledStep] = {}
    for s in dag.steps:
        # Resolve version
        if s.agent_version == "latest":
            candidates = [c for c in contracts.list_all_versions() if c.name == s.agent]
            if not candidates:
                raise CompileError(f"steps.{s.id}.agent", f"agent {s.agent!r} not in contract registry")
            active = [c for c in candidates if c.version not in (c.deprecated_versions or [])]
            if not active:
                raise CompileError(f"steps.{s.id}.agent_version", "no active versions")
            contract = max(active, key=lambda c: c.version)
        else:
            try:
                contract = contracts.get(s.agent, version=int(s.agent_version))
            except KeyError:
                raise CompileError(
                    f"steps.{s.id}.agent_version",
                    f"agent {s.agent!r} v{s.agent_version} not found",
                )

        # Timeout override must not loosen
        timeout = contract.timeout_seconds
        if s.timeout_seconds_override is not None:
            if s.timeout_seconds_override > contract.timeout_seconds:
                raise CompileError(
                    f"steps.{s.id}.timeout_seconds_override",
                    f"cannot exceed contract timeout {contract.timeout_seconds}",
                )
            timeout = s.timeout_seconds_override

        # Retry override must be subset
        retry = list(contract.retry_on)
        if s.retry_on_override is not None:
            if not set(s.retry_on_override).issubset(set(contract.retry_on)):
                raise CompileError(
                    f"steps.{s.id}.retry_on_override",
                    "must be subset of contract retry_on",
                )
            retry = s.retry_on_override

        resolved[s.id] = CompiledStep(
            id=s.id, agent=s.agent, agent_version=contract.version,
            inputs=s.inputs, when=s.when, on_failure=s.on_failure,
            fallback_step_id=s.fallback_step_id,
            parallel_group=s.parallel_group, concurrency_group=s.concurrency_group,
            timeout_seconds=timeout, retry_on=retry, upstream_ids=[],
        )

    # 2. Collect upstream dependencies from refs + predicates
    for step_id, cs in resolved.items():
        refs: list[tuple[str, Any]] = []
        _extract_ref_paths(cs.inputs, refs)
        if cs.when is not None:
            _extract_ref_paths(cs.when, refs)
        for kind, r in refs:
            if kind == "ref" and r.get("from") == "node":
                nid = r["node_id"]
                if nid not in resolved:
                    raise CompileError(f"steps.{step_id}", f"ref to unknown node {nid!r}")
                if nid == step_id:
                    raise CompileError(f"steps.{step_id}", "self-reference")
                if nid not in cs.upstream_ids:
                    cs.upstream_ids.append(nid)

    # 3. Topo sort (Kahn's)
    in_deg = {sid: 0 for sid in resolved}
    out_edges: dict[str, list[str]] = {sid: [] for sid in resolved}
    for sid, cs in resolved.items():
        for up in cs.upstream_ids:
            in_deg[sid] += 1
            out_edges[up].append(sid)
    ready = [sid for sid, d in in_deg.items() if d == 0]
    order: list[str] = []
    while ready:
        ready.sort()
        sid = ready.pop(0)
        order.append(sid)
        for nxt in out_edges[sid]:
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(resolved):
        raise CompileError("steps", "cycle detected")

    # 4. Validate ref paths against upstream output schemas
    for sid in order:
        cs = resolved[sid]
        refs: list[tuple[str, Any]] = []
        _extract_ref_paths(cs.inputs, refs)
        for kind, r in refs:
            if kind != "ref":
                continue
            if r.get("from") == "input":
                if not _path_exists_in_schema(dag.inputs_schema, r["path"]):
                    raise CompileError(
                        f"steps.{sid}.inputs", f"input path {r['path']!r} not in inputs_schema",
                    )
            elif r.get("from") == "node":
                up = resolved[r["node_id"]]
                contract = contracts.get(up.agent, version=up.agent_version)
                # path must start with "output" or "output.*"
                if not r["path"].startswith("output"):
                    raise CompileError(
                        f"steps.{sid}.inputs",
                        f"ref path must start with 'output' (got {r['path']!r})",
                    )
                sub = r["path"][len("output"):].lstrip(".")
                if sub and not _path_exists_in_schema(contract.output_schema, sub):
                    raise CompileError(
                        f"steps.{sid}.inputs",
                        f"path {r['path']!r} not in {up.agent} v{up.agent_version} output schema",
                    )

    # 5. Fallback rules
    for sid, cs in resolved.items():
        if cs.on_failure == "fallback":
            fb_id = cs.fallback_step_id
            if fb_id not in resolved:
                raise CompileError(f"steps.{sid}.fallback_step_id", "target not in DAG")
            fb = resolved[fb_id]
            if not set(fb.upstream_ids).issubset(set(cs.upstream_ids)):
                raise CompileError(
                    f"steps.{sid}.fallback_step_id",
                    "fallback's upstream deps must be subset of primary's",
                )

    return CompiledWorkflow(topo_order=order, steps=resolved, inputs_schema=dag.inputs_schema)
```

**Step 3–5:** Tests → pass → commit.

```bash
git add backend/src/workflows/compiler.py backend/tests/test_workflow_compiler.py
git commit -m "feat(workflows): compiler with topo + schema-aware ref validation"
```

---

## Task 5: AgentRunnerRegistry + integrity check

**Files:**
- Create: `backend/src/workflows/runners/__init__.py`
- Create: `backend/src/workflows/runners/registry.py`
- Create: `backend/tests/test_runner_registry.py`

**Step 1: Tests**

- `AgentRunnerRegistry.register(name, version, runner)` then `.get(name, version)` roundtrips.
- `.get` raises `KeyError` for missing.
- `.verify_covers(contract_registry)` returns a list of missing `(name, version)` tuples; empty means OK.

**Step 2: Implement `registry.py`**

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable
from src.contracts.registry import ContractRegistry


@runtime_checkable
class AgentRunner(Protocol):
    async def run(self, inputs: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]: ...


class AgentRunnerRegistry:
    def __init__(self) -> None:
        self._runners: dict[tuple[str, int], AgentRunner] = {}

    def register(self, name: str, version: int, runner: AgentRunner) -> None:
        self._runners[(name, version)] = runner

    def get(self, name: str, version: int) -> AgentRunner:
        return self._runners[(name, version)]

    def covers(self, name: str, version: int) -> bool:
        return (name, version) in self._runners

    def verify_covers(self, contracts: ContractRegistry) -> list[tuple[str, int]]:
        missing: list[tuple[str, int]] = []
        for c in contracts.list_all_versions():
            if not self.covers(c.name, c.version):
                missing.append((c.name, c.version))
        return missing
```

**Step 3:** `runners/__init__.py`: export `AgentRunnerRegistry` and a module-level `_registry: AgentRunnerRegistry | None` plus `init_runners()` and `get_runner_registry()` mirroring the contract service pattern.

**Step 4–5:** Tests → commit.

```bash
git add backend/src/workflows/runners/ backend/tests/test_runner_registry.py
git commit -m "feat(workflows): typed AgentRunnerRegistry with integrity check"
```

---

## Task 6: Runner adapters for all 10 Phase-1 contracts

**Files:**
- Create one file per agent under `backend/src/workflows/runners/` (e.g., `log_agent.py`, `k8s_agent.py`, …).
- Modify: `backend/src/workflows/runners/__init__.py` — compose them all.
- Create: `backend/tests/test_runner_integrity.py`

**Step 1: Integrity test**

```python
# backend/tests/test_runner_integrity.py
from src.contracts.service import init_registry as init_contracts
from src.workflows.runners import init_runners, get_runner_registry


def test_every_contract_has_runner():
    contracts = init_contracts()
    init_runners()
    runners = get_runner_registry()
    missing = runners.verify_covers(contracts)
    assert missing == [], f"missing runners: {missing}"
```

**Step 2: Run — expect FAIL** (no runners registered).

**Step 3: Implement each adapter.** Pre-survey of the 10 Phase-0 agent entry points (class, method, sig, return shape) is locked below — implementers should match exactly:

| Agent (manifest name) | Class | Entry method | Construction | Returns | Adapter action |
|---|---|---|---|---|---|
| `log_agent` | `LogAnalysisAgent` | `async run(context, event_emitter=None) -> dict` | `LogAnalysisAgent(connection_config=None)` | dict (matches manifest) | pass-through |
| `k8s_agent` | `K8sAgent` | `async run(context, event_emitter=None) -> dict` | `K8sAgent()` | dict (matches) | pass-through |
| `metrics_agent` | `MetricsAgent` | `async run(context, event_emitter=None) -> dict` | `MetricsAgent()` | dict (matches) | pass-through |
| `tracing_agent` | `TracingAgent` | `async run_two_pass(context, event_emitter=None) -> dict` | `TracingAgent()` | dict (matches) | pass-through; **use `run_two_pass`** |
| `code_agent` | `CodeNavigatorAgent` | `async run_two_pass(context, event_emitter=None) -> dict` | `CodeNavigatorAgent()` | dict (matches) | pass-through; **use `run_two_pass`** |
| `change_agent` | `ChangeAgent` | `async run_two_pass(context, event_emitter=None) -> dict` | `ChangeAgent()` | dict (matches) | pass-through; **use `run_two_pass`** |
| `critic_agent` | `CriticAgent` | `async validate(finding, state) -> CriticVerdict` (Pydantic) | `CriticAgent()` | Pydantic model | **reshape**: build `Finding` + `DiagnosticState` from inputs; return `verdict.model_dump(mode="json")` |
| `pipeline_agent` | `PipelineAgent` | `async run(inputs: PipelineCapabilityInput \| dict) -> dict` | `PipelineAgent(llm=<shared_client>)` | dict (matches) | **shared LLM**: adapter holds a shared LLM client (lazy-singleton in `runners/__init__.py`) passed into constructor |
| `impact_analyzer` | `ImpactAnalyzer` | sync `recommend_severity(service_name, blast_radius)` + sync `infer_business_impact(services)` | `ImpactAnalyzer()` | Pydantic + list[dict] | **orchestrate+reshape**: wrap both calls in `asyncio.to_thread`, merge into `{blast_radius, severity_recommendation, business_impact}` per manifest |
| `intent_parser` | `IntentParser` | sync `parse(message, pending_action)` | `IntentParser()` | `UserIntent` dataclass | **async wrap**: `asyncio.to_thread`, return `dataclasses.asdict(result)` |

Adapter pattern for the 7 "pass-through dict-return" agents (`log_agent`, `k8s_agent`, `metrics_agent`, `tracing_agent`, `code_agent`, `change_agent`, `pipeline_agent`):

```python
# backend/src/workflows/runners/log_agent.py
from typing import Any
from src.agents.log_agent import LogAnalysisAgent


class LogAgentRunner:
    async def run(self, inputs: dict[str, Any], *, context: dict[str, Any]) -> dict[str, Any]:
        agent = LogAnalysisAgent()
        # inputs IS the context dict (Phase-0 agents already expect a context dict);
        # context here is Phase-2 executor context (cancellation flag, run_id, etc.) — pass neither nor event_emitter for Phase 2.
        return await agent.run(inputs)
```

Adapter pattern for `critic_agent` (reshape required):

```python
# backend/src/workflows/runners/critic_agent.py
from src.agents.critic_agent import CriticAgent
from src.models.schemas import Finding, DiagnosticState  # existing types


class CriticAgentRunner:
    def __init__(self) -> None:
        self._agent = CriticAgent()  # creates AnthropicClient internally

    async def run(self, inputs, *, context):
        finding = Finding(**inputs["finding"])
        state = DiagnosticState(**inputs["state"])
        verdict = await self._agent.validate(finding, state)
        return verdict.model_dump(mode="json")
```

Adapter pattern for `impact_analyzer` (sync, orchestrate two methods):

```python
# backend/src/workflows/runners/impact_analyzer.py
import asyncio
from dataclasses import asdict
from src.agents.impact_analyzer import ImpactAnalyzer


class ImpactAnalyzerRunner:
    def __init__(self) -> None:
        self._agent = ImpactAnalyzer()

    async def run(self, inputs, *, context):
        service = inputs["service_name"]
        services = inputs.get("services", [service])
        blast_radius = inputs["blast_radius"]  # caller-provided
        sev = await asyncio.to_thread(self._agent.recommend_severity, service, blast_radius)
        biz = await asyncio.to_thread(self._agent.infer_business_impact, services)
        return {
            "blast_radius": blast_radius,
            "severity_recommendation": sev.model_dump(mode="json"),
            "business_impact": biz,
        }
```

Adapter pattern for `intent_parser` (sync wrap):

```python
# backend/src/workflows/runners/intent_parser.py
import asyncio
from dataclasses import asdict
from src.agents.intent_parser import IntentParser


class IntentParserRunner:
    def __init__(self) -> None:
        self._agent = IntentParser()

    async def run(self, inputs, *, context):
        intent = await asyncio.to_thread(
            self._agent.parse, inputs["message"], inputs.get("pending_action")
        )
        return asdict(intent)
```

Composition root `runners/__init__.py`:

```python
from .registry import AgentRunnerRegistry

_registry: AgentRunnerRegistry | None = None


def init_runners() -> AgentRunnerRegistry:
    global _registry
    reg = AgentRunnerRegistry()
    # Shared LLM client for pipeline_agent (lazy).
    from src.utils.llm_client import get_default_llm_client  # or existing helper
    llm = get_default_llm_client()

    from .log_agent import LogAgentRunner
    from .k8s_agent import K8sAgentRunner
    from .metrics_agent import MetricsAgentRunner
    from .tracing_agent import TracingAgentRunner
    from .code_agent import CodeAgentRunner
    from .change_agent import ChangeAgentRunner
    from .critic_agent import CriticAgentRunner
    from .pipeline_agent import PipelineAgentRunner
    from .impact_analyzer import ImpactAnalyzerRunner
    from .intent_parser import IntentParserRunner

    reg.register("log_agent", 1, LogAgentRunner())
    reg.register("k8s_agent", 1, K8sAgentRunner())
    reg.register("metrics_agent", 1, MetricsAgentRunner())
    reg.register("tracing_agent", 1, TracingAgentRunner())
    reg.register("code_agent", 1, CodeAgentRunner())
    reg.register("change_agent", 1, ChangeAgentRunner())
    reg.register("critic_agent", 1, CriticAgentRunner())
    reg.register("pipeline_agent", 1, PipelineAgentRunner(llm=llm))
    reg.register("impact_analyzer", 1, ImpactAnalyzerRunner())
    reg.register("intent_parser", 1, IntentParserRunner())

    _registry = reg
    return reg


def get_runner_registry() -> AgentRunnerRegistry:
    if _registry is None:
        raise RuntimeError("runners not initialized — call init_runners() at startup")
    return _registry
```

**Do not modify any Phase-0 agent module.** All reshaping lives in the adapter file.

**Step 4: Run integrity test — expect PASS.**

**Step 5: Commit**

```bash
git add backend/src/workflows/runners/ backend/tests/test_runner_integrity.py
git commit -m "feat(workflows): runner adapters for all 10 Phase-1 agents"
```

---

## Task 7: SQLite migration + repository (`workflows` + `workflow_versions`)

**Files:**
- Create: `backend/src/workflows/migrations/001_create_workflow_tables.sql`
- Create: `backend/src/workflows/repository.py`
- Create: `backend/tests/test_workflow_repository.py`

**Schema (SQL):**

```sql
CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TEXT NOT NULL,
  created_by TEXT
);

CREATE TABLE IF NOT EXISTS workflow_versions (
  id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflows(id),
  version INTEGER NOT NULL,
  dag_json TEXT NOT NULL,
  compiled_json TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(workflow_id, version)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  id TEXT PRIMARY KEY,
  workflow_version_id TEXT NOT NULL REFERENCES workflow_versions(id),
  status TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  inputs_json TEXT NOT NULL,
  error_json TEXT,
  idempotency_key TEXT,
  run_mode TEXT NOT NULL DEFAULT 'workflow',
  UNIQUE(workflow_version_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS workflow_step_runs (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES workflow_runs(id),
  step_id TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  inputs_json TEXT,
  output_json TEXT,
  attempt INTEGER NOT NULL DEFAULT 1,
  duration_ms INTEGER,
  error_json TEXT,
  UNIQUE(run_id, step_id)
);

CREATE TABLE IF NOT EXISTS workflow_run_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES workflow_runs(id),
  sequence INTEGER NOT NULL,
  timestamp TEXT NOT NULL,
  type TEXT NOT NULL,
  node_id TEXT,
  attempt INTEGER,
  duration_ms INTEGER,
  error_class TEXT,
  error_message TEXT,
  parent_node_id TEXT,
  payload_json TEXT,
  UNIQUE(run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_events_run_seq ON workflow_run_events(run_id, sequence);
```

**Repository API (minimal):**

```python
class WorkflowRepository:
    def __init__(self, db_path: str): ...
    def create_workflow(self, *, name, description, created_by) -> Workflow: ...
    def get_workflow(self, id_or_name: str) -> Workflow | None: ...
    def list_workflows(self) -> list[Workflow]: ...
    def create_version(self, workflow_id: str, dag_json: str, compiled_json: str) -> WorkflowVersion: ...
    def get_version(self, workflow_id: str, version: int) -> WorkflowVersion | None: ...
    def latest_version(self, workflow_id: str) -> WorkflowVersion | None: ...

    def create_run(self, *, version_id, inputs_json, idempotency_key) -> Run: ...
    def get_run(self, run_id: str) -> Run | None: ...
    def update_run_status(self, run_id, status, *, ended_at=None, error_json=None) -> None: ...

    def upsert_step_run(self, ...) -> None: ...

    def append_event(self, ...) -> int: ...  # returns sequence
    def list_events_since(self, run_id, after_sequence: int) -> list[Event]: ...
```

Use `sqlite3` stdlib with `PRAGMA foreign_keys=ON`, row-level transactions, `OperationalError` retry for `database is locked`. `append_event` computes sequence via `SELECT COALESCE(MAX(sequence), 0) + 1 FROM workflow_run_events WHERE run_id = ?` inside the write transaction.

**Tests:** one test per repository method, using `tmp_path` for a temp DB file.

**Commit:**

```bash
git add backend/src/workflows/migrations/ backend/src/workflows/repository.py backend/tests/test_workflow_repository.py
git commit -m "feat(workflows): SQLite schema + repository"
```

---

## Task 8: Save-time service — `POST /workflows/{id}/versions` end-to-end

**Files:**
- Create: `backend/src/workflows/service.py`
- Create: `backend/src/api/routes_workflows.py` (start — just the save path)
- Modify: `backend/src/api/main.py` (register router + flag-gated)
- Create: `backend/tests/test_workflows_save_api.py`

**`service.py`:** thin orchestration layer.

```python
class WorkflowService:
    def __init__(self, repo, contracts, runners): ...

    def create_workflow(self, name, description, created_by) -> Workflow: ...

    def create_version(self, workflow_id, dag: WorkflowDag) -> WorkflowVersion:
        compiled = compile_dag(dag, self.contracts)
        # Extra check: runners cover all referenced (agent, version)
        for cs in compiled.steps.values():
            if not self.runners.covers(cs.agent, cs.agent_version):
                raise CompileError(f"steps.{cs.id}.agent", f"no runner for {cs.agent} v{cs.agent_version}")
        return self.repo.create_version(workflow_id, dag.model_dump_json(), json.dumps(asdict(compiled), default=str))
```

**Router:** `POST /api/v4/workflows`, `GET /api/v4/workflows`, `GET /api/v4/workflows/{id}`, `POST /api/v4/workflows/{id}/versions` — all behind `Depends(require_workflows_flag)` that reads `config.settings.WORKFLOWS_ENABLED` per-request (same pattern as Phase 1 catalog). On `CompileError`, return 422 with `{"error_path", "message"}`.

**Tests:** create workflow → create version with a valid 3-step DAG → get it back. Invalid DAG → 422 with correct path. Flag off → 404.

**Commit:**

```bash
git add backend/src/workflows/service.py backend/src/api/routes_workflows.py backend/src/api/main.py backend/tests/test_workflows_save_api.py
git commit -m "feat(api): workflows + versions save path with flag gate"
```

---

## Task 9: Executor — scheduler core (topo + global cap + FIFO, no failures yet)

**Files:**
- Create: `backend/src/workflows/executor.py`
- Create: `backend/tests/test_executor_scheduler.py`

**Scope:** deterministic topo execution with global `MAX_CONCURRENT_STEPS` cap and FIFO by readiness. Every node SUCCEEDs (use a dummy runner). No predicates yet. No failure handling yet. No SSE yet. Emits events to the repo only.

**Key invariants tested:**

- 5-step linear chain: executes in order.
- 3 parallel leaves + 1 join: leaves execute with up to `MAX_CONCURRENT_STEPS=3`; join executes after all three.
- With `MAX_CONCURRENT_STEPS=1`, parallel leaves execute in step id lex order.
- `run_mode='workflow'` written to DB.
- Events appended: `run.started`, per-step `started`/`completed`, `run.completed` — with monotonic sequences.

**Commit:**

```bash
git add backend/src/workflows/executor.py backend/tests/test_executor_scheduler.py
git commit -m "feat(workflows): executor scheduler with topo + global cap + FIFO"
```

---

## Task 10: Executor — concurrency groups

**Files:**
- Modify: `backend/src/workflows/executor.py`
- Create: `backend/tests/test_executor_concurrency_groups.py`

**Scope:** honour `CONCURRENCY_GROUP_CAPS` env JSON. When a step's `concurrency_group` is capped, count only steps in that group for admission.

**Test:** 5 steps all in group `g1`, cap `{"g1": 2}`, global cap 10 → at most 2 running concurrently at any time (instrument via a semaphore probe in the dummy runner).

**Commit:**

```bash
git commit -m "feat(workflows): per-group concurrency caps"
```

---

## Task 11: Executor — predicates (`when`) + SKIPPED state

**Files:**
- Modify: `backend/src/workflows/executor.py`
- Create: `backend/tests/test_executor_predicates.py`

**Scope:** evaluate `when` via evaluator before scheduling. If `False` or `SkippedRefError`, state = `SKIPPED`. Downstream ref to SKIPPED → runtime error on that downstream step (fail-fast unless overridden).

**Tests:**
- `when=eq(input.env, "prod")` + `inputs.env="dev"` → step SKIPPED.
- Downstream ref to SKIPPED node → downstream step FAILED with `skipped_ref` error class.
- SKIPPED does NOT trigger its own `on_failure`.

**Commit:**

```bash
git commit -m "feat(workflows): node predicates + SKIPPED state semantics"
```

---

## Task 12: Executor — failure policies (`fail` / `continue` / `fallback`)

**Files:**
- Modify: `backend/src/workflows/executor.py`
- Create: `backend/tests/test_executor_failures.py`

**Scope:**
- `fail` (default): run → FAILED; remaining scheduled steps marked `cancelled`.
- `continue`: step → FAILED; downstream refs fail (see Task 11); *independent* branches continue.
- `fallback`: on failure, schedule `fallback_step_id` with same state; its output replaces primary's; primary status remains `FAILED` but downstream refs resolve via fallback output. Fallback failure → run fails (fail-fast).

**Tests:** one per policy. `fallback` test verifies downstream receives fallback's output.

**Commit:**

```bash
git commit -m "feat(workflows): on_failure policies fail/continue/fallback"
```

---

## Task 13: Executor — timeout + retry wrapping

**Files:**
- Modify: `backend/src/workflows/executor.py`
- Create: `backend/tests/test_executor_timeout_retry.py`

**Scope:** wrap each runner call in `asyncio.wait_for(timeout=compiled.timeout_seconds)`. On `asyncio.TimeoutError`, if `TimeoutError` (or the raised exception name) is in `compiled.retry_on`, retry up to 2 additional attempts; record `attempt` on the step run.

**Tests:**
- Slow runner + tight timeout → FAILED with `error_class=TimeoutError`.
- Flaky runner (fail twice, succeed third) + `retry_on=["ValueError"]` → SUCCEEDED with `attempt=3`.
- Flaky runner + exception NOT in retry_on → FAILED on attempt 1.

**Commit:**

```bash
git commit -m "feat(workflows): per-step timeout + bounded retries"
```

---

## Task 14: Executor — cancellation lifecycle

**Files:**
- Modify: `backend/src/workflows/executor.py`
- Create: `backend/tests/test_executor_cancellation.py`

**Scope:**
- `ExecutorRegistry.cancel(run_id)` sets `CANCELLING`.
- Executor loop: no new steps scheduled once CANCELLING.
- In-flight runners receive `context["is_cancelled"]` (a `asyncio.Event`).
- 30-second grace (configurable for tests via `CANCEL_GRACE_SECONDS`). After grace, force `CANCELLED`; remaining in-flight steps marked `cancelled`.

**Tests:** cooperative-runner (observes flag, returns promptly); stubborn-runner (ignores flag, forced-cancel after short test grace).

**Commit:**

```bash
git commit -m "feat(workflows): cooperative cancellation with grace window"
```

---

## Task 15: Executor — drift detection at run start

**Files:**
- Modify: `backend/src/workflows/executor.py`
- Create: `backend/tests/test_executor_drift.py`

**Scope:** before scheduling the first step, re-validate each compiled step's `(agent, agent_version)` still exists in the current `ContractRegistry` and the output schemas used by downstream refs still contain those paths. On mismatch, `run.status=FAILED`, `error_json={"class": "drift_detected", ...}`, emit `run.failed`.

**Test:** compile workflow → swap contract registry with a modified output schema that drops a referenced path → run fails with drift error before any step runs.

**Commit:**

```bash
git commit -m "feat(workflows): runtime drift check against live contracts"
```

---

## Task 16: Run API — `POST /workflows/{id}/runs` + idempotency

**Files:**
- Modify: `backend/src/api/routes_workflows.py`
- Modify: `backend/src/workflows/service.py`
- Create: `backend/tests/test_run_api.py`

**Scope:**
- `POST /api/v4/workflows/{id}/runs` body: `{"version": int | "latest", "inputs": {...}, "idempotency_key": str?}`.
- Validates `inputs` against `inputs_schema` via `jsonschema`.
- If `idempotency_key` provided and already used for that version → return existing run (200).
- Otherwise create run (status `PENDING`), enqueue on executor (fire-and-forget), return 202 with run summary.
- `GET /api/v4/runs/{run_id}` returns run + step summaries.

**Tests:** happy path; input-schema violation → 422; idempotent replay; invalid version → 404.

**Commit:**

```bash
git commit -m "feat(api): POST runs with idempotency + GET run status"
```

---

## Task 17: SSE stream `GET /runs/{id}/events` with `Last-Event-ID` resume

**Files:**
- Modify: `backend/src/api/routes_workflows.py`
- Create: `backend/tests/test_run_events_sse.py`

**Scope:** use `sse_starlette.sse.EventSourceResponse`.
- Accept `Last-Event-ID` header (= last `sequence` seen).
- Stream: replay persisted events with `sequence > last_id`, then subscribe to live events until run reaches terminal status.
- Event `id` = `sequence` (string).

**Tests:**
- No `Last-Event-ID` → streams from sequence 1.
- With `Last-Event-ID=3` → skips 1..3.
- Disconnect mid-stream + reconnect with last seen id resumes correctly.
- Terminal event (`run.*`) closes the stream.

**Commit:**

```bash
git commit -m "feat(api): SSE event stream with resume"
```

---

## Task 18: Cancel endpoint `POST /runs/{id}/cancel`

**Files:**
- Modify: `backend/src/api/routes_workflows.py`
- Create: `backend/tests/test_run_cancel_api.py`

**Scope:** route hits `ExecutorRegistry.cancel(run_id)`, returns 202. Tests verify the run's final state is `CANCELLED` and a `run.cancelled` event is emitted.

**Commit:**

```bash
git commit -m "feat(api): POST cancel endpoint"
```

---

## Task 19: Startup wiring + integrity enforcement

**Files:**
- Modify: `backend/src/api/main.py`

**Scope:** inside existing lifespan `startup()`, after Phase-1 contracts init:

```python
from src.workflows.runners import init_runners
from src.workflows.repository import WorkflowRepository
from src.workflows.service import WorkflowService
from src.workflows.executor import ExecutorRegistry

runners = init_runners()
missing = runners.verify_covers(contracts)
if missing:
    raise RuntimeError(f"Phase 2 startup: missing runners {missing}")

repo = WorkflowRepository(db_path=...)
service = WorkflowService(repo=repo, contracts=contracts, runners=runners)
executor = ExecutorRegistry(service=service, repo=repo, runners=runners)
app.state.workflow_service = service
app.state.executor = executor
```

Router uses `request.app.state.workflow_service` / `executor` to keep imports tight.

**Smoke test:** `python3 -c "from src.api.main import app; ..."` prints workflow routes mounted + no error.

**Commit:**

```bash
git add backend/src/api/main.py
git commit -m "feat(workflows): wire service + executor into app lifespan"
```

---

## Task 20: Non-impact snapshot tests

**Files:**
- Create: `backend/tests/test_workflows_nonimpact.py`

**Scope:** mirror Phase 1's `test_auto_mode_nonimpact.py` pattern:
- `WORKFLOWS_ENABLED=false` default → `/api/v4/workflows`, `/api/v4/workflows/x`, `/api/v4/workflows/x/runs`, `/api/v4/runs/y`, `/api/v4/runs/y/events`, `/api/v4/runs/y/cancel` all return 404.
- `/api/v4/findings/bogus` still returns non-500 (Phase 1 invariant).
- `/api/v4/sessions` still returns <500.

**Commit:**

```bash
git commit -m "test(workflows): non-impact snapshot tests"
```

---

## Task 21: End-to-end verification + PR

**Step 1: Full backend suite**

```bash
python3 -m pytest backend/tests/ 2>&1 | tail -5
```
Expected: all tests pass, including Phase 1's 41.

**Step 2: Non-impact diff check**

```bash
git diff main..HEAD -- backend/src/agents/supervisor.py backend/src/api/routes_v4.py backend/src/models/schemas.py frontend/src/components/Investigation/
```
Expected: empty.

**Step 3: Manual smoke**

- Start backend with `WORKFLOWS_ENABLED=true`.
- `curl -X POST localhost:8000/api/v4/workflows -d '{"name":"demo","description":""}'` → 201.
- Create a 2-step version (log_agent → metrics_agent) via `curl`.
- POST a run; `GET /runs/{id}` shows progression.
- Connect SSE stream; observe events.
- POST cancel on an in-flight run; observe `CANCELLED`.
- Flip flag off, restart, verify all workflow routes 404.
- Open an existing investigation session; confirm visually unchanged.

**Step 4: Push + PR**

```bash
git push -u origin feature/phase2-executor
gh pr create --base main --title "Phase 2: workflow executor + orchestrator (flag-gated)" --body "..."
```

**Step 5: Final commit marker**

```bash
git commit --allow-empty -m "chore: Phase 2 executor complete"
```

---

## Phase 2 Exit Criteria

- [ ] All 10 Phase-1 agents have runners; boot fails without them.
- [ ] Workflows + versions CRUD works; invalid DAGs rejected at save with precise error paths.
- [ ] Executor runs topo order, parallel within caps, FIFO by readiness.
- [ ] Node states SUCCESS / FAILED / SKIPPED behave per design §4.5.
- [ ] `on_failure: fail | continue | fallback` behave per design §4.6.
- [ ] Timeouts + retries respect contract upper bounds.
- [ ] Cooperative cancel with 30s grace works.
- [ ] Drift detection fires when live contract diverges from compiled workflow.
- [ ] SSE stream resumable via `Last-Event-ID`.
- [ ] `WORKFLOWS_ENABLED=false` → all new routes 404.
- [ ] Phase 1 tests still green.
- [ ] Non-impact diff invariants hold.
- [ ] Manual smoke per Task 21 passes.

---

## What's NOT in Phase 2 (deferred)

- Frontend: `/workflows` builder UI → Phase 3.
- Canvas run replay → Phase 4.
- Supervisor integration → Phase 5.
- Scheduled runs, RBAC, import/export → Phase 6.
