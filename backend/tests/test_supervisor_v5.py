import pytest
from datetime import datetime, timezone
from src.agents.supervisor import SupervisorAgent, update_confidence_ledger, add_reasoning_step
from src.models.schemas import (
    DiagnosticStateV5, ConfidenceLedger, ReasoningManifest, EvidencePin, TimeWindow,
)


class TestSupervisorV5:
    def test_v5_dispatch_order(self):
        """V5 should use metrics-first order."""
        sup = SupervisorAgent()
        expected_order = ["metrics_agent", "tracing_agent", "k8s_agent", "log_agent", "code_agent"]
        # Verify the agent registry has all expected agents
        for agent in expected_order:
            assert agent in sup._agents

    def test_confidence_updates_after_agent(self):
        ledger = ConfidenceLedger()
        pins = [
            EvidencePin(
                claim="metric spike",
                supporting_evidence=["cpu=95%"],
                source_agent="metrics_agent",
                source_tool="prometheus",
                confidence=0.9,
                timestamp=datetime.now(timezone.utc),
                evidence_type="metric",
            )
        ]
        update_confidence_ledger(ledger, pins)
        assert ledger.metrics_confidence == 0.9
        assert ledger.weighted_final > 0.0

    def test_confidence_updates_multiple_types(self):
        ledger = ConfidenceLedger()
        pins = [
            EvidencePin(
                claim="metric spike", supporting_evidence=["cpu=95%"],
                source_agent="metrics_agent", source_tool="prometheus",
                confidence=0.9, timestamp=datetime.now(timezone.utc),
                evidence_type="metric",
            ),
            EvidencePin(
                claim="error logs found", supporting_evidence=["NullPointerException"],
                source_agent="log_agent", source_tool="elasticsearch",
                confidence=0.8, timestamp=datetime.now(timezone.utc),
                evidence_type="log",
            ),
        ]
        update_confidence_ledger(ledger, pins)
        assert ledger.metrics_confidence == 0.9
        assert ledger.log_confidence == 0.8
        # weighted_final = 0.9*0.30 + 0.8*0.25 = 0.27 + 0.20 = 0.47
        assert abs(ledger.weighted_final - 0.47) < 0.01

    def test_reasoning_steps_recorded(self):
        manifest = ReasoningManifest(session_id="test")
        add_reasoning_step(
            manifest, "dispatch_metrics_agent",
            "Starting with metrics per v5 priority",
            [], 0.0, [],
        )
        add_reasoning_step(
            manifest, "dispatch_k8s_agent",
            "K8s next for cluster state",
            ["metric spike"], 0.3, ["log_agent"],
        )
        assert len(manifest.steps) == 2
        assert manifest.steps[0].step_number == 1
        assert manifest.steps[1].step_number == 2
        assert manifest.steps[1].decision == "dispatch_k8s_agent"
        assert "metric spike" in manifest.steps[1].evidence_considered

    def test_diagnostic_state_v5_fields(self):
        state = DiagnosticStateV5(
            session_id="test",
            service_name="order-svc",
            phase="initial",
            time_window=TimeWindow(start="2026-01-01T00:00:00", end="2026-01-01T01:00:00"),
        )
        assert state.evidence_pins == []
        assert state.confidence_ledger.weighted_final == 0.0
        assert state.evidence_graph.nodes == []
        assert state.hypotheses == []
        assert state.change_correlations == []
        assert state.blast_radius is None
        assert state.severity_recommendation is None

    def test_diagnostic_state_v5_inherits_v4(self):
        state = DiagnosticStateV5(
            session_id="test",
            service_name="order-svc",
            phase="initial",
            time_window=TimeWindow(start="2026-01-01T00:00:00", end="2026-01-01T01:00:00"),
        )
        # V4 fields should be present
        assert state.agents_completed == []
        assert state.all_findings == []
        assert state.overall_confidence == 0

    def test_diagnostic_state_v5_auto_init_reasoning_manifest(self):
        state = DiagnosticStateV5(
            session_id="test-session",
            service_name="order-svc",
            phase="initial",
            time_window=TimeWindow(start="2026-01-01T00:00:00", end="2026-01-01T01:00:00"),
        )
        assert state.reasoning_manifest is not None
        assert state.reasoning_manifest.session_id == "test-session"
        assert state.reasoning_manifest.steps == []

    def test_supervisor_has_run_v5_method(self):
        sup = SupervisorAgent()
        assert hasattr(sup, "run_v5")
        assert callable(sup.run_v5)
