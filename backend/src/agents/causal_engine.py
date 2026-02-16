"""Evidence graph builder and causal intelligence engine (Phase 4, Task 13)."""

import uuid
from src.models.schemas import (
    EvidencePin,
    EvidenceNode,
    CausalEdge,
    EvidenceGraph,
    IncidentTimeline,
    TimelineEvent,
)


class EvidenceGraphBuilder:
    """Builds an evidence graph from evidence pins and causal links."""

    def __init__(self) -> None:
        self.graph = EvidenceGraph()

    def add_evidence(self, pin: EvidencePin, node_type: str) -> str:
        """Add an evidence node to the graph and return its id."""
        node_id = f"n-{uuid.uuid4().hex[:8]}"
        node = EvidenceNode(
            id=node_id,
            pin=pin,
            node_type=node_type,
            temporal_position=pin.timestamp,
        )
        self.graph.nodes.append(node)
        return node_id

    def add_causal_link(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        confidence: float,
        reasoning: str,
    ) -> None:
        """Add a causal edge between two evidence nodes."""
        edge = CausalEdge(
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            confidence=confidence,
            reasoning=reasoning,
        )
        self.graph.edges.append(edge)

    def identify_root_causes(self) -> list[str]:
        """Identify root causes: nodes that are sources but never targets."""
        targets = {e.target_id for e in self.graph.edges}
        sources = {e.source_id for e in self.graph.edges}
        roots = [nid for nid in sources if nid not in targets]
        self.graph.root_causes = roots
        return roots

    def build_timeline(self) -> IncidentTimeline:
        """Build an incident timeline from evidence nodes sorted by timestamp."""
        sorted_nodes = sorted(self.graph.nodes, key=lambda n: n.temporal_position)
        events = []
        for node in sorted_nodes:
            events.append(
                TimelineEvent(
                    timestamp=node.temporal_position,
                    source=node.pin.source_agent,
                    event_type=node.pin.evidence_type,
                    description=node.pin.claim,
                    evidence_node_id=node.id,
                    severity="error" if node.node_type in ("cause", "symptom") else "info",
                )
            )
        self.graph.timeline = [n.id for n in sorted_nodes]
        return IncidentTimeline(events=events)
