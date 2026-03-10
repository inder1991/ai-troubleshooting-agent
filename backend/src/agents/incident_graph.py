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
        """Add an evidence node to the graph and return its unique ID."""
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
        """Add a confirmed causal edge between two nodes with temporal delta."""
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
                # Same trace_id -> correlates_with
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
        """Causal Influence Scoring: downstream_reach + temporal_priority + critic_confidence.

        Weights:
        - downstream_reach (0.4): root causes propagate widely
        - temporal_priority (0.35): causes precede effects
        - critic_confidence (0.25): validated edges increase trust
        """
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
                            default=0.0,
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
