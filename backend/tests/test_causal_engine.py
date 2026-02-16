"""Tests for the evidence graph builder (Phase 4, Task 13)."""

from datetime import datetime
from src.models.schemas import EvidencePin
from src.agents.causal_engine import EvidenceGraphBuilder


def _pin(claim: str, ts: datetime, evidence_type: str = "log") -> EvidencePin:
    return EvidencePin(
        claim=claim,
        supporting_evidence=["ev-1"],
        source_agent="log_agent",
        source_tool="elasticsearch",
        confidence=0.8,
        timestamp=ts,
        evidence_type=evidence_type,
    )


class TestAddEvidence:
    def test_add_evidence_creates_node(self):
        builder = EvidenceGraphBuilder()
        pin = _pin("Error spike", datetime(2025, 12, 26, 14, 0))
        node_id = builder.add_evidence(pin, "symptom")
        assert node_id.startswith("n-")
        assert len(builder.graph.nodes) == 1
        assert builder.graph.nodes[0].pin.claim == "Error spike"
        assert builder.graph.nodes[0].node_type == "symptom"

    def test_add_multiple_evidence(self):
        builder = EvidenceGraphBuilder()
        id1 = builder.add_evidence(_pin("A", datetime(2025, 1, 1, 10, 0)), "cause")
        id2 = builder.add_evidence(_pin("B", datetime(2025, 1, 1, 10, 5)), "symptom")
        assert id1 != id2
        assert len(builder.graph.nodes) == 2


class TestAddCausalLink:
    def test_add_causal_link(self):
        builder = EvidenceGraphBuilder()
        id1 = builder.add_evidence(_pin("Cause", datetime(2025, 1, 1, 10, 0)), "cause")
        id2 = builder.add_evidence(_pin("Effect", datetime(2025, 1, 1, 10, 5)), "symptom")
        builder.add_causal_link(id1, id2, "causes", 0.9, "Cause preceded effect")
        assert len(builder.graph.edges) == 1
        edge = builder.graph.edges[0]
        assert edge.source_id == id1
        assert edge.target_id == id2
        assert edge.relationship == "causes"
        assert edge.confidence == 0.9

    def test_add_multiple_links(self):
        builder = EvidenceGraphBuilder()
        ids = [
            builder.add_evidence(_pin(f"N{i}", datetime(2025, 1, 1, 10, i)), "context")
            for i in range(3)
        ]
        builder.add_causal_link(ids[0], ids[1], "precedes", 0.7, "r1")
        builder.add_causal_link(ids[1], ids[2], "causes", 0.8, "r2")
        assert len(builder.graph.edges) == 2


class TestIdentifyRootCauses:
    def test_identify_root_causes(self):
        builder = EvidenceGraphBuilder()
        id1 = builder.add_evidence(_pin("Root", datetime(2025, 1, 1, 10, 0)), "cause")
        id2 = builder.add_evidence(_pin("Mid", datetime(2025, 1, 1, 10, 5)), "contributing_factor")
        id3 = builder.add_evidence(_pin("Symptom", datetime(2025, 1, 1, 10, 10)), "symptom")
        builder.add_causal_link(id1, id2, "causes", 0.9, "r1")
        builder.add_causal_link(id2, id3, "causes", 0.85, "r2")
        roots = builder.identify_root_causes()
        assert roots == [id1]
        assert builder.graph.root_causes == [id1]

    def test_multiple_root_causes(self):
        builder = EvidenceGraphBuilder()
        id1 = builder.add_evidence(_pin("Root A", datetime(2025, 1, 1, 10, 0)), "cause")
        id2 = builder.add_evidence(_pin("Root B", datetime(2025, 1, 1, 10, 1)), "cause")
        id3 = builder.add_evidence(_pin("Effect", datetime(2025, 1, 1, 10, 5)), "symptom")
        builder.add_causal_link(id1, id3, "contributes_to", 0.7, "r1")
        builder.add_causal_link(id2, id3, "contributes_to", 0.6, "r2")
        roots = builder.identify_root_causes()
        assert set(roots) == {id1, id2}

    def test_no_edges_no_root_causes(self):
        builder = EvidenceGraphBuilder()
        builder.add_evidence(_pin("Lone", datetime(2025, 1, 1, 10, 0)), "context")
        roots = builder.identify_root_causes()
        assert roots == []


class TestBuildTimeline:
    def test_build_timeline_sorted(self):
        builder = EvidenceGraphBuilder()
        # Add out of order
        builder.add_evidence(_pin("Late", datetime(2025, 1, 1, 10, 10)), "symptom")
        builder.add_evidence(_pin("Early", datetime(2025, 1, 1, 10, 0)), "cause")
        builder.add_evidence(_pin("Mid", datetime(2025, 1, 1, 10, 5)), "contributing_factor")
        timeline = builder.build_timeline()
        assert len(timeline.events) == 3
        assert timeline.events[0].description == "Early"
        assert timeline.events[1].description == "Mid"
        assert timeline.events[2].description == "Late"
        # Verify timestamps are sorted
        timestamps = [e.timestamp for e in timeline.events]
        assert timestamps == sorted(timestamps)

    def test_severity_mapping(self):
        builder = EvidenceGraphBuilder()
        builder.add_evidence(_pin("Cause node", datetime(2025, 1, 1, 10, 0)), "cause")
        builder.add_evidence(_pin("Symptom node", datetime(2025, 1, 1, 10, 1)), "symptom")
        builder.add_evidence(_pin("Context node", datetime(2025, 1, 1, 10, 2)), "context")
        builder.add_evidence(_pin("Contributing", datetime(2025, 1, 1, 10, 3)), "contributing_factor")
        timeline = builder.build_timeline()
        assert timeline.events[0].severity == "error"   # cause
        assert timeline.events[1].severity == "error"   # symptom
        assert timeline.events[2].severity == "info"    # context
        assert timeline.events[3].severity == "info"    # contributing_factor

    def test_timeline_ids_match_graph(self):
        builder = EvidenceGraphBuilder()
        builder.add_evidence(_pin("A", datetime(2025, 1, 1, 10, 0)), "cause")
        builder.add_evidence(_pin("B", datetime(2025, 1, 1, 10, 5)), "symptom")
        builder.build_timeline()
        assert len(builder.graph.timeline) == 2
        node_ids = [n.id for n in builder.graph.nodes]
        for tid in builder.graph.timeline:
            assert tid in node_ids


class TestEmptyGraph:
    def test_empty_graph(self):
        builder = EvidenceGraphBuilder()
        assert builder.graph.nodes == []
        assert builder.graph.edges == []
        roots = builder.identify_root_causes()
        assert roots == []
        timeline = builder.build_timeline()
        assert timeline.events == []
        assert builder.graph.timeline == []
