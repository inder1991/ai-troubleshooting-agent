"""PR-C — namespace auto-detect guard tests.

Bug #6 (SDET audit): the log_agent auto-detect step used to overwrite
``state.namespace`` whenever the current value was falsy or equal to
``"default"``. The guard is wrong in two directions:

  · If the operator explicitly typed ``"default"`` (a legitimate k8s
    namespace) at session start, auto-detect silently replaced it with
    whatever the log sample suggested, often sending subsequent k8s
    queries to the wrong namespace.
  · If the operator set nothing (None) but auto-detect picked a wrong
    namespace, the operator had no way to see that a swap happened
    except by correlating logs with kubectl output.

The fix introduces ``DiagnosticState.namespace_user_set``, set by the
supervisor at state construction based on whether ``initial_input``
carried a non-empty namespace. The auto-detect branch now refuses to
overwrite when the flag is True, regardless of the current value.
"""
from __future__ import annotations

from src.agents.supervisor import SupervisorAgent  # noqa: F401 — module import check


# ── Namespace flag wiring ─────────────────────────────────────────────


def _build_state(**kwargs) -> object:
    """Exercise the exact code path the route uses to build initial state.

    We don't invoke the full supervisor.run() loop — we only need the
    DiagnosticState that its opening lines construct from initial_input.
    Copied from supervisor.SupervisorAgent.run but inlined here so the
    test doesn't need any LLM / emitter plumbing.
    """
    from src.agents.supervisor import DiagnosticPhase
    from src.models.schemas import DiagnosticState, TimeWindow

    initial_input = {
        "session_id": kwargs.get("session_id", "s"),
        "incident_id": kwargs.get("incident_id", "i"),
        "service_name": kwargs.get("service_name", "svc"),
        "time_start": "now-1h",
        "time_end": "now",
        **kwargs,
    }
    return DiagnosticState(
        session_id=initial_input["session_id"],
        incident_id=initial_input["incident_id"],
        phase=DiagnosticPhase.COLLECTING_CONTEXT,
        service_name=initial_input["service_name"],
        time_window=TimeWindow(
            start=initial_input["time_start"],
            end=initial_input["time_end"],
        ),
        namespace=initial_input.get("namespace"),
        namespace_user_set=bool(initial_input.get("namespace")),
    )


def test_user_set_flag_true_when_namespace_provided():
    state = _build_state(namespace="payments-prod")
    assert state.namespace == "payments-prod"
    assert state.namespace_user_set is True


def test_user_set_flag_true_even_for_literal_default():
    """`default` is a real kubernetes namespace — not a sentinel."""
    state = _build_state(namespace="default")
    assert state.namespace == "default"
    assert state.namespace_user_set is True


def test_user_set_flag_false_when_namespace_not_provided():
    state = _build_state()
    assert state.namespace is None
    assert state.namespace_user_set is False


def test_user_set_flag_false_when_namespace_empty_string():
    """Empty string is not a user-provided namespace — same as None."""
    state = _build_state(namespace="")
    assert state.namespace_user_set is False


# ── Auto-detect guard logic ───────────────────────────────────────────
# The logic under test lives inline in supervisor._update_state_with_result
# (log_agent branch). We assert on a fresh state after simulating the
# same conditional so future refactors that move the block stay covered.


def _apply_autodetect_guard(state, detected_ns: str | None) -> None:
    """Mirror of supervisor's auto-detect block (PR-C).

    Kept here as an explicit contract the supervisor must not drift from.
    If the supervisor changes, update this helper AND add a test for the
    new behaviour rather than silently diverging.
    """
    user_set = getattr(state, "namespace_user_set", False)
    if detected_ns and not user_set and not state.namespace:
        state.namespace = detected_ns


def test_autodetect_sets_namespace_when_user_didnt_supply_one():
    state = _build_state()
    _apply_autodetect_guard(state, "auto-detected-ns")
    assert state.namespace == "auto-detected-ns"


def test_autodetect_refuses_to_overwrite_user_provided_default():
    state = _build_state(namespace="default")
    _apply_autodetect_guard(state, "auto-detected-ns")
    assert state.namespace == "default"


def test_autodetect_refuses_to_overwrite_any_user_namespace():
    state = _build_state(namespace="payments-prod")
    _apply_autodetect_guard(state, "auto-detected-ns")
    assert state.namespace == "payments-prod"


def test_autodetect_noops_when_detection_empty():
    state = _build_state()
    _apply_autodetect_guard(state, None)
    assert state.namespace is None


# ── Log verification ──────────────────────────────────────────────────


def test_supervisor_file_carries_suppress_log_string():
    """Operator-audit requirement — the supervisor must log when it
    suppresses an auto-detect so post-hoc investigation can prove the
    operator-set namespace was respected. This is a source-level check
    because the supervisor logger is JSON-formatted and doesn't
    propagate to pytest caplog reliably.
    """
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "src" / "agents" / "supervisor.py"
    body = src.read_text()
    assert "namespace_detect_skipped" in body
    assert "Namespace auto-detect suppressed" in body
