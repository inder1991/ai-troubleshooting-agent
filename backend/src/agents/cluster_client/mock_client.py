"""Mock ClusterClient that returns fixture data for demo/dev/testing."""

from __future__ import annotations
import json
import os
from typing import Any
from src.agents.cluster_client.base import ClusterClient, QueryResult, OBJECT_CAPS

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")

def _load_fixture(name: str) -> dict:
    path = os.path.join(FIXTURES_DIR, name)
    with open(path, "r") as f:
        return json.load(f)

class MockClusterClient(ClusterClient):
    def __init__(self, platform: str = "openshift"):
        self._platform = platform

    async def detect_platform(self) -> dict[str, str]:
        return {"platform": self._platform, "version": "4.14.2" if self._platform == "openshift" else "1.28.3"}

    async def list_namespaces(self) -> QueryResult:
        ns = ["default", "kube-system", "monitoring", "production", "staging"]
        return QueryResult(data=ns, total_available=len(ns), returned=len(ns))

    async def list_nodes(self) -> QueryResult:
        data = _load_fixture("cluster_node_mock.json")
        nodes = data["nodes"]
        return QueryResult(data=nodes, total_available=len(nodes), returned=len(nodes))

    async def list_pods(self, namespace: str = "") -> QueryResult:
        data = _load_fixture("cluster_node_mock.json")
        pods = data.get("top_pods", [])
        return QueryResult(data=pods, total_available=len(pods), returned=len(pods))

    async def list_events(self, namespace: str = "", field_selector: str = "") -> QueryResult:
        data = _load_fixture("cluster_node_mock.json")
        events = data.get("events", [])
        cap = OBJECT_CAPS["events"]
        truncated = len(events) > cap
        returned = events[:cap]
        return QueryResult(data=returned, total_available=len(events), returned=len(returned), truncated=truncated)

    async def list_pvcs(self, namespace: str = "") -> QueryResult:
        data = _load_fixture("cluster_storage_mock.json")
        pvcs = data.get("pvcs", [])
        return QueryResult(data=pvcs, total_available=len(pvcs), returned=len(pvcs))

    async def get_api_health(self) -> dict[str, Any]:
        data = _load_fixture("cluster_ctrl_plane_mock.json")
        return data.get("api_health", {"status": "ok"})

    async def query_prometheus(self, query: str, time_range: str = "1h") -> QueryResult:
        if "dns" in query or "coredns" in query:
            data = _load_fixture("cluster_network_mock.json")
            metrics = data.get("dns_metrics", {})
        elif "node" in query or "cpu" in query or "memory" in query:
            data = _load_fixture("cluster_node_mock.json")
            metrics = {"nodes": data.get("nodes", [])}
        else:
            metrics = {"value": 0}
        return QueryResult(data=[metrics], total_available=1, returned=1)

    async def query_logs(self, index: str, query: dict, max_lines: int = 2000) -> QueryResult:
        data = _load_fixture("cluster_network_mock.json")
        logs = data.get("logs", [])
        return QueryResult(data=logs, total_available=len(logs), returned=len(logs))

    async def get_cluster_operators(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        data = _load_fixture("cluster_ctrl_plane_mock.json")
        ops = data.get("cluster_operators", [])
        return QueryResult(data=ops, total_available=len(ops), returned=len(ops))

    async def get_machine_sets(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        return QueryResult(data=[{"name": "worker-us-east-1a", "replicas": 3, "ready": 3}], total_available=1, returned=1)

    async def get_routes(self, namespace: str = "") -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        return QueryResult(data=[{"name": "app-route", "host": "app.example.com", "status": "Admitted"}], total_available=1, returned=1)
