"""Drift detection engine — compares KG intent against live adapter state."""
import logging

from .topology_store import TopologyStore

logger = logging.getLogger(__name__)


class DriftEngine:
    """Compares KG intent against live adapter state for a device."""

    def __init__(self, store: TopologyStore):
        self.store = store

    async def check_device(self, device_id: str, adapter) -> list[dict]:
        """Run all drift checks for a single device.
        Returns list of drift event dicts (not yet persisted)."""
        events: list[dict] = []
        events.extend(await self._diff_routes(device_id, adapter))
        events.extend(await self._diff_rules(device_id, adapter))
        events.extend(await self._diff_interfaces(device_id, adapter))
        events.extend(await self._diff_nat_rules(device_id, adapter))
        events.extend(await self._diff_zones(device_id, adapter))
        return events

    async def _diff_routes(self, device_id: str, adapter) -> list[dict]:
        kg_routes = self.store.list_routes(device_id=device_id)
        kg_map = {r.destination_cidr: r for r in kg_routes}
        try:
            live_routes = await adapter.get_routes()
        except Exception:
            logger.warning("Failed to fetch live routes for device %s", device_id)
            return []
        live_map = {r.destination_cidr: r for r in live_routes}

        events = []
        # Routes expected in KG but missing from live device
        for cidr, kg_route in kg_map.items():
            if cidr not in live_map:
                events.append({
                    "entity_type": "route", "entity_id": kg_route.id,
                    "drift_type": "missing", "field": "destination_cidr",
                    "expected": cidr, "actual": "(not present)",
                    "severity": "critical" if cidr == "0.0.0.0/0" else "warning",
                })
        # Routes present on live device but not in KG
        for cidr in live_map:
            if cidr not in kg_map:
                events.append({
                    "entity_type": "route", "entity_id": f"live-{device_id}-{cidr}",
                    "drift_type": "added", "field": "destination_cidr",
                    "expected": "(not in topology)", "actual": cidr,
                    "severity": "info",
                })
        # Routes present in both — check for field-level changes
        for cidr in kg_map.keys() & live_map.keys():
            kg_r, live_r = kg_map[cidr], live_map[cidr]
            if kg_r.next_hop and live_r.next_hop != kg_r.next_hop:
                events.append({
                    "entity_type": "route", "entity_id": kg_r.id,
                    "drift_type": "changed", "field": "next_hop",
                    "expected": kg_r.next_hop, "actual": live_r.next_hop,
                    "severity": "warning",
                })
        return events

    async def _diff_rules(self, device_id: str, adapter) -> list[dict]:
        kg_rules = self.store.list_firewall_rules(device_id=device_id)
        kg_map = {r.rule_name: r for r in kg_rules}
        try:
            live_rules = await adapter.get_rules()
        except Exception:
            logger.warning("Failed to fetch live rules for device %s", device_id)
            return []
        live_map = {r.rule_name: r for r in live_rules}

        events = []
        # Rules expected in KG but missing from live device
        for name, kg_rule in kg_map.items():
            if name not in live_map:
                events.append({
                    "entity_type": "firewall_rule", "entity_id": kg_rule.id,
                    "drift_type": "missing", "field": "rule_name",
                    "expected": name, "actual": "(not present)",
                    "severity": "critical",
                })
        # Rules present on live device but not in KG
        for name in live_map:
            if name not in kg_map:
                events.append({
                    "entity_type": "firewall_rule", "entity_id": f"live-{device_id}-{name}",
                    "drift_type": "added", "field": "rule_name",
                    "expected": "(not in topology)", "actual": name,
                    "severity": "warning",
                })
        # Rules present in both — check for field-level changes
        for name in kg_map.keys() & live_map.keys():
            kg_r, live_r = kg_map[name], live_map[name]
            # Normalize action to string for comparison (handles both enum and str)
            kg_action = kg_r.action if isinstance(kg_r.action, str) else kg_r.action.value
            live_action = live_r.action if isinstance(live_r.action, str) else live_r.action.value
            if kg_action != live_action:
                events.append({
                    "entity_type": "firewall_rule", "entity_id": kg_r.id,
                    "drift_type": "changed", "field": "action",
                    "expected": kg_action, "actual": live_action,
                    "severity": "critical",
                })
        return events

    async def _diff_interfaces(self, device_id: str, adapter) -> list[dict]:
        kg_ifaces = self.store.list_interfaces(device_id=device_id)
        kg_map = {i.name: i for i in kg_ifaces}
        try:
            live_ifaces = await adapter.get_interfaces()
        except Exception:
            logger.warning("Failed to fetch live interfaces for device %s", device_id)
            return []
        live_map = {i.name: i for i in live_ifaces}

        events = []
        # Interfaces expected in KG but missing from live device
        for name, kg_iface in kg_map.items():
            if name not in live_map:
                events.append({
                    "entity_type": "interface", "entity_id": kg_iface.id,
                    "drift_type": "missing", "field": "name",
                    "expected": name, "actual": "(not present)",
                    "severity": "warning",
                })
        # Interfaces present on live device but not in KG
        for name in live_map:
            if name not in kg_map:
                events.append({
                    "entity_type": "interface", "entity_id": f"live-{device_id}-{name}",
                    "drift_type": "added", "field": "name",
                    "expected": "(not in topology)", "actual": name,
                    "severity": "info",
                })
        # Interfaces present in both — check for field-level changes
        for name in kg_map.keys() & live_map.keys():
            kg_i, live_i = kg_map[name], live_map[name]
            if kg_i.ip and live_i.ip != kg_i.ip:
                events.append({
                    "entity_type": "interface", "entity_id": kg_i.id,
                    "drift_type": "changed", "field": "ip",
                    "expected": kg_i.ip, "actual": live_i.ip,
                    "severity": "warning",
                })
        return events

    async def _diff_nat_rules(self, device_id: str, adapter) -> list[dict]:
        try:
            live_rules = await adapter.get_nat_rules()
        except Exception:
            logger.warning("Failed to fetch live NAT rules for device %s", device_id)
            return []
        kg_rules = self.store.list_nat_rules(device_id=device_id)
        kg_ids = {(r.rule_id or r.id) for r in kg_rules}
        live_ids = {(r.rule_id or r.id) for r in live_rules}

        events = []
        for rid in kg_ids - live_ids:
            events.append({
                "entity_type": "nat_rule", "entity_id": rid,
                "drift_type": "missing", "field": "rule_id",
                "expected": rid, "actual": "(not present)",
                "severity": "warning",
            })
        for rid in live_ids - kg_ids:
            events.append({
                "entity_type": "nat_rule", "entity_id": rid,
                "drift_type": "added", "field": "rule_id",
                "expected": "(not in topology)", "actual": rid,
                "severity": "info",
            })
        return events

    async def _diff_zones(self, device_id: str, adapter) -> list[dict]:
        try:
            live_zones = await adapter.get_zones()
        except Exception:
            logger.warning("Failed to fetch live zones for device %s", device_id)
            return []
        kg_zones = self.store.list_zones()
        kg_names = {z.name for z in kg_zones}
        live_names = {z.name for z in live_zones}

        events = []
        for name in live_names - kg_names:
            events.append({
                "entity_type": "zone", "entity_id": f"live-{device_id}-{name}",
                "drift_type": "added", "field": "name",
                "expected": "(not in topology)", "actual": name,
                "severity": "info",
            })
        return events
