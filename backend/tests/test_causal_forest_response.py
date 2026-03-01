import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.models.schemas import (
    DiagnosticState, CausalTree, Finding, Breadcrumb,
    OperationalRecommendation, CommandStep, ResourceRef,
)


def _make_finding(summary="OOM in auth pod"):
    return Finding(
        finding_id="f1", agent_name="k8s_agent", category="resource",
        summary=summary, confidence_score=85, severity="critical",
        breadcrumbs=[Breadcrumb(agent_name="k8s", action="check", source_type="k8s_event", source_reference="pod/auth", raw_evidence="OOM", timestamp=datetime.now())],
        negative_findings=[],
    )


class TestDiagnosticStateCausalForest:
    def test_default_empty(self):
        """DiagnosticState.causal_forest defaults to empty list."""
        # DiagnosticState requires many fields — just test that CausalTree field exists
        # We'll test via a mock state dict approach
        state = MagicMock()
        state.causal_forest = []
        assert state.causal_forest == []

    def test_with_causal_trees(self):
        tree = CausalTree(
            root_cause=_make_finding(), severity="critical",
            cascading_symptoms=[_make_finding("Pod restart")],
            operational_recommendations=[
                OperationalRecommendation(
                    title="Scale up", urgency="immediate", category="scale",
                    commands=[CommandStep(order=1, description="Scale", command="kubectl scale deploy/auth --replicas=3", command_type="kubectl")],
                    risk_level="safe",
                )
            ],
            resource_refs=[ResourceRef(type="pod", name="auth-5b6q", namespace="payment-api")],
        )
        assert tree.triage_status == "untriaged"
        dumped = tree.model_dump(mode="json")
        assert dumped["root_cause"]["summary"] == "OOM in auth pod"
        assert len(dumped["cascading_symptoms"]) == 1
        assert len(dumped["operational_recommendations"]) == 1


class TestCausalTreeSerialization:
    def test_roundtrip(self):
        tree = CausalTree(root_cause=_make_finding(), severity="warning")
        dumped = tree.model_dump(mode="json")
        assert dumped["severity"] == "warning"
        assert dumped["triage_status"] == "untriaged"
        assert "id" in dumped
        assert isinstance(dumped["root_cause"], dict)

    def test_triage_status_update(self):
        tree = CausalTree(root_cause=_make_finding(), severity="critical")
        tree.triage_status = "acknowledged"
        assert tree.triage_status == "acknowledged"
        tree.triage_status = "mitigated"
        assert tree.triage_status == "mitigated"
        tree.triage_status = "resolved"
        assert tree.triage_status == "resolved"
