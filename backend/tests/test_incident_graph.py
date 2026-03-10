import pytest
import networkx as nx
from src.agents.incident_graph import IncidentGraphBuilder


class TestIncidentGraphBuilder:
    def setup_method(self):
        self.builder = IncidentGraphBuilder(session_id="test-session-001")

    def test_add_node_returns_id(self):
        node_id = self.builder.add_node(
            node_type="error_event",
            data={"exception_type": "NullPointerException", "service": "payment"},
            timestamp=1710000000,
            confidence=0.9,
            severity="critical",
            agent_source="log_agent",
        )
        assert node_id.startswith("n-")
        assert len(self.builder.G.nodes) == 1

    def test_add_node_stores_attributes(self):
        node_id = self.builder.add_node(
            node_type="metric_anomaly",
            data={"metric_name": "cpu_usage", "current_value": 0.94},
            timestamp=1710000100,
            confidence=0.85,
            severity="high",
            agent_source="metrics_agent",
        )
        node = self.builder.G.nodes[node_id]
        assert node["node_type"] == "metric_anomaly"
        assert node["confidence"] == 0.85
        assert node["agent_source"] == "metrics_agent"

    def test_add_edge_creates_connection(self):
        n1 = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {}, 1710000100, 0.85, "high", "metrics_agent")
        self.builder.add_confirmed_edge(n1, n2, "causes", 0.8, "CPU spike preceded error", "critic_ensemble")
        assert self.builder.G.has_edge(n1, n2)
        edge = self.builder.G.edges[n1, n2]
        assert edge["edge_type"] == "causes"
        assert edge["confidence"] == 0.8

    def test_temporal_consistency_rejects_future_cause(self):
        n1 = self.builder.add_node("error_event", {}, 1710000200, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {}, 1710000000, 0.85, "high", "metrics_agent")
        self.builder.add_confirmed_edge(n1, n2, "causes", 0.8, "test", "critic")
        violations = self.builder.enforce_temporal_consistency()
        assert len(violations) == 1
        assert not self.builder.G.has_edge(n1, n2)

    def test_cycle_detection_breaks_weakest_edge(self):
        n1 = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {}, 1710000100, 0.85, "high", "metrics_agent")
        n3 = self.builder.add_node("k8s_event", {}, 1710000200, 0.7, "medium", "k8s_agent")
        self.builder.add_confirmed_edge(n1, n2, "causes", 0.9, "strong", "critic")
        self.builder.add_confirmed_edge(n2, n3, "triggers", 0.8, "medium", "critic")
        self.builder.add_confirmed_edge(n3, n1, "causes", 0.3, "weak-cycle", "critic")
        broken = self.builder.break_cycles()
        assert len(broken) >= 1
        assert not self.builder.G.has_edge(n3, n1)

    def test_tentative_edges_same_trace_id(self):
        n1 = self.builder.add_node("error_event", {"trace_id": "abc123", "service": "payment"}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("trace_span", {"trace_id": "abc123", "service": "auth"}, 1710000010, 0.8, "high", "tracing_agent")
        self.builder.create_tentative_edges()
        assert self.builder.G.has_edge(n1, n2) or self.builder.G.has_edge(n2, n1)

    def test_tentative_edges_same_service_temporal_proximity(self):
        n1 = self.builder.add_node("error_event", {"service": "payment"}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {"service": "payment"}, 1710000060, 0.85, "high", "metrics_agent")
        self.builder.create_tentative_edges()
        assert self.builder.G.has_edge(n1, n2)

    def test_no_tentative_edge_distant_timestamps(self):
        n1 = self.builder.add_node("error_event", {"service": "payment"}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {"service": "payment"}, 1710010000, 0.85, "high", "metrics_agent")
        self.builder.create_tentative_edges()
        assert not self.builder.G.has_edge(n1, n2)

    def test_to_serializable_returns_dict(self):
        n1 = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {}, 1710000100, 0.85, "high", "metrics_agent")
        self.builder.add_confirmed_edge(n1, n2, "causes", 0.8, "test", "critic")
        self.builder.rank_root_causes()
        result = self.builder.to_serializable()
        assert "nodes" in result
        assert "edges" in result
        assert "root_causes" in result
        assert "causal_paths" in result
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1

    def test_subgraph_extraction(self):
        n1 = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {}, 1710000100, 0.85, "high", "metrics_agent")
        n3 = self.builder.add_node("k8s_event", {}, 1710000200, 0.7, "medium", "k8s_agent")
        n4 = self.builder.add_node("code_location", {}, 1710000300, 0.6, "low", "code_agent")
        self.builder.add_confirmed_edge(n1, n2, "causes", 0.9, "r1", "critic")
        self.builder.add_confirmed_edge(n2, n3, "triggers", 0.8, "r2", "critic")
        self.builder.add_confirmed_edge(n3, n4, "located_in", 0.7, "r3", "critic")
        sub = self.builder.extract_subgraph(n2, hops=1)
        assert n1 in sub.nodes
        assert n2 in sub.nodes
        assert n3 in sub.nodes
        assert n4 not in sub.nodes


class TestCausalInfluenceScoring:
    def setup_method(self):
        self.builder = IncidentGraphBuilder(session_id="test-scoring")

    def test_single_node_gets_default_score(self):
        n1 = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        scores = self.builder.rank_root_causes()
        assert len(scores) == 1
        assert 0.0 <= scores[0][1] <= 1.0

    def test_earliest_node_scores_highest_temporal(self):
        n_early = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        n_late = self.builder.add_node("metric_anomaly", {}, 1710000300, 0.85, "high", "metrics_agent")
        self.builder.add_confirmed_edge(n_early, n_late, "causes", 0.8, "test", "critic")
        scores = dict(self.builder.rank_root_causes())
        assert scores[n_early] > scores[n_late]

    def test_node_with_most_downstream_scores_highest(self):
        root = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        mid = self.builder.add_node("metric_anomaly", {}, 1710000100, 0.85, "high", "metrics_agent")
        leaf1 = self.builder.add_node("k8s_event", {}, 1710000200, 0.7, "medium", "k8s_agent")
        leaf2 = self.builder.add_node("trace_span", {}, 1710000200, 0.6, "low", "tracing_agent")
        self.builder.add_confirmed_edge(root, mid, "causes", 0.9, "r1", "critic")
        self.builder.add_confirmed_edge(mid, leaf1, "triggers", 0.8, "r2", "critic")
        self.builder.add_confirmed_edge(root, leaf2, "triggers", 0.7, "r3", "critic")
        scores = dict(self.builder.rank_root_causes())
        assert scores[root] > scores[mid]
        assert scores[root] > scores[leaf1]

    def test_empty_graph_returns_empty(self):
        scores = self.builder.rank_root_causes()
        assert scores == []

    def test_blast_radius_bfs(self):
        n1 = self.builder.add_node("error_event", {}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {}, 1710000100, 0.85, "high", "metrics_agent")
        n3 = self.builder.add_node("k8s_event", {}, 1710000200, 0.7, "medium", "k8s_agent")
        self.builder.add_confirmed_edge(n1, n2, "causes", 0.9, "r1", "critic")
        self.builder.add_confirmed_edge(n2, n3, "triggers", 0.8, "r2", "critic")
        descendants = nx.descendants(self.builder.G, n1)
        assert len(descendants) == 2
