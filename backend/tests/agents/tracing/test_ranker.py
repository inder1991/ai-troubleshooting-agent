"""TraceRanker scoring + top-N policy tests."""
from __future__ import annotations

from src.agents.tracing.ranker import RankerConfig, SymptomHints, TraceRanker
from src.models.schemas import TraceSummary


def _summary(tid, dur=100.0, spans=10, errs=0, svc="x") -> TraceSummary:
    return TraceSummary(
        trace_id=tid, root_service=svc, root_operation="/op",
        start_time_us=1_700_000_000_000_000, duration_ms=dur,
        span_count=spans, error_count=errs,
    )


def test_empty_input():
    assert TraceRanker().rank([]) == []


def test_error_trace_beats_healthy():
    healthy = _summary("h", dur=100.0, errs=0)
    errored = _summary("e", dur=100.0, errs=1)
    ranked = TraceRanker().rank([healthy, errored], SymptomHints(expecting_errors=True))
    assert ranked[0].summary.trace_id == "e"


def test_latency_z_score_breaks_ties():
    t_normal = _summary("n", dur=100.0)
    t_slow = _summary("s", dur=500.0)
    t_slower = _summary("s2", dur=1000.0)
    ranked = TraceRanker().rank([t_normal, t_slow, t_slower],
                                SymptomHints(expecting_errors=False))
    assert ranked[0].summary.trace_id == "s2"


def test_top_n_limits():
    cands = [_summary(f"t{i}") for i in range(10)]
    ranked = TraceRanker(RankerConfig(top_n=3)).rank(cands)
    assert len(ranked) == 3


def test_error_representation_in_top_n():
    """Top-N must include at least one error-carrying trace when any exist."""
    healthy = [_summary(f"h{i}", dur=100.0 * (10 - i)) for i in range(5)]  # durations 1000..200
    errored = [_summary("e1", dur=50.0, errs=1)]  # low latency, has error
    cands = healthy + errored
    ranked = TraceRanker(RankerConfig(top_n=3)).rank(
        cands, SymptomHints(expecting_errors=True)
    )
    picked_ids = [r.summary.trace_id for r in ranked]
    assert "e1" in picked_ids, "error trace should be surfaced in top-N"


def test_demotes_error_free_traces_under_error_symptom():
    healthy = _summary("h", dur=500.0)
    errored = _summary("e", dur=100.0, errs=1)
    ranked = TraceRanker().rank([healthy, errored], SymptomHints(expecting_errors=True))
    assert ranked[0].summary.trace_id == "e"
