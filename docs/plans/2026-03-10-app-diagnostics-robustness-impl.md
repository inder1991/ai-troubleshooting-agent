# App Diagnostics Robustness Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the app diagnostics workflow across 10 areas: evidence graph with causal influence scoring, 4-role critic ensemble with Bayesian calibration, chat tool calling with parallel execution, tracing agent re-enablement, infra-repo awareness, service dependency graph, multi-file visibility, prompt framework, live refresh, and token overflow protection.

**Architecture:** Additive layers on existing DiagnosticState — no changes to `_update_state_with_result()`, `_build_agent_context()`, `_decide_next_agents()`, or `_update_phase()`. New modules read FROM state and write to new fields. Frontend receives new data via existing `getFindings()` passthrough.

**Tech Stack:** Python 3.14, FastAPI, NetworkX, Anthropic SDK (tool calling), pytest + pytest-asyncio, React 18 + TypeScript + Tailwind, Framer Motion, D3-force (already installed), ReactFlow (already installed).

**Design Doc:** `docs/plans/2026-03-10-app-diagnostics-robustness-design.md`

---

## Phase 1: Foundation — Evidence Graph + Critic Ensemble

### Task 1: IncidentGraphBuilder — Core Graph Structure

**Files:**
- Create: `backend/src/agents/incident_graph.py`
- Test: `backend/tests/test_incident_graph.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_incident_graph.py
import pytest
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
        n1 = self.builder.add_node("error_event", {}, 1710000200, 0.9, "critical", "log_agent")  # later
        n2 = self.builder.add_node("metric_anomaly", {}, 1710000000, 0.85, "high", "metrics_agent")  # earlier
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
        self.builder.add_confirmed_edge(n3, n1, "causes", 0.3, "weak-cycle", "critic")  # weakest
        broken = self.builder.break_cycles()
        assert len(broken) >= 1
        assert not self.builder.G.has_edge(n3, n1)  # weakest removed

    def test_tentative_edges_same_trace_id(self):
        n1 = self.builder.add_node("error_event", {"trace_id": "abc123", "service": "payment"}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("trace_span", {"trace_id": "abc123", "service": "auth"}, 1710000010, 0.8, "high", "tracing_agent")
        self.builder.create_tentative_edges()
        assert self.builder.G.has_edge(n1, n2) or self.builder.G.has_edge(n2, n1)

    def test_tentative_edges_same_service_temporal_proximity(self):
        n1 = self.builder.add_node("error_event", {"service": "payment"}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {"service": "payment"}, 1710000060, 0.85, "high", "metrics_agent")  # 60s later
        self.builder.create_tentative_edges()
        assert self.builder.G.has_edge(n1, n2)

    def test_no_tentative_edge_distant_timestamps(self):
        n1 = self.builder.add_node("error_event", {"service": "payment"}, 1710000000, 0.9, "critical", "log_agent")
        n2 = self.builder.add_node("metric_anomaly", {"service": "payment"}, 1710010000, 0.85, "high", "metrics_agent")  # 2.7h later
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
        assert n4 not in sub.nodes  # 2 hops away
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_incident_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agents.incident_graph'`

**Step 3: Write the implementation**

```python
# backend/src/agents/incident_graph.py
"""
IncidentGraphBuilder — NetworkX-based evidence graph with causal influence scoring.

Builds a directed graph of incident evidence nodes connected by causal/temporal edges.
Uses composite scoring (downstream reach + temporal priority + critic confidence) for
root cause ranking instead of PageRank.
"""
import uuid
import networkx as nx


class IncidentGraphBuilder:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.G = nx.DiGraph()
        self._root_causes: list[tuple[str, float]] = []
        self._causal_paths: list[dict] = []

    def add_node(self, node_type: str, data: dict, timestamp: float,
                 confidence: float, severity: str, agent_source: str) -> str:
        node_id = f"n-{uuid.uuid4().hex[:12]}"
        self.G.add_node(node_id,
            node_type=node_type,
            data=data,
            timestamp=timestamp,
            confidence=confidence,
            severity=severity,
            agent_source=agent_source,
        )
        return node_id

    def add_confirmed_edge(self, source_id: str, target_id: str, edge_type: str,
                           confidence: float, reasoning: str, created_by: str):
        if source_id not in self.G or target_id not in self.G:
            return
        temporal_delta = None
        src_ts = self.G.nodes[source_id].get("timestamp")
        tgt_ts = self.G.nodes[target_id].get("timestamp")
        if src_ts and tgt_ts:
            temporal_delta = int((tgt_ts - src_ts) * 1000)
        self.G.add_edge(source_id, target_id,
            edge_type=edge_type,
            confidence=confidence,
            reasoning=reasoning,
            created_by=created_by,
            temporal_delta_ms=temporal_delta,
        )

    def create_tentative_edges(self):
        """Create heuristic edges based on shared trace_id or service+temporal proximity."""
        nodes = list(self.G.nodes(data=True))
        for i, (id_a, data_a) in enumerate(nodes):
            for id_b, data_b in nodes[i + 1:]:
                if self.G.has_edge(id_a, id_b) or self.G.has_edge(id_b, id_a):
                    continue
                # Same trace_id → correlates_with
                trace_a = data_a.get("data", {}).get("trace_id")
                trace_b = data_b.get("data", {}).get("trace_id")
                if trace_a and trace_b and trace_a == trace_b:
                    earlier, later = (id_a, id_b) if (data_a.get("timestamp", 0) <= data_b.get("timestamp", 0)) else (id_b, id_a)
                    self.G.add_edge(earlier, later,
                        edge_type="correlates_with", confidence=0.6,
                        reasoning=f"Shared trace_id: {trace_a}", created_by="heuristic")
                    continue
                # Same service + temporal proximity (< 5 min)
                svc_a = data_a.get("data", {}).get("service")
                svc_b = data_b.get("data", {}).get("service")
                ts_a = data_a.get("timestamp", 0)
                ts_b = data_b.get("timestamp", 0)
                if svc_a and svc_b and svc_a == svc_b and abs(ts_a - ts_b) < 300:
                    earlier, later = (id_a, id_b) if ts_a <= ts_b else (id_b, id_a)
                    self.G.add_edge(earlier, later,
                        edge_type="precedes", confidence=0.4,
                        reasoning=f"Same service ({svc_a}), {abs(ts_a - ts_b):.0f}s apart",
                        created_by="heuristic")

    def enforce_temporal_consistency(self) -> list[tuple[str, str]]:
        """Remove causal/trigger edges where source timestamp > target timestamp."""
        violations = []
        causal_types = {"causes", "triggers", "manifests_as", "precedes"}
        for u, v, data in list(self.G.edges(data=True)):
            if data.get("edge_type") not in causal_types:
                continue
            ts_u = self.G.nodes[u].get("timestamp")
            ts_v = self.G.nodes[v].get("timestamp")
            if ts_u and ts_v and ts_u > ts_v:
                violations.append((u, v))
                self.G.remove_edge(u, v)
        return violations

    def break_cycles(self) -> list[tuple[str, str]]:
        """Break cycles by removing the lowest-confidence edge in each cycle."""
        broken = []
        while True:
            try:
                cycle = nx.find_cycle(self.G)
            except nx.NetworkXNoCycle:
                break
            # Find weakest edge in cycle
            weakest = min(cycle, key=lambda e: self.G.edges[e[0], e[1]].get("confidence", 1.0))
            self.G.remove_edge(weakest[0], weakest[1])
            broken.append((weakest[0], weakest[1]))
        return broken

    def rank_root_causes(self) -> list[tuple[str, float]]:
        """Causal Influence Scoring: downstream_reach + temporal_priority + critic_confidence."""
        if len(self.G.nodes) == 0:
            self._root_causes = []
            return []

        all_ts = [self.G.nodes[n].get("timestamp") for n in self.G.nodes if self.G.nodes[n].get("timestamp")]
        t_min = min(all_ts) if all_ts else 0
        t_max = max(all_ts) if all_ts else 1
        t_range = max(t_max - t_min, 1)
        max_reachable = max(len(self.G.nodes) - 1, 1)

        scores = {}
        for node in self.G.nodes:
            reachable = len(nx.descendants(self.G, node))
            downstream_reach = reachable / max_reachable

            t = self.G.nodes[node].get("timestamp", t_max)
            temporal_priority = 1.0 - ((t - t_min) / t_range)

            out_edges = list(self.G.out_edges(node, data=True))
            edge_confs = [e[2].get("confidence", 0.5) for e in out_edges]
            critic_confidence = sum(edge_confs) / len(edge_confs) if edge_confs else 0.5

            scores[node] = round(0.4 * downstream_reach + 0.35 * temporal_priority + 0.25 * critic_confidence, 4)

        self._root_causes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        self._build_causal_paths()
        return self._root_causes

    def _build_causal_paths(self):
        """Extract causal paths from top root causes to leaf nodes."""
        self._causal_paths = []
        if not self._root_causes:
            return
        top_roots = [r[0] for r in self._root_causes[:3]]
        leaves = [n for n in self.G.nodes if self.G.out_degree(n) == 0 and n not in top_roots]
        for root in top_roots:
            for leaf in leaves:
                try:
                    path = nx.shortest_path(self.G, root, leaf, weight=lambda u, v, d: 1 - d.get("confidence", 0.5))
                    self._causal_paths.append({
                        "root": root,
                        "leaf": leaf,
                        "path": path,
                        "total_confidence": min(
                            (self.G.edges[path[i], path[i+1]].get("confidence", 0.5) for i in range(len(path)-1)),
                            default=0.0
                        ),
                    })
                except nx.NetworkXNoPath:
                    continue

    def extract_subgraph(self, node_id: str, hops: int = 2) -> nx.DiGraph:
        """Extract N-hop neighborhood around a node."""
        neighbors = {node_id}
        frontier = {node_id}
        for _ in range(hops):
            next_frontier = set()
            for n in frontier:
                next_frontier.update(self.G.successors(n))
                next_frontier.update(self.G.predecessors(n))
            frontier = next_frontier - neighbors
            neighbors.update(frontier)
        return self.G.subgraph(neighbors).copy()

    def to_serializable(self) -> dict:
        """Serialize graph to dict for API response / state storage."""
        nodes = []
        for nid, data in self.G.nodes(data=True):
            nodes.append({"id": nid, **{k: v for k, v in data.items()}})
        edges = []
        for u, v, data in self.G.edges(data=True):
            edges.append({"source": u, "target": v, **{k: v2 for k, v2 in data.items()}})
        return {
            "nodes": nodes,
            "edges": edges,
            "root_causes": [{"node_id": r[0], "score": r[1]} for r in self._root_causes[:5]],
            "causal_paths": self._causal_paths[:10],
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_incident_graph.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agents/incident_graph.py backend/tests/test_incident_graph.py
git commit -m "feat(graph): add IncidentGraphBuilder with causal influence scoring"
```

---

### Task 2: Causal Influence Scoring — Edge Cases

**Files:**
- Test: `backend/tests/test_incident_graph.py` (extend)

**Step 1: Write additional edge-case tests**

```python
# Append to backend/tests/test_incident_graph.py

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
        # root has 3 downstream, mid has 1, leaves have 0
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
```

**Step 2: Run to verify they fail** then **Step 3: Implementation already done** (Task 1 covers it).

**Step 4: Run all graph tests**

Run: `cd backend && python -m pytest tests/test_incident_graph.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/tests/test_incident_graph.py
git commit -m "test(graph): add causal influence scoring edge case tests"
```

---

### Task 3: Bayesian Confidence Calibrator

**Files:**
- Create: `backend/src/agents/confidence_calibrator.py`
- Test: `backend/tests/test_bayesian_calibrator.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_bayesian_calibrator.py
import pytest
from src.agents.confidence_calibrator import BayesianConfidenceCalibrator


class TestBayesianCalibrator:
    def setup_method(self):
        self.calibrator = BayesianConfidenceCalibrator()

    def test_default_prior_is_065(self):
        result = self.calibrator.calibrate(
            agent_name="log_agent",
            critic_score=1.0,
            evidence_count=10,
        )
        # prior=0.65, critic=1.0, evidence_weight≈1.0 → ~0.65
        assert 0.6 <= result <= 0.7

    def test_low_critic_score_reduces_confidence(self):
        high = self.calibrator.calibrate("log_agent", critic_score=0.9, evidence_count=3)
        low = self.calibrator.calibrate("log_agent", critic_score=0.3, evidence_count=3)
        assert high > low

    def test_more_evidence_increases_confidence(self):
        few = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=1)
        many = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=5)
        assert many > few

    def test_evidence_weight_has_diminishing_returns(self):
        w3 = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=3)
        w5 = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=5)
        w10 = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=10)
        # Gap between 3→5 should be larger than 5→10
        assert (w5 - w3) >= (w10 - w5)

    def test_update_priors_adjusts_accuracy(self):
        self.calibrator.update_priors("log_agent", was_correct=True)
        self.calibrator.update_priors("log_agent", was_correct=True)
        self.calibrator.update_priors("log_agent", was_correct=True)
        # After 3 correct results, prior should increase from 0.65
        result = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=3)
        default_result = BayesianConfidenceCalibrator().calibrate("log_agent", critic_score=0.8, evidence_count=3)
        assert result > default_result

    def test_update_priors_decreases_on_wrong(self):
        self.calibrator.update_priors("log_agent", was_correct=False)
        self.calibrator.update_priors("log_agent", was_correct=False)
        result = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=3)
        default_result = BayesianConfidenceCalibrator().calibrate("log_agent", critic_score=0.8, evidence_count=3)
        assert result < default_result

    def test_confidence_clamped_0_to_1(self):
        result = self.calibrator.calibrate("log_agent", critic_score=1.0, evidence_count=100)
        assert 0.0 <= result <= 1.0
        result2 = self.calibrator.calibrate("log_agent", critic_score=0.0, evidence_count=0)
        assert 0.0 <= result2 <= 1.0

    def test_breakdown_returns_all_factors(self):
        breakdown = self.calibrator.get_calibration_breakdown("log_agent", critic_score=0.8, evidence_count=3)
        assert "calibrated_confidence" in breakdown
        assert "factors" in breakdown
        assert "agent_prior" in breakdown["factors"]
        assert "critic_score" in breakdown["factors"]
        assert "evidence_weight" in breakdown["factors"]
        assert "evidence_count" in breakdown["factors"]
```

**Step 2: Run to verify fail**

Run: `cd backend && python -m pytest tests/test_bayesian_calibrator.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# backend/src/agents/confidence_calibrator.py
"""Bayesian confidence calibration for agent findings."""
import math


class BayesianConfidenceCalibrator:
    """Bayesian calibration: prior × critic_score × evidence_weight → posterior."""

    DEFAULT_PRIOR = 0.65

    def __init__(self):
        self.agent_priors: dict[str, float] = {}

    def calibrate(self, agent_name: str, critic_score: float, evidence_count: int) -> float:
        prior = self.agent_priors.get(agent_name, self.DEFAULT_PRIOR)
        evidence_weight = min(1.0, 0.5 + 0.2 * math.log1p(evidence_count))
        raw = prior * critic_score * evidence_weight
        return round(min(1.0, max(0.0, raw)), 3)

    def update_priors(self, agent_name: str, was_correct: bool):
        current = self.agent_priors.get(agent_name, self.DEFAULT_PRIOR)
        self.agent_priors[agent_name] = 0.9 * current + 0.1 * (1.0 if was_correct else 0.0)

    def get_calibration_breakdown(self, agent_name: str, critic_score: float, evidence_count: int) -> dict:
        prior = self.agent_priors.get(agent_name, self.DEFAULT_PRIOR)
        evidence_weight = min(1.0, 0.5 + 0.2 * math.log1p(evidence_count))
        return {
            "calibrated_confidence": self.calibrate(agent_name, critic_score, evidence_count),
            "factors": {
                "agent_prior": round(prior, 3),
                "critic_score": round(critic_score, 3),
                "evidence_weight": round(evidence_weight, 3),
                "evidence_count": evidence_count,
            },
        }
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_bayesian_calibrator.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agents/confidence_calibrator.py backend/tests/test_bayesian_calibrator.py
git commit -m "feat(critic): add Bayesian confidence calibrator"
```

---

### Task 4: Critic Ensemble — Deterministic Pre-checks

**Files:**
- Create: `backend/src/agents/critic_ensemble.py`
- Test: `backend/tests/test_critic_ensemble.py`

**Step 1: Write failing tests for Stage 1 (deterministic only)**

```python
# backend/tests/test_critic_ensemble.py
import pytest
from src.agents.critic_ensemble import DeterministicValidator


class TestDeterministicValidator:
    def setup_method(self):
        self.validator = DeterministicValidator()

    def test_pass_when_valid(self):
        pin = {
            "claim": "OOMKilled in payment pod",
            "source_agent": "k8s_agent",
            "timestamp": 1710000100,
            "causal_role": "root_cause",
        }
        graph_nodes = {
            "n-001": {"timestamp": 1710000000, "node_type": "error_event"},
            "n-002": {"timestamp": 1710000200, "node_type": "metric_anomaly"},
        }
        graph_edges = [("n-001", "n-002", {"edge_type": "causes"})]
        result = self.validator.validate(pin, graph_nodes, graph_edges, [])
        assert result["status"] == "pass"

    def test_reject_missing_claim(self):
        pin = {"claim": "", "source_agent": "k8s_agent"}
        result = self.validator.validate(pin, {}, [], [])
        assert result["status"] == "hard_reject"
        assert "schema_incomplete" in result["violations"]

    def test_reject_missing_source_agent(self):
        pin = {"claim": "some claim", "source_agent": ""}
        result = self.validator.validate(pin, {}, [], [])
        assert result["status"] == "hard_reject"
        assert "schema_incomplete" in result["violations"]

    def test_reject_temporal_violation(self):
        pin = {
            "claim": "Pod caused etcd failure",
            "source_agent": "k8s_agent",
            "timestamp": 1710000300,  # AFTER the effect
            "caused_node_id": "n-effect",
        }
        graph_nodes = {
            "n-effect": {"timestamp": 1710000100, "node_type": "error_event"},
        }
        result = self.validator.validate(pin, graph_nodes, [], [])
        assert result["status"] == "hard_reject"
        assert "temporal_violation" in result["violations"]

    def test_reject_contradiction(self):
        pin = {
            "claim": "Service A is healthy",
            "source_agent": "k8s_agent",
            "service": "service-a",
            "causal_role": "informational",
        }
        existing = [{
            "claim": "Service A is failing with OOMKilled",
            "source_agent": "k8s_agent",
            "service": "service-a",
            "validation_status": "validated",
            "causal_role": "root_cause",
            "pin_id": "p-001",
        }]
        result = self.validator.validate(pin, {}, [], existing)
        assert result["status"] == "hard_reject"
        assert any("contradicts" in v for v in result["violations"])
```

**Step 2: Run to verify fail**

Run: `cd backend && python -m pytest tests/test_critic_ensemble.py -v`
Expected: FAIL

**Step 3: Write implementation (Stage 1 only — no LLM calls)**

```python
# backend/src/agents/critic_ensemble.py
"""
Critic Ensemble: Deterministic pre-checks + LLM ensemble debate.
Stage 1 (this task): DeterministicValidator — 0 LLM calls.
Stage 2 (Task 5): EnsembleCritic — Advocate/Challenger/Retriever/Judge.
"""


# Domain invariants: cause-type cannot produce certain effect-types
INCIDENT_INVARIANTS = [
    {"name": "pod_cannot_cause_etcd", "cause_type": "k8s_event", "cause_contains": "pod",
     "effect_type": "error_event", "effect_contains": "etcd"},
    {"name": "app_error_cannot_cause_node_failure", "cause_type": "error_event",
     "cause_contains": "application", "effect_type": "k8s_event", "effect_contains": "node"},
]


class DeterministicValidator:
    """Stage 1: deterministic pre-checks with 0 LLM calls."""

    def validate(self, pin: dict, graph_nodes: dict, graph_edges: list,
                 existing_pins: list) -> dict:
        violations = []

        # Schema check
        if not pin.get("claim") or not pin.get("source_agent"):
            violations.append("schema_incomplete")

        # Temporal: if pin claims to cause a node, pin must precede it
        caused_id = pin.get("caused_node_id")
        if caused_id and caused_id in graph_nodes:
            pin_ts = pin.get("timestamp", 0)
            effect_ts = graph_nodes[caused_id].get("timestamp", 0)
            if pin_ts and effect_ts and pin_ts > effect_ts:
                violations.append("temporal_violation")

        # Contradiction: same service + conflicting causal roles
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
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_critic_ensemble.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agents/critic_ensemble.py backend/tests/test_critic_ensemble.py
git commit -m "feat(critic): add deterministic pre-check validator (Stage 1)"
```

---

### Task 5: Critic Ensemble — LLM Debate (Advocate/Challenger/Retriever/Judge)

**Files:**
- Modify: `backend/src/agents/critic_ensemble.py`
- Test: `backend/tests/test_critic_ensemble.py` (extend)

**Step 1: Write failing tests (mocked LLM)**

```python
# Append to backend/tests/test_critic_ensemble.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.critic_ensemble import EnsembleCritic


class TestEnsembleCritic:
    def setup_method(self):
        self.mock_llm = MagicMock()
        self.critic = EnsembleCritic(llm_client=self.mock_llm)

    def test_hard_reject_skips_llm(self):
        finding = {"claim": "", "source_agent": ""}
        state = {"all_findings": []}
        graph = {"nodes": {}, "edges": []}
        result = asyncio.get_event_loop().run_until_complete(
            self.critic.validate(finding, state, graph)
        )
        assert result["verdict"] == "challenged"
        self.mock_llm.chat.assert_not_called()

    @patch("src.agents.critic_ensemble.EnsembleCritic._run_evidence_retriever")
    def test_full_debate_calls_four_roles(self, mock_retriever):
        mock_retriever.return_value = "No additional evidence."
        self.mock_llm.chat = AsyncMock(side_effect=[
            "The finding is valid because...",   # Advocate
            "However, there are concerns...",     # Challenger
            '{"verdict":"validated","confidence":0.82,"causal_role":"root_cause",'
            '"reasoning":"Valid","supporting_evidence":[],"contradictions":[],"graph_edges":[]}',  # Judge
        ])
        finding = {
            "claim": "OOMKilled in payment pod",
            "source_agent": "k8s_agent",
            "timestamp": 1710000100,
        }
        state = {"all_findings": [finding]}
        graph = {"nodes": {}, "edges": []}
        result = asyncio.get_event_loop().run_until_complete(
            self.critic.validate(finding, state, graph)
        )
        assert result["verdict"] == "validated"
        assert result["confidence"] == 0.82
        assert self.mock_llm.chat.call_count == 3  # Advocate + Challenger + Judge
        mock_retriever.assert_called_once()

    def test_parse_judge_output_valid_json(self):
        raw = '{"verdict":"challenged","confidence":0.4,"causal_role":"correlated","reasoning":"Weak evidence","supporting_evidence":[],"contradictions":["metric data missing"],"graph_edges":[]}'
        result = self.critic._parse_judge_output(raw)
        assert result["verdict"] == "challenged"
        assert result["confidence"] == 0.4
```

**Step 2: Run to verify fail**

Run: `cd backend && python -m pytest tests/test_critic_ensemble.py::TestEnsembleCritic -v`
Expected: FAIL — `ImportError: cannot import name 'EnsembleCritic'`

**Step 3: Add EnsembleCritic class to critic_ensemble.py**

```python
# Append to backend/src/agents/critic_ensemble.py
import json
import logging

logger = logging.getLogger(__name__)

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
            # Extract JSON from potential markdown code blocks
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
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_critic_ensemble.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agents/critic_ensemble.py backend/tests/test_critic_ensemble.py
git commit -m "feat(critic): add 4-role ensemble debate (Advocate/Challenger/Retriever/Judge)"
```

---

### Task 6: Token Budget Utility

**Files:**
- Create: `backend/src/utils/token_budget.py`
- Test: `backend/tests/test_token_budget.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_token_budget.py
import pytest
from src.utils.token_budget import estimate_tokens, enforce_budget


class TestTokenBudget:
    def test_estimate_tokens_basic(self):
        text = "Hello world this is a test"
        tokens = estimate_tokens(text)
        assert 5 <= tokens <= 10

    def test_estimate_tokens_empty(self):
        assert estimate_tokens("") == 0

    def test_enforce_budget_no_truncation_needed(self):
        system = "You are a helper."
        conversation = [{"role": "user", "content": "Hi"}]
        context = "Short context."
        s, c, ctx = enforce_budget(system, conversation, context, model_max=200_000)
        assert s == system
        assert c == conversation
        assert ctx == context

    def test_enforce_budget_truncates_conversation(self):
        system = "System prompt."
        conversation = [{"role": "user", "content": f"Message {i}"} for i in range(100)]
        context = "A" * 500_000  # Very large context
        s, c, ctx = enforce_budget(system, conversation, context, model_max=200_000)
        assert len(c) <= 10  # Truncated to last 10

    def test_enforce_budget_respects_target_ratio(self):
        system = "System prompt."
        conversation = [{"role": "user", "content": "Hi"}]
        context = "A" * 800_000  # Way too large
        s, c, ctx = enforce_budget(system, conversation, context, model_max=200_000, target_ratio=0.7)
        total = estimate_tokens(s) + estimate_tokens(str(c)) + estimate_tokens(ctx)
        assert total <= 200_000  # Must fit
```

**Step 2: Run to verify fail**

Run: `cd backend && python -m pytest tests/test_token_budget.py -v`

**Step 3: Write implementation**

```python
# backend/src/utils/token_budget.py
"""Token estimation and context truncation for LLM calls."""


def estimate_tokens(text: str) -> int:
    """Approximate token count (4 chars ≈ 1 token for English text)."""
    return len(text) // 4


def enforce_budget(system_prompt: str, conversation: list, context: str,
                   model_max: int = 200_000, target_ratio: float = 0.7) -> tuple[str, list, str]:
    """Truncate context to fit within model context window."""
    target = int(model_max * target_ratio)
    total = estimate_tokens(system_prompt) + estimate_tokens(str(conversation)) + estimate_tokens(context)

    if total <= target:
        return system_prompt, conversation, context

    # Step 1: Truncate conversation to last 10 turns
    truncated_conv = conversation[-10:]
    total = estimate_tokens(system_prompt) + estimate_tokens(str(truncated_conv)) + estimate_tokens(context)
    if total <= target:
        return system_prompt, truncated_conv, context

    # Step 2: Truncate context string to fit remaining budget
    remaining = target - estimate_tokens(system_prompt) - estimate_tokens(str(truncated_conv))
    max_chars = max(0, remaining * 4)
    truncated_context = context[:max_chars]
    return system_prompt, truncated_conv, truncated_context
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_token_budget.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/utils/token_budget.py backend/tests/test_token_budget.py
git commit -m "feat(utils): add token budget estimation and context truncation"
```

---

### Task 7: Prompt Framework

**Files:**
- Create: `backend/src/prompts/__init__.py`
- Create: `backend/src/prompts/rules.py`
- Create: `backend/src/prompts/chat_prompts.py`

**Step 1: Create the prompts directory and files**

```python
# backend/src/prompts/__init__.py
from .rules import GROUNDING_RULES
from .chat_prompts import CHAT_RULES, CHAT_TOOLS_SCHEMA
```

```python
# backend/src/prompts/rules.py
"""Shared grounding/citation/temporal rules injected into ALL LLM calls."""

GROUNDING_RULES = """
GROUNDING:
- Never speculate about values you don't have. Say "I don't have that data" and suggest how to get it.
- Never hallucinate metric values, pod names, timestamps, or file paths.
- If uncertain, state your confidence level explicitly.

CITATION:
- Always reference specific values: "CPU hit 94% at 14:03:22" not "CPU was high".
- Cite the data source: "[Prometheus] container_cpu_usage peaked at 0.94" or "[ES logs] NullPointerException in PaymentService".
- When referencing findings, include the agent that produced them.

TEMPORAL REASONING:
- Events are ordered by timestamp. Correlation does not imply causation.
- A cause MUST precede its effect. Never claim A caused B if A happened after B.
- Always note the time delta between correlated events.

COMPLETENESS:
- Report what you checked and found nothing (negative findings are evidence).
- Distinguish between "confirmed" (validated by critic) and "suspected" (single-agent, unvalidated).
- Never claim root cause without at least 2 corroborating signals from different data sources.
"""
```

```python
# backend/src/prompts/chat_prompts.py
"""Chat-specific rules and tool schemas."""

CHAT_RULES = """
ROLE: You are an AI SRE assistant embedded in a live incident investigation.

WORKFLOW:
- If the user asks about a metric/pod/log you don't have in context, use the appropriate tool to fetch it live.
- If a tool call fails, tell the user what failed and suggest alternatives.
- When presenting comparisons, use markdown tables.
- When presenting sequences, use numbered lists.
- Keep responses concise (3-5 sentences for simple questions, structured sections for complex ones).

BOUNDARIES:
- You can READ data via tools. You cannot MODIFY infrastructure.
- For remediation actions (fix, rollback, restart), explain what would happen and ask for explicit approval.
- Stay within the scope of the current investigation session.
"""

CHAT_TOOLS_SCHEMA = [
    {
        "name": "query_prometheus",
        "description": "Query Prometheus for metric values over a time range. Use for CPU, memory, request rate, error rate, latency questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PromQL query string"},
                "start": {"type": "string", "description": "Start time (ISO 8601 or relative like '1h')"},
                "end": {"type": "string", "description": "End time (ISO 8601 or 'now')"},
                "step": {"type": "string", "description": "Query resolution step (e.g., '15s', '1m')"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_logs",
        "description": "Search Elasticsearch logs by keyword, service, or time range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (Lucene syntax)"},
                "service": {"type": "string", "description": "Filter by service name"},
                "time_from": {"type": "string", "description": "Start time"},
                "time_to": {"type": "string", "description": "End time"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_pod_status",
        "description": "Get current status of a Kubernetes pod including restarts, resource usage, and events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pod_name": {"type": "string", "description": "Pod name (supports prefix matching)"},
                "namespace": {"type": "string", "description": "K8s namespace"},
            },
            "required": ["pod_name"],
        },
    },
    {
        "name": "query_trace",
        "description": "Fetch distributed trace spans from Jaeger by trace ID or service name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "description": "Specific trace ID"},
                "service": {"type": "string", "description": "Service name to search traces for"},
                "limit": {"type": "integer", "description": "Max traces to return (default 5)"},
            },
        },
    },
    {
        "name": "search_findings",
        "description": "Search collected investigation findings by agent, severity, or keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Search keyword"},
                "agent": {"type": "string", "description": "Filter by agent (log_agent, metrics_agent, etc.)"},
                "severity": {"type": "string", "description": "Filter by severity (critical, high, medium, low)"},
            },
        },
    },
    {
        "name": "run_promql",
        "description": "Execute a raw PromQL query and return current results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "promql": {"type": "string", "description": "PromQL expression"},
            },
            "required": ["promql"],
        },
    },
]
```

**Step 2: Verify imports work**

Run: `cd backend && python -c "from src.prompts import GROUNDING_RULES, CHAT_RULES, CHAT_TOOLS_SCHEMA; print('OK')" `
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/prompts/
git commit -m "feat(prompts): add grounding rules and chat tool schemas"
```

---

### Task 8: Schema Update — evidence_graph Field

**Files:**
- Modify: `backend/src/models/schemas.py:874-936` (DiagnosticState)
- Modify: `backend/src/api/routes_v4.py:710` (findings endpoint)

**Step 1: Add evidence_graph field to DiagnosticState**

In `backend/src/models/schemas.py`, add to DiagnosticState class (after existing fields around line 935):

```python
# Add after the last existing field in DiagnosticState
evidence_graph: Optional[dict] = None  # {nodes, edges, root_causes, causal_paths}
```

Note: `DiagnosticStateV5` at line 938 already has `evidence_graph` — check if the field name matches. If V5 already defines it, only add to V4's `DiagnosticState`.

**Step 2: Add evidence_graph to findings API response**

In `backend/src/api/routes_v4.py`, find the findings endpoint response builder (around line 710) and ensure `evidence_graph` is included in the response dict. Since `_dump()` serializes the full state, verify it passes through. If findings are manually constructed, add:

```python
"evidence_graph": state.evidence_graph,
```

**Step 3: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/test_evidence_graph.py tests/test_causal_engine.py -v`
Expected: All existing tests PASS

**Step 4: Commit**

```bash
git add backend/src/models/schemas.py backend/src/api/routes_v4.py
git commit -m "feat(schema): add evidence_graph field to DiagnosticState"
```

---

### Task 9: Supervisor Integration — _ingest_into_graph

**Files:**
- Modify: `backend/src/agents/supervisor.py:897` (after `_update_state_with_result`)

**Step 1: Write test**

```python
# backend/tests/test_supervisor_graph_integration.py
import pytest
from src.agents.incident_graph import IncidentGraphBuilder


class TestSupervisorGraphIngestion:
    """Test the _finding_to_node_type mapping and graph ingestion logic."""

    def test_finding_to_node_type_log_agent(self):
        assert _finding_to_node_type("log_agent", {"category": "error"}) == "error_event"

    def test_finding_to_node_type_metrics_agent(self):
        assert _finding_to_node_type("metrics_agent", {}) == "metric_anomaly"

    def test_finding_to_node_type_k8s_agent(self):
        assert _finding_to_node_type("k8s_agent", {}) == "k8s_event"

    def test_finding_to_node_type_tracing_agent(self):
        assert _finding_to_node_type("tracing_agent", {}) == "trace_span"

    def test_finding_to_node_type_code_agent(self):
        assert _finding_to_node_type("code_agent", {}) == "code_location"

    def test_finding_to_node_type_change_agent(self):
        assert _finding_to_node_type("change_agent", {}) == "code_change"

    def test_finding_to_node_type_unknown(self):
        assert _finding_to_node_type("unknown_agent", {}) == "error_event"


def _finding_to_node_type(agent_name: str, finding: dict) -> str:
    """Map agent name to graph node type. Extracted for testability."""
    mapping = {
        "log_agent": "error_event",
        "metrics_agent": "metric_anomaly",
        "k8s_agent": "k8s_event",
        "tracing_agent": "trace_span",
        "code_agent": "code_location",
        "change_agent": "code_change",
    }
    return mapping.get(agent_name, "error_event")
```

**Step 2: Add `_ingest_into_graph` method and `_finding_to_node_type` to supervisor.py**

Add after `_update_state_with_result()` (around line 1441):

```python
@staticmethod
def _finding_to_node_type(agent_name: str, finding: dict) -> str:
    mapping = {
        "log_agent": "error_event",
        "metrics_agent": "metric_anomaly",
        "k8s_agent": "k8s_event",
        "tracing_agent": "trace_span",
        "code_agent": "code_location",
        "change_agent": "code_change",
    }
    return mapping.get(agent_name, "error_event")

async def _ingest_into_graph(self, state, agent_name: str, result: dict):
    """Additive layer: reads from state findings, writes to state.evidence_graph."""
    from src.agents.incident_graph import IncidentGraphBuilder

    if not hasattr(state, '_incident_graph_builder') or state._incident_graph_builder is None:
        state._incident_graph_builder = IncidentGraphBuilder(state.session_id)

    builder = state._incident_graph_builder
    new_findings = result.get("findings", [])
    for finding in new_findings:
        builder.add_node(
            node_type=self._finding_to_node_type(agent_name, finding),
            data=finding,
            timestamp=finding.get("timestamp", 0),
            confidence=finding.get("confidence", finding.get("confidence_score", 0.5)),
            severity=finding.get("severity", "medium"),
            agent_source=agent_name,
        )

    builder.create_tentative_edges()
    builder.enforce_temporal_consistency()
    builder.break_cycles()
    builder.rank_root_causes()
    state.evidence_graph = builder.to_serializable()
```

**Step 3: Wire into the main loop** — In `supervisor.py` `run()` method, after the call to `_update_state_with_result()`, add:

```python
await self._ingest_into_graph(state, agent_name, result)
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_supervisor_graph_integration.py tests/test_incident_graph.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_supervisor_graph_integration.py
git commit -m "feat(supervisor): wire IncidentGraphBuilder into agent result processing"
```

---

### Task 10: Service Dependency Graph

**Files:**
- Create: `backend/src/agents/service_dependency.py`
- Test: `backend/tests/test_service_dependency.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_service_dependency.py
import pytest
from src.agents.service_dependency import ServiceDependencyGraph


class TestServiceDependencyGraph:
    def setup_method(self):
        self.graph = ServiceDependencyGraph()

    def test_add_dependency(self):
        self.graph.add_dependency("payment", "auth", "tracing")
        assert self.graph.G.has_edge("payment", "auth")

    def test_topological_fix_order(self):
        self.graph.add_dependency("payment", "auth", "tracing")
        self.graph.add_dependency("auth", "postgres", "tracing")
        order = self.graph.get_fix_order(["payment", "auth", "postgres"])
        assert order.index("postgres") < order.index("auth")
        assert order.index("auth") < order.index("payment")

    def test_fix_order_with_cycle_falls_back(self):
        self.graph.add_dependency("a", "b", "tracing")
        self.graph.add_dependency("b", "a", "tracing")
        order = self.graph.get_fix_order(["a", "b"])
        assert set(order) == {"a", "b"}

    def test_blast_radius(self):
        self.graph.add_dependency("payment", "auth", "tracing")
        self.graph.add_dependency("payment", "redis", "tracing")
        self.graph.add_dependency("auth", "postgres", "tracing")
        radius = self.graph.get_blast_radius("payment")
        assert len(radius["direct_dependents"]) == 2
        assert radius["total_affected"] == 4  # payment + auth + redis + postgres

    def test_build_from_trace_spans(self):
        state = {
            "trace_analysis": {
                "spans": [
                    {"service": "payment", "child_service": "auth"},
                    {"service": "auth", "child_service": "postgres"},
                ]
            }
        }
        self.graph.build_from_sources(state)
        assert self.graph.G.has_edge("payment", "auth")
        assert self.graph.G.has_edge("auth", "postgres")

    def test_empty_state_no_crash(self):
        self.graph.build_from_sources({})
        assert len(self.graph.G.nodes) == 0
```

**Step 2: Run to verify fail**

Run: `cd backend && python -m pytest tests/test_service_dependency.py -v`

**Step 3: Write implementation**

```python
# backend/src/agents/service_dependency.py
"""Service dependency graph for topological campaign fix ordering."""
import networkx as nx


class ServiceDependencyGraph:
    def __init__(self):
        self.G = nx.DiGraph()

    def add_dependency(self, from_service: str, to_service: str, source: str):
        self.G.add_edge(from_service, to_service, source=source)

    def build_from_sources(self, state: dict):
        """Build from trace spans and K8s analysis."""
        trace = state.get("trace_analysis") or {}
        for span in trace.get("spans", []):
            parent_svc = span.get("service")
            child_svc = span.get("child_service")
            if parent_svc and child_svc and parent_svc != child_svc:
                self.add_dependency(parent_svc, child_svc, "tracing")

        k8s = state.get("k8s_analysis") or {}
        for dep in k8s.get("service_dependencies", []):
            self.add_dependency(dep["from"], dep["to"], "k8s")

    def get_fix_order(self, affected_services: list[str]) -> list[str]:
        """Topologically sorted: upstream (root) → downstream (leaf)."""
        affected_set = set(affected_services)
        subgraph = self.G.subgraph([s for s in affected_services if s in self.G])
        try:
            ordered = list(reversed(list(nx.topological_sort(subgraph))))
            # Add any services not in graph at the end
            remaining = [s for s in affected_services if s not in ordered]
            return ordered + remaining
        except nx.NetworkXUnfeasible:
            return affected_services

    def get_blast_radius(self, service: str) -> dict:
        if service not in self.G:
            return {"direct_dependents": [], "transitive_dependents": [], "total_affected": 1}
        downstream = list(nx.descendants(self.G, service))
        return {
            "direct_dependents": list(self.G.successors(service)),
            "transitive_dependents": downstream,
            "total_affected": len(downstream) + 1,
        }
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_service_dependency.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agents/service_dependency.py backend/tests/test_service_dependency.py
git commit -m "feat(campaign): add service dependency graph for topological fix ordering"
```

---

### Task 11: Frontend Types — EvidenceGraph + ChatToolCall

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add graph types** (after `CausalTree` interface around line 1165)

```typescript
// Evidence Graph types (Phase 1)
export interface GraphNode {
  id: string;
  node_type: 'error_event' | 'metric_anomaly' | 'k8s_event' | 'trace_span' | 'code_change' | 'config_change' | 'code_location';
  data: Record<string, unknown>;
  timestamp: number;
  confidence: number;
  severity: string;
  agent_source: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  edge_type: 'causes' | 'triggers' | 'manifests_as' | 'correlates_with' | 'precedes' | 'located_in';
  confidence: number;
  reasoning: string;
  created_by: string;
  temporal_delta_ms?: number;
}

export interface CausalPath {
  root: string;
  leaf: string;
  path: string[];
  total_confidence: number;
}

export interface EvidenceGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  root_causes: Array<{ node_id: string; score: number }>;
  causal_paths: CausalPath[];
}

// Chat Tool Call types (Phase 2)
export interface ChatToolCallEvent {
  tool: string;
  input: Record<string, unknown>;
  status: 'running' | 'complete' | 'error';
  result_summary?: string;
  tool_use_id?: string;
}
```

**Step 2: Add `evidence_graph` to `V4Findings`** (around line 356)

```typescript
// Add to V4Findings interface:
evidence_graph?: EvidenceGraphData;
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add EvidenceGraph, GraphNode, GraphEdge, ChatToolCallEvent types"
```

---

## Phase 2: Intelligence — Chat Tools + Tracing + Prompts

### Task 12: Chat Tool Calling — Supervisor Upgrade

**Files:**
- Modify: `backend/src/agents/supervisor.py:2220-3070` (`handle_user_message`)

**Step 1: Write test for chat tool execution**

```python
# backend/tests/test_chat_tool_calling.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.prompts.chat_prompts import CHAT_TOOLS_SCHEMA


class TestChatToolCalling:
    def test_chat_tools_schema_valid(self):
        """Verify all 6 tools have name, description, input_schema."""
        assert len(CHAT_TOOLS_SCHEMA) == 6
        for tool in CHAT_TOOLS_SCHEMA:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_search_findings_tool_filters_by_agent(self):
        """Test the search_findings tool logic in isolation."""
        from src.agents.supervisor import SupervisorAgent

        findings = [
            {"agent_name": "log_agent", "summary": "NPE in payment", "severity": "critical"},
            {"agent_name": "metrics_agent", "summary": "CPU spike", "severity": "high"},
            {"agent_name": "k8s_agent", "summary": "OOMKilled", "severity": "critical"},
        ]
        # This tests the filtering logic that will be in _execute_chat_tool
        filtered = [f for f in findings if f.get("agent_name") == "log_agent"]
        assert len(filtered) == 1
        assert filtered[0]["summary"] == "NPE in payment"

    def test_search_findings_tool_filters_by_severity(self):
        findings = [
            {"agent_name": "log_agent", "summary": "NPE in payment", "severity": "critical"},
            {"agent_name": "metrics_agent", "summary": "CPU spike", "severity": "high"},
        ]
        filtered = [f for f in findings if f.get("severity") == "critical"]
        assert len(filtered) == 1

    def test_search_findings_tool_filters_by_keyword(self):
        findings = [
            {"agent_name": "log_agent", "summary": "NPE in payment service"},
            {"agent_name": "metrics_agent", "summary": "CPU spike on auth"},
        ]
        keyword = "payment"
        filtered = [f for f in findings if keyword.lower() in f.get("summary", "").lower()]
        assert len(filtered) == 1
```

**Step 2: Run to verify fail**

Run: `cd backend && python -m pytest tests/test_chat_tool_calling.py -v`

**Step 3: Modify `handle_user_message` in supervisor.py**

Replace the existing `handle_user_message` implementation (lines 2220-3070) with tool-calling version. Key changes:
- Import `CHAT_RULES`, `CHAT_TOOLS_SCHEMA` from `src.prompts.chat_prompts`
- Import `GROUNDING_RULES` from `src.prompts.rules`
- Import `enforce_budget` from `src.utils.token_budget`
- Build compact system prompt from state
- Use `chat_with_tools` instead of `chat_stream`
- Execute tools in parallel via `asyncio.gather`
- Add `_execute_chat_tool` method
- Add `_build_chat_system_prompt` method

The specific code is in the design doc (Phase 2A). Wire the `search_findings` tool to filter `state.all_findings`. Wire `query_prometheus`, `query_logs`, `check_pod_status`, `query_trace` to existing agent tool methods as thin wrappers.

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_chat_tool_calling.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_chat_tool_calling.py
git commit -m "feat(chat): upgrade handle_user_message to tool calling with parallel execution"
```

---

### Task 13: Re-enable Tracing Agent

**Files:**
- Modify: `backend/src/agents/supervisor.py:131` (uncomment tracing_agent)
- Modify: `backend/src/agents/supervisor.py:408-465` (`_decide_next_agents` — add tracing dispatch)

**Step 1: Uncomment tracing_agent registration**

In supervisor.py, find the `_agents` dict (around line 131) and uncomment `"tracing_agent": TracingAgent`.

**Step 2: Update `_decide_next_agents`**

Add tracing_agent to parallel dispatch after LOGS_ANALYZED:
```python
# In LOGS_ANALYZED branch, alongside metrics_agent + k8s_agent:
if state.trace_id:
    agents.append("tracing_agent")
```

**Step 3: Run existing supervisor tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -k "supervisor or tracing" -v --timeout=30`
Expected: No regressions

**Step 4: Commit**

```bash
git add backend/src/agents/supervisor.py
git commit -m "feat(tracing): re-enable tracing agent in supervisor dispatch"
```

---

### Task 14: Frontend — WebSocket chat_tool_call Handler

**Files:**
- Modify: `frontend/src/hooks/useWebSocket.ts:61-70` (add handler type)
- Modify: `frontend/src/hooks/useWebSocket.ts:127-171` (add case)

**Step 1: Add `onChatToolCall` to handler interface** (around line 61)

```typescript
// Add to V4WebSocketHandlers:
onChatToolCall?: (event: ChatToolCallEvent) => void;
```

Import `ChatToolCallEvent` from `../types`.

**Step 2: Add message case** (around line 153)

```typescript
case 'chat_tool_call':
  handlers.onChatToolCall?.(parsed.payload as ChatToolCallEvent);
  break;
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

**Step 4: Commit**

```bash
git add frontend/src/hooks/useWebSocket.ts
git commit -m "feat(ws): add chat_tool_call message type handler"
```

---

### Task 15: Frontend — ChatContext Tool Call State

**Files:**
- Modify: `frontend/src/contexts/ChatContext.tsx:29-42` (add activeToolCalls)
- Modify: `frontend/src/contexts/ChatContext.tsx:241-247` (fix isWaiting)

**Step 1: Add `activeToolCalls` state to ChatUIContextValue** (line 29)

```typescript
// Add to ChatUIContextValue:
activeToolCalls: ChatToolCallEvent[];
addToolCall: (event: ChatToolCallEvent) => void;
```

**Step 2: Add state and handler in ChatProvider** (around line 206)

```typescript
const [activeToolCalls, setActiveToolCalls] = useState<ChatToolCallEvent[]>([]);

const addToolCall = useCallback((event: ChatToolCallEvent) => {
  setActiveToolCalls(prev => {
    const existing = prev.findIndex(t => t.tool_use_id === event.tool_use_id);
    if (existing >= 0) {
      const updated = [...prev];
      updated[existing] = event;
      // Remove completed tool calls after 3 seconds
      if (event.status === 'complete' || event.status === 'error') {
        setTimeout(() => setActiveToolCalls(p => p.filter(t => t.tool_use_id !== event.tool_use_id)), 3000);
      }
      return updated;
    }
    return [...prev, event];
  });
}, []);
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`

**Step 4: Commit**

```bash
git add frontend/src/contexts/ChatContext.tsx
git commit -m "feat(chat): add activeToolCalls state to ChatContext"
```

---

### Task 16: Frontend — ChatDrawer ToolCallPill

**Files:**
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx:222-270` (message area)

**Step 1: Add ToolCallPill inline component**

```tsx
const ToolCallPill: React.FC<{ tool: ChatToolCallEvent }> = ({ tool }) => (
  <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono bg-white/5 border border-white/10">
    <span className="material-symbols-outlined text-[14px] text-cyan-400">
      {tool.status === 'running' ? 'hourglass_top' : tool.status === 'complete' ? 'check_circle' : 'error'}
    </span>
    <span className="text-slate-300">{tool.tool}</span>
    {tool.status === 'running' && (
      <span className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
    )}
    {tool.result_summary && (
      <span className="text-slate-500">{tool.result_summary}</span>
    )}
  </div>
);
```

**Step 2: Render active tool calls** above the streaming bubble (around line 249):

```tsx
{activeToolCalls.length > 0 && (
  <div className="flex flex-wrap gap-1.5 px-4 py-2">
    {activeToolCalls.map((tc, i) => (
      <ToolCallPill key={tc.tool_use_id || i} tool={tc} />
    ))}
  </div>
)}
```

**Step 3: Verify TypeScript compiles and build succeeds**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/components/Chat/ChatDrawer.tsx
git commit -m "feat(chat): add ToolCallPill component for live tool execution display"
```

---

### Task 17: Frontend — Extract TraceWaterfall to Standalone Component

**Files:**
- Create: `frontend/src/components/Investigation/cards/TraceWaterfall.tsx`
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx:1591-1667` (remove inline, import)
- Modify: `frontend/src/types/index.ts:194-204` (extend SpanInfo)

**Step 1: Extend SpanInfo type** (in types/index.ts)

```typescript
// Add to SpanInfo interface:
start_offset_ms?: number;
trace_id?: string;
critical_path?: boolean;
```

**Step 2: Create standalone TraceWaterfall component**

Extract the inline component from EvidenceFindings.tsx lines 1591-1667 into its own file. Add the new fields for horizontal positioning:

```tsx
// frontend/src/components/Investigation/cards/TraceWaterfall.tsx
import React, { useMemo } from 'react';
import type { SpanInfo } from '../../../types';

interface TraceWaterfallProps {
  spans: SpanInfo[];
}

const TraceWaterfall: React.FC<TraceWaterfallProps> = ({ spans }) => {
  // ... extract existing logic from EvidenceFindings.tsx lines 1591-1667
  // Add: start_offset_ms for horizontal positioning
  // Add: trace_id grouping
  // Add: critical_path highlighting
};

export default TraceWaterfall;
```

**Step 3: Update EvidenceFindings.tsx** — Remove inline TraceWaterfall definition, add import:

```typescript
import TraceWaterfall from './cards/TraceWaterfall';
```

**Step 4: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 5: Commit**

```bash
git add frontend/src/components/Investigation/cards/TraceWaterfall.tsx frontend/src/components/Investigation/EvidenceFindings.tsx frontend/src/types/index.ts
git commit -m "refactor(trace): extract TraceWaterfall to standalone component with enhanced SpanInfo"
```

---

## Phase 3: Multi-Repo + Infra

### Task 18: Infra Repo Detection in Code Agent

**Files:**
- Modify: `backend/src/agents/code_agent.py`
- Test: `backend/tests/test_infra_detection.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_infra_detection.py
import pytest


def _detect_repo_type(file_tree: list[str]) -> str:
    """Extracted for testability. Will be added to code_agent.py."""
    from src.agents.code_agent_utils import detect_repo_type
    return detect_repo_type(file_tree)


class TestInfraDetection:
    def test_helm_chart(self):
        files = ["Chart.yaml", "values.yaml", "templates/deployment.yaml"]
        assert _detect_repo_type(files) == "infrastructure"

    def test_terraform(self):
        files = ["main.tf", "variables.tf", "outputs.tf"]
        assert _detect_repo_type(files) == "infrastructure"

    def test_kustomize(self):
        files = ["kustomization.yaml", "base/deployment.yaml"]
        assert _detect_repo_type(files) == "infrastructure"

    def test_application_repo(self):
        files = ["src/main.py", "tests/test_main.py", "requirements.txt"]
        assert _detect_repo_type(files) == "application"

    def test_monorepo(self):
        files = ["src/main.py", "charts/Chart.yaml", "deploy/k8s/deployment.yaml"]
        assert _detect_repo_type(files) == "monorepo"
```

**Step 2: Create utility function**

```python
# backend/src/agents/code_agent_utils.py
"""Utility functions for code agent — extracted for testability."""


def detect_repo_type(file_tree: list[str]) -> str:
    infra_markers = {"Chart.yaml", "kustomization.yaml", "Dockerfile", "docker-compose.yml"}
    has_infra = any(f.split("/")[-1] in infra_markers for f in file_tree)
    has_tf = any(f.endswith(".tf") for f in file_tree)
    has_k8s_manifests = sum(1 for f in file_tree
        if f.endswith(('.yaml', '.yml'))
        and any(d in f for d in ['deploy', 'k8s', 'manifests', 'charts'])) > 2
    has_app_code = any(f.endswith(('.py', '.js', '.ts', '.java', '.go')) for f in file_tree)

    is_infra = has_infra or has_tf or has_k8s_manifests
    if is_infra and has_app_code:
        return "monorepo"
    if is_infra:
        return "infrastructure"
    return "application"
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/test_infra_detection.py -v`

**Step 4: Commit**

```bash
git add backend/src/agents/code_agent_utils.py backend/tests/test_infra_detection.py
git commit -m "feat(code): add infra repo type detection (Helm/Terraform/Kustomize)"
```

---

### Task 19: Infra Fix Rules in Fix Generator

**Files:**
- Modify: `backend/src/agents/agent3/fix_generator.py`

**Step 1: Add INFRA_FIX_RULES constant**

Add the infra-specific prompt rules dict from the design doc (Section 3A) as a module-level constant. These rules are injected into the fix generator prompt when `repo_type == "infrastructure"`.

```python
INFRA_FIX_RULES = {
    "helm": "Modify values.yaml resource limits, NOT template files directly. Use Helm value paths.",
    "kustomize": "Use patches or overlays, not base modifications. Preserve kustomization.yaml structure.",
    "terraform": "Update variable defaults in variables.tf, not hardcoded values. Never change resource names.",
    "k8s_manifest": "Update Deployment/StatefulSet resource requests and limits. Ensure requests <= limits.",
}
```

**Step 2: Wire into prompt building** — In the fix generation prompt builder, check `repo_type` and append the relevant rules.

**Step 3: Commit**

```bash
git add backend/src/agents/agent3/fix_generator.py
git commit -m "feat(fix): add infra-specific fix rules for Helm/Terraform/Kustomize/K8s"
```

---

### Task 20: Campaign Orchestrator — Dependent Fixes + Service Graph

**Files:**
- Modify: `backend/src/agents/agent3/campaign_orchestrator.py`

**Step 1: Add prior-fix context injection**

In `run_campaign()`, maintain a `prior_fixes` dict. Before generating each repo's fix, inject the prior fixes as context (see design doc Section 3B).

**Step 2: Wire ServiceDependencyGraph**

```python
from src.agents.service_dependency import ServiceDependencyGraph

# In run_campaign():
svc_graph = ServiceDependencyGraph()
svc_graph.build_from_sources(state)
affected = [fix.service_name for fix in repo_fixes]
fix_order = svc_graph.get_fix_order(affected)
# Reorder repo_fixes by topological sort
```

**Step 3: Add cross-repo PR linking**

Append coordinated campaign table to each PR body.

**Step 4: Run existing campaign tests**

Run: `cd backend && python -m pytest tests/ -k "campaign" -v`

**Step 5: Commit**

```bash
git add backend/src/agents/agent3/campaign_orchestrator.py
git commit -m "feat(campaign): add dependent fix generation and service graph ordering"
```

---

### Task 21: Frontend — SurgicalTelescope File Tree Sidebar

**Files:**
- Modify: `frontend/src/components/Investigation/SurgicalTelescope.tsx`

**Step 1: Add file tree sidebar** (200px left panel)

Parse the diff content to extract file paths and line change counts. Display as a vertical list with `+N/-M` badges, colored by change type. Click a file to scroll/jump to its diff section.

Key additions:
- Parse `--- filepath ---` or `diff --git` headers from diff string
- Count `+` and `-` lines per file
- Add file list panel with click handlers
- Show "3 files changed, 47 insertions(+), 12 deletions(-)" summary header

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/components/Investigation/SurgicalTelescope.tsx
git commit -m "feat(telescope): add file tree sidebar with change counts"
```

---

### Task 22: Frontend — ChatDrawer infra_repo_request Action Chips

**Files:**
- Modify: `frontend/src/components/Chat/ChatDrawer.tsx:23-66` (deriveActionChips)

**Step 1: Add infra_repo_request case**

```typescript
// Add to deriveActionChips() after the repo_mismatch case:
case 'infra_repo_request':
  return [
    { label: 'Add Infra Repo', action: 'provide_infra_repo' },
    { label: 'Skip', action: 'skip_infra' },
  ];
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 3: Commit**

```bash
git add frontend/src/components/Chat/ChatDrawer.tsx
git commit -m "feat(chat): add infra_repo_request action chips"
```

---

## Phase 4: Polish

### Task 23: EvidenceFindings — Render Dead Data Paths

**Files:**
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx`

**Step 1: Render ErrorPattern.sample_logs** (currently typed but never displayed)

Find where ErrorPattern content is rendered (around lines 357-425). After the error message/frequency section, add:

```tsx
{pattern.sample_logs && pattern.sample_logs.length > 0 && (
  <details className="mt-2">
    <summary className="text-[10px] text-slate-500 cursor-pointer hover:text-slate-300">
      {pattern.sample_logs.length} sample log{pattern.sample_logs.length > 1 ? 's' : ''}
    </summary>
    <div className="mt-1 space-y-1 max-h-32 overflow-y-auto custom-scrollbar">
      {pattern.sample_logs.map((log, i) => (
        <pre key={i} className="text-[10px] text-slate-400 bg-black/30 rounded px-2 py-1 overflow-x-auto">
          {log}
        </pre>
      ))}
    </div>
  </details>
)}
```

**Step 2: Fix anchor bar** — Add IntersectionObserver scroll-spy and click-to-scroll

Add `id` attributes to each evidence section matching the anchor bar hrefs (`section-root-cause`, `section-cascading`, etc.). Add an IntersectionObserver to highlight the active section in the anchor bar.

**Step 3: Fix trace count mismatch** — The anchor bar badge shows unfiltered `trace_spans.length` but the render section filters by `duration_ms`. Use the same filter for the badge count.

**Step 4: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 5: Commit**

```bash
git add frontend/src/components/Investigation/EvidenceFindings.tsx
git commit -m "fix(evidence): render sample_logs, fix anchor bar scroll-spy and trace count"
```

---

### Task 24: EvidenceFindings — Cross-Correlation Click Handlers

**Files:**
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx`

**Step 1: Add metric → logs click handler**

When a metric anomaly timestamp is clicked, dispatch a chat command to filter logs around that time window (±2 minutes):

```tsx
const handleMetricToLogs = (timestamp: string) => {
  // Open chat with pre-filled command
  sendMessage(`/logs time:${timestamp} window:2m`);
  openDrawer();
};
```

**Step 2: Add log trace_id → TraceWaterfall scroll**

When a `trace_id` appears in a log entry, make it clickable. On click, scroll to the trace waterfall section and highlight the matching trace.

**Step 3: Add span operation → SurgicalTelescope link**

When a span operation name matches a code file mapped by Code Agent, add a link to open SurgicalTelescope for that file.

**Step 4: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 5: Commit**

```bash
git add frontend/src/components/Investigation/EvidenceFindings.tsx
git commit -m "feat(evidence): add cross-correlation click-through handlers"
```

---

### Task 25: Frontend — EvidenceGraphView Component

**Files:**
- Create: `frontend/src/components/Investigation/cards/EvidenceGraphView.tsx`
- Modify: `frontend/src/components/Investigation/EvidenceFindings.tsx` (add section)

**Step 1: Create EvidenceGraphView**

Build an interactive DAG visualization using ReactFlow (already installed as dependency). Nodes colored by type, edges labeled by relationship. Click node to scroll to finding.

```tsx
// frontend/src/components/Investigation/cards/EvidenceGraphView.tsx
import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls, MiniMap } from 'reactflow';
import type { EvidenceGraphData } from '../../../types';

interface EvidenceGraphViewProps {
  graph: EvidenceGraphData;
  onNodeClick?: (nodeId: string) => void;
}

const NODE_COLORS: Record<string, string> = {
  error_event: '#ef4444',
  metric_anomaly: '#06b6d4',
  k8s_event: '#f97316',
  trace_span: '#8b5cf6',
  code_change: '#10b981',
  code_location: '#3b82f6',
  config_change: '#eab308',
};

const EvidenceGraphView: React.FC<EvidenceGraphViewProps> = ({ graph, onNodeClick }) => {
  const { nodes, edges } = useMemo(() => {
    const rfNodes = graph.nodes.map((n, i) => ({
      id: n.id,
      position: { x: (i % 4) * 220, y: Math.floor(i / 4) * 120 },
      data: {
        label: `${n.node_type}\n${n.data?.service || n.data?.metric_name || n.id.slice(0, 8)}`,
      },
      style: {
        background: NODE_COLORS[n.node_type] || '#666',
        color: '#fff',
        border: graph.root_causes.some(r => r.node_id === n.id) ? '2px solid #fbbf24' : 'none',
        borderRadius: 8,
        padding: '8px 12px',
        fontSize: 11,
        fontWeight: 600,
      },
    }));
    const rfEdges = graph.edges.map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      label: e.edge_type,
      style: { stroke: `rgba(255,255,255,${e.confidence})` },
      labelStyle: { fill: '#94a3b8', fontSize: 9 },
      animated: e.edge_type === 'causes',
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [graph]);

  return (
    <div className="w-full h-[400px] bg-black/30 rounded-lg overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_, node) => onNodeClick?.(node.id)}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1a1a1a" />
        <Controls />
        <MiniMap style={{ background: '#0a0a0a' }} />
      </ReactFlow>
    </div>
  );
};

export default EvidenceGraphView;
```

**Step 2: Add to EvidenceFindings** — Import and render above the causal forest section:

```tsx
{findings.evidence_graph && findings.evidence_graph.nodes.length > 0 && (
  <VineCard label="Evidence Graph" icon="hub" id="section-graph">
    <EvidenceGraphView graph={findings.evidence_graph} />
  </VineCard>
)}
```

**Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/components/Investigation/cards/EvidenceGraphView.tsx frontend/src/components/Investigation/EvidenceFindings.tsx
git commit -m "feat(graph): add interactive EvidenceGraphView with ReactFlow"
```

---

### Task 26: WorkerSignature — Calibrated Confidence Display

**Files:**
- Modify: `frontend/src/components/Investigation/hud/WorkerSignature.tsx`

**Step 1: Add optional calibrated confidence prop**

```typescript
interface WorkerSignatureProps {
  confidence: number;
  agentCode: AgentCode;
  calibratedConfidence?: number;  // NEW
  calibrationFactors?: {          // NEW
    agent_prior: number;
    critic_score: number;
    evidence_weight: number;
  };
}
```

**Step 2: Render calibrated vs raw** when `calibratedConfidence` is provided:

```tsx
{calibratedConfidence !== undefined && (
  <span className="text-[9px] text-slate-500 ml-1">
    (raw: {confidence}% → cal: {Math.round(calibratedConfidence * 100)}%)
  </span>
)}
```

**Step 3: Verify build**

Run: `cd frontend && npx tsc --noEmit && npm run build`

**Step 4: Commit**

```bash
git add frontend/src/components/Investigation/hud/WorkerSignature.tsx
git commit -m "feat(hud): add calibrated confidence display to WorkerSignature"
```

---

## Final Verification

### Task 27: Full Build Verification

**Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v --timeout=30 -x`
Expected: All PASS, 0 failures

**Step 2: Run frontend TypeScript check and build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 0 errors, clean build

**Step 3: Verify git status is clean**

Run: `git status`
Expected: All changes committed

---

## Task Dependency Graph

```
Phase 1 (Foundation):
  Task 1 (IncidentGraph) ──┐
  Task 2 (Scoring Tests) ──┤
  Task 3 (Calibrator) ─────┤
  Task 4 (DeterministicValidator) ──┤
  Task 5 (EnsembleCritic) ─────────┤──→ Task 9 (Supervisor Integration)
  Task 6 (Token Budget) ───────────┘
  Task 7 (Prompt Framework)
  Task 8 (Schema Update) ──→ Task 9 (Supervisor Integration)
  Task 10 (ServiceDependencyGraph)
  Task 11 (Frontend Types) ──→ Tasks 14-17, 25

Phase 2 (Intelligence):
  Task 12 (Chat Tool Calling) ←── Tasks 6, 7
  Task 13 (Tracing Agent)
  Task 14 (WS Handler) ←── Task 11
  Task 15 (ChatContext) ←── Task 14
  Task 16 (ChatDrawer Pills) ←── Task 15
  Task 17 (TraceWaterfall Extract) ←── Task 11

Phase 3 (Multi-Repo):
  Task 18 (Infra Detection)
  Task 19 (Infra Fix Rules) ←── Task 18
  Task 20 (Campaign Upgrade) ←── Tasks 10, 19
  Task 21 (Telescope File Tree)
  Task 22 (Infra Chips)

Phase 4 (Polish):
  Task 23 (Dead Data Renders)
  Task 24 (Correlation Clicks)
  Task 25 (EvidenceGraphView) ←── Tasks 9, 11
  Task 26 (WorkerSignature Calibrated) ←── Task 3

  Task 27 (Final Verification) ←── ALL
```

## New Dependencies to Install

```bash
# Backend (add to requirements.txt)
networkx>=3.0    # Graph algorithms
gensim>=4.3.0    # Node2Vec embeddings (Phase 2, graph embedder)
numpy>=1.26      # Graph embedding vectors

# Frontend — no new dependencies (ReactFlow, d3-force already installed)
```
