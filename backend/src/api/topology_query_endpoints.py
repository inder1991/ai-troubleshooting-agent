"""Topology query endpoints — path-finding, IP resolution, neighbors."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from src.utils.logger import get_logger

logger = get_logger(__name__)

topology_query_router = APIRouter(prefix="/api/v4/network/query", tags=["topology-query"])

_knowledge_graph = None


def init_topology_query_endpoints(knowledge_graph):
    global _knowledge_graph
    _knowledge_graph = knowledge_graph


@topology_query_router.get("/paths")
def find_paths(src: str, dst: str, k: int = 3):
    kg = _knowledge_graph
    if not kg:
        return {"paths": []}
    paths = kg.find_k_shortest_paths(src, dst, k)
    return {"paths": paths, "src": src, "dst": dst, "k": k}


@topology_query_router.get("/resolve-ip")
def resolve_ip(ip: str):
    kg = _knowledge_graph
    if not kg:
        return {"candidates": []}
    candidates = kg.find_candidate_devices(ip)
    return {"ip": ip, "candidates": candidates}


@topology_query_router.get("/neighbors/{device_id}")
def get_neighbors(device_id: str):
    kg = _knowledge_graph
    if not kg or device_id not in kg.graph:
        raise HTTPException(status_code=404, detail="Device not found")
    successors = list(kg.graph.successors(device_id))
    predecessors = list(kg.graph.predecessors(device_id))
    neighbors = list(set(successors + predecessors))
    edges = []
    for n in neighbors:
        if kg.graph.has_edge(device_id, n):
            edge_data = dict(kg.graph[device_id][n])
            edges.append({"src": device_id, "dst": n, **edge_data})
        if kg.graph.has_edge(n, device_id):
            edge_data = dict(kg.graph[n][device_id])
            edges.append({"src": n, "dst": device_id, **edge_data})
    return {"device_id": device_id, "neighbors": neighbors, "edges": edges}


@topology_query_router.post("/boost-confidence")
def boost_confidence(body: dict):
    kg = _knowledge_graph
    if not kg:
        raise HTTPException(status_code=503, detail="KG not available")
    src = body.get("src", "")
    dst = body.get("dst", "")
    boost = body.get("boost", 0.05)
    kg.boost_edge_confidence(src, dst, boost)
    return {"status": "boosted", "src": src, "dst": dst}
