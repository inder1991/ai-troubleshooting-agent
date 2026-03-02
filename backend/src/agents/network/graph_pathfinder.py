"""Graph pathfinder node — finds candidate paths through the topology."""
from src.network.knowledge_graph import NetworkKnowledgeGraph
from src.network.models import DeviceType


def graph_pathfinder(state: dict, *, kg: NetworkKnowledgeGraph) -> dict:
    """Find K shortest paths between source and destination.

    Uses dual cost model: cost = (1 - confidence) + topology_penalty.
    Identifies firewalls in each path.

    Sets diagnosis_status to "no_path_known" if no paths found.
    """
    src_ip = state.get("src_ip", "")
    dst_ip = state.get("dst_ip", "")

    # Find source and destination device IDs
    src_device_id = kg.find_device_by_ip(src_ip)
    dst_device_id = kg.find_device_by_ip(dst_ip)

    if not src_device_id or not dst_device_id:
        return {
            "candidate_paths": [],
            "firewalls_in_path": [],
            "diagnosis_status": "no_path_known",
            "evidence": [{"type": "path_discovery", "detail": "Cannot find device IDs for src/dst IPs"}],
        }

    # Build dynamic route edges
    kg.build_route_edges(src_ip, dst_ip)

    # Find K shortest paths
    paths = kg.find_k_shortest_paths(src_device_id, dst_device_id, k=3)

    if not paths:
        return {
            "candidate_paths": [],
            "firewalls_in_path": [],
            "diagnosis_status": "no_path_known",
            "evidence": [{"type": "path_discovery", "detail": f"No path found from {src_device_id} to {dst_device_id}"}],
        }

    # Convert paths to dicts and identify firewalls
    candidate_paths = []
    firewalls = []
    seen_firewalls = set()

    for i, path in enumerate(paths):
        path_dict = {
            "index": i,
            "hops": path,
            "hop_count": len(path),
        }
        candidate_paths.append(path_dict)

        # Check each node in path for firewalls
        for node_id in path:
            node_data = kg.graph.nodes.get(node_id, {})
            if node_data.get("device_type") == DeviceType.FIREWALL.value and node_id not in seen_firewalls:
                firewalls.append({
                    "device_id": node_id,
                    "device_name": node_data.get("name", ""),
                    "vendor": node_data.get("vendor", ""),
                })
                seen_firewalls.add(node_id)

    return {
        "candidate_paths": candidate_paths,
        "firewalls_in_path": firewalls,
        "evidence": [{"type": "path_discovery", "detail": f"Found {len(paths)} candidate paths"}],
    }
