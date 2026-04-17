"""
IncidentGraph — strictly-typed directed graph of incident evidence.

Edge types form a closed enum (causes/correlates/precedes/contradicts/supports).
'causes' edges cannot be added directly — they must satisfy the CausalRuleEngine
(temporal precedence, lag within bound, registered signature pattern or explicit
user override). This removes the prior "any edge is as good as any other" bug
and is a prerequisite for deterministic root-cause ranking.
"""
from __future__ import annotations

import networkx as nx

EDGE_TYPES: frozenset[str] = frozenset(
    {"causes", "correlates", "precedes", "contradicts", "supports"}
)

# Max plausible lag between cause and effect. Overridable per-engine.
DEFAULT_MAX_LAG_S: int = 3600

# Weights used to score downstream influence when ranking root causes. Held
# here (not in a YAML) because the set of edge types is itself a closed enum;
# co-locating the weights keeps the policy auditable.
_EDGE_WEIGHTS: dict[str, float] = {
    "causes": 1.0,
    "precedes": 0.5,
    "correlates": 0.2,
    "supports": 0.1,
    "contradicts": -0.3,
}


class CausalRuleEngine:
    """Certifies whether a proposed 'causes' edge is admissible.

    Admission rules (all must hold, unless `user_override=True`):
      a. temporal precedence: source.t <= target.t
      b. lag within bound: `lag_s is not None and lag_s <= max_lag_s`
      c. pattern match: `pattern_id` is set (the Phase-4 signature library
         registers these; until then callers must pass an explicit id or
         use user_override).
    """

    def __init__(self, max_lag_s: int = DEFAULT_MAX_LAG_S) -> None:
        self.max_lag_s = max_lag_s

    def certify(
        self,
        graph: nx.DiGraph,
        source: str,
        target: str,
        *,
        lag_s: int | None,
        pattern_id: str | None,
        user_override: bool = False,
    ) -> None:
        if user_override:
            return
        src = graph.nodes[source]
        tgt = graph.nodes[target]
        src_t = src.get("t")
        tgt_t = tgt.get("t")
        if src_t is None or tgt_t is None:
            raise ValueError(
                f"certify: temporal information missing on {source!r} or {target!r}"
            )
        if src_t > tgt_t:
            raise ValueError(
                f"certify: temporal order violated (source t={src_t} > target t={tgt_t})"
            )
        if lag_s is None or lag_s > self.max_lag_s:
            raise ValueError(
                f"certify: lag_s must be <= {self.max_lag_s}s; got {lag_s!r}"
            )
        if pattern_id is None:
            raise ValueError(
                "certify: no pattern match — pass pattern_id (Phase 4 signature library) "
                "or user_override=True for manual classification"
            )


class IncidentGraph:
    """Typed directed graph of incident evidence.

    Thin wrapper over networkx.DiGraph enforcing:
      - every edge carries an `edge_type` from EDGE_TYPES
      - `causes` edges must pass CausalRuleEngine.certify
    """

    SCHEMA_VERSION: int = 1

    def __init__(self, rule_engine: CausalRuleEngine | None = None) -> None:
        self.G: nx.DiGraph = nx.DiGraph()
        self._rule_engine = rule_engine or CausalRuleEngine()

    @property
    def nodes(self):
        return self.G.nodes

    @property
    def edges(self):
        return self.G.edges

    def add_node(self, node_id: str, t: float | None = None, **attrs) -> None:
        """Add a node. `t` is the event timestamp (seconds, any monotonic origin)."""
        self.G.add_node(node_id, t=t, **attrs)

    def add_edge(
        self,
        source: str,
        target: str,
        *,
        edge_type: str | None = None,
        lag_s: int | None = None,
        pattern_id: str | None = None,
        user_override: bool = False,
        **attrs,
    ) -> None:
        if edge_type is None:
            raise ValueError("edge_type is required (one of %s)" % sorted(EDGE_TYPES))
        if edge_type not in EDGE_TYPES:
            raise ValueError(
                f"edge_type must be one of {sorted(EDGE_TYPES)}, got {edge_type!r}"
            )
        if edge_type == "causes":
            if source not in self.G or target not in self.G:
                raise ValueError(
                    "edge_type='causes' requires both source and target nodes to "
                    "exist before the edge is added"
                )
            self._rule_engine.certify(
                self.G,
                source,
                target,
                lag_s=lag_s,
                pattern_id=pattern_id,
                user_override=user_override,
            )
        self.G.add_edge(
            source,
            target,
            edge_type=edge_type,
            lag_s=lag_s,
            pattern_id=pattern_id,
            **attrs,
        )

    def outgoing_edges(self, node: str) -> list[tuple[str, str, dict]]:
        return [(u, v, d) for u, v, d in self.G.out_edges(node, data=True)]

    def incoming_edges(self, node: str) -> list[tuple[str, str, dict]]:
        return [(u, v, d) for u, v, d in self.G.in_edges(node, data=True)]

    def incoming_causes(self, node: str) -> int:
        return sum(
            1 for _, _, d in self.incoming_edges(node)
            if d.get("edge_type") == "causes"
        )

    def depth(self, node: str) -> int:
        """Longest path length from any graph source to `node`."""
        best = 0
        for src in self.G.nodes:
            if src == node:
                continue
            if not nx.has_path(self.G, src, node):
                continue
            length = nx.shortest_path_length(self.G, src, node)
            if length > best:
                best = length
        return best

    def rank_root_causes(self) -> list[tuple[str, float]]:
        """Rank nodes by weighted outgoing edge-type influence.

        Weights (see EDGE_WEIGHTS above):
          causes > precedes > correlates > supports; contradicts penalises.
        """
        scores: dict[str, float] = {}
        for n in self.G.nodes:
            score = 0.0
            for _, _, d in self.G.out_edges(n, data=True):
                score += _EDGE_WEIGHTS.get(d.get("edge_type", ""), 0.0)
            scores[n] = round(score, 4)
        return sorted(scores.items(), key=lambda item: -item[1])

    def to_serializable(self) -> dict:
        """Serialize graph to dict for API response / state storage."""
        nodes = [{"id": nid, **data} for nid, data in self.G.nodes(data=True)]
        edges = [
            {"source": u, "target": v, **data}
            for u, v, data in self.G.edges(data=True)
        ]
        return {
            "schema_version": self.SCHEMA_VERSION,
            "nodes": nodes,
            "edges": edges,
            "root_causes": [
                {"node_id": n, "score": s} for n, s in self.rank_root_causes()[:5]
            ],
        }
