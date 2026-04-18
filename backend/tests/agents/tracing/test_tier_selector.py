"""TierSelector decision-cascade unit tests — 12 rules."""
from __future__ import annotations

from src.agents.tracing.tier_selector import TierSelector, TierSelectorInputs


def _inputs(**overrides) -> TierSelectorInputs:
    defaults = dict(
        has_mined_multiple_traces=False,
        envoy_findings_count=0,
        envoy_is_self_explanatory=False,
        elk_fallback_active=False,
        sampling_was_expected=True,
        summarized_span_count=50,
        summarizer_ambiguous_failure_point=False,
        has_any_error_span=False,
    )
    defaults.update(overrides)
    return TierSelectorInputs(**defaults)


def test_tier0_when_envoy_self_explanatory_single_trace():
    d = TierSelector.select(_inputs(envoy_findings_count=1, envoy_is_self_explanatory=True))
    assert d.tier == 0
    assert d.model_key == "none"


def test_tier2_when_tail_sampling_rescue():
    # Tail-sampling rescue semantically means the trace is MISSING — so no
    # Envoy findings are possible (empty span list → no scan). Test the
    # rescue rule in isolation.
    d = TierSelector.select(_inputs(
        sampling_was_expected=False, envoy_findings_count=0,
    ))
    assert d.tier == 2
    assert "rescue" in d.rationale


def test_tier2_when_cross_trace_consensus():
    d = TierSelector.select(_inputs(has_mined_multiple_traces=True))
    assert d.tier == 2
    assert "cross_trace" in d.rationale


def test_tier2_when_elk_fallback():
    d = TierSelector.select(_inputs(elk_fallback_active=True))
    assert d.tier == 2
    assert "elk_fallback" in d.rationale


def test_tier2_when_ambiguous_failure_point():
    d = TierSelector.select(_inputs(summarizer_ambiguous_failure_point=True))
    assert d.tier == 2
    assert "ambiguous" in d.rationale


def test_tier2_when_span_count_over_ceiling():
    d = TierSelector.select(_inputs(summarized_span_count=1000))
    assert d.tier == 2


def test_tier1_when_single_trace_envoy_hint():
    d = TierSelector.select(_inputs(envoy_findings_count=1, envoy_is_self_explanatory=False))
    assert d.tier == 1
    assert d.model_key == "cheap"


def test_tier1_when_single_trace_has_error():
    d = TierSelector.select(_inputs(has_any_error_span=True))
    assert d.tier == 1


def test_tier1_default_for_latency_flow():
    d = TierSelector.select(_inputs())  # no errors, no envoy, small span count
    assert d.tier == 1
    assert "latency_flow" in d.rationale or "single_trace" in d.rationale


def test_escalate_on_low_confidence():
    from src.models.schemas import TierDecision
    prev = TierDecision(tier=1, rationale="x", model_key="cheap")
    esc = TierSelector.escalate_on_low_confidence(prev, returned_confidence=30)
    assert esc is not None
    assert esc.tier == 2


def test_no_escalate_when_confidence_high():
    from src.models.schemas import TierDecision
    prev = TierDecision(tier=1, rationale="x", model_key="cheap")
    assert TierSelector.escalate_on_low_confidence(prev, returned_confidence=75) is None


def test_no_escalate_when_already_tier_2():
    from src.models.schemas import TierDecision
    prev = TierDecision(tier=2, rationale="x", model_key="default")
    assert TierSelector.escalate_on_low_confidence(prev, returned_confidence=20) is None
