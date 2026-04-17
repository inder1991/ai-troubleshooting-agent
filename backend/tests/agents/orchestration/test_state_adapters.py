"""Stage A.1 — planner_inputs + eval_gate_inputs adapters.

Uses lightweight stand-ins rather than real DiagnosticState so the tests
don't need to construct a full pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.agents.orchestration.state_adapters import (
    eval_gate_inputs,
    planner_inputs,
)


@dataclass
class StubState:
    """Duck-typed DiagnosticState subset the adapters read."""

    agents_completed: list[str] = field(default_factory=list)
    agent_statuses: dict[str, str] = field(default_factory=dict)
    coverage_gaps: list[str] = field(default_factory=list)
    repo_url: Optional[str] = None
    cluster_url: Optional[str] = None
    namespace: Optional[str] = None
    trace_id: Optional[str] = None
    overall_confidence: float = 0.0
    service_name: str = "payment"
    patient_zero: Optional[Any] = None
    inferred_dependencies: list[Any] = field(default_factory=list)
    critic_verdicts: list[Any] = field(default_factory=list)


DEFAULT_AGENTS = {"log_agent", "metrics_agent", "k8s_agent", "tracing_agent", "code_agent", "change_agent"}


class TestPlannerInputs:
    def test_minimal_state_maps_flags(self):
        s = StubState(
            repo_url="https://github.com/x/y",
            cluster_url="https://c.example",
            trace_id="t-1",
        )
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.has_repo is True
        assert pi.has_cluster is True
        assert pi.has_trace_id is True

    def test_namespace_alone_counts_as_cluster(self):
        s = StubState(namespace="payments")
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.has_cluster is True

    def test_coverage_gaps_parsed_to_dict(self):
        s = StubState(coverage_gaps=[
            "metrics_agent: prometheus unreachable",
            "k8s_agent: circuit open",
        ])
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.coverage_gaps == {
            "metrics_agent": "prometheus unreachable",
            "k8s_agent": "circuit open",
        }

    def test_prior_failures_from_agent_statuses(self):
        s = StubState(
            agent_statuses={"metrics_agent": "error", "log_agent": "success"},
        )
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.prior_failures == {"metrics_agent"}

    def test_confidence_percent_to_fraction(self):
        s = StubState(overall_confidence=85)
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.confidence == 0.85

    def test_confidence_already_fractional_passes_through(self):
        s = StubState(overall_confidence=0.42)
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.confidence == 0.42

    def test_primary_service_from_patient_zero_dict(self):
        s = StubState(
            patient_zero={"service": "checkout"},
            service_name="payment",
        )
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.primary_service == "checkout"

    def test_primary_service_falls_back_to_service_name(self):
        s = StubState(service_name="payment")
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.primary_service == "payment"

    def test_dependency_graph_built_from_inferred_deps(self):
        s = StubState(
            inferred_dependencies=[
                {"source": "payment", "target": "db"},
                {"source": "payment", "target": "redis"},
                {"source": "db", "target": "storage"},
            ],
        )
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.dependency_graph == {
            "payment": ["db", "redis"],
            "db": ["storage"],
        }

    def test_round_estimates_from_completed_agents_count(self):
        s = StubState(agents_completed=["log_agent", "metrics_agent"])
        pi = planner_inputs(s, registered_agents=DEFAULT_AGENTS)
        assert pi.round == 2

    def test_registered_agents_is_passed_through(self):
        s = StubState()
        pi = planner_inputs(s, registered_agents={"log_agent"})
        assert pi.registered_agents == {"log_agent"}


class TestEvalGateInputs:
    def test_basic_shape(self):
        s = StubState(
            agents_completed=["log_agent", "metrics_agent"],
            overall_confidence=65,
        )
        gi = eval_gate_inputs(s, round_num=2)
        assert gi.rounds == 2
        assert gi.max_rounds == 10
        assert gi.confidence == 0.65
        assert gi.coverage_ratio == 2 / 6

    def test_challenged_verdicts_counted(self):
        @dataclass
        class Verdict:
            verdict: str

        s = StubState(
            critic_verdicts=[
                Verdict("confirmed"),
                Verdict("challenged"),
                Verdict("challenged"),
            ],
        )
        gi = eval_gate_inputs(s, round_num=1)
        assert gi.challenged_verdicts == 2

    def test_coverage_ratio_clamped_at_1(self):
        s = StubState(agents_completed=["a", "b", "c", "d", "e", "f", "g"])
        gi = eval_gate_inputs(s, round_num=7, max_agents=6)
        assert gi.coverage_ratio == 1.0

    def test_rounds_since_new_signal_passed_through(self):
        s = StubState()
        gi = eval_gate_inputs(s, round_num=3, rounds_since_new_signal=2)
        assert gi.rounds_since_new_signal == 2
