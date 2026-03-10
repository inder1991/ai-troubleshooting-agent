"""
Critic Ensemble: Deterministic pre-checks + LLM ensemble debate.
Stage 1 (this task): DeterministicValidator — 0 LLM calls.
"""

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
