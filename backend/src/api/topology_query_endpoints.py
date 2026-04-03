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


@topology_query_router.get("/blast-radius")
def get_blast_radius(device_id: str):
    """Compute failure impact — all devices downstream of this device on physical links."""
    kg = _knowledge_graph
    if not kg:
        return {"device_id": device_id, "affected": [], "count": 0}
    if device_id not in kg.graph:
        raise HTTPException(status_code=404, detail="Device not found in topology")

    import networkx as nx

    PHYSICAL_EDGE_TYPES = {"layer2_link", "layer3_link", "tunnel_link",
                           "attached_to", "load_balances", "mpls_path", "ha_peer"}

    # Build physical-only subgraph
    physical_subgraph = nx.DiGraph()
    physical_subgraph.add_nodes_from(kg.graph.nodes(data=True))
    for u, v, data in kg.graph.edges(data=True):
        if data.get("edge_type", "") in PHYSICAL_EDGE_TYPES:
            physical_subgraph.add_edge(u, v, **data)

    try:
        descendants = nx.descendants(physical_subgraph, device_id)
    except nx.NetworkXError:
        descendants = set()

    affected = []
    for d in descendants:
        node_data = kg.graph.nodes.get(d, {})
        if node_data.get("node_type") == "device":
            affected.append({
                "id": d,
                "name": node_data.get("name", d),
                "vendor": node_data.get("vendor", ""),
                "role": node_data.get("role", ""),
                "group": node_data.get("group", ""),
            })

    return {"device_id": device_id, "affected": affected, "count": len(affected)}


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
