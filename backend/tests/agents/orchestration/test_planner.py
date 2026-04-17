"""Task 2.9 — Planner: deterministic next-agent selection."""
from src.agents.orchestration.planner import Planner, PlannerInputs


def _inputs(**kw) -> PlannerInputs:
    base = dict(
        registered_agents={"log_agent", "metrics_agent", "k8s_agent", "tracing_agent", "code_agent", "change_agent"},
        agents_completed=[],
        has_cluster=True,
        has_repo=True,
        has_trace_id=True,
    )
    base.update(kw)
    return PlannerInputs(**base)


def test_first_round_picks_log_agent_first():
    next_ = Planner().next(_inputs())
    assert next_[0] == "log_agent"


def test_returns_up_to_two_agents_per_round():
    next_ = Planner().next(_inputs())
    assert len(next_) <= 2


def test_completed_agents_are_skipped():
    next_ = Planner().next(_inputs(agents_completed=["log_agent", "metrics_agent"]))
    assert "log_agent" not in next_
    assert "metrics_agent" not in next_


def test_prior_failures_not_retried():
    next_ = Planner().next(_inputs(prior_failures={"log_agent"}))
    assert "log_agent" not in next_


def test_coverage_gaps_not_retried():
    next_ = Planner().next(_inputs(coverage_gaps={"k8s_agent": "no cluster configured"}))
    assert "k8s_agent" not in next_


def test_tracing_agent_requires_trace_id():
    next_ = Planner().next(
        _inputs(
            agents_completed=["log_agent", "metrics_agent", "k8s_agent"],
            has_trace_id=False,
        )
    )
    assert "tracing_agent" not in next_


def test_code_agent_requires_repo():
    next_ = Planner().next(
        _inputs(
            agents_completed=["log_agent", "metrics_agent", "k8s_agent", "tracing_agent"],
            has_repo=False,
        )
    )
    assert "code_agent" not in next_


def test_empty_when_all_agents_completed():
    all_completed = ["log_agent", "metrics_agent", "k8s_agent", "tracing_agent", "code_agent", "change_agent"]
    assert Planner().next(_inputs(agents_completed=all_completed)) == []


def test_unregistered_agents_are_skipped():
    next_ = Planner().next(_inputs(registered_agents={"metrics_agent"}))
    assert next_ == ["metrics_agent"]
