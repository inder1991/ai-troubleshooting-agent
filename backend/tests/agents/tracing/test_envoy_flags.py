"""EnvoyResponseFlagsMatcher unit tests."""
from __future__ import annotations

from src.agents.tracing.envoy_flags import EnvoyResponseFlagsMatcher
from src.models.schemas import SpanInfo


def _span(**kw) -> SpanInfo:
    defaults = dict(span_id="s1", service_name="svc", operation_name="op",
                    duration_ms=100.0, status="ok", tags={})
    defaults.update(kw)
    return SpanInfo(**defaults)


def test_match_uh():
    span = _span(tags={"response.flags": "UH", "upstream.cluster": "inventory"})
    f = EnvoyResponseFlagsMatcher.match_span(span)
    assert f is not None
    assert f.flag == "UH"
    assert "no healthy" in f.human_summary.lower()
    assert f.upstream_cluster == "inventory"


def test_match_returns_none_when_no_flag():
    assert EnvoyResponseFlagsMatcher.match_span(_span()) is None


def test_priority_urx_wins_over_uh():
    """When multiple flags coexist, retry-limit-exceeded wins over no-healthy-upstream."""
    span = _span(tags={"response.flags": "UH,URX"})
    f = EnvoyResponseFlagsMatcher.match_span(span)
    assert f is not None
    assert f.flag == "URX"


def test_uo_is_circuit_breaker():
    span = _span(tags={"response.flags": "UO"})
    f = EnvoyResponseFlagsMatcher.match_span(span)
    assert f is not None and "circuit breaker" in f.human_summary.lower()


def test_unknown_flag_still_handled_gracefully():
    span = _span(tags={"response.flags": "XYZ"})
    # Not crash; matcher returns None when flag not in table.
    f = EnvoyResponseFlagsMatcher.match_span(span)
    # _pick_primary_flag returns first unknown; _FLAG_TABLE lookup misses → None
    assert f is None


def test_alternative_key_name():
    """Some customers flatten to 'response_flags' without dot."""
    span = _span(tags={"response_flags": "UT"})
    f = EnvoyResponseFlagsMatcher.match_span(span)
    assert f is not None and f.flag == "UT"


def test_scan_trace_finds_all():
    spans = [
        _span(span_id="s1", tags={"response.flags": "UH"}),
        _span(span_id="s2", tags={}),
        _span(span_id="s3", tags={"response.flags": "UT"}),
    ]
    findings = EnvoyResponseFlagsMatcher.scan_trace(spans)
    assert len(findings) == 2
    assert {f.flag for f in findings} == {"UH", "UT"}


def test_self_explanatory_true_for_single_decisive_flag():
    finding = EnvoyResponseFlagsMatcher.match_span(_span(tags={"response.flags": "UH"}))
    assert EnvoyResponseFlagsMatcher.is_self_explanatory([finding]) is True


def test_self_explanatory_false_for_multiple():
    f1 = EnvoyResponseFlagsMatcher.match_span(_span(span_id="a", tags={"response.flags": "UH"}))
    f2 = EnvoyResponseFlagsMatcher.match_span(_span(span_id="b", tags={"response.flags": "UT"}))
    assert EnvoyResponseFlagsMatcher.is_self_explanatory([f1, f2]) is False


def test_self_explanatory_false_for_dc():
    """Downstream cancel isn't a clean diagnosis — needs LLM context."""
    f = EnvoyResponseFlagsMatcher.match_span(_span(tags={"response.flags": "DC"}))
    assert EnvoyResponseFlagsMatcher.is_self_explanatory([f]) is False
