"""What-If Simulation Engine for topology designs.

Merges live topology + design patch into a simulated graph, then runs
validation analysis — no real infrastructure changes.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.network.topology_store import TopologyStore
    from src.network.knowledge_graph import NetworkKnowledgeGraph


@dataclass
class SimulatedTopology:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    routes: list[dict] = field(default_factory=list)
    firewall_rules: list[dict] = field(default_factory=list)


@dataclass
class ConnectivityResult:
    reachable: bool
    path: list[str] = field(default_factory=list)
    blocked_by: str | None = None


@dataclass
class PolicyResult:
    allowed: bool
    firewall_id: str | None = None
    rule_id: str | None = None
    rule_description: str | None = None


@dataclass
class PacketSpec:
    src_ip: str
    dst_ip: str
    port: int
    protocol: str  # TCP/UDP/ICMP


@dataclass
class IntegrityIssue:
    type: str       # duplicate_ip | routing_loop | isolated_subnet | missing_gateway | zone_violation
    severity: str   # error | warning
    device: str | None = None
    description: str = ""


class NetworkSimulator:
    """Simulates network behaviour by merging live topology with planned design changes."""

    def __init__(self, topology_store: "TopologyStore", knowledge_graph: "NetworkKnowledgeGraph"):
        self.store = topology_store
        self.kg = knowledge_graph

    # ------------------------------------------------------------------
    # Build simulated topology
    # ------------------------------------------------------------------
    def build_simulated_topology(self, design_id: str) -> SimulatedTopology:
        """Merge live inventory + planned nodes into one graph."""
        live = self.store.get_live_inventory_as_reactflow()
        design = self.store.get_design(design_id)
        if not design:
            raise ValueError(f"Design {design_id} not found")

        planned = json.loads(design["snapshot_json"])
        planned_nodes = planned.get("nodes", [])
        planned_edges = planned.get("edges", [])

        # Merge nodes — live first, then planned (skip if ID already in live)
        live_node_ids = {n["id"] for n in live["nodes"]}
        merged_nodes = list(live["nodes"])
        for pn in planned_nodes:
            if pn["id"] not in live_node_ids:
                merged_nodes.append(pn)

        # Merge edges
        live_edge_keys = {(e["source"], e["target"]) for e in live["edges"]}
        merged_edges = list(live["edges"])
        for pe in planned_edges:
            key = (pe["source"], pe["target"])
            if key not in live_edge_keys:
                merged_edges.append(pe)

        # Load routes and firewall rules from store
        routes = []
        try:
            raw_routes = self.store.list_routes()
            routes = [r.model_dump(mode="json") if hasattr(r, "model_dump") else vars(r) for r in raw_routes]
        except Exception:
            pass

        fw_rules = []
        try:
            raw_rules = self.store.list_firewall_rules()
            fw_rules = [r.model_dump(mode="json") if hasattr(r, "model_dump") else vars(r) for r in raw_rules]
        except Exception:
            pass

        return SimulatedTopology(
            nodes=merged_nodes,
            edges=merged_edges,
            routes=routes,
            firewall_rules=fw_rules,
        )

    # ------------------------------------------------------------------
    # Connectivity analysis
    # ------------------------------------------------------------------
    def simulate_connectivity(self, sim_topo: SimulatedTopology,
                              source_id: str, target_id: str) -> ConnectivityResult:
        """BFS path analysis: can source reach target?"""
        # Build adjacency graph
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in sim_topo.edges:
            src = edge["source"]
            tgt = edge["target"]
            adj[src].append(tgt)
            adj[tgt].append(src)

        # BFS
        visited: set[str] = set()
        parent: dict[str, str | None] = {source_id: None}
        queue: deque[str] = deque([source_id])
        visited.add(source_id)

        while queue:
            current = queue.popleft()
            if current == target_id:
                # Reconstruct path
                path = []
                node = target_id
                while node is not None:
                    path.append(node)
                    node = parent.get(node)
                path.reverse()

                # Check firewall rules along path
                blocked = self._check_firewalls_on_path(sim_topo, path)
                if blocked:
                    return ConnectivityResult(
                        reachable=False,
                        path=path,
                        blocked_by=blocked,
                    )
                return ConnectivityResult(reachable=True, path=path)

            for neighbor in adj[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    parent[neighbor] = current
                    queue.append(neighbor)

        return ConnectivityResult(reachable=False, path=[], blocked_by="No path exists")

    def _check_firewalls_on_path(self, sim_topo: SimulatedTopology,
                                  path: list[str]) -> str | None:
        """Check if any firewall on the path blocks traffic."""
        # Build node type map
        node_types: dict[str, str] = {}
        for node in sim_topo.nodes:
            nid = node["id"]
            data = node.get("data", {})
            node_types[nid] = (data.get("deviceType") or "").lower()

        fw_types = {"firewall"}
        for node_id in path:
            if node_types.get(node_id, "") in fw_types:
                # Check if any deny rule matches
                for rule in sim_topo.firewall_rules:
                    rule_device = rule.get("device_id", "")
                    if rule_device == node_id and rule.get("action", "").lower() == "deny":
                        return f"{node_id} rule: {rule.get('description', rule.get('id', 'unknown'))}"
        return None

    # ------------------------------------------------------------------
    # Firewall policy check
    # ------------------------------------------------------------------
    def simulate_firewall_policy(self, sim_topo: SimulatedTopology,
                                  packet: PacketSpec) -> PolicyResult:
        """Check if a packet (src, dst, port, protocol) would be allowed."""
        # Find IP→device mapping
        ip_to_device: dict[str, str] = {}
        for node in sim_topo.nodes:
            ip = node.get("data", {}).get("ip", "")
            if ip:
                ip_to_device[ip] = node["id"]

        src_device = ip_to_device.get(packet.src_ip)
        dst_device = ip_to_device.get(packet.dst_ip)

        if not src_device or not dst_device:
            return PolicyResult(
                allowed=False,
                rule_description=f"Device not found for {'source' if not src_device else 'destination'} IP",
            )

        # Find path and check firewalls
        connectivity = self.simulate_connectivity(sim_topo, src_device, dst_device)
        if not connectivity.reachable and connectivity.blocked_by != "No path exists":
            return PolicyResult(
                allowed=False,
                firewall_id=connectivity.blocked_by.split(" ")[0] if connectivity.blocked_by else None,
                rule_description=connectivity.blocked_by,
            )

        # Check specific firewall rules along the path
        node_types: dict[str, str] = {}
        for node in sim_topo.nodes:
            node_types[node["id"]] = (node.get("data", {}).get("deviceType") or "").lower()

        for node_id in connectivity.path:
            if node_types.get(node_id, "") != "firewall":
                continue
            for rule in sim_topo.firewall_rules:
                if rule.get("device_id") != node_id:
                    continue
                if self._rule_matches_packet(rule, packet):
                    action = rule.get("action", "").lower()
                    return PolicyResult(
                        allowed=(action in ("allow", "permit", "accept")),
                        firewall_id=node_id,
                        rule_id=rule.get("id"),
                        rule_description=rule.get("description", f"{action} rule on {node_id}"),
                    )

        # No matching rule = default allow (no firewall on path or no matching rule)
        return PolicyResult(allowed=True, rule_description="No blocking rule found")

    def _rule_matches_packet(self, rule: dict, packet: PacketSpec) -> bool:
        """Check if a firewall rule matches a packet spec."""
        # Protocol check
        rule_proto = (rule.get("protocol") or "any").lower()
        if rule_proto != "any" and rule_proto != packet.protocol.lower():
            return False

        # Port check
        rule_port = rule.get("dst_port") or rule.get("port")
        if rule_port and str(rule_port) != "any" and int(rule_port) != packet.port:
            return False

        # Source/destination IP check (simplified — exact or 'any')
        rule_src = rule.get("src_ip") or rule.get("source_ip") or "any"
        rule_dst = rule.get("dst_ip") or rule.get("destination_ip") or "any"
        if rule_src != "any" and rule_src != packet.src_ip:
            return False
        if rule_dst != "any" and rule_dst != packet.dst_ip:
            return False

        return True

    # ------------------------------------------------------------------
    # Integrity checks
    # ------------------------------------------------------------------
    def detect_integrity_issues(self, sim_topo: SimulatedTopology) -> list[IntegrityIssue]:
        """Run automated network health checks on the simulated topology."""
        issues: list[IntegrityIssue] = []
        issues.extend(self._check_duplicate_ips(sim_topo))
        issues.extend(self._check_routing_loops(sim_topo))
        issues.extend(self._check_isolated_subnets(sim_topo))
        issues.extend(self._check_zone_violations(sim_topo))
        issues.extend(self._check_missing_gateways(sim_topo))
        return issues

    def _check_duplicate_ips(self, sim_topo: SimulatedTopology) -> list[IntegrityIssue]:
        """Check for duplicate IP addresses across all devices."""
        issues = []
        ip_owners: dict[str, list[str]] = defaultdict(list)
        for node in sim_topo.nodes:
            ip = node.get("data", {}).get("ip", "")
            if ip:
                label = node.get("data", {}).get("label", node["id"])
                ip_owners[ip].append(label)

        for ip, owners in ip_owners.items():
            if len(owners) > 1:
                issues.append(IntegrityIssue(
                    type="duplicate_ip",
                    severity="error",
                    device=owners[0],
                    description=f"IP {ip} is assigned to multiple devices: {', '.join(owners)}",
                ))
        return issues

    def _check_routing_loops(self, sim_topo: SimulatedTopology) -> list[IntegrityIssue]:
        """Detect cycles in route graph."""
        issues = []
        # Build directed route graph
        route_adj: dict[str, list[str]] = defaultdict(list)
        for route in sim_topo.routes:
            src = route.get("device_id", "")
            next_hop = route.get("next_hop_device", "") or route.get("next_hop", "")
            if src and next_hop and src != next_hop:
                route_adj[src].append(next_hop)

        # DFS cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = defaultdict(lambda: WHITE)

        def dfs(node: str, path: list[str]) -> bool:
            color[node] = GRAY
            path.append(node)
            for neighbor in route_adj[node]:
                if color[neighbor] == GRAY:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    issues.append(IntegrityIssue(
                        type="routing_loop",
                        severity="error",
                        device=neighbor,
                        description=f"Routing loop detected: {' → '.join(cycle)}",
                    ))
                    return True
                if color[neighbor] == WHITE:
                    if dfs(neighbor, path):
                        return True
            path.pop()
            color[node] = BLACK
            return False

        for node in list(route_adj.keys()):
            if color[node] == WHITE:
                dfs(node, [])

        return issues

    def _check_isolated_subnets(self, sim_topo: SimulatedTopology) -> list[IntegrityIssue]:
        """Check for subnets that are unreachable from any gateway."""
        issues = []
        # Find subnet nodes and gateway nodes (routers)
        subnet_nodes = []
        gateway_nodes = set()
        for node in sim_topo.nodes:
            dt = (node.get("data", {}).get("deviceType") or "").lower()
            if dt == "subnet":
                subnet_nodes.append(node)
            elif dt in ("router", "gateway", "l3_switch"):
                gateway_nodes.add(node["id"])

        if not gateway_nodes or not subnet_nodes:
            return issues

        # Build adjacency
        adj: dict[str, set[str]] = defaultdict(set)
        for edge in sim_topo.edges:
            adj[edge["source"]].add(edge["target"])
            adj[edge["target"]].add(edge["source"])

        # BFS from all gateways
        reachable: set[str] = set()
        queue: deque[str] = deque(gateway_nodes)
        reachable.update(gateway_nodes)
        while queue:
            current = queue.popleft()
            for neighbor in adj[current]:
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append(neighbor)

        for sn in subnet_nodes:
            if sn["id"] not in reachable:
                label = sn.get("data", {}).get("label", sn["id"])
                issues.append(IntegrityIssue(
                    type="isolated_subnet",
                    severity="warning",
                    device=None,
                    description=f"Subnet '{label}' is unreachable from any gateway",
                ))

        return issues

    def _check_zone_violations(self, sim_topo: SimulatedTopology) -> list[IntegrityIssue]:
        """Check for cross-zone connections without a firewall in between."""
        issues = []
        node_zones: dict[str, str] = {}
        node_types: dict[str, str] = {}
        for node in sim_topo.nodes:
            data = node.get("data", {})
            zone = data.get("zone", "")
            if zone:
                node_zones[node["id"]] = zone
            node_types[node["id"]] = (data.get("deviceType") or "").lower()

        fw_types = {"firewall"}
        for edge in sim_topo.edges:
            src = edge["source"]
            tgt = edge["target"]
            src_zone = node_zones.get(src, "")
            tgt_zone = node_zones.get(tgt, "")
            if src_zone and tgt_zone and src_zone != tgt_zone:
                if node_types.get(src, "") not in fw_types and node_types.get(tgt, "") not in fw_types:
                    issues.append(IntegrityIssue(
                        type="zone_violation",
                        severity="warning",
                        device=src,
                        description=f"Direct cross-zone link {src} ({src_zone}) → {tgt} ({tgt_zone}) without firewall",
                    ))

        return issues

    def _check_missing_gateways(self, sim_topo: SimulatedTopology) -> list[IntegrityIssue]:
        """Check for subnets that have no gateway device connected."""
        issues = []
        gateway_types = {"router", "gateway", "l3_switch", "firewall"}

        # Build adjacency
        adj: dict[str, set[str]] = defaultdict(set)
        for edge in sim_topo.edges:
            adj[edge["source"]].add(edge["target"])
            adj[edge["target"]].add(edge["source"])

        for node in sim_topo.nodes:
            dt = (node.get("data", {}).get("deviceType") or "").lower()
            if dt == "subnet":
                # Check if any neighbor is a gateway type
                neighbors = adj.get(node["id"], set())
                node_types = {}
                for n in sim_topo.nodes:
                    node_types[n["id"]] = (n.get("data", {}).get("deviceType") or "").lower()

                has_gateway = any(node_types.get(nb, "") in gateway_types for nb in neighbors)
                if not has_gateway and neighbors:
                    label = node.get("data", {}).get("label", node["id"])
                    issues.append(IntegrityIssue(
                        type="missing_gateway",
                        severity="warning",
                        device=None,
                        description=f"Subnet '{label}' has no gateway (router/firewall) connected",
                    ))
        return issues

    # ------------------------------------------------------------------
    # Full simulation run
    # ------------------------------------------------------------------
    def run_full_simulation(self, design_id: str) -> dict:
        """Run a complete simulation: build topology, run all checks, return results."""
        sim_topo = self.build_simulated_topology(design_id)

        # Integrity checks
        integrity_issues = self.detect_integrity_issues(sim_topo)

        # Auto connectivity tests: test each planned node → every gateway
        connectivity_tests = []
        planned_nodes = [n for n in sim_topo.nodes if n.get("data", {}).get("_source") == "planned"]
        gateways = [n for n in sim_topo.nodes
                     if (n.get("data", {}).get("deviceType") or "").lower() in ("router", "gateway", "firewall")]

        for pn in planned_nodes[:10]:  # Cap at 10 planned nodes to limit runtime
            for gw in gateways[:5]:    # Cap at 5 gateways
                result = self.simulate_connectivity(sim_topo, pn["id"], gw["id"])
                connectivity_tests.append({
                    "source": pn.get("data", {}).get("label", pn["id"]),
                    "target": gw.get("data", {}).get("label", gw["id"]),
                    "result": "reachable" if result.reachable else "blocked",
                    "path": result.path,
                    "blocked_by": result.blocked_by,
                })

        errors = sum(1 for i in integrity_issues if i.severity == "error")
        warnings = sum(1 for i in integrity_issues if i.severity == "warning")
        passed = len(connectivity_tests) - sum(1 for t in connectivity_tests if t["result"] == "blocked")

        return {
            "connectivity_tests": connectivity_tests,
            "integrity_checks": [
                {
                    "type": i.type,
                    "severity": i.severity,
                    "device": i.device,
                    "description": i.description,
                }
                for i in integrity_issues
            ],
            "summary": {
                "errors": errors,
                "warnings": warnings,
                "passed": passed,
            },
        }
