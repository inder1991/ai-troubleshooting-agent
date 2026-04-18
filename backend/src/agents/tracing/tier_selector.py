"""3-tier model-cost cascade for TracingAgent.

Locked design:

  Tier 0 — **No LLM** (deterministic)
    Envoy response.flags gives a self-explanatory answer OR single-trace
    analysis with unambiguous failure. Zero LLM cost, ~500ms latency.

  Tier 1 — **Haiku** (cheap)
    Single-trace synthesis. Adds natural-language explanation on top of
    deterministic findings but doesn't need complex multi-step reasoning.
    ~$0.005/call.

  Tier 2 — **Sonnet** (default)
    Cross-trace consensus (multiple mined traces), ELK log reconstruction,
    ambiguous summarizer output, large post-summary spans, or rescue-mode.
    ~$0.016/call.

Model names are LOGICAL (cheap / default), resolved via ``key_resolver``
from the B.11 multi-key Anthropic store. Operator maps logical names to
actual Anthropic model IDs via the Settings UI — no chart change needed
when Anthropic ships new models.

Failures route UP the tiers only. A Tier 1 call returning low confidence
can retry at Tier 2. We never fall BACK to a cheaper tier to save cost at
the expense of quality — defeats the point.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.models.schemas import EnvoyFlagFinding, TierDecision


@dataclass
class TierSelectorInputs:
    """Deterministic signals the selector reads."""

    has_mined_multiple_traces: bool
    envoy_findings_count: int
    envoy_is_self_explanatory: bool
    elk_fallback_active: bool
    sampling_was_expected: bool  # False when tail_based & trace missing
    summarized_span_count: int
    summarizer_ambiguous_failure_point: bool
    has_any_error_span: bool


class TierSelector:
    """Pure-function tier selection. Twelve rules, ordered by specificity."""

    # Tunables (operator may override).
    min_confidence_for_tier_1_stay: int = 60
    tier_1_span_ceiling: int = 500

    @staticmethod
    def select(inputs: TierSelectorInputs) -> TierDecision:
        # Rule 1 — Envoy self-explanatory, no cross-trace work, no ELK → Tier 0.
        if (
            inputs.envoy_is_self_explanatory
            and not inputs.has_mined_multiple_traces
            and not inputs.elk_fallback_active
        ):
            return TierDecision(
                tier=0,
                rationale="envoy_flag_self_explanatory",
                model_key="none",
            )

        # Rule 2 — tail-sampling surprise (trace should have been there, isn't) → Tier 2.
        # Losing a tail-sampled trace IS itself diagnostic signal — needs careful reasoning.
        if not inputs.sampling_was_expected:
            return TierDecision(
                tier=2,
                rationale="tail_sampling_trace_missing_rescue_mode",
                model_key="default",
            )

        # Rule 3 — cross-trace consensus (3 mined traces) → always Tier 2 for reconciliation.
        if inputs.has_mined_multiple_traces:
            return TierDecision(
                tier=2,
                rationale="cross_trace_consensus_multi_trace",
                model_key="default",
            )

        # Rule 4 — ELK fallback path (log reconstruction is noisier, needs better reasoning).
        if inputs.elk_fallback_active:
            return TierDecision(
                tier=2,
                rationale="elk_fallback_low_signal_quality",
                model_key="default",
            )

        # Rule 5 — ambiguous failure point from summarizer → Tier 2.
        if inputs.summarizer_ambiguous_failure_point:
            return TierDecision(
                tier=2,
                rationale="summarizer_ambiguous_failure_point",
                model_key="default",
            )

        # Rule 6 — post-summary span count over Tier 1 ceiling → Tier 2.
        if inputs.summarized_span_count > TierSelector.tier_1_span_ceiling:
            return TierDecision(
                tier=2,
                rationale=(
                    f"post_summary_span_count_over_tier1_ceiling "
                    f"({inputs.summarized_span_count} > {TierSelector.tier_1_span_ceiling})"
                ),
                model_key="default",
            )

        # Rule 7 — we have envoy findings (just not self-explanatory) +
        # single trace — Tier 1 can handle the synthesis.
        if inputs.envoy_findings_count >= 1:
            return TierDecision(
                tier=1,
                rationale="single_trace_with_envoy_hint",
                model_key="cheap",
            )

        # Rule 8 — single trace, small, has an error — Tier 1 is enough.
        if inputs.has_any_error_span:
            return TierDecision(
                tier=1,
                rationale="single_trace_unambiguous_failure",
                model_key="cheap",
            )

        # Rule 9 — single trace, small, no errors → still Tier 1 (user wants
        # a flow analysis / latency story; doesn't need Sonnet).
        return TierDecision(
            tier=1,
            rationale="single_trace_latency_flow_analysis",
            model_key="cheap",
        )

    @staticmethod
    def escalate_on_low_confidence(
        previous: TierDecision, returned_confidence: int
    ) -> TierDecision | None:
        """Return a Tier 2 retry decision when Tier 1 returned low confidence.

        Returns None if no escalation is warranted (already at Tier 2, or
        confidence is acceptable).
        """
        if previous.tier >= 2:
            return None
        if returned_confidence >= TierSelector.min_confidence_for_tier_1_stay:
            return None
        return TierDecision(
            tier=2,
            rationale=(
                f"tier1_confidence_below_threshold "
                f"({returned_confidence} < {TierSelector.min_confidence_for_tier_1_stay})"
            ),
            model_key="default",
        )

    @staticmethod
    def from_envoy_findings(
        findings: list[EnvoyFlagFinding],
        *,
        has_mined_multiple_traces: bool,
        elk_fallback_active: bool,
        sampling_was_expected: bool,
        summarized_span_count: int,
        summarizer_ambiguous_failure_point: bool,
        has_any_error_span: bool,
    ) -> TierDecision:
        """Convenience wrapper — derives envoy-related flags from findings list."""
        from src.agents.tracing.envoy_flags import EnvoyResponseFlagsMatcher

        inputs = TierSelectorInputs(
            has_mined_multiple_traces=has_mined_multiple_traces,
            envoy_findings_count=len(findings),
            envoy_is_self_explanatory=EnvoyResponseFlagsMatcher.is_self_explanatory(findings),
            elk_fallback_active=elk_fallback_active,
            sampling_was_expected=sampling_was_expected,
            summarized_span_count=summarized_span_count,
            summarizer_ambiguous_failure_point=summarizer_ambiguous_failure_point,
            has_any_error_span=has_any_error_span,
        )
        return TierSelector.select(inputs)
