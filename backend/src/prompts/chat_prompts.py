"""Chat-specific rules and tool schemas."""

CHAT_RULES = """
ROLE: You are an AI SRE assistant embedded in a live incident investigation.

WORKFLOW:
- If the user asks about a metric/pod/log you don't have in context, use the appropriate tool to fetch it live.
- If a tool call fails, tell the user what failed and suggest alternatives.
- When presenting comparisons, use markdown tables.
- When presenting sequences, use numbered lists.
- Keep responses concise (3-5 sentences for simple questions, structured sections for complex ones).

BOUNDARIES:
- You can READ data via tools. You cannot MODIFY infrastructure.
- For remediation actions (fix, rollback, restart), explain what would happen and ask for explicit approval.
- Stay within the scope of the current investigation session.
"""

CHAT_TOOLS_SCHEMA = [
    {
        "name": "query_prometheus",
        "description": "Query Prometheus for metric values over a time range. Use for CPU, memory, request rate, error rate, latency questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PromQL query string"},
                "start": {"type": "string", "description": "Start time (ISO 8601 or relative like '1h')"},
                "end": {"type": "string", "description": "End time (ISO 8601 or 'now')"},
                "step": {"type": "string", "description": "Query resolution step (e.g., '15s', '1m')"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_logs",
        "description": "Search Elasticsearch logs by keyword, service, or time range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (Lucene syntax)"},
                "service": {"type": "string", "description": "Filter by service name"},
                "time_from": {"type": "string", "description": "Start time"},
                "time_to": {"type": "string", "description": "End time"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_pod_status",
        "description": "Get current status of a Kubernetes pod including restarts, resource usage, and events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pod_name": {"type": "string", "description": "Pod name (supports prefix matching)"},
                "namespace": {"type": "string", "description": "K8s namespace"},
            },
            "required": ["pod_name"],
        },
    },
    {
        "name": "query_trace",
        "description": "Fetch distributed trace spans from Jaeger by trace ID or service name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trace_id": {"type": "string", "description": "Specific trace ID"},
                "service": {"type": "string", "description": "Service name to search traces for"},
                "limit": {"type": "integer", "description": "Max traces to return (default 5)"},
            },
        },
    },
    {
        "name": "search_findings",
        "description": "Search collected investigation findings by agent, severity, or keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Search keyword"},
                "agent": {"type": "string", "description": "Filter by agent (log_agent, metrics_agent, etc.)"},
                "severity": {"type": "string", "description": "Filter by severity (critical, high, medium, low)"},
            },
        },
    },
    {
        "name": "run_promql",
        "description": "Execute a raw PromQL query and return current results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "promql": {"type": "string", "description": "PromQL expression"},
            },
            "required": ["promql"],
        },
    },
]
