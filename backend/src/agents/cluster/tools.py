"""Anthropic tool schemas for cluster diagnostic agents."""

CLUSTER_TOOLS = [
    {
        "name": "list_pods",
        "description": "List pods in a namespace with status, restarts, node assignment, and resource requests/limits",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query. Empty string for all namespaces."}
            },
            "required": []
        }
    },
    {
        "name": "describe_pod",
        "description": "Get detailed pod spec, status, events, and conditions for a specific pod",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Pod namespace"}
            },
            "required": ["name", "namespace"]
        }
    },
    {
        "name": "list_deployments",
        "description": "List deployments with replica status, rollout conditions, and strategy",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query"}
            },
            "required": []
        }
    },
    {
        "name": "list_events",
        "description": "Get Kubernetes events for resources. Filter by namespace or field selector",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace"},
                "field_selector": {"type": "string", "description": "K8s field selector (e.g. involvedObject.kind=Node)"}
            },
            "required": []
        }
    },
    {
        "name": "list_nodes",
        "description": "List cluster nodes with conditions, capacity, and roles",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_pvcs",
        "description": "List PersistentVolumeClaims with binding status and capacity",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace"}
            },
            "required": []
        }
    },
    {
        "name": "list_services",
        "description": "List services with type, endpoints count, and selector",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace"}
            },
            "required": []
        }
    },
    {
        "name": "list_hpas",
        "description": "List HorizontalPodAutoscalers with current/target metrics and scaling status",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace"}
            },
            "required": []
        }
    },
    {
        "name": "get_pod_logs",
        "description": "Get last N lines of a pod's logs",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Pod name"},
                "namespace": {"type": "string", "description": "Pod namespace"},
                "tail_lines": {"type": "integer", "description": "Number of lines from the end", "default": 100}
            },
            "required": ["name", "namespace"]
        }
    },
    {
        "name": "query_prometheus",
        "description": "Query a Prometheus metric expression",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PromQL expression"},
                "time_range": {"type": "string", "description": "Time range (default: 1h)", "default": "1h"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_network_policies",
        "description": "List NetworkPolicies with selector, ingress/egress rules",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace"}
            },
            "required": []
        }
    },
    {
        "name": "list_rbac",
        "description": "List Roles, RoleBindings, and ServiceAccounts in a namespace",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace"}
            },
            "required": []
        }
    },
    {
        "name": "list_statefulsets",
        "description": "List StatefulSets with replica status and ordered pod failure conditions",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query. Empty string for all namespaces."}
            },
            "required": []
        }
    },
    {
        "name": "list_daemonsets",
        "description": "List DaemonSets with desired/ready/unavailable counts across nodes",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query. Empty string for all namespaces."}
            },
            "required": []
        }
    },
    {
        "name": "list_jobs",
        "description": "List Jobs with completion status, failure counts, and backoff limit",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query. Empty string for all namespaces."}
            },
            "required": []
        }
    },
    {
        "name": "list_cronjobs",
        "description": "List CronJobs with schedule, suspend status, and last successful run time",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query. Empty string for all namespaces."}
            },
            "required": []
        }
    },
    {
        "name": "list_routes",
        "description": "List OpenShift Routes with host, TLS config, backend service, and admitted status",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query"}
            },
            "required": []
        }
    },
    {
        "name": "list_ingresses",
        "description": "List Kubernetes Ingresses with hosts, TLS secrets, backends, and ingress class",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query"}
            },
            "required": []
        }
    },
    {
        "name": "list_webhooks",
        "description": "List ValidatingWebhookConfigurations and MutatingWebhookConfigurations",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_cluster_version",
        "description": "Get OpenShift ClusterVersion with upgrade status, conditions, and history",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "list_subscriptions",
        "description": "List OLM Subscriptions with package, channel, CSV version, and state",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query"}
            },
            "required": []
        }
    },
    {
        "name": "list_csvs",
        "description": "List OLM ClusterServiceVersions with phase, reason, and message",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query"}
            },
            "required": []
        }
    },
    {
        "name": "list_install_plans",
        "description": "List OLM InstallPlans with approval status, phase, and CSV names",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "Namespace to query"}
            },
            "required": []
        }
    },
    {
        "name": "list_machines",
        "description": "List OpenShift Machines with phase, provider ID, node reference, and conditions",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_proxy_config",
        "description": "Get OpenShift cluster-wide proxy configuration (httpProxy, httpsProxy, noProxy, trustedCA)",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "submit_findings",
        "description": "Submit your diagnostic findings. Call this when analysis is complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "anomalies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "domain": {"type": "string"},
                            "anomaly_id": {"type": "string"},
                            "description": {"type": "string"},
                            "evidence_ref": {"type": "string"},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]}
                        },
                        "required": ["domain", "anomaly_id", "description", "evidence_ref"]
                    }
                },
                "ruled_out": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "integer", "minimum": 0, "maximum": 100}
            },
            "required": ["anomalies", "ruled_out", "confidence"]
        }
    }
]

# Per-agent tool subsets
CTRL_PLANE_TOOLS = ["list_nodes", "list_pods", "list_deployments", "list_events", "query_prometheus", "get_cluster_version", "list_subscriptions", "list_csvs", "list_install_plans", "list_machines", "get_proxy_config", "submit_findings"]
NODE_TOOLS = ["list_pods", "list_nodes", "list_deployments", "list_statefulsets", "list_daemonsets", "list_jobs", "list_cronjobs", "list_events", "list_hpas", "list_pvcs", "query_prometheus", "get_pod_logs", "submit_findings"]
NETWORK_TOOLS = ["list_services", "list_pods", "list_events", "list_network_policies", "list_routes", "list_ingresses", "query_prometheus", "get_pod_logs", "submit_findings"]
STORAGE_TOOLS = ["list_pvcs", "list_pods", "list_events", "query_prometheus", "submit_findings"]
RBAC_TOOLS = ["list_rbac", "list_pods", "list_events", "submit_findings"]


def get_version_context(platform_version: str) -> str:
    """Return version-specific Kubernetes context for prompts."""
    version_notes = []
    try:
        parts = platform_version.replace("+", ".").split(".")
        major = int(parts[0]) if parts else 1
        minor = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return ""

    if minor >= 25:
        version_notes.append("PodSecurity admission replaces PodSecurityPolicy (deprecated)")
    if minor >= 27:
        version_notes.append("In-place pod resize is available (alpha)")
    if minor >= 29:
        version_notes.append("Native sidecar containers are available")
    if minor >= 30:
        version_notes.append("Recursive read-only mounts are available")
    if minor >= 31:
        version_notes.append("AppArmor GA, nftables kube-proxy backend")

    if not version_notes:
        return ""
    return "Version-specific notes:\n" + "\n".join(f"- {n}" for n in version_notes)


def get_tools_for_agent(agent_name: str) -> list[dict]:
    """Return the tool schemas available to a specific agent."""
    tool_names = {
        "ctrl_plane": CTRL_PLANE_TOOLS,
        "node": NODE_TOOLS,
        "network": NETWORK_TOOLS,
        "storage": STORAGE_TOOLS,
        "rbac": RBAC_TOOLS,
    }.get(agent_name, [])
    return [t for t in CLUSTER_TOOLS if t["name"] in tool_names]
