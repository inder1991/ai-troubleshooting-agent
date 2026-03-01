"""
Agent Registry: defines all 25 diagnostic agents, their configurations,
health probe functions, and status logic.

This is the single source of truth for the Agent Matrix page.
The frontend reads it via GET /api/v4/agents.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

# ---------------------------------------------------------------------------
# Health probe cache (30-second TTL)
# ---------------------------------------------------------------------------

_health_cache: dict[str, tuple[bool, float]] = {}
_CACHE_TTL = 30.0


async def _probe_with_timeout(
    coro,
    key: str,
    timeout: float = 3.0,
) -> bool:
    """Run a health check coroutine with timeout and caching."""
    now = time.monotonic()
    cached = _health_cache.get(key)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    try:
        result = await asyncio.wait_for(coro(), timeout=timeout)
        _health_cache[key] = (result, now)
        return result
    except (asyncio.TimeoutError, Exception):
        _health_cache[key] = (False, now)
        return False


# ---------------------------------------------------------------------------
# Individual health check functions
# ---------------------------------------------------------------------------


async def check_k8s_connectivity() -> bool:
    """Check Kubernetes API connectivity via kubectl."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "kubectl", "get", "namespaces", "--request-timeout=3s",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def check_prometheus_connectivity() -> bool:
    """Check Prometheus connectivity via HTTP."""
    import os
    try:
        import httpx
        prom_url = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{prom_url}/api/v1/query", params={"query": "up"})
            return resp.status_code == 200
    except Exception:
        return False


async def check_elasticsearch_connectivity() -> bool:
    """Check Elasticsearch connectivity via HTTP ping."""
    import os
    try:
        import httpx
        es_url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(es_url)
            return resp.status_code == 200
    except Exception:
        return False


async def check_github_connectivity() -> bool:
    """Check GitHub API connectivity."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.github.com/rate_limit")
            return resp.status_code in (200, 401)  # 401 = reachable but no token
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Health probes mapping: tool key -> async probe function
# ---------------------------------------------------------------------------

HEALTH_PROBES: dict[str, Any] = {
    "k8s_api": lambda: _probe_with_timeout(check_k8s_connectivity, "k8s_api"),
    "prometheus": lambda: _probe_with_timeout(check_prometheus_connectivity, "prometheus"),
    "elasticsearch": lambda: _probe_with_timeout(check_elasticsearch_connectivity, "elasticsearch"),
    "github": lambda: _probe_with_timeout(check_github_connectivity, "github"),
}


async def run_all_health_probes() -> dict[str, bool]:
    """Run all health probes in parallel and return results."""
    keys = list(HEALTH_PROBES.keys())
    results = await asyncio.gather(
        *(HEALTH_PROBES[k]() for k in keys),
        return_exceptions=True,
    )
    return {
        k: (r is True) for k, r in zip(keys, results)
    }


def clear_health_cache() -> None:
    """Clear the health probe cache. Used in tests."""
    _health_cache.clear()


# ---------------------------------------------------------------------------
# Agent Registry: 25 agents (15 app_diagnostics + 10 cluster_diagnostics)
# ---------------------------------------------------------------------------

AGENT_REGISTRY: list[dict[str, Any]] = [
    # =========================================================================
    # APP DIAGNOSTICS (15 agents)
    # =========================================================================

    # --- Orchestrators (3) ---
    {
        "id": "supervisor_agent",
        "name": "SUPERVISOR_AGENT",
        "workflow": "app_diagnostics",
        "role": "orchestrator",
        "description": "State machine orchestrator that routes work to specialized analysis agents and manages investigation lifecycle.",
        "icon": "hub",
        "level": 5,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 200000,
            "mode": "orchestrator",
        },
        "timeout_s": 120,
        "tools": ["llm_router", "state_machine"],
        "tool_health_checks": {},
        "architecture_stages": ["Intent Parse", "Agent Dispatch", "Evidence Merge", "Verdict Build"],
    },
    {
        "id": "critic_agent",
        "name": "CRITIC_AGENT",
        "workflow": "app_diagnostics",
        "role": "orchestrator",
        "description": "Reviews investigation findings, challenges weak evidence, and scores diagnostic confidence.",
        "icon": "rate_review",
        "level": 4,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.2,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 60,
        "tools": ["llm_review"],
        "tool_health_checks": {},
        "architecture_stages": ["Evidence Review", "Confidence Score", "Gap Identification", "Verdict Challenge"],
    },
    {
        "id": "evidence_graph_builder",
        "name": "EVIDENCE_GRAPH_BUILDER",
        "workflow": "app_diagnostics",
        "role": "orchestrator",
        "description": "Builds causal evidence graphs from correlated signals across log, metric, trace, and k8s data sources.",
        "icon": "account_tree",
        "level": 4,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["graph_builder"],
        "tool_health_checks": {},
        "architecture_stages": ["Signal Collection", "Correlation Analysis", "Graph Construction", "Root Cause Ranking"],
    },

    # --- Analysis (6) ---
    {
        "id": "log_analysis_agent",
        "name": "LOG_ANALYSIS_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Analyzes application logs from Elasticsearch to identify error patterns, stack traces, and anomalous log sequences.",
        "icon": "description",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["search_logs", "fetch_pod_logs"],
        "tool_health_checks": {
            "elasticsearch": "check_elasticsearch_connectivity",
            "k8s_api": "check_k8s_connectivity",
        },
        "architecture_stages": ["Log Fetch", "Pattern Detection", "LLM Analysis", "Evidence Pin"],
    },
    {
        "id": "metrics_agent",
        "name": "METRICS_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Queries Prometheus for CPU, memory, latency, and error rate anomalies correlated to the incident timeframe.",
        "icon": "monitoring",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["query_prometheus"],
        "tool_health_checks": {
            "prometheus": "check_prometheus_connectivity",
        },
        "architecture_stages": ["PromQL Query", "Anomaly Detection", "LLM Analysis", "Evidence Pin"],
    },
    {
        "id": "k8s_agent",
        "name": "K8S_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Inspects Kubernetes resources including pod status, events, deployments, and resource quotas for cluster-level issues.",
        "icon": "cloud",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "react",
        },
        "timeout_s": 45,
        "tools": ["check_pod_status", "get_events", "describe_resource"],
        "tool_health_checks": {
            "k8s_api": "check_k8s_connectivity",
        },
        "architecture_stages": ["Resource Scan", "Event Analysis", "ReAct Loop", "Evidence Pin"],
    },
    {
        "id": "tracing_agent",
        "name": "TRACING_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Analyzes distributed traces to identify slow spans, error propagation, and service dependency failures.",
        "icon": "timeline",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "react",
        },
        "timeout_s": 45,
        "tools": ["query_traces"],
        "tool_health_checks": {
            "elasticsearch": "check_elasticsearch_connectivity",
        },
        "architecture_stages": ["Trace Fetch", "Span Analysis", "ReAct Loop", "Evidence Pin"],
    },
    {
        "id": "code_navigator_agent",
        "name": "CODE_NAVIGATOR_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Navigates source code repositories to find relevant files, recent changes, and code patterns related to the incident.",
        "icon": "code",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "react",
        },
        "timeout_s": 60,
        "tools": ["read_file", "search_code", "list_files"],
        "tool_health_checks": {
            "github": "check_github_connectivity",
        },
        "architecture_stages": ["File Discovery", "Code Read", "ReAct Loop", "Evidence Pin"],
    },
    {
        "id": "change_agent",
        "name": "CHANGE_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Analyzes recent deployments, config changes, and git commits to correlate changes with incident onset.",
        "icon": "difference",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "react",
        },
        "timeout_s": 45,
        "tools": ["git_log", "git_diff", "get_events"],
        "tool_health_checks": {
            "github": "check_github_connectivity",
            "k8s_api": "check_k8s_connectivity",
        },
        "architecture_stages": ["Change Detection", "Diff Analysis", "ReAct Loop", "Evidence Pin"],
    },

    # --- Validation (1) ---
    {
        "id": "impact_analyzer",
        "name": "IMPACT_ANALYZER",
        "workflow": "app_diagnostics",
        "role": "validation",
        "description": "Assesses blast radius and user impact by analyzing affected services, endpoints, and error rates.",
        "icon": "crisis_alert",
        "level": 4,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 30,
        "tools": ["query_prometheus", "check_pod_status"],
        "tool_health_checks": {
            "prometheus": "check_prometheus_connectivity",
            "k8s_api": "check_k8s_connectivity",
        },
        "architecture_stages": ["Scope Assessment", "Blast Radius Calc", "User Impact Score", "Report Build"],
    },

    # --- Fix Generation (5) ---
    {
        "id": "fix_generator",
        "name": "FIX_GENERATOR",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Generates code fixes based on root cause analysis, producing diffs and PR-ready patches.",
        "icon": "build",
        "level": 5,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.2,
            "context_window": 200000,
            "mode": "autonomous",
        },
        "timeout_s": 90,
        "tools": ["read_file", "write_file", "search_code"],
        "tool_health_checks": {
            "github": "check_github_connectivity",
        },
        "architecture_stages": ["Root Cause Intake", "Fix Planning", "Code Generation", "Diff Production"],
    },
    {
        "id": "static_validator",
        "name": "STATIC_VALIDATOR",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Validates generated code fixes using AST parsing, linting, and import validation without execution.",
        "icon": "check_circle",
        "level": 2,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.0,
            "context_window": 64000,
            "mode": "deterministic",
        },
        "timeout_s": 30,
        "tools": ["ast_parse", "ruff_lint"],
        "tool_health_checks": {},
        "architecture_stages": ["AST Parse", "Lint Check", "Import Validation", "Result Report"],
    },
    {
        "id": "cross_agent_reviewer",
        "name": "CROSS_AGENT_REVIEWER",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Peer reviews generated fixes by verifying logical correctness against the codebase context.",
        "icon": "grading",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["read_file", "search_code"],
        "tool_health_checks": {
            "github": "check_github_connectivity",
        },
        "architecture_stages": ["Diff Review", "Context Check", "LLM Verification", "Approval Decision"],
    },
    {
        "id": "impact_assessor",
        "name": "IMPACT_ASSESSOR",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Assesses potential side effects, security concerns, and regression risk of proposed code fixes.",
        "icon": "security",
        "level": 3,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 30,
        "tools": ["ast_parse", "dependency_scan"],
        "tool_health_checks": {},
        "architecture_stages": ["Side Effect Scan", "Security Check", "Regression Risk", "Risk Report"],
    },
    {
        "id": "pr_stager",
        "name": "PR_STAGER",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Handles git operations for staging fixes: branch creation, file staging, commit, and PR template generation.",
        "icon": "merge_type",
        "level": 2,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.0,
            "context_window": 64000,
            "mode": "deterministic",
        },
        "timeout_s": 60,
        "tools": ["git_branch", "git_commit", "git_push"],
        "tool_health_checks": {
            "github": "check_github_connectivity",
        },
        "architecture_stages": ["Branch Create", "File Stage", "Commit Build", "PR Template"],
    },

    # =========================================================================
    # CLUSTER DIAGNOSTICS (10 agents)
    # =========================================================================

    # --- Orchestrators (6) ---
    {
        "id": "topology_resolver",
        "name": "TOPOLOGY_RESOLVER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Reads or builds cached cluster topology snapshots including nodes, pods, services, and their relationships.",
        "icon": "device_hub",
        "level": 4,
        "llm_config": {
            "model": "none",
            "temperature": 0.0,
            "context_window": 0,
            "mode": "deterministic",
        },
        "timeout_s": 30,
        "tools": ["k8s_lister", "topology_cache"],
        "tool_health_checks": {
            "k8s_api": "check_k8s_connectivity",
        },
        "architecture_stages": ["Cache Check", "Topology Read", "Graph Build", "Scope Prune"],
    },
    {
        "id": "alert_correlator",
        "name": "ALERT_CORRELATOR",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Groups cluster events and alerts into correlated issue clusters with root cause candidates.",
        "icon": "link",
        "level": 4,
        "llm_config": {
            "model": "none",
            "temperature": 0.0,
            "context_window": 0,
            "mode": "deterministic",
        },
        "timeout_s": 30,
        "tools": ["k8s_lister", "list_events"],
        "tool_health_checks": {
            "k8s_api": "check_k8s_connectivity",
        },
        "architecture_stages": ["Alert Fetch", "Temporal Grouping", "Root Candidate ID", "Cluster Build"],
    },
    {
        "id": "causal_firewall",
        "name": "CAUSAL_FIREWALL",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Two-tier pre-LLM filtering that blocks impossible causal links using invariant rules before LLM reasoning.",
        "icon": "shield",
        "level": 4,
        "llm_config": {
            "model": "none",
            "temperature": 0.0,
            "context_window": 0,
            "mode": "deterministic",
        },
        "timeout_s": 15,
        "tools": ["invariant_checker"],
        "tool_health_checks": {},
        "architecture_stages": ["Hard Block Check", "Soft Rule Score", "Search Space Prune", "Annotation Build"],
    },
    {
        "id": "dispatch_router",
        "name": "DISPATCH_ROUTER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Determines which domain agents should run based on diagnostic scope and dispatches work in parallel.",
        "icon": "alt_route",
        "level": 3,
        "llm_config": {
            "model": "none",
            "temperature": 0.0,
            "context_window": 0,
            "mode": "deterministic",
        },
        "timeout_s": 10,
        "tools": ["scope_resolver"],
        "tool_health_checks": {},
        "architecture_stages": ["Scope Read", "Domain Select", "Fan-Out Dispatch", "Coverage Calc"],
    },
    {
        "id": "synthesizer",
        "name": "SYNTHESIZER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Three-stage synthesis pipeline that merges domain reports, performs causal reasoning, and builds the final verdict.",
        "icon": "merge",
        "level": 5,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 200000,
            "mode": "autonomous",
        },
        "timeout_s": 60,
        "tools": ["llm_synthesis"],
        "tool_health_checks": {},
        "architecture_stages": ["Report Merge", "Causal Reasoning", "Confidence Calc", "Verdict Build"],
    },
    {
        "id": "guard_formatter",
        "name": "GUARD_FORMATTER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Structures diagnostic output into a 3-layer health scan format with current risks, predictions, and deltas.",
        "icon": "format_list_bulleted",
        "level": 3,
        "llm_config": {
            "model": "none",
            "temperature": 0.0,
            "context_window": 0,
            "mode": "deterministic",
        },
        "timeout_s": 15,
        "tools": ["report_formatter"],
        "tool_health_checks": {},
        "architecture_stages": ["Risk Assessment", "Prediction Build", "Delta Calc", "Scan Format"],
    },

    # --- Domain Experts (4) ---
    {
        "id": "ctrl_plane_agent",
        "name": "CTRL_PLANE_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes control plane health including API server, etcd, scheduler, and controller manager components.",
        "icon": "settings_suggest",
        "level": 4,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["k8s_lister", "prometheus_query", "list_events"],
        "tool_health_checks": {
            "k8s_api": "check_k8s_connectivity",
            "prometheus": "check_prometheus_connectivity",
        },
        "architecture_stages": ["Component Scan", "Metric Fetch", "LLM Analysis", "Report Build"],
    },
    {
        "id": "node_agent",
        "name": "NODE_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes node conditions, resource utilization, pod evictions, and scheduling failures.",
        "icon": "dns",
        "level": 4,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["k8s_lister", "prometheus_query", "list_events", "list_pods"],
        "tool_health_checks": {
            "k8s_api": "check_k8s_connectivity",
            "prometheus": "check_prometheus_connectivity",
        },
        "architecture_stages": ["Topology Read", "Event Fetch", "LLM Analysis", "Report Build"],
    },
    {
        "id": "network_agent",
        "name": "NETWORK_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes network policies, ingress rules, DNS resolution, service mesh, and connectivity between services.",
        "icon": "lan",
        "level": 4,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["k8s_lister", "prometheus_query", "list_events"],
        "tool_health_checks": {
            "k8s_api": "check_k8s_connectivity",
            "prometheus": "check_prometheus_connectivity",
        },
        "architecture_stages": ["Policy Scan", "DNS Check", "LLM Analysis", "Report Build"],
    },
    {
        "id": "storage_agent",
        "name": "STORAGE_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes persistent volumes, storage classes, CSI drivers, and volume mount failures.",
        "icon": "storage",
        "level": 4,
        "llm_config": {
            "model": "claude-sonnet-4-20250514",
            "temperature": 0.1,
            "context_window": 128000,
            "mode": "autonomous",
        },
        "timeout_s": 45,
        "tools": ["k8s_lister", "prometheus_query", "list_events"],
        "tool_health_checks": {
            "k8s_api": "check_k8s_connectivity",
            "prometheus": "check_prometheus_connectivity",
        },
        "architecture_stages": ["PV/PVC Scan", "CSI Check", "LLM Analysis", "Report Build"],
    },
]


# ---------------------------------------------------------------------------
# Derived: dict lookup by agent ID
# ---------------------------------------------------------------------------

AGENT_REGISTRY_MAP: dict[str, dict[str, Any]] = {
    agent["id"]: agent for agent in AGENT_REGISTRY
}


# ---------------------------------------------------------------------------
# Status logic: determines active/degraded/offline from health results
# ---------------------------------------------------------------------------


def get_agent_status(
    agent: dict[str, Any],
    health_results: dict[str, bool],
) -> tuple[str, list[str]]:
    """Determine agent status from health probe results.

    Returns:
        (status, degraded_tools) where status is "active" | "degraded" | "offline"
        and degraded_tools is a list of tool keys that are failing.
    """
    checks = agent.get("tool_health_checks", {})

    # No health checks defined -> always active
    if not checks:
        return "active", []

    failing: list[str] = []
    for tool_key in checks:
        if not health_results.get(tool_key, False):
            failing.append(tool_key)

    if not failing:
        return "active", []

    # If ALL checks fail -> offline
    if len(failing) == len(checks):
        return "offline", failing

    # Some checks fail -> degraded
    return "degraded", failing
