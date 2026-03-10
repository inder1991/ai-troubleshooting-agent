"""
Critic Ensemble: Deterministic pre-checks + LLM ensemble debate.
Stage 1: DeterministicValidator — 0 LLM calls.
Stage 2: EnsembleCritic — Advocate/Challenger/Retriever/Judge.
"""
import json
import logging

logger = logging.getLogger(__name__)

INCIDENT_INVARIANTS = [
    {"name": "pod_cannot_cause_etcd", "cause_type": "k8s_event", "cause_contains": "pod", "effect_type": "error_event", "effect_contains": "etcd"},
    {"name": "app_error_cannot_cause_node_failure", "cause_type": "error_event", "cause_contains": "application", "effect_type": "k8s_event", "effect_contains": "node"},
]

class DeterministicValidator:
    """Stage 1: deterministic pre-checks with 0 LLM calls."""

    def validate(self, pin: dict, graph_nodes: dict, graph_edges: list, existing_pins: list) -> dict:
        violations = []

        if not pin.get("claim") or not pin.get("source_agent"):
            violations.append("schema_incomplete")

        caused_id = pin.get("caused_node_id")
        if caused_id and caused_id in graph_nodes:
            pin_ts = pin.get("timestamp", 0)
            effect_ts = graph_nodes[caused_id].get("timestamp", 0)
            if pin_ts and effect_ts and pin_ts > effect_ts:
                violations.append("temporal_violation")

        pin_service = pin.get("service")
        pin_role = pin.get("causal_role")
        for existing in existing_pins:
            if (existing.get("validation_status") == "validated"
                    and existing.get("service") == pin_service
                    and pin_service
                    and existing.get("causal_role") != pin_role
                    and existing.get("causal_role") in ("root_cause", "cascading_symptom")
                    and pin_role in ("informational",)):
                violations.append(f"contradicts:{existing.get('pin_id', 'unknown')}")

        if violations:
            return {"status": "hard_reject", "violations": violations}
        return {"status": "pass"}


ADVOCATE_SYSTEM = """You are an advocate in an incident investigation debate.
Argue why this finding is valid and significant. Reference specific evidence.
Be thorough but concise (max 200 words)."""

CHALLENGER_SYSTEM = """You are a challenger in an incident investigation debate.
Find contradictions, alternative explanations, or missing evidence.
Be specific about what data would disprove this finding (max 200 words)."""

JUDGE_SYSTEM = """You are a judge in an incident investigation debate.
Read the advocate, challenger, and additional evidence. Produce a structured JSON verdict.

Output ONLY valid JSON matching this schema:
{
  "verdict": "validated | challenged | insufficient_data",
  "confidence": 0.0-1.0,
  "causal_role": "root_cause | cascading_symptom | correlated | informational",
  "reasoning": "one sentence explanation",
  "supporting_evidence": ["node_id_1"],
  "contradictions": ["description"],
  "graph_edges": [{"source_node_id":"n-x","target_node_id":"n-y","edge_type":"causes","confidence":0.8,"reasoning":"why"}]
}"""


class EnsembleCritic:
    """Four-role debate: Advocate, Challenger, Evidence Retriever, Judge."""

    def __init__(self, llm_client, model: str = "claude-sonnet-4-20250514"):
        self.llm = llm_client
        self.model = model
        self.deterministic = DeterministicValidator()

    async def validate(self, finding: dict, state: dict, graph: dict) -> dict:
        # Stage 1: Deterministic pre-check
        pre = self.deterministic.validate(
            finding, graph.get("nodes", {}), graph.get("edges", []),
            state.get("all_findings", [])
        )
        if pre["status"] == "hard_reject":
            return {
                "verdict": "challenged",
                "confidence": 0.95,
                "reasoning": f"Deterministic rejection: {pre['violations']}",
                "causal_role": "informational",
                "supporting_evidence": [],
                "contradictions": pre["violations"],
                "graph_edges": [],
            }

        evidence_context = self._build_evidence_context(finding, state)

        # Stage 2: Four-role debate
        advocate_result = await self.llm.chat(
            system=ADVOCATE_SYSTEM,
            messages=[{"role": "user", "content": evidence_context}],
            model=self.model, temperature=0.0,
        )

        challenger_result = await self.llm.chat(
            system=CHALLENGER_SYSTEM,
            messages=[{"role": "user", "content": evidence_context}],
            model=self.model, temperature=0.3,
        )

        retriever_result = await self._run_evidence_retriever(
            advocate_result, challenger_result, evidence_context, state
        )

        judge_result = await self.llm.chat(
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": (
                f"ADVOCATE:\n{advocate_result}\n\n"
                f"CHALLENGER:\n{challenger_result}\n\n"
                f"ADDITIONAL EVIDENCE:\n{retriever_result}\n\n"
                f"RAW EVIDENCE:\n{evidence_context}"
            )}],
            model=self.model, temperature=0.0,
        )

        return self._parse_judge_output(judge_result)

    async def _run_evidence_retriever(self, advocate: str, challenger: str,
                                       context: str, state: dict) -> str:
        """Placeholder for retriever — will be wired to real tools in Phase 2."""
        return "No additional evidence retrieved."

    def _build_evidence_context(self, finding: dict, state: dict) -> str:
        sections = [f"FINDING UNDER REVIEW:\n{json.dumps(finding, default=str)}"]
        related = [f for f in state.get("all_findings", []) if f != finding][:5]
        if related:
            sections.append(f"RELATED FINDINGS:\n{json.dumps(related, default=str)[:3000]}")
        return "\n\n".join(sections)

    def _parse_judge_output(self, raw: str) -> dict:
        try:
            text = raw.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse judge output, defaulting to insufficient_data")
            return {
                "verdict": "insufficient_data",
                "confidence": 0.3,
                "causal_role": "informational",
                "reasoning": "Judge output could not be parsed",
                "supporting_evidence": [],
                "contradictions": [],
                "graph_edges": [],
            }
