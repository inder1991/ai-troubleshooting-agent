"""Reachability matrix — zone-to-zone connectivity analysis."""
from __future__ import annotations
from src.network.knowledge_graph import NetworkKnowledgeGraph


def compute_reachability_matrix(
    kg: NetworkKnowledgeGraph,
    zone_ids: list[str],
) -> dict:
    """Compute zone-to-zone reachability using graph pathfinding only.

    No traceroute — purely topological analysis.
    Returns: {matrix: [{src_zone, dst_zone, reachable, path_count, confidence}]}
    """
    # Find representative devices per zone
    zone_devices: dict[str, list[str]] = {}
    for node_id, data in kg.graph.nodes(data=True):
        z = data.get("zone_id", "")
        if z in zone_ids:
            zone_devices.setdefault(z, []).append(node_id)

    matrix = []
    for src_zone in zone_ids:
        for dst_zone in zone_ids:
            if src_zone == dst_zone:
                continue
            src_devs = zone_devices.get(src_zone, [])
            dst_devs = zone_devices.get(dst_zone, [])
            if not src_devs or not dst_devs:
                matrix.append({
                    "src_zone": src_zone,
                    "dst_zone": dst_zone,
                    "reachable": "unknown",
                    "path_count": 0,
                    "confidence": 0.0,
                })
                continue
            # Test with first representative device from each zone
            paths = kg.find_k_shortest_paths(src_devs[0], dst_devs[0], k=1)
            matrix.append({
                "src_zone": src_zone,
                "dst_zone": dst_zone,
                "reachable": "yes" if paths else "no",
                "path_count": len(paths),
                "confidence": 0.8 if paths else 0.0,
            })

    return {"matrix": matrix, "zone_count": len(zone_ids)}
