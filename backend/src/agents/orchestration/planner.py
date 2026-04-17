"""Planner — deterministic next-agent selection.

Replaces the supervisor's ``_decide_next_agents`` chain-of-ifs with a
small, testable unit. Inputs:
  - agents_completed
  - coverage_gaps (set of agent_name → reason, from Task 1.14)
  - registered_agents (what the host has wired up)
  - repo_url / cluster_url / namespace / trace_id (capability hints)
  - prior_failures (agents that errored this run)
  - confidence / round / primary_service / dependency_graph (Task 4.4
    upstream-walk inputs — optional; omitted inputs fall through to the
    original priority-order planner).

No LLM. The upstream-walk extension (Phase 4) fires only when confidence
is low after at least one completed round; it returns a targeted batch
of (agent, service) specs walking the dependency graph to depth=2.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class PlannerInputs:
    registered_agents: set[str]
    agents_completed: list[str]
    prior_failures: set[str] = field(default_factory=set)
    coverage_gaps: dict[str, str] = field(default_factory=dict)
    has_repo: bool = False
    has_cluster: bool = False
    has_trace_id: bool = False
    # Upstream-walk inputs (Task 4.4). All optional; omitted -> disabled.
    confidence: Optional[float] = None
    round: int = 0
    primary_service: Optional[str] = None
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentServiceSpec:
    """Targeted dispatch spec emitted by the upstream walker."""

    agent: str
    service: str


# Upstream walk triggers when post-round confidence is below this.
_UPSTREAM_CONFIDENCE_TRIGGER: float = 0.50
# How deep to traverse the dependency graph.
_UPSTREAM_DEPTH: int = 2
# Which agents re-run on each upstream service.
_UPSTREAM_AGENTS: tuple[str, ...] = ("metrics_agent", "log_agent")


# Fixed, auditable agent priority. Log → Metrics → K8s → Tracing → Code → Change.
# Matches the v5 pivot order in supervisor.py so behaviour is unchanged when
# Dispatcher+Planner+Reducer are wired in.
_PRIORITY: tuple[str, ...] = (
    "log_agent",
    "metrics_agent",
    "k8s_agent",
    "tracing_agent",
    "code_agent",
    "change_agent",
)


def _upstream_services(
    graph: dict[str, list[str]],
    start: str,
    *,
    depth: int,
) -> list[str]:
    """BFS upstream from ``start`` to ``depth`` hops. Deterministic order.

    ``graph[node]`` lists the direct upstream dependencies of ``node``.
    Missing keys are treated as no upstream. Returns a list of services
    encountered (excluding the start itself), in BFS-visit order.
    """
    visited: set[str] = {start}
    frontier: deque[tuple[str, int]] = deque([(start, 0)])
    out: list[str] = []
    while frontier:
        node, d = frontier.popleft()
        if d >= depth:
            continue
        for neighbour in graph.get(node, ()):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            out.append(neighbour)
            frontier.append((neighbour, d + 1))
    return out


class Planner:
    """Returns the next agents to dispatch, deterministically."""

    def upstream_walk(self, s: PlannerInputs) -> list[AgentServiceSpec]:
        """Emit targeted (agent, service) specs when confidence is low.

        Returns an empty list unless all of:
          - confidence is set and < 0.50
          - round >= 1 (at least one full dispatch round completed)
          - primary_service is set
          - dependency_graph has entries for the primary service
        """
        if s.confidence is None or s.confidence >= _UPSTREAM_CONFIDENCE_TRIGGER:
            return []
        if s.round < 1:
            return []
        if not s.primary_service or not s.dependency_graph:
            return []
        upstream = _upstream_services(
            s.dependency_graph,
            s.primary_service,
            depth=_UPSTREAM_DEPTH,
        )
        if not upstream:
            return []
        specs: list[AgentServiceSpec] = []
        for svc in upstream:
            for agent in _UPSTREAM_AGENTS:
                if agent in s.registered_agents:
                    specs.append(AgentServiceSpec(agent=agent, service=svc))
        return specs

    def next(self, s: PlannerInputs) -> list[str]:
        completed = set(s.agents_completed)
        # Never retry within a single investigation — prior_failures are sticky.
        blocked = completed | s.prior_failures | set(s.coverage_gaps.keys())

        specs: list[str] = []
        for agent in _PRIORITY:
            if agent in blocked:
                continue
            if agent not in s.registered_agents:
                continue
            if agent == "tracing_agent" and not s.has_trace_id:
                continue
            if agent == "k8s_agent" and not s.has_cluster:
                continue
            if agent == "code_agent" and not s.has_repo:
                continue
            if agent == "change_agent" and not s.has_repo:
                continue
            specs.append(agent)

        # Batch of up to two agents per round — balance concurrency vs. token
        # burn. Tuned to match the supervisor's current "1–2 agents per round"
        # emergent behaviour without a big kitchen-sink fan-out.
        return specs[:2]
