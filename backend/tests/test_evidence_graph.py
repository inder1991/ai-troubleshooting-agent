"""Tests for evidence graph data models (Phase 4, Task 12)."""

import pytest
from datetime import datetime
from pydantic import ValidationError
from src.models.schemas import (
    EvidencePin,
    EvidenceNode,
    CausalEdge,
    EvidenceGraph,
    TimelineEvent,
    IncidentTimeline,
    Hypothesis,
    DiagnosticStateV5,
    DiagnosticPhase,
    TimeWindow,
)


def _make_pin(claim: str = "Test claim", evidence_type: str = "log",
              confidence: float = 0.8, timestamp: datetime | None = None) -> EvidencePin:
    return EvidencePin(
        claim=claim,
        supporting_evidence=["evidence-1"],
        source_agent="log_agent",
        source_tool="elasticsearch",
        confidence=confidence,
        timestamp=timestamp or datetime(2025, 12, 26, 14, 0, 0),
        evidence_type=evidence_type,
    )


# ---------------------------------------------------------------------------
# EvidenceNode
# ---------------------------------------------------------------------------


class TestEvidenceNode:
    def test_create_node(self):
        pin = _make_pin()
        node = EvidenceNode(
            id="n-abc123",
            pin=pin,
            node_type="symptom",
            temporal_position=pin.timestamp,
        )
        assert node.id == "n-abc123"
        assert node.node_type == "symptom"
        assert node.pin.claim == "Test claim"

    def test_all_node_types(self):
        pin = _make_pin()
        for ntype in ("symptom", "cause", "contributing_factor", "context"):
            node = EvidenceNode(
                id="n-1", pin=pin, node_type=ntype,
                temporal_position=pin.timestamp,
            )
            assert node.node_type == ntype

    def test_reject_invalid_node_type(self):
        pin = _make_pin()
        with pytest.raises(ValidationError):
            EvidenceNode(
                id="n-1", pin=pin, node_type="invalid",
                temporal_position=pin.timestamp,
            )


# ---------------------------------------------------------------------------
# CausalEdge
# ---------------------------------------------------------------------------


class TestCausalEdge:
    def test_create_edge(self):
        edge = CausalEdge(
            source_id="n-1",
            target_id="n-2",
            relationship="causes",
            confidence=0.9,
            reasoning="Log errors preceded metric spike",
        )
        assert edge.source_id == "n-1"
        assert edge.relationship == "causes"
        assert edge.confidence == 0.9

    def test_all_relationship_types(self):
        for rel in ("causes", "correlates", "precedes", "contributes_to"):
            edge = CausalEdge(
                source_id="n-1", target_id="n-2",
                relationship=rel, confidence=0.5, reasoning="test",
            )
            assert edge.relationship == rel

    def test_reject_invalid_relationship(self):
        with pytest.raises(ValidationError):
            CausalEdge(
                source_id="n-1", target_id="n-2",
                relationship="unknown", confidence=0.5, reasoning="test",
            )

    def test_reject_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            CausalEdge(
                source_id="n-1", target_id="n-2",
                relationship="causes", confidence=1.5, reasoning="test",
            )
        with pytest.raises(ValidationError):
            CausalEdge(
                source_id="n-1", target_id="n-2",
                relationship="causes", confidence=-0.1, reasoning="test",
            )


# ---------------------------------------------------------------------------
# EvidenceGraph
# ---------------------------------------------------------------------------


class TestEvidenceGraph:
    def test_create_empty_graph(self):
        graph = EvidenceGraph()
        assert graph.nodes == []
        assert graph.edges == []
        assert graph.root_causes == []
        assert graph.timeline == []

    def test_graph_with_nodes_and_edges(self):
        pin1 = _make_pin("DB pool exhausted", timestamp=datetime(2025, 12, 26, 14, 0))
        pin2 = _make_pin("High latency", timestamp=datetime(2025, 12, 26, 14, 5))
        node1 = EvidenceNode(id="n-1", pin=pin1, node_type="cause",
                             temporal_position=pin1.timestamp)
        node2 = EvidenceNode(id="n-2", pin=pin2, node_type="symptom",
                             temporal_position=pin2.timestamp)
        edge = CausalEdge(source_id="n-1", target_id="n-2",
                          relationship="causes", confidence=0.85,
                          reasoning="DB exhaustion causes latency")
        graph = EvidenceGraph(
            nodes=[node1, node2],
            edges=[edge],
            root_causes=["n-1"],
            timeline=["n-1", "n-2"],
        )
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert graph.root_causes == ["n-1"]


# ---------------------------------------------------------------------------
# TimelineEvent & IncidentTimeline
# ---------------------------------------------------------------------------


class TestTimelineEvent:
    def test_create_event(self):
        event = TimelineEvent(
            timestamp=datetime(2025, 12, 26, 14, 0),
            source="log_agent",
            event_type="log",
            description="Error spike detected",
            evidence_node_id="n-1",
            severity="error",
        )
        assert event.source == "log_agent"
        assert event.severity == "error"

    def test_all_severity_levels(self):
        for sev in ("info", "warning", "error", "critical"):
            event = TimelineEvent(
                timestamp=datetime.now(), source="agent",
                event_type="log", description="test",
                evidence_node_id="n-1", severity=sev,
            )
            assert event.severity == sev

    def test_reject_invalid_severity(self):
        with pytest.raises(ValidationError):
            TimelineEvent(
                timestamp=datetime.now(), source="agent",
                event_type="log", description="test",
                evidence_node_id="n-1", severity="unknown",
            )


class TestIncidentTimeline:
    def test_create_empty(self):
        tl = IncidentTimeline()
        assert tl.events == []

    def test_timeline_with_events(self):
        events = [
            TimelineEvent(
                timestamp=datetime(2025, 12, 26, 14, i),
                source="agent", event_type="log",
                description=f"Event {i}", evidence_node_id=f"n-{i}",
                severity="info",
            )
            for i in range(3)
        ]
        tl = IncidentTimeline(events=events)
        assert len(tl.events) == 3


# ---------------------------------------------------------------------------
# Hypothesis
# ---------------------------------------------------------------------------


class TestHypothesis:
    def test_create_hypothesis(self):
        h = Hypothesis(
            hypothesis_id="h-001",
            description="Database connection pool exhaustion caused cascading timeouts",
            confidence=0.85,
            supporting_node_ids=["n-1", "n-2"],
            causal_chain=["n-1", "n-3", "n-2"],
        )
        assert h.hypothesis_id == "h-001"
        assert h.confidence == 0.85
        assert len(h.supporting_node_ids) == 2
        assert len(h.causal_chain) == 3

    def test_defaults(self):
        h = Hypothesis(
            hypothesis_id="h-002",
            description="Unknown cause",
            confidence=0.1,
        )
        assert h.supporting_node_ids == []
        assert h.causal_chain == []

    def test_reject_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            Hypothesis(hypothesis_id="h", description="d", confidence=1.5)


# ---------------------------------------------------------------------------
# DiagnosticStateV5 integration
# ---------------------------------------------------------------------------


class TestDiagnosticStateV5EvidenceGraph:
    def _base(self):
        return dict(
            session_id="sess-eg-001",
            phase=DiagnosticPhase.INITIAL,
            service_name="payment-service",
            time_window=TimeWindow(start="2025-12-26T14:00:00", end="2025-12-26T15:00:00"),
        )

    def test_defaults(self):
        state = DiagnosticStateV5(**self._base())
        assert isinstance(state.evidence_graph, EvidenceGraph)
        assert state.evidence_graph.nodes == []
        assert state.hypotheses == []
        assert isinstance(state.incident_timeline, IncidentTimeline)
        assert state.incident_timeline.events == []

    def test_with_graph_and_hypotheses(self):
        pin = _make_pin()
        node = EvidenceNode(id="n-1", pin=pin, node_type="cause",
                            temporal_position=pin.timestamp)
        graph = EvidenceGraph(nodes=[node], root_causes=["n-1"])
        hyp = Hypothesis(hypothesis_id="h-1", description="Root cause",
                         confidence=0.9, supporting_node_ids=["n-1"])
        state = DiagnosticStateV5(
            **self._base(),
            evidence_graph=graph,
            hypotheses=[hyp],
        )
        assert len(state.evidence_graph.nodes) == 1
        assert len(state.hypotheses) == 1
        assert state.hypotheses[0].confidence == 0.9
