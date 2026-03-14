"""Network tool definitions and view-based tool group routing."""


# ── Tool Group: Topology ──
_TOPOLOGY_TOOLS: list[dict] = [
    {
        "name": "get_topology_graph",
        "description": "Get the full network topology graph including devices, subnets, zones, and connections. Returns nodes and edges with metadata.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_path",
        "description": "Find the network path between two IP addresses. Returns ordered hops with devices, interfaces, and zones traversed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "src_ip": {"type": "string", "description": "Source IP address"},
                "dst_ip": {"type": "string", "description": "Destination IP address"},
            },
            "required": ["src_ip", "dst_ip"],
        },
    },
    {
        "name": "list_devices_in_zone",
        "description": "List all devices in a specific security zone.",
        "input_schema": {
            "type": "object",
            "properties": {"zone_id": {"type": "string", "description": "Zone ID"}},
            "required": ["zone_id"],
        },
    },
    {
        "name": "get_device_details",
        "description": "Get full details for a specific device including interfaces, routes, and zone membership.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device ID or name"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_interfaces",
        "description": "List interfaces for a device with IP, MAC, status, speed, and zone.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device ID"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_routes",
        "description": "Get routing table for a device.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string", "description": "Device ID"}},
            "required": ["device_id"],
        },
    },
]

# ── Tool Group: Flows ──
_FLOW_TOOLS: list[dict] = [
    {
        "name": "get_top_talkers",
        "description": "Get top source-destination pairs by traffic volume within a time window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "description": "Time window (e.g., '5m', '1h')", "default": "5m"},
                "limit": {"type": "integer", "description": "Max results (default 20, max 500)", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_traffic_matrix",
        "description": "Get the full traffic matrix showing bytes between all source-destination pairs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "15m"},
            },
            "required": [],
        },
    },
    {
        "name": "get_protocol_breakdown",
        "description": "Get protocol distribution (TCP/UDP/ICMP/other) by traffic volume.",
        "input_schema": {
            "type": "object",
            "properties": {"window": {"type": "string", "default": "1h"}},
            "required": [],
        },
    },
    {
        "name": "get_conversations",
        "description": "Get active network conversations with bytes, packets, and duration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "5m"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "get_applications",
        "description": "Get application-layer traffic breakdown (HTTP, DNS, SSH, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": [],
        },
    },
    {
        "name": "get_asn_breakdown",
        "description": "Get traffic breakdown by Autonomous System Number (ASN).",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": [],
        },
    },
    {
        "name": "get_volume_timeline",
        "description": "Get traffic volume time series data for trend analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "interval": {"type": "string", "default": "1m"},
            },
            "required": [],
        },
    },
]

# ── Tool Group: IPAM ──
_IPAM_TOOLS: list[dict] = [
    {
        "name": "search_ip",
        "description": "Search for an IP address across all subnets. Returns subnet, allocation status, hostname, and history.",
        "input_schema": {
            "type": "object",
            "properties": {"ip": {"type": "string", "description": "IP address to search"}},
            "required": ["ip"],
        },
    },
    {
        "name": "get_subnet_utilization",
        "description": "Get utilization stats for a subnet: total IPs, assigned, available, reserved, utilization percentage.",
        "input_schema": {
            "type": "object",
            "properties": {"subnet_id": {"type": "string", "description": "Subnet ID or CIDR"}},
            "required": ["subnet_id"],
        },
    },
    {
        "name": "get_ip_conflicts",
        "description": "List all detected IP address conflicts across the network.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_capacity_forecast",
        "description": "Get capacity forecast for a subnet or region based on historical allocation trends.",
        "input_schema": {
            "type": "object",
            "properties": {"subnet_id": {"type": "string"}},
            "required": ["subnet_id"],
        },
    },
    {
        "name": "get_allocation_history",
        "description": "Get IP allocation history for a subnet showing assignments, releases, and changes over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subnet_id": {"type": "string", "description": "Subnet ID or CIDR"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["subnet_id"],
        },
    },
    {
        "name": "list_subnets",
        "description": "List all subnets with CIDR, name, VLAN, utilization, and zone.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 100}},
            "required": [],
        },
    },
]

# ── Tool Group: Firewall ──
_FIREWALL_TOOLS: list[dict] = [
    {
        "name": "evaluate_rule",
        "description": "Check if traffic between source and destination would be allowed or denied by firewall rules on a specific device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "Firewall device ID"},
                "src_ip": {"type": "string"},
                "dst_ip": {"type": "string"},
                "port": {"type": "integer"},
                "protocol": {"type": "string", "default": "tcp"},
            },
            "required": ["device_id", "src_ip", "dst_ip", "port"],
        },
    },
    {
        "name": "list_rules_for_device",
        "description": "List all firewall/ACL rules configured on a device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "simulate_rule_change",
        "description": "Simulate adding/removing a firewall rule and show impact. INVESTIGATION MODE ONLY.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "action": {"type": "string", "enum": ["add", "remove"]},
                "rule": {"type": "object", "description": "Rule definition"},
            },
            "required": ["device_id", "action", "rule"],
        },
    },
    {
        "name": "get_nacls",
        "description": "Get Network ACL rules for a VPC or subnet (cloud environments).",
        "input_schema": {
            "type": "object",
            "properties": {"vpc_id": {"type": "string"}},
            "required": ["vpc_id"],
        },
    },
]

# ── Tool Group: Device ──
_DEVICE_TOOLS: list[dict] = [
    {
        "name": "list_devices",
        "description": "List all managed network devices with name, vendor, type, management IP, and status.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 100}},
            "required": [],
        },
    },
    {
        "name": "get_device_health",
        "description": "Get current health metrics for a device: CPU, memory, uptime, temperature, interface error counts.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_interface_stats",
        "description": "Get interface-level statistics: bandwidth utilization, error rates, packet drops, CRC errors.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}, "interface_name": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_syslog_events",
        "description": "Get recent syslog events for a device, sorted by timestamp descending.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "get_snmp_metrics",
        "description": "Get SNMP-polled metrics for a device: CPU, memory, interface counters, custom OIDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string", "description": "Device ID"},
                "oid": {"type": "string", "description": "Optional specific OID to query"},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "get_traps",
        "description": "Get recent SNMP traps for a device.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["device_id"],
        },
    },
]

# ── Tool Group: Alerts ──
_ALERT_TOOLS: list[dict] = [
    {
        "name": "get_active_alerts",
        "description": "Get all currently active alerts with severity, source device, message, and timestamps.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_alert_history",
        "description": "Get historical alerts within a time window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "24h"},
                "limit": {"type": "integer", "default": 100},
            },
            "required": [],
        },
    },
    {
        "name": "get_drift_events",
        "description": "Get detected configuration drift events — changes between baseline and live config.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 50}},
            "required": [],
        },
    },
]

# ── Tool Group: Diagnostic ──
_DIAGNOSTIC_TOOLS: list[dict] = [
    {
        "name": "diagnose_path",
        "description": "Run a full path diagnosis between two IPs using the LangGraph diagnostic pipeline. Returns hops, firewall verdicts, NAT translations, and a final verdict.",
        "input_schema": {
            "type": "object",
            "properties": {
                "src_ip": {"type": "string"},
                "dst_ip": {"type": "string"},
                "port": {"type": "integer", "default": 80},
                "protocol": {"type": "string", "default": "tcp"},
            },
            "required": ["src_ip", "dst_ip"],
        },
    },
    {
        "name": "explain_finding",
        "description": "Explain a specific diagnostic finding in plain language, including what it means, its severity, and recommended next steps.",
        "input_schema": {
            "type": "object",
            "properties": {
                "finding_id": {"type": "string", "description": "Finding ID or description to explain"},
            },
            "required": ["finding_id"],
        },
    },
    {
        "name": "correlate_events",
        "description": "Correlate alerts, syslog events, and flow changes within a time window to find related events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "30m"},
                "device_id": {"type": "string", "description": "Optional device to scope correlation"},
            },
            "required": [],
        },
    },
    {
        "name": "root_cause_analyze",
        "description": "Analyze a set of symptoms (alerts, metrics anomalies) and suggest probable root causes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symptoms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of observed symptoms or alert descriptions",
                },
            },
            "required": ["symptoms"],
        },
    },
]

# ── Tool Group: Control Plane ──
_CONTROL_PLANE_TOOLS: list[dict] = [
    {
        "name": "get_bgp_neighbors",
        "description": "Get BGP neighbor/peer status for a device: peer IP, ASN, state, uptime, prefixes received/advertised.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_bgp_routes",
        "description": "Get BGP routing table for a device: prefix, next-hop, AS path, local preference, MED.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "prefix": {"type": "string", "description": "Optional prefix filter (e.g., '10.0.0.0/8')"},
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "get_route_flaps",
        "description": "Get recent route flap events: prefix, timestamps, peer, flap count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "window": {"type": "string", "default": "1h"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "get_tunnel_status",
        "description": "Get VPN/GRE/IPsec tunnel status: tunnel name, endpoints, state, uptime.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_tunnel_latency",
        "description": "Get latency and jitter measurements for tunnels on a device.",
        "input_schema": {
            "type": "object",
            "properties": {"device_id": {"type": "string"}},
            "required": ["device_id"],
        },
    },
    {
        "name": "get_vpn_sessions",
        "description": "Get active VPN sessions: user/site, tunnel type, duration, bytes transferred.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 50}},
            "required": [],
        },
    },
]

# ── Tool Group: Cloud Networking ──
_CLOUD_NETWORK_TOOLS: list[dict] = [
    {
        "name": "get_vpc_routes",
        "description": "Get route table for a VPC: destination, target, status.",
        "input_schema": {
            "type": "object",
            "properties": {"vpc_id": {"type": "string"}},
            "required": ["vpc_id"],
        },
    },
    {
        "name": "get_security_group_rules",
        "description": "Get security group rules for a cloud resource.",
        "input_schema": {
            "type": "object",
            "properties": {"security_group_id": {"type": "string"}},
            "required": ["security_group_id"],
        },
    },
    {
        "name": "get_nacl_rules",
        "description": "Get Network ACL rules for a VPC subnet.",
        "input_schema": {
            "type": "object",
            "properties": {"nacl_id": {"type": "string"}},
            "required": ["nacl_id"],
        },
    },
    {
        "name": "get_load_balancer_health",
        "description": "Get health status of load balancer targets/backends.",
        "input_schema": {
            "type": "object",
            "properties": {"lb_id": {"type": "string"}},
            "required": ["lb_id"],
        },
    },
    {
        "name": "get_peering_status",
        "description": "Get VPC peering or transit gateway attachment status.",
        "input_schema": {
            "type": "object",
            "properties": {"vpc_id": {"type": "string"}},
            "required": ["vpc_id"],
        },
    },
]

# ── Tool Group: Shared (always loaded) ──
_SHARED_TOOLS: list[dict] = [
    {
        "name": "summarize_context",
        "description": "Summarize the current visible data and conversation context. Use when the user asks for an overview.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "start_investigation",
        "description": "Escalate to a cross-view Network Investigation session. Use when the user's question spans multiple network domains.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why investigation mode is needed"},
            },
            "required": ["reason"],
        },
    },
]

# ── View → Tool Group mapping ──
_VIEW_TOOL_GROUPS: dict[str, list[list[dict]]] = {
    "observatory": [_FLOW_TOOLS, _ALERT_TOOLS, _DEVICE_TOOLS, _DIAGNOSTIC_TOOLS],
    "network-topology": [_TOPOLOGY_TOOLS, _FIREWALL_TOOLS, _DIAGNOSTIC_TOOLS],
    "ipam": [_IPAM_TOOLS, _TOPOLOGY_TOOLS],
    "device-monitoring": [_DEVICE_TOOLS, _ALERT_TOOLS, _DIAGNOSTIC_TOOLS, _CONTROL_PLANE_TOOLS],
    "network-adapters": [_FIREWALL_TOOLS, _DEVICE_TOOLS, _CLOUD_NETWORK_TOOLS],
    "matrix": [_TOPOLOGY_TOOLS, _FIREWALL_TOOLS, _CONTROL_PLANE_TOOLS],
    "mib-browser": [_DEVICE_TOOLS],
    "cloud-resources": [_CLOUD_NETWORK_TOOLS, _FIREWALL_TOOLS, _TOPOLOGY_TOOLS],
    "security-resources": [_CLOUD_NETWORK_TOOLS, _FIREWALL_TOOLS],
}

_ALL_GROUPS = [
    _TOPOLOGY_TOOLS, _FLOW_TOOLS, _IPAM_TOOLS, _FIREWALL_TOOLS,
    _DEVICE_TOOLS, _ALERT_TOOLS, _DIAGNOSTIC_TOOLS,
    _CONTROL_PLANE_TOOLS, _CLOUD_NETWORK_TOOLS,
]


class NetworkToolRegistry:
    @staticmethod
    def get_tools_for_view(view: str) -> list[dict]:
        """Return deduplicated tools for a view plus shared tools.

        Unknown views receive only the shared tools.
        """
        groups = _VIEW_TOOL_GROUPS.get(view, [])
        tools: list[dict] = []
        seen: set[str] = set()
        for group in groups:
            for tool in group:
                if tool["name"] not in seen:
                    tools.append(tool)
                    seen.add(tool["name"])
        # Always include shared tools
        for tool in _SHARED_TOOLS:
            if tool["name"] not in seen:
                tools.append(tool)
                seen.add(tool["name"])
        return tools

    @staticmethod
    def get_all_tools() -> list[dict]:
        """Return all tools from every group (deduplicated) plus shared.

        Used for investigation mode where the LLM needs access to all tools.
        """
        tools: list[dict] = []
        seen: set[str] = set()
        for group in _ALL_GROUPS:
            for tool in group:
                if tool["name"] not in seen:
                    tools.append(tool)
                    seen.add(tool["name"])
        for tool in _SHARED_TOOLS:
            if tool["name"] not in seen:
                tools.append(tool)
                seen.add(tool["name"])
        return tools
