"""Evidence graph builder and causal intelligence engine (Phase 4, Task 13)."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from src.models.schemas import (
    EvidencePin,
    EvidenceNode,
    CausalEdge,
    EvidenceGraph,
    IncidentTimeline,
    TimelineEvent,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CrossRepoEdge:
    source_repo: str
    source_file: str
    source_commit: str
    source_timestamp: datetime | None
    target_repo: str
    target_file: str
    target_import: str
    correlation_type: str
    correlation_score: float


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

    def add_cross_repo_edge(self, edge: CrossRepoEdge) -> None:
        """Add a cross-repo causal edge between a source breaking change and a target import."""
        ts = edge.source_timestamp or datetime(1970, 1, 1)
        source_id = self.add_evidence(
            EvidencePin(
                claim=f"Breaking change in {edge.source_repo}:{edge.source_file}",
                supporting_evidence=[f"Commit {edge.source_commit}"],
                source_agent="cross_repo_tracer",
                source_tool="cross_repo_tracer",
                confidence=edge.correlation_score,
                timestamp=ts,
                evidence_type="change",
            ),
            node_type="cross_repo_source",
        )
        target_id = self.add_evidence(
            EvidencePin(
                claim=f"Import in {edge.target_repo}:{edge.target_file}",
                supporting_evidence=[edge.target_import],
                source_agent="cross_repo_tracer",
                source_tool="cross_repo_tracer",
                confidence=edge.correlation_score,
                timestamp=ts,
                evidence_type="code",
            ),
            node_type="cross_repo_target",
        )
        self.add_causal_link(
            source_id,
            target_id,
            edge.correlation_type,
            edge.correlation_score,
            f"Cross-repo: {edge.source_repo} → {edge.target_repo}",
        )

    def identify_root_causes(self) -> list[str]:
        """Identify root causes: nodes that are sources but never targets, plus isolated nodes."""
        logger.info("Causal analysis started", extra={"agent_name": "causal_engine", "action": "analysis_start", "extra": {"nodes": len(self.graph.nodes), "edges": len(self.graph.edges)}})
        targets = {e.target_id for e in self.graph.edges}
        sources = {e.source_id for e in self.graph.edges}
        all_node_ids = {n.id for n in self.graph.nodes}
        # Nodes that are sources but never targets
        roots = [nid for nid in sources if nid not in targets]
        # Isolated nodes (no edges at all) are also potential root causes
        connected = sources | targets
        isolated = [nid for nid in all_node_ids if nid not in connected]
        roots.extend(isolated)
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
