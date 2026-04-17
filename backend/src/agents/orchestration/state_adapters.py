"""State adapters — translate DiagnosticState into the orchestration units'
input dataclasses.

Keeping these as pure functions in a separate module (rather than private
methods on SupervisorAgent) has two benefits:

  1. Supervisor.run() reads like prose: ``Planner().next(planner_inputs(state))``
     instead of ``self._planner.next(self._planner_inputs(state))``.
  2. Adapter logic is unit-testable without standing up a SupervisorAgent
     (which pulls in AnthropicClient + a bunch of other construction).

Stage A.1 of the run_v5 orchestration swap — see
docs/plans/2026-04-18-run-v5-orchestration-swap.md.
"""
from __future__ import annotations

from typing import Any, Optional

from src.agents.orchestration.eval_gate import EvalGateInputs
from src.agents.orchestration.planner import PlannerInputs


def planner_inputs(
    state: Any,
    *,
    registered_agents: set[str],
) -> PlannerInputs:
    """Build a PlannerInputs from a DiagnosticState.

    ``registered_agents`` is the set the supervisor actually wired up in its
    ``_agents`` dict; we don't read it off the state because an agent may be
    present in the class but disabled for this investigation (e.g. no API
    key configured).
    """
    coverage_gaps_dict = _coverage_gaps_to_dict(
        getattr(state, "coverage_gaps", None) or []
    )
    prior_failures = {
        a
        for a, status in (getattr(state, "agent_statuses", None) or {}).items()
        if status == "error"
    }
    return PlannerInputs(
        registered_agents=set(registered_agents),
        agents_completed=list(getattr(state, "agents_completed", None) or []),
        prior_failures=prior_failures,
        coverage_gaps=coverage_gaps_dict,
        has_repo=bool(getattr(state, "repo_url", None)),
        has_cluster=bool(
            getattr(state, "cluster_url", None)
            or getattr(state, "namespace", None)
        ),
        has_trace_id=bool(getattr(state, "trace_id", None)),
        confidence=_confidence_fraction(state),
        round=_round_from_completed(state),
        primary_service=_primary_service(state),
        dependency_graph=_dependency_graph(state),
    )


def eval_gate_inputs(
    state: Any,
    *,
    round_num: int,
    rounds_since_new_signal: int = 0,
    max_rounds: int = 10,
    max_agents: Optional[int] = None,
) -> EvalGateInputs:
    """Build an EvalGateInputs for the current loop iteration.

    The gate needs a coverage_ratio bounded to [0, 1]; we compute it from
    completed agents vs max_agents (or registered count).
    """
    completed = len(getattr(state, "agents_completed", None) or [])
    denom = max(max_agents or 6, 1)
    coverage_ratio = min(completed / denom, 1.0)
    challenged = sum(
        1
        for cv in (getattr(state, "critic_verdicts", None) or [])
        if getattr(cv, "verdict", None) == "challenged"
    )
    return EvalGateInputs(
        rounds=round_num,
        max_rounds=max_rounds,
        confidence=_confidence_fraction(state) or 0.0,
        challenged_verdicts=challenged,
        coverage_ratio=coverage_ratio,
        rounds_since_new_signal=rounds_since_new_signal,
    )


# ── internals ────────────────────────────────────────────────────────────


def _coverage_gaps_to_dict(gaps: list[str]) -> dict[str, str]:
    """Parse ``"agent: reason"`` strings into ``{agent: reason}``."""
    out: dict[str, str] = {}
    for entry in gaps:
        if not isinstance(entry, str) or ":" not in entry:
            continue
        agent, _, reason = entry.partition(":")
        agent = agent.strip()
        reason = reason.strip()
        if agent:
            out[agent] = reason
    return out


def _confidence_fraction(state: Any) -> Optional[float]:
    """overall_confidence is 0..100; Planner/EvalGate want 0..1."""
    v = getattr(state, "overall_confidence", None)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f > 1.5:
        return max(0.0, min(f / 100.0, 1.0))
    return max(0.0, min(f, 1.0))


def _round_from_completed(state: Any) -> int:
    """Rough proxy: one 'round' per completed agent. Exact round tracking
    is owned by the supervisor loop — this is a fallback for when the
    caller hasn't threaded round_num through."""
    return len(getattr(state, "agents_completed", None) or [])


def _primary_service(state: Any) -> Optional[str]:
    """Prefer patient_zero's service when we have one — that's the focus
    of the investigation. Fall back to the inbound service_name."""
    pz = getattr(state, "patient_zero", None)
    if isinstance(pz, dict) and pz.get("service"):
        return str(pz["service"])
    if pz is not None:
        svc = getattr(pz, "service", None)
        if svc:
            return str(svc)
    return getattr(state, "service_name", None) or None


def _dependency_graph(state: Any) -> dict[str, list[str]]:
    """Build ``{service: [upstream, ...]}`` from state.inferred_dependencies.

    Upstream-walk direction: if dep.relationship is 'depends_on' / 'calls',
    the source depends on the target — so target is upstream of source.
    """
    graph: dict[str, list[str]] = {}
    for dep in getattr(state, "inferred_dependencies", None) or []:
        src = _dep_field(dep, "source") or _dep_field(dep, "from")
        tgt = _dep_field(dep, "target") or _dep_field(dep, "to")
        if not src or not tgt:
            continue
        graph.setdefault(src, [])
        if tgt not in graph[src]:
            graph[src].append(tgt)
    return graph


def _dep_field(dep: Any, name: str) -> Optional[str]:
    if isinstance(dep, dict):
        v = dep.get(name)
    else:
        v = getattr(dep, name, None)
    return str(v) if v else None
