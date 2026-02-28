"""Tests for War Room v2 data models (ResourceRef, CommandStep, OperationalRecommendation, CausalTree)."""

import pytest
from datetime import datetime
from pydantic import ValidationError
from src.models.schemas import (
    ResourceRef,
    CommandStep,
    OperationalRecommendation,
    CausalTree,
    Finding,
    EvidencePin,
    Breadcrumb,
    NegativeFinding,
    CorrelatedSignalGroup,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    finding_id: str = "f-001",
    agent_name: str = "log_agent",
    category: str = "error_pattern",
    summary: str = "OOMKilled in payment-service pod",
    confidence_score: int = 85,
    severity: str = "critical",
) -> Finding:
    """Create a minimal Finding for use in tests."""
    breadcrumb = Breadcrumb(
        agent_name=agent_name,
        action="analyzed logs",
        source_type="log",
        source_reference="elk:payment-service-*",
        raw_evidence="java.lang.OutOfMemoryError: Java heap space",
        timestamp=datetime(2026, 3, 1, 10, 0, 0),
    )
    neg = NegativeFinding(
        agent_name=agent_name,
        what_was_checked="CPU throttling",
        result="No CPU throttling detected",
        implication="CPU is not the bottleneck",
        source_reference="prometheus",
    )
    return Finding(
        finding_id=finding_id,
        agent_name=agent_name,
        category=category,
        summary=summary,
        confidence_score=confidence_score,
        severity=severity,
        breadcrumbs=[breadcrumb],
        negative_findings=[neg],
    )


# ---------------------------------------------------------------------------
# TestResourceRef
# ---------------------------------------------------------------------------


class TestResourceRef:
    def test_minimal(self):
        ref = ResourceRef(type="pod", name="payment-service-abc123")
        assert ref.type == "pod"
        assert ref.name == "payment-service-abc123"
        assert ref.namespace is None
        assert ref.status is None
        assert ref.age is None

    def test_full(self):
        ref = ResourceRef(
            type="deployment",
            name="payment-service",
            namespace="prod",
            status="Running",
            age="2d",
        )
        assert ref.type == "deployment"
        assert ref.name == "payment-service"
        assert ref.namespace == "prod"
        assert ref.status == "Running"
        assert ref.age == "2d"

    def test_openshift_types(self):
        """OpenShift-specific resource types should work as free-form strings."""
        for rtype in ("deploymentconfig", "route", "buildconfig", "imagestream"):
            ref = ResourceRef(type=rtype, name=f"test-{rtype}")
            assert ref.type == rtype

    def test_serialization_roundtrip(self):
        ref = ResourceRef(type="service", name="api-gateway", namespace="default", status="Active")
        data = ref.model_dump()
        restored = ResourceRef(**data)
        assert restored.type == ref.type
        assert restored.name == ref.name
        assert restored.namespace == ref.namespace
        assert restored.status == ref.status


# ---------------------------------------------------------------------------
# TestCommandStep
# ---------------------------------------------------------------------------


class TestCommandStep:
    def test_basic(self):
        step = CommandStep(
            order=1,
            description="Scale up deployment",
            command="kubectl scale deployment/payment-service --replicas=3",
            command_type="kubectl",
        )
        assert step.order == 1
        assert step.command_type == "kubectl"
        assert step.is_dry_run is False
        assert step.dry_run_command is None
        assert step.validation_command is None

    def test_with_dry_run(self):
        step = CommandStep(
            order=1,
            description="Rollback deployment",
            command="kubectl rollout undo deployment/payment-service",
            command_type="kubectl",
            is_dry_run=True,
            dry_run_command="kubectl rollout undo deployment/payment-service --dry-run=client",
            validation_command="kubectl rollout status deployment/payment-service",
        )
        assert step.is_dry_run is True
        assert step.dry_run_command is not None
        assert "dry-run" in step.dry_run_command
        assert step.validation_command is not None

    def test_all_command_types(self):
        for cmd_type in ("kubectl", "oc", "helm", "shell"):
            step = CommandStep(
                order=1,
                description="Test",
                command="test-cmd",
                command_type=cmd_type,
            )
            assert step.command_type == cmd_type

    def test_invalid_command_type(self):
        with pytest.raises(ValidationError):
            CommandStep(
                order=1,
                description="Test",
                command="test-cmd",
                command_type="invalid",
            )


# ---------------------------------------------------------------------------
# TestOperationalRecommendation
# ---------------------------------------------------------------------------


class TestOperationalRecommendation:
    def test_minimal(self):
        cmd = CommandStep(
            order=1,
            description="Restart pod",
            command="kubectl delete pod payment-service-abc123",
            command_type="kubectl",
        )
        rec = OperationalRecommendation(
            title="Restart failing pod",
            urgency="immediate",
            category="restart",
            commands=[cmd],
            risk_level="safe",
        )
        assert rec.title == "Restart failing pod"
        assert rec.urgency == "immediate"
        assert rec.category == "restart"
        assert rec.risk_level == "safe"
        assert len(rec.commands) == 1
        assert rec.rollback_commands == []
        assert rec.prerequisites == []
        assert rec.expected_outcome == ""
        assert rec.resource_refs == []
        # Auto-generated UUID id
        assert len(rec.id) > 0

    def test_with_rollback(self):
        scale_up = CommandStep(
            order=1,
            description="Scale up replicas",
            command="kubectl scale deployment/payment-service --replicas=5",
            command_type="kubectl",
        )
        scale_down = CommandStep(
            order=1,
            description="Revert scale",
            command="kubectl scale deployment/payment-service --replicas=2",
            command_type="kubectl",
        )
        ref = ResourceRef(type="deployment", name="payment-service", namespace="prod")
        rec = OperationalRecommendation(
            title="Scale up payment-service",
            urgency="immediate",
            category="scale",
            commands=[scale_up],
            rollback_commands=[scale_down],
            risk_level="caution",
            prerequisites=["Verify HPA is disabled"],
            expected_outcome="Payment service handles increased load",
            resource_refs=[ref],
        )
        assert len(rec.rollback_commands) == 1
        assert rec.prerequisites == ["Verify HPA is disabled"]
        assert rec.expected_outcome == "Payment service handles increased load"
        assert len(rec.resource_refs) == 1
        assert rec.resource_refs[0].type == "deployment"

    def test_invalid_urgency(self):
        with pytest.raises(ValidationError):
            OperationalRecommendation(
                title="Test",
                urgency="later",
                category="restart",
                commands=[],
                risk_level="safe",
            )

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            OperationalRecommendation(
                title="Test",
                urgency="immediate",
                category="delete_everything",
                commands=[],
                risk_level="safe",
            )

    def test_invalid_risk_level(self):
        with pytest.raises(ValidationError):
            OperationalRecommendation(
                title="Test",
                urgency="immediate",
                category="restart",
                commands=[],
                risk_level="yolo",
            )

    def test_unique_ids(self):
        """Each recommendation should get a unique auto-generated id."""
        rec1 = OperationalRecommendation(
            title="A", urgency="immediate", category="restart",
            commands=[], risk_level="safe",
        )
        rec2 = OperationalRecommendation(
            title="B", urgency="immediate", category="restart",
            commands=[], risk_level="safe",
        )
        assert rec1.id != rec2.id


# ---------------------------------------------------------------------------
# TestCausalTree
# ---------------------------------------------------------------------------


class TestCausalTree:
    def test_minimal(self):
        finding = _make_finding()
        tree = CausalTree(
            root_cause=finding,
            severity="critical",
        )
        assert tree.root_cause.finding_id == "f-001"
        assert tree.severity == "critical"
        assert tree.blast_radius is None
        assert tree.cascading_symptoms == []
        assert tree.correlated_signals == []
        assert tree.operational_recommendations == []
        assert tree.triage_status == "untriaged"
        assert tree.resource_refs == []
        assert len(tree.id) > 0

    def test_with_symptoms_and_recommendations(self):
        root = _make_finding(finding_id="f-root", summary="OOM in payment-service")
        symptom1 = _make_finding(
            finding_id="f-sym-1",
            summary="Increased 5xx errors on API gateway",
            severity="high",
        )
        symptom2 = _make_finding(
            finding_id="f-sym-2",
            summary="Checkout flow timeouts",
            severity="high",
        )
        signal_group = CorrelatedSignalGroup(
            group_name="Memory pressure",
            signal_type="USE",
            metrics=["container_memory_usage_bytes", "container_oom_events_total"],
            narrative="Memory usage climbing steadily before OOM",
        )
        cmd = CommandStep(
            order=1,
            description="Increase memory limit",
            command="kubectl set resources deployment/payment-service --limits=memory=2Gi",
            command_type="kubectl",
        )
        rec = OperationalRecommendation(
            title="Increase memory limits",
            urgency="immediate",
            category="config_patch",
            commands=[cmd],
            risk_level="caution",
            expected_outcome="Pod no longer OOM killed",
        )
        pod_ref = ResourceRef(type="pod", name="payment-service-abc123", namespace="prod", status="CrashLoopBackOff")
        deploy_ref = ResourceRef(type="deployment", name="payment-service", namespace="prod")

        tree = CausalTree(
            root_cause=root,
            severity="critical",
            blast_radius={"affected_pods": 3, "affected_services": ["api-gateway", "checkout"]},
            cascading_symptoms=[symptom1, symptom2],
            correlated_signals=[signal_group],
            operational_recommendations=[rec],
            triage_status="acknowledged",
            resource_refs=[pod_ref, deploy_ref],
        )

        assert tree.root_cause.finding_id == "f-root"
        assert len(tree.cascading_symptoms) == 2
        assert tree.cascading_symptoms[0].finding_id == "f-sym-1"
        assert tree.cascading_symptoms[1].finding_id == "f-sym-2"
        assert len(tree.correlated_signals) == 1
        assert tree.correlated_signals[0].signal_type == "USE"
        assert len(tree.operational_recommendations) == 1
        assert tree.operational_recommendations[0].category == "config_patch"
        assert tree.triage_status == "acknowledged"
        assert tree.blast_radius["affected_pods"] == 3
        assert len(tree.resource_refs) == 2
        assert tree.resource_refs[0].status == "CrashLoopBackOff"

    def test_invalid_severity(self):
        with pytest.raises(ValidationError):
            CausalTree(
                root_cause=_make_finding(),
                severity="high",  # Not valid for CausalTree (only critical/warning/info)
            )

    def test_invalid_triage_status(self):
        with pytest.raises(ValidationError):
            CausalTree(
                root_cause=_make_finding(),
                severity="critical",
                triage_status="closed",
            )

    def test_unique_ids(self):
        tree1 = CausalTree(root_cause=_make_finding(), severity="critical")
        tree2 = CausalTree(root_cause=_make_finding(), severity="warning")
        assert tree1.id != tree2.id


# ---------------------------------------------------------------------------
# TestResourceRefsOnExistingModels
# ---------------------------------------------------------------------------


class TestResourceRefsOnExistingModels:
    def test_finding_has_resource_refs(self):
        ref = ResourceRef(type="pod", name="payment-service-abc123", namespace="prod")
        finding = _make_finding()
        finding_with_refs = Finding(
            finding_id="f-002",
            agent_name="k8s_agent",
            category="pod_health",
            summary="Pod in CrashLoopBackOff",
            confidence_score=90,
            severity="critical",
            breadcrumbs=finding.breadcrumbs,
            negative_findings=finding.negative_findings,
            resource_refs=[ref],
        )
        assert len(finding_with_refs.resource_refs) == 1
        assert finding_with_refs.resource_refs[0].type == "pod"
        assert finding_with_refs.resource_refs[0].name == "payment-service-abc123"

    def test_finding_resource_refs_default_empty(self):
        finding = _make_finding()
        assert finding.resource_refs == []

    def test_evidence_pin_has_resource_refs(self):
        ref = ResourceRef(type="service", name="api-gateway", namespace="prod", status="Active")
        pin = EvidencePin(
            claim="API gateway returning 503",
            source_agent="metrics_agent",
            source_tool="prometheus",
            confidence=0.88,
            timestamp=datetime(2026, 3, 1, 10, 0, 0),
            evidence_type="metric",
            resource_refs=[ref],
        )
        assert len(pin.resource_refs) == 1
        assert pin.resource_refs[0].type == "service"
        assert pin.resource_refs[0].name == "api-gateway"

    def test_evidence_pin_resource_refs_default_empty(self):
        pin = EvidencePin(
            claim="Test claim",
            source_agent="agent",
            source_tool="tool",
            confidence=0.5,
            timestamp=datetime.now(),
            evidence_type="log",
        )
        assert pin.resource_refs == []

    def test_finding_serialization_with_resource_refs(self):
        """Ensure resource_refs survive serialization roundtrip on Finding."""
        ref = ResourceRef(type="configmap", name="app-config", namespace="prod")
        finding = Finding(
            finding_id="f-003",
            agent_name="k8s_agent",
            category="config",
            summary="ConfigMap missing key",
            confidence_score=70,
            severity="medium",
            breadcrumbs=[
                Breadcrumb(
                    agent_name="k8s_agent",
                    action="checked configmap",
                    source_type="config",
                    source_reference="configmap/app-config",
                    raw_evidence="Missing DATABASE_URL key",
                    timestamp=datetime(2026, 3, 1, 10, 0, 0),
                )
            ],
            negative_findings=[],
            resource_refs=[ref],
        )
        data = finding.model_dump()
        assert len(data["resource_refs"]) == 1
        assert data["resource_refs"][0]["type"] == "configmap"
        assert data["resource_refs"][0]["name"] == "app-config"
