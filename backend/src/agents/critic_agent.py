import asyncio
import json
import re as _re
from typing import Optional

from src.models.schemas import (
    Finding, CriticVerdict, DiagnosticState, Breadcrumb, TokenUsage, EvidencePin
)
from src.utils.llm_client import AnthropicClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class CriticAgent:
    """Read-only agent that cross-validates findings against other agent data."""

    def __init__(self, llm_client=None):
        self.agent_name = "critic"
        self.llm_client = llm_client or AnthropicClient(agent_name="critic")

    async def validate(self, finding: Finding, state: DiagnosticState) -> CriticVerdict:
        """Validate a finding against all available evidence in the diagnostic state."""
        logger.info("Critic started", extra={"agent_name": "critic", "action": "validate_start", "extra": {"finding": finding.finding_id}})
        context = self._build_context(finding, state)

        try:
            response = await asyncio.wait_for(
                self.llm_client.chat(
                    prompt=context,
                    system="""You are a Critic Agent. Your ONLY job is to validate or challenge findings from other agents.

Rules:
1. You have NO write access — you can only read and analyze existing data
2. Check the finding against data from ALL other agents
3. Look for contradictions, inconsistencies, or unsupported claims
4. If evidence supports the finding, verdict is "validated"
5. If evidence contradicts the finding, verdict is "challenged"
6. If there's not enough evidence either way, verdict is "insufficient_data"

Respond with JSON:
{
    "verdict": "validated|challenged|insufficient_data",
    "reasoning": "Detailed explanation",
    "recommendation": "What to do next (if challenged)",
    "confidence_in_verdict": 85
}""",
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Critic validate() timed out after 30s", extra={
                "agent_name": "critic", "action": "validate_timeout",
                "extra": {"finding": finding.finding_id},
            })
            return CriticVerdict(
                finding_id=finding.finding_id,
                agent_source=finding.agent_name,
                verdict="insufficient_data",
                reasoning="Critic validation timed out after 30s",
                recommendation="Retry validation or increase timeout",
                confidence_in_verdict=0,
            )

        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response.text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response.text)

            verdict_obj = CriticVerdict(
                finding_id=finding.finding_id,
                agent_source=finding.agent_name,
                verdict=data.get("verdict", "insufficient_data"),
                reasoning=data.get("reasoning", "Unable to parse response"),
                recommendation=data.get("recommendation"),
                confidence_in_verdict=min(max(data.get("confidence_in_verdict", 50), 0), 100),
            )
            logger.info("Verdict issued", extra={"agent_name": "critic", "action": "verdict", "extra": {"finding": finding.finding_id, "verdict": verdict_obj.verdict, "confidence": verdict_obj.confidence_in_verdict}})
            return verdict_obj
        except json.JSONDecodeError:
            logger.warning("Failed to parse Critic JSON response", extra={
                "agent_name": "critic", "action": "parse_error",
                "extra": {"finding": finding.finding_id, "response_preview": response.text[:200]},
            })
            return CriticVerdict(
                finding_id=finding.finding_id,
                agent_source=finding.agent_name,
                verdict="insufficient_data",
                reasoning=f"Failed to parse Critic response: {response.text[:200]}",
                confidence_in_verdict=30,
            )
        except Exception as e:
            logger.error("Critic validation unexpected error", extra={
                "agent_name": "critic", "action": "validation_error",
                "extra": {"finding": finding.finding_id, "error": str(e)},
            })
            return CriticVerdict(
                finding_id=finding.finding_id,
                agent_source=finding.agent_name,
                verdict="insufficient_data",
                reasoning=f"Critic validation error: {str(e)[:200]}",
                confidence_in_verdict=20,
            )

    async def validate_delta(
        self,
        new_pin: EvidencePin,
        existing_pins: list[EvidencePin],
        causal_chains: list,
    ) -> dict:
        """Delta-validate a new evidence pin against existing pins.

        Returns a dict with keys:
            validation_status: "validated" | "rejected"
            causal_role: "root_cause" | "cascading_symptom" | "correlated" | "informational"
            confidence: float
            reasoning: str
            contradictions: list[str]
        """
        _default = {
            "validation_status": "validated",
            "causal_role": "informational",
            "confidence": new_pin.confidence,
            "reasoning": "Default: accepted without LLM validation.",
            "contradictions": [],
        }

        prompt = self._build_delta_context(new_pin, existing_pins, causal_chains)

        try:
            response = await asyncio.wait_for(
                self.llm_client.chat(
                    prompt=prompt,
                    system=(
                        "You are a Critic Agent performing delta revalidation. A new evidence pin "
                        "has been added to an ongoing investigation. Your job is to evaluate whether "
                        "this new evidence supports, contradicts, or merely correlates with existing "
                        "findings.\n\n"
                        "Respond with ONLY a JSON object (no markdown, no extra text):\n"
                        "{\n"
                        '  "validation_status": "validated" or "rejected",\n'
                        '  "causal_role": "root_cause" | "cascading_symptom" | "correlated" | "informational",\n'
                        '  "confidence": <float 0-1>,\n'
                        '  "reasoning": "<explanation>",\n'
                        '  "contradictions": ["<list of contradictions, empty if none>"]\n'
                        "}"
                    ),
                ),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.error("Critic validate_delta() timed out after 30s", extra={
                "agent_name": "critic", "action": "delta_timeout",
                "extra": {"pin_id": new_pin.id},
            })
            _default["validation_status"] = "timeout"
            _default["reasoning"] = "Critic delta validation timed out"
            return _default
        except Exception as e:
            logger.error("Critic delta validation LLM error", extra={
                "agent_name": "critic", "action": "delta_llm_error",
                "extra": {"pin_id": new_pin.id, "error": str(e)},
            })
            return _default

        try:
            # Try to extract JSON from response (handles markdown fences, etc.)
            json_match = _re.search(r'\{[\s\S]*\}', response.text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response.text)

            return {
                "validation_status": data.get("validation_status", "validated"),
                "causal_role": data.get("causal_role", "informational"),
                "confidence": float(data.get("confidence", new_pin.confidence)),
                "reasoning": data.get("reasoning", "No reasoning provided."),
                "contradictions": data.get("contradictions", []),
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning("Failed to parse Critic delta JSON response", extra={
                "agent_name": "critic", "action": "delta_parse_error",
                "extra": {"pin_id": new_pin.id, "response_preview": response.text[:200]},
            })
            return _default

    def _build_delta_context(
        self,
        new_pin: EvidencePin,
        existing_pins: list[EvidencePin],
        causal_chains: list,
    ) -> str:
        """Build prompt context for delta validation."""
        parts = [
            "## New Evidence Pin to Validate",
            f"ID: {new_pin.id}",
            f"Claim: {new_pin.claim}",
            f"Source tool: {new_pin.source_tool}",
            f"Evidence type: {new_pin.evidence_type}",
            f"Confidence: {new_pin.confidence}",
            f"Severity: {new_pin.severity}",
            f"Domain: {new_pin.domain}",
            f"Source: {new_pin.source}",
            f"Triggered by: {new_pin.triggered_by}",
        ]

        if new_pin.raw_output:
            parts.append(f"Raw output (truncated): {new_pin.raw_output[:2000]}")

        if existing_pins:
            parts.append(f"\n## Existing Evidence Pins ({len(existing_pins)} total)")
            for ep in existing_pins[:10]:  # Limit to 10 for prompt size
                parts.append(
                    f"- [{ep.evidence_type}] {ep.claim} "
                    f"(confidence={ep.confidence}, severity={ep.severity}, "
                    f"causal_role={ep.causal_role}, validation={ep.validation_status})"
                )
        else:
            parts.append("\n## Existing Evidence Pins: None (this is the first pin)")

        if causal_chains:
            parts.append(f"\n## Causal Chains ({len(causal_chains)} total)")
            for chain in causal_chains[:5]:
                parts.append(f"- {chain}")

        return "\n".join(parts)

    def _build_context(self, finding: Finding, state: DiagnosticState) -> str:
        """Build context string from the finding and all available agent data."""
        parts = [
            f"## Finding to Validate",
            f"Agent: {finding.agent_name}",
            f"Category: {finding.category}",
            f"Summary: {finding.summary}",
            f"Confidence: {finding.confidence_score}",
            f"Severity: {finding.severity}",
        ]

        if finding.breadcrumbs:
            parts.append("\n## Evidence from this finding:")
            for b in finding.breadcrumbs[:5]:
                parts.append(f"- [{b.source_type}] {b.action}: {b.raw_evidence} (Source: {b.source_reference})")

        # Add data from other agents
        if state.log_analysis and finding.agent_name != "log_agent":
            parts.append("\n## Log Analysis Data:")
            parts.append(f"Primary pattern: {state.log_analysis.primary_pattern.exception_type} "
                        f"(frequency: {state.log_analysis.primary_pattern.frequency}, "
                        f"confidence: {state.log_analysis.primary_pattern.confidence_score})")
            if state.log_analysis.negative_findings:
                parts.append("Negative findings:")
                for nf in state.log_analysis.negative_findings[:3]:
                    parts.append(f"  - {nf.what_was_checked}: {nf.result}")

        if state.metrics_analysis and finding.agent_name != "metrics_agent":
            parts.append("\n## Metrics Data:")
            for a in state.metrics_analysis.anomalies[:3]:
                parts.append(f"- {a.metric_name}: baseline={a.baseline_value}, peak={a.peak_value}, severity={a.severity}")
            if state.metrics_analysis.negative_findings:
                for nf in state.metrics_analysis.negative_findings[:3]:
                    parts.append(f"  - Checked: {nf.what_was_checked}: {nf.result}")

        if state.k8s_analysis and finding.agent_name != "k8s_agent":
            parts.append("\n## K8s Data:")
            parts.append(f"CrashLoop: {state.k8s_analysis.is_crashloop}")
            parts.append(f"Restarts: {state.k8s_analysis.total_restarts_last_hour}")
            if state.k8s_analysis.resource_mismatch:
                parts.append(f"Resource mismatch: {state.k8s_analysis.resource_mismatch}")

        if state.trace_analysis and finding.agent_name != "tracing_agent":
            parts.append("\n## Tracing Data:")
            parts.append(f"Total services: {state.trace_analysis.total_services}")
            if state.trace_analysis.failure_point:
                fp = state.trace_analysis.failure_point
                parts.append(f"Failure point: {fp.service_name} - {fp.operation_name} ({fp.status})")

        # Add all negative findings from other agents
        other_negatives = [nf for nf in state.all_negative_findings if nf.agent_name != finding.agent_name]
        if other_negatives:
            parts.append("\n## Negative Findings from Other Agents:")
            for nf in other_negatives[:5]:
                parts.append(f"- [{nf.agent_name}] {nf.what_was_checked}: {nf.result} → {nf.implication}")

        return "\n".join(parts)

    def get_token_usage(self) -> TokenUsage:
        return self.llm_client.get_total_usage()

    @staticmethod
    def _evaluate_finding(finding: Finding, **agent_contexts) -> CriticVerdict:
        """Simple rule-based evaluation (for testing without LLM).

        This is a static helper for offline validation. The `validate()` method uses the LLM instead.
        """
        verdict = "validated"
        reasoning_parts = []

        metrics_context = agent_contexts.get("metrics_context", {})
        k8s_context = agent_contexts.get("k8s_context", {})

        # Check for DB-related findings against metrics
        if "database" in finding.category.lower() or "db" in finding.category.lower():
            if "down" in finding.summary.lower():
                db_cpu = metrics_context.get("db_cpu", {})
                if db_cpu.get("status") == "healthy" and db_cpu.get("value", 100) < 20:
                    verdict = "challenged"
                    reasoning_parts.append(
                        f"Metrics show DB CPU at {db_cpu.get('value')}% (healthy) — contradicts 'DB is down' claim"
                    )

        # Check OOM findings against K8s data
        if "oom" in finding.category.lower():
            oom_kills = k8s_context.get("oom_kills", 0)
            memory_percent = k8s_context.get("memory_percent", 0)
            if oom_kills > 0 and memory_percent > 80:
                verdict = "validated"
                reasoning_parts.append(
                    f"K8s confirms {oom_kills} OOM kills, memory at {memory_percent}% — consistent with finding"
                )
            elif oom_kills == 0:
                verdict = "challenged"
                reasoning_parts.append("K8s shows zero OOM kills — contradicts OOM finding")

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "No contradicting evidence found"

        return CriticVerdict(
            finding_id=finding.finding_id,
            agent_source=finding.agent_name,
            verdict=verdict,
            reasoning=reasoning,
            confidence_in_verdict=80 if verdict != "insufficient_data" else 40,
        )
