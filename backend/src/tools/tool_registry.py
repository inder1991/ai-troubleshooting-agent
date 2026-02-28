"""
Tool registry: defines all available investigation tools, their parameters, and slash commands.
This is the single source of truth -- the frontend reads it via GET /tools, the router uses
it for slash command mapping and context defaults.
"""

TOOL_REGISTRY = [
    {
        "intent": "fetch_pod_logs",
        "label": "Get Pod Logs",
        "icon": "terminal",
        "slash_command": "/logs",
        "category": "logs",
        "description": "Fetch logs from a running or previously crashed pod",
        "params_schema": [
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
            {"name": "pod", "type": "select", "required": True, "default_from_context": "active_pod", "options": []},
            {"name": "container", "type": "select", "required": False, "options": []},
            {"name": "previous", "type": "boolean", "required": False},
            {"name": "tail_lines", "type": "number", "required": False},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "query_prometheus",
        "label": "Run PromQL",
        "icon": "monitoring",
        "slash_command": "/promql",
        "category": "metrics",
        "description": "Execute a Prometheus query and pin the result",
        "params_schema": [
            {"name": "query", "type": "string", "required": True},
            {"name": "range_minutes", "type": "number", "required": False},
        ],
        "requires_context": [],
    },
    {
        "intent": "describe_resource",
        "label": "Describe Resource",
        "icon": "info",
        "slash_command": "/describe",
        "category": "cluster",
        "description": "kubectl describe for any K8s/OpenShift resource",
        "params_schema": [
            {"name": "kind", "type": "select", "required": True, "options": ["pod", "deployment", "service", "node", "configmap", "ingress", "pvc"]},
            {"name": "name", "type": "string", "required": True},
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "get_events",
        "label": "Cluster Events",
        "icon": "event_note",
        "slash_command": "/events",
        "category": "cluster",
        "description": "Fetch Kubernetes events filtered by namespace and time",
        "params_schema": [
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
            {"name": "since_minutes", "type": "number", "required": False},
            {"name": "involved_object", "type": "string", "required": False},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "search_logs",
        "label": "Search ELK Logs",
        "icon": "search",
        "slash_command": "/search",
        "category": "logs",
        "description": "Search Elasticsearch for log patterns across services",
        "params_schema": [
            {"name": "query", "type": "string", "required": True},
            {"name": "index", "type": "string", "required": False, "default_from_context": "elk_index"},
            {"name": "level", "type": "select", "required": False, "options": ["ERROR", "WARN", "INFO", "DEBUG"]},
            {"name": "since_minutes", "type": "number", "required": False},
        ],
        "requires_context": [],
    },
    {
        "intent": "check_pod_status",
        "label": "Pod Health",
        "icon": "health_and_safety",
        "slash_command": "/pods",
        "category": "cluster",
        "description": "Check pod status, restart counts, and OOM kills",
        "params_schema": [
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
            {"name": "label_selector", "type": "string", "required": False},
        ],
        "requires_context": ["namespace"],
    },
    {
        "intent": "re_investigate_service",
        "label": "Investigate Service",
        "icon": "radar",
        "slash_command": "/investigate",
        "category": "cluster",
        "description": "Run the full agent pipeline against a different service",
        "params_schema": [
            {"name": "service", "type": "string", "required": True},
            {"name": "namespace", "type": "string", "required": True, "default_from_context": "active_namespace"},
        ],
        "requires_context": ["namespace"],
    },
]

# Derived: slash command -> intent mapping
SLASH_COMMAND_MAP = {t["slash_command"]: t["intent"] for t in TOOL_REGISTRY}
