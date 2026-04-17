"""Task 2.9 — Reducer merges StepResults into a structured round payload."""
from src.agents.orchestration.dispatcher import StepResult
from src.agents.orchestration.reducer import Reducer


def _ok(agent: str, pins: list | None = None) -> StepResult:
    return StepResult(
        agent=agent,
        status="ok",
        value={"evidence_pins": pins or []},
    )


def _fail(agent: str, status: str = "error") -> StepResult:
    return StepResult(agent=agent, status=status, error="boom")


def test_reduce_collects_successful_agents():
    out = Reducer().reduce(
        [_ok("log_agent", [{"claim": "a"}]), _ok("metrics_agent")]
    )
    assert out.agents_completed == ["log_agent", "metrics_agent"]


def test_reduce_collects_failures_separately():
    out = Reducer().reduce([_ok("log_agent"), _fail("metrics_agent")])
    assert out.agents_completed == ["log_agent"]
    assert out.failed_agents == ["metrics_agent"]


def test_reduce_collects_pins_from_all_agents():
    out = Reducer().reduce(
        [
            _ok("log_agent", [{"claim": "a"}]),
            _ok("metrics_agent", [{"claim": "b"}, {"claim": "c"}]),
        ]
    )
    assert len(out.evidence_pins) == 3


def test_reduce_new_signal_true_only_when_pins_produced():
    assert Reducer().reduce([_ok("log_agent", [{"claim": "a"}])]).new_signal is True
    assert Reducer().reduce([_ok("log_agent", [])]).new_signal is False
    assert Reducer().reduce([_fail("log_agent")]).new_signal is False


def test_timeout_counts_as_failure():
    out = Reducer().reduce([_fail("log_agent", status="timeout")])
    assert out.failed_agents == ["log_agent"]


def test_empty_round():
    out = Reducer().reduce([])
    assert out.agents_completed == []
    assert out.failed_agents == []
    assert out.evidence_pins == []
    assert out.new_signal is False


def test_non_dict_value_produces_no_pins_but_still_succeeds():
    # Agents that return a non-dict value are still marked completed; the
    # reducer just contributes no pins from them.
    out = Reducer().reduce([StepResult(agent="log_agent", status="ok", value=42)])
    assert out.agents_completed == ["log_agent"]
    assert out.evidence_pins == []
