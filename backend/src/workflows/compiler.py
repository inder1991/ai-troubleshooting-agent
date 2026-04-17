from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from src.contracts.registry import ContractRegistry
from src.workflows._schema import _check_schema_version
from src.workflows.models import WorkflowDag, StepSpec


class CompileError(ValueError):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path


@dataclass
class CompiledStep:
    SCHEMA_VERSION = 1

    id: str
    agent: str
    agent_version: int
    inputs: dict
    when: dict | None
    on_failure: str
    fallback_step_id: str | None
    parallel_group: str | None
    concurrency_group: str | None
    timeout_seconds: float
    retry_on: list[str]
    upstream_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "id": self.id,
            "agent": self.agent,
            "agent_version": self.agent_version,
            "inputs": self.inputs,
            "when": self.when,
            "on_failure": self.on_failure,
            "fallback_step_id": self.fallback_step_id,
            "parallel_group": self.parallel_group,
            "concurrency_group": self.concurrency_group,
            "timeout_seconds": self.timeout_seconds,
            "retry_on": list(self.retry_on),
            "upstream_ids": list(self.upstream_ids),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CompiledStep":
        _check_schema_version(d, cls.SCHEMA_VERSION, cls.__name__)
        return cls(
            id=d["id"],
            agent=d["agent"],
            agent_version=d["agent_version"],
            inputs=d["inputs"],
            when=d.get("when"),
            on_failure=d.get("on_failure", "fail"),
            fallback_step_id=d.get("fallback_step_id"),
            parallel_group=d.get("parallel_group"),
            concurrency_group=d.get("concurrency_group"),
            timeout_seconds=float(d["timeout_seconds"]),
            retry_on=list(d.get("retry_on", [])),
            upstream_ids=list(d.get("upstream_ids", [])),
        )


@dataclass
class CompiledWorkflow:
    SCHEMA_VERSION = 1

    topo_order: list[str]
    steps: dict[str, CompiledStep]
    inputs_schema: dict

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "topo_order": list(self.topo_order),
            "steps": {sid: s.to_dict() for sid, s in self.steps.items()},
            "inputs_schema": self.inputs_schema,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CompiledWorkflow":
        _check_schema_version(d, cls.SCHEMA_VERSION, cls.__name__)
        return cls(
            topo_order=list(d["topo_order"]),
            steps={sid: CompiledStep.from_dict(s) for sid, s in d["steps"].items()},
            inputs_schema=d.get("inputs_schema", {}),
        )


def _extract_ref_paths(expr: Any, acc: list[tuple[str, Any]]) -> None:
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
    """Best-effort walk of JSON Schema properties/items along a dotted path.

    If any segment of the schema is not an ``object`` with ``properties`` or
    an ``array`` with ``items``, treat it as permissive and return True.
    """
    cur = schema
    for part in path.split("."):
        if not isinstance(cur, dict):
            return True
        if cur.get("type") == "object" and "properties" in cur:
            props = cur["properties"]
            if part not in props:
                return False
            cur = props[part]
        elif cur.get("type") == "array" and "items" in cur:
            cur = cur["items"]
        else:
            return True
    return True


def compile_dag(dag: WorkflowDag, contracts: ContractRegistry) -> CompiledWorkflow:
    max_steps = int(os.environ.get("MAX_TOTAL_STEPS_PER_RUN", "200"))
    if len(dag.steps) > max_steps:
        raise CompileError("steps", f"exceeds MAX_TOTAL_STEPS_PER_RUN ({max_steps})")

    # 1. Resolve agent + version, validate override rules
    resolved: dict[str, CompiledStep] = {}
    for s in dag.steps:
        if s.agent_version == "latest":
            candidates = [c for c in contracts.list_all_versions() if c.name == s.agent]
            if not candidates:
                raise CompileError(
                    f"steps.{s.id}.agent",
                    f"agent {s.agent!r} not in contract registry",
                )
            active = [
                c for c in candidates if c.version not in (c.deprecated_versions or [])
            ]
            if not active:
                raise CompileError(
                    f"steps.{s.id}.agent_version", "no active versions"
                )
            contract = max(active, key=lambda c: c.version)
        else:
            try:
                contract = contracts.get(s.agent, version=int(s.agent_version))
            except KeyError:
                raise CompileError(
                    f"steps.{s.id}.agent_version",
                    f"agent {s.agent!r} v{s.agent_version} not found",
                )

        timeout = contract.timeout_seconds
        if s.timeout_seconds_override is not None:
            if s.timeout_seconds_override > contract.timeout_seconds:
                raise CompileError(
                    f"steps.{s.id}.timeout_seconds_override",
                    f"cannot exceed contract timeout {contract.timeout_seconds}",
                )
            timeout = s.timeout_seconds_override

        retry = list(contract.retry_on)
        if s.retry_on_override is not None:
            if not set(s.retry_on_override).issubset(set(contract.retry_on)):
                raise CompileError(
                    f"steps.{s.id}.retry_on_override",
                    "must be subset of contract retry_on",
                )
            retry = list(s.retry_on_override)

        resolved[s.id] = CompiledStep(
            id=s.id,
            agent=s.agent,
            agent_version=contract.version,
            inputs=s.inputs,
            when=s.when,
            on_failure=s.on_failure,
            fallback_step_id=s.fallback_step_id,
            parallel_group=s.parallel_group,
            concurrency_group=s.concurrency_group,
            timeout_seconds=timeout,
            retry_on=retry,
            upstream_ids=[],
        )

    # 2. Collect upstream dependencies from refs + predicates
    for step_id, cs in resolved.items():
        refs: list[tuple[str, Any]] = []
        _extract_ref_paths(cs.inputs, refs)
        if cs.when is not None:
            _extract_ref_paths(cs.when, refs)
        for kind, r in refs:
            if kind != "ref":
                continue
            if r.get("from") == "node":
                nid = r["node_id"]
                if nid not in resolved:
                    raise CompileError(
                        f"steps.{step_id}", f"ref to unknown node {nid!r}"
                    )
                if nid == step_id:
                    raise CompileError(f"steps.{step_id}", "self-reference")
                if nid not in cs.upstream_ids:
                    cs.upstream_ids.append(nid)

    # 3. Topo sort (Kahn's, lex-sorted ready queue)
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
        if cs.when is not None:
            _extract_ref_paths(cs.when, refs)
        for kind, r in refs:
            if kind != "ref":
                continue
            if r.get("from") == "input":
                if not _path_exists_in_schema(dag.inputs_schema, r["path"]):
                    raise CompileError(
                        f"steps.{sid}.inputs",
                        f"input path {r['path']!r} not in inputs_schema",
                    )
            elif r.get("from") == "node":
                up = resolved[r["node_id"]]
                contract = contracts.get(up.agent, version=up.agent_version)
                if not r["path"].startswith("output"):
                    raise CompileError(
                        f"steps.{sid}.inputs",
                        f"ref path must start with 'output' (got {r['path']!r})",
                    )
                sub = r["path"][len("output"):].lstrip(".")
                if sub and not _path_exists_in_schema(contract.output_schema, sub):
                    raise CompileError(
                        f"steps.{sid}.inputs",
                        f"path {r['path']!r} not in "
                        f"{up.agent} v{up.agent_version} output schema",
                    )

    # 5. Fallback rules
    for sid, cs in resolved.items():
        if cs.on_failure == "fallback":
            fb_id = cs.fallback_step_id
            if fb_id not in resolved:
                raise CompileError(
                    f"steps.{sid}.fallback_step_id", "target not in DAG"
                )
            fb = resolved[fb_id]
            if not set(fb.upstream_ids).issubset(set(cs.upstream_ids)):
                raise CompileError(
                    f"steps.{sid}.fallback_step_id",
                    "fallback's upstream deps must be subset of primary's",
                )

    return CompiledWorkflow(
        topo_order=order, steps=resolved, inputs_schema=dag.inputs_schema
    )
