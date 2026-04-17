"""Planner — deterministic next-agent selection.

Replaces the supervisor's ``_decide_next_agents`` chain-of-ifs with a
small, testable unit. Inputs:
  - agents_completed
  - coverage_gaps (set of agent_name → reason, from Task 1.14)
  - registered_agents (what the host has wired up)
  - repo_url / cluster_url / namespace / trace_id (capability hints)
  - prior_failures (agents that errored this run)

No LLM. Phase-3+ will extend with confidence-driven next-agent choice;
this module is the skeleton to extend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class PlannerInputs:
    registered_agents: set[str]
    agents_completed: list[str]
    prior_failures: set[str] = field(default_factory=set)
    coverage_gaps: dict[str, str] = field(default_factory=dict)
    has_repo: bool = False
    has_cluster: bool = False
    has_trace_id: bool = False


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


class Planner:
    """Returns the next agents to dispatch, deterministically."""

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
