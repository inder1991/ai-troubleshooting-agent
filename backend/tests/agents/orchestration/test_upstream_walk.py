"""Task 4.4 — topology-aware upstream walk on low confidence."""
from __future__ import annotations

from src.agents.orchestration.planner import (
    AgentServiceSpec,
    Planner,
    PlannerInputs,
)


def _base_inputs(**overrides) -> PlannerInputs:
    base = dict(
        registered_agents={"metrics_agent", "log_agent", "k8s_agent"},
        agents_completed=["log_agent", "metrics_agent"],
        primary_service="payment",
        round=1,
        confidence=0.30,
        dependency_graph={
            "payment": ["db", "redis"],
            "db": ["storage"],
            "redis": [],
        },
    )
    base.update(overrides)
    return PlannerInputs(**base)


class TestUpstreamWalkTriggers:
    def test_walks_upstream_when_confidence_low_after_round_1(self):
        specs = Planner().upstream_walk(_base_inputs())
        services = {s.service for s in specs}
        assert "db" in services or "redis" in services

    def test_depth_2_reaches_storage(self):
        specs = Planner().upstream_walk(_base_inputs())
        services = {s.service for s in specs}
        assert "storage" in services

    def test_no_walk_when_confidence_sufficient(self):
        assert Planner().upstream_walk(_base_inputs(confidence=0.90)) == []

    def test_no_walk_on_round_0(self):
        assert Planner().upstream_walk(_base_inputs(round=0)) == []

    def test_no_walk_without_primary_service(self):
        assert Planner().upstream_walk(_base_inputs(primary_service=None)) == []

    def test_no_walk_without_graph(self):
        assert Planner().upstream_walk(_base_inputs(dependency_graph={})) == []

    def test_no_walk_when_service_has_no_upstreams(self):
        # redis has no deps in this graph
        assert Planner().upstream_walk(_base_inputs(primary_service="redis")) == []


class TestSpecShape:
    def test_each_upstream_gets_metrics_and_log(self):
        specs = Planner().upstream_walk(_base_inputs())
        for svc in {s.service for s in specs}:
            agents_for_svc = {s.agent for s in specs if s.service == svc}
            assert "metrics_agent" in agents_for_svc
            assert "log_agent" in agents_for_svc

    def test_unregistered_agents_are_skipped(self):
        specs = Planner().upstream_walk(
            _base_inputs(registered_agents={"metrics_agent"})
        )
        assert all(s.agent == "metrics_agent" for s in specs)

    def test_spec_is_frozen_dataclass(self):
        import dataclasses
        s = AgentServiceSpec(agent="metrics_agent", service="db")
        assert dataclasses.is_dataclass(s)


class TestDeterminism:
    def test_same_inputs_same_order(self):
        a = Planner().upstream_walk(_base_inputs())
        b = Planner().upstream_walk(_base_inputs())
        assert a == b


class TestExistingPathUnchanged:
    def test_planner_next_still_works_without_walk_inputs(self):
        """Task 4.4 must not regress Task 2.9's Planner.next contract."""
        minimal = PlannerInputs(
            registered_agents={"log_agent", "metrics_agent"},
            agents_completed=[],
        )
        assert Planner().next(minimal) == ["log_agent", "metrics_agent"]
