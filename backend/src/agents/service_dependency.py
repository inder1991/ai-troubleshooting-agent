"""Service dependency graph for topological campaign fix ordering."""
import networkx as nx


class ServiceDependencyGraph:
    def __init__(self):
        self.G = nx.DiGraph()

    def add_dependency(self, from_service: str, to_service: str, source: str):
        self.G.add_edge(from_service, to_service, source=source)

    def build_from_sources(self, state: dict):
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
        affected_set = set(affected_services)
        subgraph = self.G.subgraph([s for s in affected_services if s in self.G])
        try:
            ordered = list(reversed(list(nx.topological_sort(subgraph))))
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
