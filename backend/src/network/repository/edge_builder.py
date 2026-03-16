"""EdgeBuilderService — extracts edge-building algorithms from KnowledgeGraph.

Reads topology entities from TopologyStore (devices, interfaces, subnets,
routes, HA groups, VPN tunnels, MPLS) and produces NeighborLink objects
that get persisted via the TopologyRepository.

This is the canonical source of all device-to-device edges.
Previously this logic lived inside KnowledgeGraph.load_from_store() —
now it's a standalone service that feeds the repository pipeline.

Edge types produced:
  - layer2_link:  from LLDP/CDP neighbor tables
  - layer3_link:  from shared /30-/31 subnets (P2P links)
  - routes_via:   from routing table next-hop resolution
  - ha_peer:      from HA group membership
  - tunnel_link:  from VPN tunnel endpoints
  - mpls_path:    from MPLS circuit endpoints
  - attached_to:  from TGW → VPC attachments
  - load_balances: from LB → target group targets
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timezone
from typing import Optional

from ..topology_store import TopologyStore
from ..ip_resolver import IPResolver
from .domain import NeighborLink

logger = logging.getLogger(__name__)


def _strip_cidr(ip: str) -> str:
    return ip.split("/")[0] if ip and "/" in ip else ip


class EdgeBuilderService:
    """Builds all device-to-device edges from topology data.

    Usage:
        builder = EdgeBuilderService(store)
        edges = builder.build_all()
        for edge in edges:
            repo.upsert_neighbor_link(edge)
    """

    def __init__(self, store: TopologyStore):
        self._store = store
        self._ip_resolver = IPResolver()
        self._device_index: dict[str, str] = {}  # ip → device_id

    def build_all(self) -> list[NeighborLink]:
        """Run all edge-building algorithms. Returns deduplicated edge list."""
        self._build_indexes()

        edges: list[NeighborLink] = []
        edges.extend(self._build_l2_edges())
        edges.extend(self._build_l3_p2p_edges())
        edges.extend(self._build_route_edges())
        edges.extend(self._build_ha_edges())
        edges.extend(self._build_tunnel_edges())
        edges.extend(self._build_mpls_edges())
        edges.extend(self._build_tgw_edges())
        edges.extend(self._build_lb_edges())

        # Deduplicate
        deduped = self._deduplicate(edges)
        logger.info("EdgeBuilder: %d edges built (%d before dedup)",
                     len(deduped), len(edges))
        return deduped

    def _build_indexes(self) -> None:
        """Build IP resolver and device index from current store data."""
        subnets = self._store.list_subnets()
        self._ip_resolver.load_subnets([s.model_dump(mode="json") for s in subnets])

        self._device_index.clear()
        for d in self._store.list_devices():
            if d.management_ip:
                self._device_index[d.management_ip] = d.id
            for iface in self._store.list_interfaces(device_id=d.id):
                if iface.ip:
                    bare_ip = _strip_cidr(iface.ip)
                    self._device_index[bare_ip] = d.id
                    self._device_index[iface.ip] = d.id

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _make_link(self, device_a: str, iface_a: str,
                   device_b: str, iface_b: str,
                   edge_type: str, protocol: str = "",
                   confidence: float = 0.9) -> NeighborLink:
        now = datetime.now(timezone.utc)
        local_iface_id = f"{device_a}:{iface_a}" if ":" not in iface_a else iface_a
        remote_iface_id = f"{device_b}:{iface_b}" if ":" not in iface_b else iface_b
        return NeighborLink(
            id=f"{local_iface_id}--{remote_iface_id}",
            device_id=device_a,
            local_interface=local_iface_id,
            remote_device=device_b,
            remote_interface=remote_iface_id,
            protocol=protocol or edge_type,
            sources=["edge_builder"],
            first_seen=now,
            last_seen=now,
            confidence=confidence,
        )

    # ── 1. L2 links from LLDP/CDP ──

    def _build_l2_edges(self) -> list[NeighborLink]:
        edges = []
        device_ids = {d.id for d in self._store.list_devices()}

        try:
            from src.network.discovery_scheduler import MOCK_NEIGHBORS
            for device_id, neighbors in MOCK_NEIGHBORS.items():
                if device_id not in device_ids:
                    continue
                for n in neighbors:
                    remote_id = n.get("remote_device", "")
                    if remote_id not in device_ids:
                        continue
                    edges.append(self._make_link(
                        device_a=device_id,
                        iface_a=n.get("local_port", ""),
                        device_b=remote_id,
                        iface_b=n.get("remote_port", ""),
                        edge_type="layer2_link",
                        protocol=n.get("protocol", "LLDP"),
                        confidence=1.0,
                    ))
        except ImportError:
            pass
        except Exception as e:
            logger.warning("L2 edge building failed: %s", e)

        # Also read from persisted neighbor_links table
        try:
            existing = self._store.list_neighbor_links()
            for link in existing:
                if link["device_id"] in device_ids and link["remote_device"] in device_ids:
                    now = datetime.now(timezone.utc)
                    edges.append(NeighborLink(
                        id=link["id"],
                        device_id=link["device_id"],
                        local_interface=link["local_interface"],
                        remote_device=link["remote_device"],
                        remote_interface=link["remote_interface"],
                        protocol=link.get("protocol", "lldp"),
                        sources=["neighbor_links"],
                        first_seen=now, last_seen=now,
                        confidence=link.get("confidence", 0.95),
                    ))
        except Exception:
            pass

        return edges

    # ── 2. L3 P2P links from shared /30-/31 subnets ──

    def _build_l3_p2p_edges(self) -> list[NeighborLink]:
        edges = []
        subnets = self._store.list_subnets()

        # Build subnet → devices mapping
        subnet_devices: dict[str, list[tuple[str, str, str]]] = {}
        for d in self._store.list_devices():
            for iface in self._store.list_interfaces(device_id=d.id):
                if iface.ip:
                    s_meta = self._ip_resolver.resolve(_strip_cidr(iface.ip))
                    if s_meta:
                        sid = s_meta.get("id", "")
                        subnet_devices.setdefault(sid, []).append(
                            (d.id, iface.name, iface.ip)
                        )

        for sid, members in subnet_devices.items():
            if len(members) < 2:
                continue
            subnet_obj = next((s for s in subnets if s.id == sid), None)
            if not subnet_obj:
                continue
            try:
                net = ipaddress.ip_network(subnet_obj.cidr, strict=False)
                if net.prefixlen < 30:
                    continue
            except (ValueError, TypeError):
                continue

            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    d1_id, d1_iface, _ = members[i]
                    d2_id, d2_iface, _ = members[j]
                    edges.append(self._make_link(
                        device_a=d1_id, iface_a=d1_iface,
                        device_b=d2_id, iface_b=d2_iface,
                        edge_type="layer3_link",
                        protocol="l3_p2p",
                        confidence=0.9,
                    ))

        return edges

    # ── 3. Route-based forwarding edges ──

    def _build_route_edges(self) -> list[NeighborLink]:
        edges = []
        device_ids = {d.id for d in self._store.list_devices()}

        for route in self._store.list_routes():
            src_device = route.device_id
            if src_device not in device_ids:
                continue
            next_hop_device = self._device_index.get(route.next_hop)
            if not next_hop_device or next_hop_device == src_device:
                continue
            if next_hop_device not in device_ids:
                continue

            try:
                net = ipaddress.ip_network(route.destination_cidr, strict=False)
                is_default = route.destination_cidr == "0.0.0.0/0"
                is_summary = net.prefixlen <= 24
                is_dynamic = route.protocol.upper() in ("BGP", "OSPF", "EIGRP", "IS-IS")
            except (ValueError, TypeError):
                continue

            if not (is_default or (is_summary and is_dynamic)):
                continue

            edges.append(self._make_link(
                device_a=src_device, iface_a="routing",
                device_b=next_hop_device, iface_b="routing",
                edge_type="routes_via",
                protocol=route.protocol,
                confidence=0.85,
            ))

        return edges

    # ── 4. HA peer edges ──

    def _build_ha_edges(self) -> list[NeighborLink]:
        edges = []
        device_ids = {d.id for d in self._store.list_devices()}

        for ha in self._store.list_ha_groups():
            members = ha.member_ids
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    if members[i] in device_ids and members[j] in device_ids:
                        edges.append(self._make_link(
                            device_a=members[i], iface_a="ha",
                            device_b=members[j], iface_b="ha",
                            edge_type="ha_peer",
                            protocol=ha.ha_mode.value if hasattr(ha.ha_mode, 'value') else str(ha.ha_mode),
                            confidence=1.0,
                        ))

        return edges

    # ── 5. VPN tunnel edges ──

    def _build_tunnel_edges(self) -> list[NeighborLink]:
        edges = []
        device_ids = {d.id for d in self._store.list_devices()}

        for vpn in self._store.list_vpn_tunnels():
            if vpn.local_gateway_id and vpn.remote_gateway_ip:
                remote_device = self._device_index.get(vpn.remote_gateway_ip)
                if (remote_device and vpn.local_gateway_id in device_ids
                        and remote_device in device_ids
                        and vpn.local_gateway_id != remote_device):
                    ttype = vpn.tunnel_type.value if hasattr(vpn.tunnel_type, 'value') else str(vpn.tunnel_type)
                    edges.append(self._make_link(
                        device_a=vpn.local_gateway_id, iface_a=f"tunnel-{vpn.id}",
                        device_b=remote_device, iface_b=f"tunnel-{vpn.id}",
                        edge_type="tunnel_link",
                        protocol=ttype,
                        confidence=0.9,
                    ))

        return edges

    # ── 6. MPLS circuit edges ──

    def _build_mpls_edges(self) -> list[NeighborLink]:
        edges = []
        device_ids = {d.id for d in self._store.list_devices()}

        for mpls in self._store.list_mpls_circuits():
            endpoints = mpls.endpoints
            for i in range(len(endpoints) - 1):
                if endpoints[i] in device_ids and endpoints[i + 1] in device_ids:
                    edges.append(self._make_link(
                        device_a=endpoints[i], iface_a=f"mpls-{mpls.id}",
                        device_b=endpoints[i + 1], iface_b=f"mpls-{mpls.id}",
                        edge_type="mpls_path",
                        protocol="MPLS",
                        confidence=0.95,
                    ))

        return edges

    # ── 7. Transit Gateway attachment edges ──

    def _build_tgw_edges(self) -> list[NeighborLink]:
        edges = []
        device_ids = {d.id for d in self._store.list_devices()}

        for tgw in self._store.list_transit_gateways():
            if tgw.id not in device_ids:
                continue
            for vpc_id in tgw.attached_vpc_ids:
                # Find a device in this VPC
                for d in self._store.list_devices():
                    if getattr(d, 'vpc_id', None) == vpc_id and d.id in device_ids:
                        edges.append(self._make_link(
                            device_a=tgw.id, iface_a="tgw-attach",
                            device_b=d.id, iface_b="tgw-attach",
                            edge_type="attached_to",
                            protocol="tgw",
                            confidence=0.95,
                        ))
                        break

        return edges

    # ── 8. Load balancer → target edges ──

    def _build_lb_edges(self) -> list[NeighborLink]:
        edges = []
        device_ids = {d.id for d in self._store.list_devices()}

        for lb in self._store.list_load_balancers():
            if lb.id not in device_ids:
                continue
            for tg in self._store.list_lb_target_groups(lb_id=lb.id):
                for target_id in tg.target_ids:
                    resolved = target_id
                    if target_id not in device_ids:
                        resolved = self._device_index.get(_strip_cidr(target_id))
                    if resolved and resolved in device_ids and resolved != lb.id:
                        edges.append(self._make_link(
                            device_a=lb.id, iface_a=f"lb-{tg.id}",
                            device_b=resolved, iface_b=f"lb-target",
                            edge_type="load_balances",
                            protocol="lb",
                            confidence=0.9,
                        ))

        return edges

    # ── Deduplication ──

    def _deduplicate(self, edges: list[NeighborLink]) -> list[NeighborLink]:
        """Deduplicate edges. For same device pair + edge_type, keep highest confidence."""
        seen: dict[tuple, NeighborLink] = {}
        for edge in edges:
            pair = tuple(sorted([edge.device_id, edge.remote_device]))
            key = (pair[0], pair[1], edge.protocol)

            if key in seen:
                if edge.confidence > seen[key].confidence:
                    seen[key] = edge
            else:
                seen[key] = edge

        return list(seen.values())
