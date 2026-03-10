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
        assert radius["total_affected"] == 4

    def test_build_from_trace_spans(self):
        state = {"trace_analysis": {"spans": [{"service": "payment", "child_service": "auth"}, {"service": "auth", "child_service": "postgres"}]}}
        self.graph.build_from_sources(state)
        assert self.graph.G.has_edge("payment", "auth")
        assert self.graph.G.has_edge("auth", "postgres")

    def test_empty_state_no_crash(self):
        self.graph.build_from_sources({})
        assert len(self.graph.G.nodes) == 0
