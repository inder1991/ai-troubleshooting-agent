"""Executes network tools by routing to existing backend services."""
import json

import httpx

from src.utils.logger import get_logger

logger = get_logger(__name__)

# API base for internal calls
_API_BASE = "http://localhost:8000"


class NetworkToolExecutor:
    """Routes tool calls to existing backend services and returns JSON results."""

    async def execute(self, tool_name: str, tool_args: dict) -> str:
        """Route a tool call to the correct handler and return JSON string.

        Returns ``{"error": "..."}`` JSON on any failure.
        """
        try:
            handler = self._get_handler(tool_name)
            if handler is None:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
            result = await handler(tool_args)
            return json.dumps(result, default=str)
        except Exception as e:
            logger.warning("Tool execution failed: %s(%s) — %s", tool_name, tool_args, e)
            return json.dumps({"error": f"Tool '{tool_name}' failed: {str(e)}"})

    def _get_handler(self, tool_name: str):
        """Return the handler coroutine for a given tool name, or None."""
        handlers = {
            # Flow tools
            "get_top_talkers": self._handle_get_top_talkers,
            "get_traffic_matrix": self._handle_get_traffic_matrix,
            "get_protocol_breakdown": self._handle_get_protocol_breakdown,
            "get_conversations": self._handle_get_conversations,
            "get_applications": self._handle_get_applications,
            "get_asn_breakdown": self._handle_get_asn_breakdown,
            "get_volume_timeline": self._handle_get_volume_timeline,
            # Topology tools
            "get_topology_graph": self._handle_get_topology_graph,
            "query_path": self._handle_query_path,
            "list_devices_in_zone": self._handle_list_devices_in_zone,
            "get_device_details": self._handle_get_device_details,
            "get_interfaces": self._handle_get_interfaces,
            "get_routes": self._handle_get_routes,
            # IPAM tools
            "search_ip": self._handle_search_ip,
            "get_subnet_utilization": self._handle_get_subnet_utilization,
            "get_ip_conflicts": self._handle_get_ip_conflicts,
            "get_capacity_forecast": self._handle_get_capacity_forecast,
            "get_allocation_history": self._handle_get_allocation_history,
            "list_subnets": self._handle_list_subnets,
            # Firewall tools
            "evaluate_rule": self._handle_evaluate_rule,
            "list_rules_for_device": self._handle_list_rules_for_device,
            "simulate_rule_change": self._handle_simulate_rule_change,
            "get_nacls": self._handle_get_nacls,
            # Device tools
            "list_devices": self._handle_list_devices,
            "get_device_health": self._handle_get_device_health,
            "get_interface_stats": self._handle_get_interface_stats,
            "get_snmp_metrics": self._handle_get_snmp_metrics,
            "get_syslog_events": self._handle_get_syslog_events,
            "get_traps": self._handle_get_traps,
            # Alert tools
            "get_active_alerts": self._handle_get_active_alerts,
            "get_alert_history": self._handle_get_alert_history,
            "get_drift_events": self._handle_get_drift_events,
            # Diagnostic tools
            "diagnose_path": self._handle_diagnose_path,
            "explain_finding": self._handle_explain_finding,
            "correlate_events": self._handle_correlate_events,
            "root_cause_analyze": self._handle_root_cause_analyze,
            # Control plane tools
            "get_bgp_neighbors": self._handle_get_bgp_neighbors,
            "get_bgp_routes": self._handle_get_bgp_routes,
            "get_route_flaps": self._handle_get_route_flaps,
            "get_tunnel_status": self._handle_get_tunnel_status,
            "get_tunnel_latency": self._handle_get_tunnel_latency,
            "get_vpn_sessions": self._handle_get_vpn_sessions,
            # Cloud network tools
            "get_vpc_routes": self._handle_get_vpc_routes,
            "get_security_group_rules": self._handle_get_security_group_rules,
            "get_nacl_rules": self._handle_get_nacl_rules,
            "get_load_balancer_health": self._handle_get_load_balancer_health,
            "get_peering_status": self._handle_get_peering_status,
            # Shared tools
            "summarize_context": self._handle_summarize_context,
            "start_investigation": self._handle_start_investigation,
        }
        return handlers.get(tool_name)

    # ── Internal HTTP helpers ──

    async def _call_flow_api(self, path: str, params: dict | None = None) -> dict | list:
        """GET to /api/v4/network/flows/{path} with query params."""
        async with httpx.AsyncClient(base_url=_API_BASE, timeout=10.0) as client:
            resp = await client.get(f"/api/v4/network/flows/{path}", params=params or {})
            resp.raise_for_status()
            return resp.json()

    async def _call_network_api(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict | list:
        """GET or POST to /api/v4/network/{path}."""
        async with httpx.AsyncClient(base_url=_API_BASE, timeout=10.0) as client:
            if method == "GET":
                resp = await client.get(f"/api/v4/network/{path}", params=params or {})
            else:
                resp = await client.post(f"/api/v4/network/{path}", json=json_body or {})
            resp.raise_for_status()
            return resp.json()

    # ── Flow tool handlers ──

    async def _handle_get_top_talkers(self, args: dict):
        return await self._call_flow_api(
            "top-talkers",
            {"window": args.get("window", "5m"), "limit": args.get("limit", 20)},
        )

    async def _handle_get_traffic_matrix(self, args: dict):
        return await self._call_flow_api(
            "traffic-matrix",
            {"window": args.get("window", "15m")},
        )

    async def _handle_get_protocol_breakdown(self, args: dict):
        return await self._call_flow_api(
            "protocol-breakdown",
            {"window": args.get("window", "1h")},
        )

    async def _handle_get_conversations(self, args: dict):
        return await self._call_flow_api(
            "conversations",
            {"window": args.get("window", "5m"), "limit": args.get("limit", 50)},
        )

    async def _handle_get_applications(self, args: dict):
        return await self._call_flow_api(
            "applications",
            {"window": args.get("window", "1h"), "limit": args.get("limit", 30)},
        )

    async def _handle_get_asn_breakdown(self, args: dict):
        return await self._call_flow_api(
            "asn",
            {"window": args.get("window", "1h"), "limit": args.get("limit", 30)},
        )

    async def _handle_get_volume_timeline(self, args: dict):
        return await self._call_flow_api(
            "volume-timeline",
            {"window": args.get("window", "1h"), "interval": args.get("interval", "1m")},
        )

    # ── Topology tool handlers ──

    async def _handle_get_topology_graph(self, args: dict):
        return await self._call_network_api("GET", "topology/graph")

    async def _handle_query_path(self, args: dict):
        return await self._call_network_api(
            "POST",
            "query/path",
            json_body={"src_ip": args["src_ip"], "dst_ip": args["dst_ip"]},
        )

    async def _handle_list_devices_in_zone(self, args: dict):
        return await self._call_network_api("GET", f"zones/{args['zone_id']}/devices")

    async def _handle_get_device_details(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}")

    async def _handle_get_interfaces(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/interfaces")

    async def _handle_get_routes(self, args: dict):
        return await self._call_network_api("GET", f"devices/{args['device_id']}/routes")

    # ── IPAM tool handlers ──

    async def _handle_search_ip(self, args: dict):
        return await self._call_network_api(
            "POST", "ipam/search", json_body={"query": args["ip"]}
        )

    async def _handle_get_subnet_utilization(self, args: dict):
        return await self._call_network_api(
            "GET", f"subnets/{args['subnet_id']}/utilization"
        )

    async def _handle_get_ip_conflicts(self, args: dict):
        return await self._call_network_api("GET", "ipam/conflicts")

    async def _handle_get_capacity_forecast(self, args: dict):
        return await self._call_network_api(
            "GET", f"subnets/{args['subnet_id']}/forecast"
        )

    async def _handle_get_allocation_history(self, args: dict):
        return await self._call_network_api(
            "GET",
            f"subnets/{args['subnet_id']}/allocation-history",
            params={"limit": args.get("limit", 50)},
        )

    async def _handle_list_subnets(self, args: dict):
        return await self._call_network_api(
            "GET", "subnets", params={"limit": args.get("limit", 100)}
        )

    # ── Firewall tool handlers ──

    async def _handle_evaluate_rule(self, args: dict):
        return await self._call_network_api(
            "POST",
            f"firewall/{args['device_id']}/evaluate",
            json_body={
                "src_ip": args["src_ip"],
                "dst_ip": args["dst_ip"],
                "port": args["port"],
                "protocol": args.get("protocol", "tcp"),
            },
        )

    async def _handle_list_rules_for_device(self, args: dict):
        return await self._call_network_api(
            "GET",
            f"firewall/{args['device_id']}/rules",
            params={"limit": args.get("limit", 100)},
        )

    async def _handle_simulate_rule_change(self, args: dict):
        return await self._call_network_api("POST", "firewall/simulate", json_body=args)

    async def _handle_get_nacls(self, args: dict):
        return await self._call_network_api("GET", f"vpcs/{args['vpc_id']}/nacls")

    # ── Device tool handlers ──

    async def _handle_list_devices(self, args: dict):
        return await self._call_network_api(
            "GET", "devices", params={"limit": args.get("limit", 100)}
        )

    async def _handle_get_device_health(self, args: dict):
        return await self._call_network_api(
            "GET", f"devices/{args['device_id']}/health"
        )

    async def _handle_get_interface_stats(self, args: dict):
        params = {}
        if args.get("interface_name"):
            params["interface_name"] = args["interface_name"]
        return await self._call_network_api(
            "GET", f"devices/{args['device_id']}/interface-stats", params=params
        )

    async def _handle_get_snmp_metrics(self, args: dict):
        params: dict = {}
        if args.get("oid"):
            params["oid"] = args["oid"]
        return await self._call_network_api(
            "GET", f"devices/{args['device_id']}/snmp/metrics", params=params
        )

    async def _handle_get_syslog_events(self, args: dict):
        return await self._call_network_api(
            "GET",
            f"devices/{args['device_id']}/syslog",
            params={"limit": args.get("limit", 50)},
        )

    async def _handle_get_traps(self, args: dict):
        return await self._call_network_api(
            "GET",
            f"devices/{args['device_id']}/traps",
            params={"limit": args.get("limit", 50)},
        )

    # ── Alert tool handlers ──

    async def _handle_get_active_alerts(self, args: dict):
        return await self._call_network_api(
            "GET", "monitor/alerts", params={"status": "active"}
        )

    async def _handle_get_alert_history(self, args: dict):
        return await self._call_network_api(
            "GET",
            "monitor/alerts",
            params={
                "window": args.get("window", "24h"),
                "limit": args.get("limit", 100),
            },
        )

    async def _handle_get_drift_events(self, args: dict):
        return await self._call_network_api(
            "GET", "monitor/drift", params={"limit": args.get("limit", 50)}
        )

    # ── Diagnostic tool handlers ──

    async def _handle_diagnose_path(self, args: dict):
        return await self._call_network_api(
            "POST",
            "diagnose",
            json_body={
                "src_ip": args["src_ip"],
                "dst_ip": args["dst_ip"],
                "port": args.get("port", 80),
                "protocol": args.get("protocol", "tcp"),
            },
        )

    async def _handle_explain_finding(self, args: dict):
        return await self._call_network_api(
            "GET", f"diagnose/findings/{args['finding_id']}/explain"
        )

    async def _handle_correlate_events(self, args: dict):
        params: dict = {"window": args.get("window", "30m")}
        if args.get("device_id"):
            params["device_id"] = args["device_id"]
        return await self._call_network_api("GET", "monitor/correlate", params=params)

    async def _handle_root_cause_analyze(self, args: dict):
        return await self._call_network_api(
            "POST", "diagnose/root-cause", json_body={"symptoms": args["symptoms"]}
        )

    # ── Control plane tool handlers ──

    async def _handle_get_bgp_neighbors(self, args: dict):
        return await self._call_network_api(
            "GET", f"devices/{args['device_id']}/bgp/neighbors"
        )

    async def _handle_get_bgp_routes(self, args: dict):
        params = {}
        if args.get("prefix"):
            params["prefix"] = args["prefix"]
        return await self._call_network_api(
            "GET", f"devices/{args['device_id']}/bgp/routes", params=params
        )

    async def _handle_get_route_flaps(self, args: dict):
        return await self._call_network_api(
            "GET",
            "bgp/flaps",
            params={
                "window": args.get("window", "1h"),
                "limit": args.get("limit", 50),
            },
        )

    async def _handle_get_tunnel_status(self, args: dict):
        return await self._call_network_api(
            "GET", f"devices/{args['device_id']}/tunnels"
        )

    async def _handle_get_tunnel_latency(self, args: dict):
        return await self._call_network_api(
            "GET", f"devices/{args['device_id']}/tunnels/latency"
        )

    async def _handle_get_vpn_sessions(self, args: dict):
        return await self._call_network_api(
            "GET", "vpn/sessions", params={"limit": args.get("limit", 50)}
        )

    # ── Cloud network tool handlers ──

    async def _handle_get_vpc_routes(self, args: dict):
        return await self._call_network_api(
            "GET", f"vpcs/{args['vpc_id']}/routes"
        )

    async def _handle_get_security_group_rules(self, args: dict):
        return await self._call_network_api(
            "GET", f"security-groups/{args['security_group_id']}/rules"
        )

    async def _handle_get_nacl_rules(self, args: dict):
        return await self._call_network_api(
            "GET", f"nacls/{args['nacl_id']}/rules"
        )

    async def _handle_get_load_balancer_health(self, args: dict):
        return await self._call_network_api(
            "GET", f"load-balancers/{args['lb_id']}/health"
        )

    async def _handle_get_peering_status(self, args: dict):
        return await self._call_network_api(
            "GET", f"vpcs/{args['vpc_id']}/peering"
        )

    # ── Shared tool handlers ──

    async def _handle_summarize_context(self, args: dict):
        return {
            "message": "Use the visible data summary and conversation history to provide an overview."
        }

    async def _handle_start_investigation(self, args: dict):
        return {
            "action": "escalate",
            "reason": args.get("reason", "Cross-domain investigation requested"),
        }
