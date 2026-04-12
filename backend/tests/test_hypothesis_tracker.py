import pytest
from src.agents.hypothesis_tracker import HypothesisTracker


def test_first_hypothesis_allowed():
    tracker = HypothesisTracker(max_re_dispatches=2)
    allowed = tracker.should_dispatch("k8s_agent", "Check istio-proxy memory")
    assert allowed is True


def test_duplicate_hypothesis_blocked():
    tracker = HypothesisTracker(max_re_dispatches=2)
    tracker.record("k8s_agent", "Check istio-proxy memory")
    allowed = tracker.should_dispatch("k8s_agent", "Check istio-proxy memory")
    assert allowed is False


def test_same_hypothesis_different_agent_allowed():
    tracker = HypothesisTracker(max_re_dispatches=2)
    tracker.record("k8s_agent", "Check memory pressure")
    allowed = tracker.should_dispatch("metrics_agent", "Check memory pressure")
    assert allowed is True


def test_max_re_dispatches_enforced():
    tracker = HypothesisTracker(max_re_dispatches=2)
    tracker.record("k8s_agent", "hypothesis A")
    tracker.record("metrics_agent", "hypothesis B")
    allowed = tracker.should_dispatch("log_agent", "hypothesis C")
    assert allowed is False


def test_budget_exhaustion_blocks():
    tracker = HypothesisTracker(max_re_dispatches=5)
    allowed = tracker.should_dispatch("k8s_agent", "test", budget_exhausted=True)
    assert allowed is False


def test_similar_hypothesis_detected():
    tracker = HypothesisTracker(max_re_dispatches=3)
    tracker.record("k8s_agent", "Check if OOM was in the istio-proxy sidecar")
    allowed = tracker.should_dispatch("k8s_agent", "Check OOM in istio-proxy sidecar container")
    assert allowed is False


def test_investigation_graph_tracks_all():
    tracker = HypothesisTracker(max_re_dispatches=5)
    tracker.record("k8s_agent", "hyp A")
    tracker.record("metrics_agent", "hyp B")
    graph = tracker.investigation_graph()
    assert ("k8s_agent", "hyp A") in graph
    assert ("metrics_agent", "hyp B") in graph
    assert len(graph) == 2
