# Agent Matrix: AI Workforce Directory — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build a dedicated `/agents` view that presents all 25 diagnostic agents as a "team of specialized automated engineers" with real-time health status, execution traces, tool visibility, and agent detail views.

**Architecture:** Static `AGENT_REGISTRY` dict on the backend (mirrors existing `TOOL_REGISTRY` pattern) + health probe functions that run in parallel with 30s cache. Two new API endpoints (`GET /api/v4/agents`, `GET /api/v4/agents/{id}/executions`). Frontend is a full-page `AgentMatrixView` with workflow tabs, role-grouped agent cards, and a detail view overlay.

**Tech Stack:** Python 3.14, FastAPI, asyncio, pytest, React 18, TypeScript, Tailwind CSS, Material Symbols

**Branch:** `feature/agent-matrix` (from `main`)

---

## Task 1: Backend Agent Registry + Health Probes

**Files:**
- Create: `backend/src/api/agent_registry.py`
- Create: `backend/tests/test_agent_registry.py`

**What this task does:** Create the `AGENT_REGISTRY` dict containing all 25 agents and the health probe functions with 30s caching. No API endpoints yet — just the data layer.

**Context:**
- Existing pattern to follow: `backend/src/tools/tool_registry.py` — a module-level list/dict (`TOOL_REGISTRY`) with static tool definitions.
- Agent configs come from the codebase: cluster agents in `backend/src/agents/cluster/` (10 agents with `@traced_node` timeouts), app agents in `backend/src/agents/supervisor.py` (15 agents across orchestration, analysis, validation, fix_generation).
- Health probes check external dependencies (K8s API, Prometheus, Elasticsearch, GitHub). Use `asyncio.gather` with 3s individual timeouts. Cache results for 30s using a simple `(timestamp, result)` tuple.
- The `ClusterClient` base class (`backend/src/agents/cluster_client/base.py`) has methods like `list_namespaces()`, `query_prometheus()`, `get_api_health()` that can serve as health check targets.

**Changes:**

1. **`agent_registry.py`** — Create the static registry and health probe infrastructure:

```python
"""
Agent Matrix registry: static metadata for all 25 diagnostic agents
plus health-probe functions with 30-second caching.
"""
import asyncio
import time
from typing import Any

# ── Health Probe Cache ──────────────────────────────────────────────
_health_cache: dict[str, tuple[float, bool]] = {}  # tool_key -> (timestamp, healthy)
_CACHE_TTL = 30.0  # seconds


async def _probe_with_timeout(coro, timeout: float = 3.0) -> bool:
    """Run a health probe coroutine with a timeout. Returns True if healthy."""
    try:
        await asyncio.wait_for(coro, timeout=timeout)
        return True
    except Exception:
        return False


async def check_k8s_connectivity() -> bool:
    """Probe K8s API by listing namespaces."""
    cached = _health_cache.get("k8s_api")
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]
    try:
        from kubernetes import client as k8s_client, config as k8s_config
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            k8s_config.load_kube_config()
        v1 = k8s_client.CoreV1Api()
        result = await _probe_with_timeout(
            asyncio.get_event_loop().run_in_executor(None, v1.list_namespace),
        )
    except Exception:
        result = False
    _health_cache["k8s_api"] = (time.monotonic(), result)
    return result


async def check_prometheus_connectivity() -> bool:
    """Probe Prometheus by querying 'up'."""
    cached = _health_cache.get("prometheus")
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            import os
            prom_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
            resp = await client.get(f"{prom_url}/api/v1/query", params={"query": "up"})
            result = resp.status_code == 200
    except Exception:
        result = False
    _health_cache["prometheus"] = (time.monotonic(), result)
    return result


async def check_elasticsearch_connectivity() -> bool:
    """Probe Elasticsearch with a ping."""
    cached = _health_cache.get("elasticsearch")
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            import os
            es_url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
            resp = await client.get(es_url)
            result = resp.status_code == 200
    except Exception:
        result = False
    _health_cache["elasticsearch"] = (time.monotonic(), result)
    return result


async def check_github_connectivity() -> bool:
    """Probe GitHub API rate limit endpoint."""
    cached = _health_cache.get("github")
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.github.com/rate_limit")
            result = resp.status_code == 200
    except Exception:
        result = False
    _health_cache["github"] = (time.monotonic(), result)
    return result


# Map from tool dependency key -> probe function
HEALTH_PROBES: dict[str, Any] = {
    "k8s_api": check_k8s_connectivity,
    "prometheus": check_prometheus_connectivity,
    "elasticsearch": check_elasticsearch_connectivity,
    "github": check_github_connectivity,
}


async def run_all_health_probes() -> dict[str, bool]:
    """Run all health probes in parallel. Returns {tool_key: healthy}."""
    keys = list(HEALTH_PROBES.keys())
    results = await asyncio.gather(
        *(HEALTH_PROBES[k]() for k in keys),
        return_exceptions=True,
    )
    return {k: (r is True) for k, r in zip(keys, results)}


def clear_health_cache():
    """Clear cached health probe results (for testing)."""
    _health_cache.clear()


# ── Agent Registry ──────────────────────────────────────────────────

AGENT_REGISTRY: list[dict[str, Any]] = [
    # ═══════════════════════════════════════════════════════════════
    # APP DIAGNOSTICS (15 agents)
    # ═══════════════════════════════════════════════════════════════

    # — Orchestrators —
    {
        "id": "supervisor_agent",
        "name": "SUPERVISOR_AGENT",
        "workflow": "app_diagnostics",
        "role": "orchestrator",
        "description": "State machine orchestrator that routes work to specialized analysis agents and coordinates the diagnostic pipeline.",
        "icon": "account_tree",
        "level": 5,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 120,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Intent Parse", "Agent Dispatch", "Result Merge", "Confidence Check"],
    },
    {
        "id": "critic_agent",
        "name": "CRITIC_AGENT",
        "workflow": "app_diagnostics",
        "role": "orchestrator",
        "description": "Validates diagnostic findings by challenging assumptions, checking evidence quality, and scoring confidence.",
        "icon": "fact_check",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.2, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Evidence Review", "Assumption Challenge", "Confidence Score", "Verdict"],
    },
    {
        "id": "evidence_graph_builder",
        "name": "EVIDENCE_GRAPH_BUILDER",
        "workflow": "app_diagnostics",
        "role": "orchestrator",
        "description": "Constructs a directed evidence graph linking findings to root causes with causal relationships and confidence weights.",
        "icon": "hub",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Node Extract", "Edge Build", "Weight Assign", "Graph Emit"],
    },

    # — Analysis —
    {
        "id": "log_analysis_agent",
        "name": "LOG_ANALYSIS_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Analyzes application logs to identify error patterns, exception chains, and anomalous log sequences.",
        "icon": "terminal",
        "level": 3,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": ["fetch_pod_logs", "search_logs"],
        "tool_health_checks": {"k8s_api": "check_k8s_connectivity", "elasticsearch": "check_elasticsearch_connectivity"},
        "architecture_stages": ["Log Fetch", "Pattern Match", "Exception Chain", "LLM Analysis"],
    },
    {
        "id": "metrics_agent",
        "name": "METRICS_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Queries Prometheus metrics to detect anomalies in latency, error rates, CPU, memory, and custom application metrics.",
        "icon": "monitoring",
        "level": 3,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": ["query_prometheus"],
        "tool_health_checks": {"prometheus": "check_prometheus_connectivity"},
        "architecture_stages": ["Query Build", "Data Fetch", "Anomaly Detect", "Report Build"],
    },
    {
        "id": "k8s_agent",
        "name": "K8S_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Inspects Kubernetes resources — pods, deployments, events, and node conditions — for infrastructure-level issues.",
        "icon": "cloud",
        "level": 3,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": ["describe_resource", "get_events", "check_pod_status"],
        "tool_health_checks": {"k8s_api": "check_k8s_connectivity"},
        "architecture_stages": ["Resource Scan", "Event Fetch", "Condition Check", "LLM Analysis"],
    },
    {
        "id": "tracing_agent",
        "name": "TRACING_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Analyzes distributed traces to identify slow spans, error propagation paths, and service dependency bottlenecks.",
        "icon": "timeline",
        "level": 3,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Trace Fetch", "Span Analysis", "Critical Path", "Report Build"],
    },
    {
        "id": "code_navigator_agent",
        "name": "CODE_NAVIGATOR_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Navigates the application codebase to locate relevant source files, understand call chains, and assess code-level impact.",
        "icon": "code",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 90,
        "tools": ["search_code", "read_file"],
        "tool_health_checks": {"github": "check_github_connectivity"},
        "architecture_stages": ["File Search", "AST Parse", "Call Chain", "Impact Map"],
    },
    {
        "id": "change_agent",
        "name": "CHANGE_AGENT",
        "workflow": "app_diagnostics",
        "role": "analysis",
        "description": "Correlates recent code changes (commits, PRs, deployments) with the incident timeline to identify change-induced regressions.",
        "icon": "difference",
        "level": 3,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": ["git_log", "git_diff"],
        "tool_health_checks": {"github": "check_github_connectivity"},
        "architecture_stages": ["Change Fetch", "Timeline Align", "Diff Analysis", "Correlation Score"],
    },

    # — Validation —
    {
        "id": "impact_analyzer",
        "name": "IMPACT_ANALYZER",
        "workflow": "app_diagnostics",
        "role": "validation",
        "description": "Assesses the blast radius of identified issues — affected services, user impact, SLA risk, and downstream dependencies.",
        "icon": "crisis_alert",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Scope Assess", "Dependency Walk", "SLA Check", "Impact Report"],
    },

    # — Fix Generation —
    {
        "id": "fix_generator",
        "name": "FIX_GENERATOR",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Generates code fixes based on diagnosed root causes, producing minimal diffs that address the issue.",
        "icon": "build",
        "level": 5,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 120,
        "tools": ["read_file", "write_file"],
        "tool_health_checks": {"github": "check_github_connectivity"},
        "architecture_stages": ["Context Build", "Fix Plan", "Code Gen", "Diff Output"],
    },
    {
        "id": "static_validator",
        "name": "STATIC_VALIDATOR",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Validates generated fixes using static analysis — syntax checks, type safety, and lint rules.",
        "icon": "verified",
        "level": 3,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.0, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 30,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Syntax Check", "Type Verify", "Lint Run", "Verdict"],
    },
    {
        "id": "cross_agent_reviewer",
        "name": "CROSS_AGENT_REVIEWER",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Reviews fixes from the perspective of each analysis agent, ensuring the fix addresses all identified issues.",
        "icon": "rate_review",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.2, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Per-Agent Review", "Conflict Check", "Consensus", "Approval"],
    },
    {
        "id": "impact_assessor",
        "name": "IMPACT_ASSESSOR",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Evaluates proposed fixes for unintended side effects, regression risk, and deployment safety.",
        "icon": "shield",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Risk Scan", "Regression Check", "Deploy Safety", "Risk Score"],
    },
    {
        "id": "pr_stager",
        "name": "PR_STAGER",
        "workflow": "app_diagnostics",
        "role": "fix_generation",
        "description": "Stages approved fixes as pull requests with proper descriptions, test plans, and reviewer assignments.",
        "icon": "merge",
        "level": 5,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.0, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 30,
        "tools": ["create_pr"],
        "tool_health_checks": {"github": "check_github_connectivity"},
        "architecture_stages": ["Branch Create", "Commit Stage", "PR Create", "Reviewer Assign"],
    },

    # ═══════════════════════════════════════════════════════════════
    # CLUSTER DIAGNOSTICS (10 agents)
    # ═══════════════════════════════════════════════════════════════

    # — Orchestrators —
    {
        "id": "topology_resolver",
        "name": "TOPOLOGY_RESOLVER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Builds a full topology snapshot of the cluster — nodes, pods, services, ingresses, storage — and caches it per session.",
        "icon": "device_hub",
        "level": 3,
        "llm_config": {"model": "none", "temperature": 0.0, "context_window": 0, "mode": "deterministic"},
        "timeout_s": 30,
        "tools": ["k8s_lister", "list_nodes", "list_pods", "list_events"],
        "tool_health_checks": {"k8s_api": "check_k8s_connectivity"},
        "architecture_stages": ["Platform Detect", "Resource Fetch", "Graph Build", "Scope Prune"],
    },
    {
        "id": "alert_correlator",
        "name": "ALERT_CORRELATOR",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Groups alerts by topology connectivity, merging related signals into correlated issue clusters.",
        "icon": "notifications_active",
        "level": 3,
        "llm_config": {"model": "none", "temperature": 0.0, "context_window": 0, "mode": "deterministic"},
        "timeout_s": 15,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Alert Extract", "Topology Walk", "Cluster Group", "Priority Rank"],
    },
    {
        "id": "causal_firewall",
        "name": "CAUSAL_FIREWALL",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Two-tier causal link filtering — hard rules (temporal, structural) then soft rules (heuristic) — to prevent spurious correlations.",
        "icon": "security",
        "level": 3,
        "llm_config": {"model": "none", "temperature": 0.0, "context_window": 0, "mode": "deterministic"},
        "timeout_s": 10,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Hard Rules", "Soft Rules", "Link Filter", "Graph Prune"],
    },
    {
        "id": "dispatch_router",
        "name": "DISPATCH_ROUTER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Determines which domain agents to dispatch based on diagnostic scope, filtering out irrelevant domains.",
        "icon": "route",
        "level": 2,
        "llm_config": {"model": "none", "temperature": 0.0, "context_window": 0, "mode": "deterministic"},
        "timeout_s": 5,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Scope Read", "Domain Filter", "Coverage Calc", "Dispatch Plan"],
    },
    {
        "id": "synthesizer",
        "name": "SYNTHESIZER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Three-stage synthesis pipeline: merges domain reports, computes data completeness, and decides on re-dispatch if confidence is low.",
        "icon": "merge_type",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Report Merge", "Completeness Check", "Confidence Score", "Re-Dispatch Decision"],
    },
    {
        "id": "guard_formatter",
        "name": "GUARD_FORMATTER",
        "workflow": "cluster_diagnostics",
        "role": "orchestrator",
        "description": "Formats diagnostic results for Guard Mode — three-layer health scan with RAG/AMBER/GREEN severity scoring.",
        "icon": "shield",
        "level": 2,
        "llm_config": {"model": "none", "temperature": 0.0, "context_window": 0, "mode": "deterministic"},
        "timeout_s": 15,
        "tools": [],
        "tool_health_checks": {},
        "architecture_stages": ["Result Read", "Severity Score", "Layer Format", "Output Build"],
    },

    # — Domain Experts —
    {
        "id": "ctrl_plane_agent",
        "name": "CTRL_PLANE_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes control plane health — degraded operators, API server latency, etcd sync, certificate expiry, and leader election.",
        "icon": "memory",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 30,
        "tools": ["k8s_lister", "list_events", "get_cluster_operators"],
        "tool_health_checks": {"k8s_api": "check_k8s_connectivity"},
        "architecture_stages": ["Operator Scan", "API Health", "etcd Check", "LLM Analysis"],
    },
    {
        "id": "node_agent",
        "name": "NODE_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes node conditions, resource utilization, pod evictions, and scheduling failures.",
        "icon": "dns",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 45,
        "tools": ["k8s_lister", "prometheus_query", "list_events", "list_pods"],
        "tool_health_checks": {"k8s_api": "check_k8s_connectivity", "prometheus": "check_prometheus_connectivity"},
        "architecture_stages": ["Topology Read", "Event Fetch", "LLM Analysis", "Report Build"],
    },
    {
        "id": "network_agent",
        "name": "NETWORK_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes DNS failures, ingress controller health, network policies, service mesh connectivity, and CoreDNS status.",
        "icon": "lan",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 45,
        "tools": ["k8s_lister", "prometheus_query", "list_events"],
        "tool_health_checks": {"k8s_api": "check_k8s_connectivity", "prometheus": "check_prometheus_connectivity"},
        "architecture_stages": ["DNS Check", "Ingress Scan", "Policy Audit", "LLM Analysis"],
    },
    {
        "id": "storage_agent",
        "name": "STORAGE_AGENT",
        "workflow": "cluster_diagnostics",
        "role": "domain_expert",
        "description": "Analyzes storage and persistence — PVC binding, StorageClass provisioning, volume mount failures, and disk pressure.",
        "icon": "storage",
        "level": 4,
        "llm_config": {"model": "claude-sonnet-4-20250514", "temperature": 0.1, "context_window": 128000, "mode": "autonomous"},
        "timeout_s": 60,
        "tools": ["k8s_lister", "list_pvcs", "list_events"],
        "tool_health_checks": {"k8s_api": "check_k8s_connectivity"},
        "architecture_stages": ["PVC Scan", "SC Check", "Mount Verify", "LLM Analysis"],
    },
]

# Quick lookup by agent ID
AGENT_REGISTRY_MAP: dict[str, dict] = {a["id"]: a for a in AGENT_REGISTRY}


def get_agent_status(agent: dict, health_results: dict[str, bool]) -> tuple[str, list[str]]:
    """
    Determine agent status from health probe results.

    Returns (status, degraded_tools) where:
    - "active" — all tool deps reachable
    - "degraded" — agent functional but some tools failing
    - "offline" — critical dependency missing (agent has >=1 tool_health_check and ALL fail)
    """
    checks = agent.get("tool_health_checks", {})
    if not checks:
        return "active", []

    degraded: list[str] = []
    for tool_key in checks:
        if not health_results.get(tool_key, False):
            degraded.append(tool_key)

    if not degraded:
        return "active", []

    # If ALL tool deps are down, agent is offline
    if len(degraded) == len(checks):
        return "offline", degraded

    return "degraded", degraded
```

2. **`test_agent_registry.py`** — Tests for registry structure and health logic:

```python
"""Tests for agent_registry: structure validation, health probes, status logic."""
import asyncio
import pytest
from src.api.agent_registry import (
    AGENT_REGISTRY,
    AGENT_REGISTRY_MAP,
    get_agent_status,
    run_all_health_probes,
    clear_health_cache,
    _health_cache,
    _CACHE_TTL,
)


class TestRegistryStructure:
    """Validate AGENT_REGISTRY has correct shape and completeness."""

    def test_registry_has_25_agents(self):
        assert len(AGENT_REGISTRY) == 25

    def test_all_agents_have_required_fields(self):
        required = {"id", "name", "workflow", "role", "description", "icon", "level",
                     "llm_config", "timeout_s", "tools", "tool_health_checks", "architecture_stages"}
        for agent in AGENT_REGISTRY:
            missing = required - set(agent.keys())
            assert not missing, f"Agent {agent.get('id', '?')} missing: {missing}"

    def test_agent_ids_are_unique(self):
        ids = [a["id"] for a in AGENT_REGISTRY]
        assert len(ids) == len(set(ids))

    def test_agent_names_are_uppercase(self):
        for agent in AGENT_REGISTRY:
            assert agent["name"] == agent["name"].upper(), f"{agent['id']} name not uppercase"

    def test_workflows_are_valid(self):
        valid = {"app_diagnostics", "cluster_diagnostics"}
        for agent in AGENT_REGISTRY:
            assert agent["workflow"] in valid, f"{agent['id']} has invalid workflow"

    def test_app_diagnostics_has_15_agents(self):
        count = sum(1 for a in AGENT_REGISTRY if a["workflow"] == "app_diagnostics")
        assert count == 15

    def test_cluster_diagnostics_has_10_agents(self):
        count = sum(1 for a in AGENT_REGISTRY if a["workflow"] == "cluster_diagnostics")
        assert count == 10

    def test_roles_are_valid(self):
        valid = {"orchestrator", "analysis", "validation", "fix_generation", "domain_expert"}
        for agent in AGENT_REGISTRY:
            assert agent["role"] in valid, f"{agent['id']} has invalid role: {agent['role']}"

    def test_levels_are_1_to_5(self):
        for agent in AGENT_REGISTRY:
            assert 1 <= agent["level"] <= 5, f"{agent['id']} level out of range"

    def test_registry_map_matches_list(self):
        assert len(AGENT_REGISTRY_MAP) == len(AGENT_REGISTRY)
        for agent in AGENT_REGISTRY:
            assert AGENT_REGISTRY_MAP[agent["id"]] is agent

    def test_architecture_stages_non_empty(self):
        for agent in AGENT_REGISTRY:
            assert len(agent["architecture_stages"]) >= 2, f"{agent['id']} needs >=2 stages"

    def test_llm_config_has_required_keys(self):
        required = {"model", "temperature", "context_window", "mode"}
        for agent in AGENT_REGISTRY:
            missing = required - set(agent["llm_config"].keys())
            assert not missing, f"{agent['id']} llm_config missing: {missing}"


class TestAgentStatus:
    """Test get_agent_status logic."""

    def test_no_health_checks_means_active(self):
        agent = {"tool_health_checks": {}}
        status, degraded = get_agent_status(agent, {})
        assert status == "active"
        assert degraded == []

    def test_all_healthy_means_active(self):
        agent = {"tool_health_checks": {"k8s_api": "check_k8s", "prometheus": "check_prom"}}
        health = {"k8s_api": True, "prometheus": True}
        status, degraded = get_agent_status(agent, health)
        assert status == "active"
        assert degraded == []

    def test_partial_failure_means_degraded(self):
        agent = {"tool_health_checks": {"k8s_api": "check_k8s", "prometheus": "check_prom"}}
        health = {"k8s_api": True, "prometheus": False}
        status, degraded = get_agent_status(agent, health)
        assert status == "degraded"
        assert "prometheus" in degraded

    def test_all_failed_means_offline(self):
        agent = {"tool_health_checks": {"k8s_api": "check_k8s", "prometheus": "check_prom"}}
        health = {"k8s_api": False, "prometheus": False}
        status, degraded = get_agent_status(agent, health)
        assert status == "offline"
        assert len(degraded) == 2

    def test_single_check_failed_means_offline(self):
        agent = {"tool_health_checks": {"k8s_api": "check_k8s"}}
        health = {"k8s_api": False}
        status, degraded = get_agent_status(agent, health)
        assert status == "offline"

    def test_missing_health_key_treated_as_false(self):
        agent = {"tool_health_checks": {"k8s_api": "check_k8s"}}
        health = {}  # k8s_api not in results
        status, degraded = get_agent_status(agent, health)
        assert status == "offline"


class TestHealthCache:
    """Test cache behavior."""

    def setup_method(self):
        clear_health_cache()

    def test_clear_health_cache(self):
        _health_cache["test"] = (0, True)
        clear_health_cache()
        assert len(_health_cache) == 0

    def test_cache_ttl_is_30_seconds(self):
        assert _CACHE_TTL == 30.0
```

---

## Task 2: Backend API Endpoints

**Files:**
- Create: `backend/src/api/agent_endpoints.py`
- Modify: `backend/src/api/main.py` (add 1 import + 1 line to include router)
- Create: `backend/tests/test_agent_endpoints.py`

**What this task does:** Create `GET /api/v4/agents` and `GET /api/v4/agents/{id}/executions` endpoints. Wire them into the FastAPI app.

**Context:**
- Follow existing router pattern: `backend/src/api/routes_v4.py` uses `router_v4 = APIRouter(prefix="/api/v4")`.
- Session store is `sessions: Dict[str, Dict]` at `routes_v4.py:115`. We need to import it to find recent executions per agent.
- Health probes run on each `GET /api/v4/agents` call (cached 30s).
- The executions endpoint reads from the in-memory session store to find the last 5 sessions where a given agent participated. Session events are stored in `emitter` objects; use `task_events` or the session's `state` to extract agent participation.

**Changes:**

1. **`agent_endpoints.py`** — API endpoints:

```python
"""Agent Matrix API: workforce directory + execution history."""
from fastapi import APIRouter, HTTPException
from .agent_registry import (
    AGENT_REGISTRY,
    AGENT_REGISTRY_MAP,
    run_all_health_probes,
    get_agent_status,
)
from .routes_v4 import sessions

agent_router = APIRouter(prefix="/api/v4", tags=["agent-matrix"])


@agent_router.get("/agents")
async def list_agents():
    """Return all agents with live health status."""
    health = await run_all_health_probes()

    agents_out = []
    summary = {"total": len(AGENT_REGISTRY), "active": 0, "degraded": 0, "offline": 0}

    for agent in AGENT_REGISTRY:
        status, degraded_tools = get_agent_status(agent, health)
        summary[status] += 1

        # Find up to 3 recent executions from session store
        recent = _find_recent_executions(agent["id"], limit=3)

        agents_out.append({
            **agent,
            "status": status,
            "degraded_tools": degraded_tools,
            "recent_executions": recent,
        })

    return {"agents": agents_out, "summary": summary}


@agent_router.get("/agents/{agent_id}/executions")
async def get_agent_executions(agent_id: str):
    """Return last 5 sessions where this agent participated, with traces."""
    if agent_id not in AGENT_REGISTRY_MAP:
        raise HTTPException(404, f"Agent '{agent_id}' not found")

    executions = _find_recent_executions(agent_id, limit=5, include_trace=True)
    return {"agent_id": agent_id, "executions": executions}


def _find_recent_executions(
    agent_id: str, limit: int = 5, include_trace: bool = False
) -> list[dict]:
    """
    Scan the in-memory session store for sessions where this agent ran.

    For cluster agents: check domain_reports in state.
    For app agents: check agents_completed or task events.
    """
    results = []

    # Sort sessions by created_at descending
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda kv: kv[1].get("created_at", ""),
        reverse=True,
    )

    for session_id, session in sorted_sessions:
        if len(results) >= limit:
            break

        state = session.get("state")
        if not isinstance(state, dict):
            continue

        # Check cluster diagnostic sessions
        if session.get("capability") == "cluster_diagnostics":
            domain_reports = state.get("domain_reports", [])
            for report in domain_reports:
                if not isinstance(report, dict):
                    continue
                # Match domain name to agent_id
                domain = report.get("domain", "")
                mapped_agent = f"{domain}_agent" if domain else ""
                if mapped_agent == agent_id or agent_id in (
                    "topology_resolver", "alert_correlator", "causal_firewall",
                    "dispatch_router", "synthesizer", "guard_formatter",
                ):
                    entry = {
                        "session_id": session_id,
                        "timestamp": session.get("created_at", ""),
                        "status": report.get("status", "SUCCESS"),
                        "duration_ms": report.get("duration_ms", 0),
                        "confidence": report.get("confidence", 0),
                        "summary": report.get("summary", f"Cluster diagnostic session"),
                    }
                    if include_trace:
                        # Extract trace from emitter events if available
                        entry["trace"] = _extract_trace(session, agent_id)
                    results.append(entry)
                    break  # One entry per session

            # For orchestrator agents, always add if it was a cluster session
            if agent_id in ("topology_resolver", "alert_correlator", "causal_firewall",
                           "dispatch_router", "synthesizer", "guard_formatter"):
                if not any(r["session_id"] == session_id for r in results):
                    entry = {
                        "session_id": session_id,
                        "timestamp": session.get("created_at", ""),
                        "status": state.get("phase", "complete").upper() if state.get("phase") != "error" else "FAILED",
                        "duration_ms": 0,
                        "confidence": int(state.get("data_completeness", 0) * 100),
                        "summary": f"Cluster diagnostic: {session.get('service_name', 'unknown')}",
                    }
                    if include_trace:
                        entry["trace"] = _extract_trace(session, agent_id)
                    results.append(entry)
        else:
            # App diagnostic sessions: check agents_completed list
            agents_completed = state.get("agents_completed", [])
            # Map agent_id to the agent name used in the pipeline
            agent_name_map = {
                "log_analysis_agent": "log_agent",
                "metrics_agent": "metrics_agent",
                "k8s_agent": "k8s_agent",
                "change_agent": "change_agent",
                "code_navigator_agent": "code_agent",
                "supervisor_agent": "supervisor",
                "critic_agent": "critic",
            }
            pipeline_name = agent_name_map.get(agent_id, agent_id)

            if pipeline_name in agents_completed or agent_id in ("supervisor_agent", "critic_agent", "evidence_graph_builder"):
                entry = {
                    "session_id": session_id,
                    "timestamp": session.get("created_at", ""),
                    "status": "SUCCESS" if session.get("phase") not in ("error",) else "FAILED",
                    "duration_ms": 0,
                    "confidence": session.get("confidence", 0),
                    "summary": f"App diagnostic: {session.get('service_name', 'unknown')}",
                }
                if include_trace:
                    entry["trace"] = _extract_trace(session, agent_id)
                results.append(entry)

    return results


def _extract_trace(session: dict, agent_id: str) -> list[dict]:
    """Extract execution trace events for an agent from session emitter."""
    emitter = session.get("emitter")
    if not emitter:
        return []

    events = getattr(emitter, "events", [])
    trace = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("agent_name", "") == agent_id or agent_id.replace("_agent", "") in event.get("agent_name", ""):
            trace.append({
                "timestamp": event.get("timestamp", ""),
                "level": "warn" if event.get("event_type") in ("warning", "error") else "info",
                "message": event.get("message", ""),
            })
    return trace[-20:]  # Last 20 trace entries
```

2. **`main.py`** — Add router import and registration (2 lines):

Add import at line ~19 (after other router imports):
```python
from .agent_endpoints import agent_router
```

Add registration at line ~93 (after other `include_router` calls):
```python
app.include_router(agent_router)
```

3. **`test_agent_endpoints.py`** — Endpoint tests:

```python
"""Tests for agent matrix API endpoints."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_health_probes():
    """Mock all health probes to return healthy by default."""
    with patch("src.api.agent_registry.check_k8s_connectivity", new_callable=AsyncMock, return_value=True), \
         patch("src.api.agent_registry.check_prometheus_connectivity", new_callable=AsyncMock, return_value=True), \
         patch("src.api.agent_registry.check_elasticsearch_connectivity", new_callable=AsyncMock, return_value=True), \
         patch("src.api.agent_registry.check_github_connectivity", new_callable=AsyncMock, return_value=True):
        yield


class TestListAgents:
    def test_returns_all_25_agents(self, client):
        resp = client.get("/api/v4/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 25

    def test_returns_summary_counts(self, client):
        resp = client.get("/api/v4/agents")
        data = resp.json()
        summary = data["summary"]
        assert summary["total"] == 25
        assert summary["active"] + summary["degraded"] + summary["offline"] == 25

    def test_agents_have_status_field(self, client):
        resp = client.get("/api/v4/agents")
        for agent in resp.json()["agents"]:
            assert agent["status"] in ("active", "degraded", "offline")

    def test_agents_have_degraded_tools_list(self, client):
        resp = client.get("/api/v4/agents")
        for agent in resp.json()["agents"]:
            assert isinstance(agent["degraded_tools"], list)

    def test_agents_have_recent_executions(self, client):
        resp = client.get("/api/v4/agents")
        for agent in resp.json()["agents"]:
            assert isinstance(agent["recent_executions"], list)


class TestGetAgentExecutions:
    def test_valid_agent_returns_200(self, client):
        resp = client.get("/api/v4/agents/node_agent/executions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "node_agent"
        assert isinstance(data["executions"], list)

    def test_invalid_agent_returns_404(self, client):
        resp = client.get("/api/v4/agents/nonexistent/executions")
        assert resp.status_code == 404
```

---

## Task 3: Frontend Types + API Service + Routing

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/App.tsx` (ViewState type + view rendering + sidebar logic)
- Modify: `frontend/src/components/Layout/SidebarNav.tsx` (NavView type + nav item)

**What this task does:** Add TypeScript types for the Agent Matrix, API service functions, routing infrastructure, and navigation. No visual components yet — just wiring.

**Context:**
- `ViewState` type at `App.tsx:36`: `'home' | 'form' | 'investigation' | ... | 'cluster-diagnostics'`
- `NavView` type at `SidebarNav.tsx:3`: `'home' | 'sessions' | 'integrations' | 'settings'`
- Sidebar nav items array at `SidebarNav.tsx:11-16`
- `showSidebar` logic at `App.tsx:348`
- API functions in `frontend/src/services/api.ts` follow `async function → fetch → return json` pattern
- All types in `frontend/src/types/index.ts`

**Changes:**

1. **`types/index.ts`** — Add Agent Matrix types (append after existing types, around line 528+):

```typescript
// ===== Agent Matrix Types =====

export interface AgentLLMConfig {
  model: string;
  temperature: number;
  context_window: number;
  mode: string;
}

export interface AgentExecution {
  session_id: string;
  timestamp: string;
  status: string;
  duration_ms: number;
  confidence: number;
  summary: string;
  trace?: AgentTraceEntry[];
}

export interface AgentTraceEntry {
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  message: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  workflow: 'app_diagnostics' | 'cluster_diagnostics';
  role: 'orchestrator' | 'analysis' | 'validation' | 'fix_generation' | 'domain_expert';
  description: string;
  icon: string;
  level: number;
  llm_config: AgentLLMConfig;
  timeout_s: number;
  tools: string[];
  tool_health_checks: Record<string, string>;
  architecture_stages: string[];
  status: 'active' | 'degraded' | 'offline';
  degraded_tools: string[];
  recent_executions: AgentExecution[];
}

export interface AgentMatrixSummary {
  total: number;
  active: number;
  degraded: number;
  offline: number;
}

export interface AgentMatrixResponse {
  agents: AgentInfo[];
  summary: AgentMatrixSummary;
}

export interface AgentExecutionsResponse {
  agent_id: string;
  executions: AgentExecution[];
}
```

2. **`api.ts`** — Add API functions (append after existing exports):

```typescript
// ===== Agent Matrix API =====

export const getAgents = async (): Promise<AgentMatrixResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/agents`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to fetch agents'));
  }
  return response.json();
};

export const getAgentExecutions = async (agentId: string): Promise<AgentExecutionsResponse> => {
  const response = await fetch(`${API_BASE_URL}/api/v4/agents/${agentId}/executions`);
  if (!response.ok) {
    throw new Error(await extractErrorDetail(response, 'Failed to fetch agent executions'));
  }
  return response.json();
};
```

Also add `AgentMatrixResponse, AgentExecutionsResponse` to the imports from `'../types'` at the top of `api.ts`.

3. **`App.tsx`** — Add agent-matrix view state and rendering:

Change `ViewState` type (line 36):
```typescript
type ViewState = 'home' | 'form' | 'investigation' | 'sessions' | 'integrations' | 'settings' | 'dossier' | 'cluster-diagnostics' | 'agent-matrix';
```

Add import for AgentMatrixView (after other component imports, ~line 33):
```typescript
import AgentMatrixView from './components/AgentMatrix/AgentMatrixView';
```

Update `showSidebar` (line 348) to hide sidebar for agent-matrix:
```typescript
const showSidebar = viewState !== 'investigation' && viewState !== 'dossier' && viewState !== 'cluster-diagnostics' && viewState !== 'agent-matrix';
```

Add `navView` mapping (line 345-346) — add agents case:
```typescript
const navView: NavView =
  viewState === 'sessions' ? 'sessions' : viewState === 'integrations' ? 'integrations' : viewState === 'settings' ? 'settings' : viewState === 'agent-matrix' ? 'agents' : 'home';
```

Add view rendering block after the cluster-diagnostics block (~line 468):
```typescript
{viewState === 'agent-matrix' && (
  <AgentMatrixView onGoHome={handleGoHome} />
)}
```

4. **`SidebarNav.tsx`** — Add agents nav item:

Update `NavView` type (line 3):
```typescript
export type NavView = 'home' | 'sessions' | 'integrations' | 'settings' | 'agents';
```

Add nav item to array (after settings, line 15):
```typescript
{ id: 'agents' as NavView, label: 'Agent Matrix', icon: 'smart_toy' },
```

**Verification:** `npx tsc --noEmit` should pass (AgentMatrixView will be a placeholder stub for now — create a minimal one in the next task).

---

## Task 4: Agent Grid Page (AgentMatrixView + Header + Tabs + Cards + Footer)

**Files:**
- Create: `frontend/src/components/AgentMatrix/AgentMatrixView.tsx`
- Create: `frontend/src/components/AgentMatrix/AgentMatrixHeader.tsx`
- Create: `frontend/src/components/AgentMatrix/WorkflowTabs.tsx`
- Create: `frontend/src/components/AgentMatrix/AgentGrid.tsx`
- Create: `frontend/src/components/AgentMatrix/AgentCard.tsx`
- Create: `frontend/src/components/AgentMatrix/AgentMatrixFooter.tsx`

**What this task does:** Build the full agent grid page — the main view users see when clicking "Agent Matrix" in the sidebar. Includes the HUD header, workflow tabs, role-grouped cards, and footer. Clicking a card will be wired to the detail view in the next task.

**Context:**
- Design system: Dark bg `#0a1214` for cards, border `border-duck-border` (#224349), hover cyan transition, monospace font for agent names.
- Status dot colors: active=cyan (#07b6d5), degraded=amber (#f59e0b) with pulse, offline=red (#ef4444).
- Tool pills: `bg-duck-cyan/10 text-duck-cyan border-duck-cyan/20` pattern from design doc.
- Role groups: orchestrator, analysis, validation, fix_generation, domain_expert.
- Tabs: "App Diagnostics" and "Cluster Diagnostics" — filter already-loaded agents by workflow.
- Material Symbols icon font is already loaded (`material-symbols-outlined` class).
- Tailwind custom colors: `duck-bg`, `duck-card`, `duck-border`, `duck-accent`, `duck-surface`, `primary`.
- API call: `getAgents()` from `services/api.ts` on mount.

**Changes:**

1. **`AgentMatrixView.tsx`** — Main container with data fetching:

```tsx
import React, { useState, useEffect, useCallback } from 'react';
import type { AgentInfo, AgentMatrixSummary } from '../../types';
import { getAgents } from '../../services/api';
import AgentMatrixHeader from './AgentMatrixHeader';
import WorkflowTabs from './WorkflowTabs';
import AgentGrid from './AgentGrid';
import AgentMatrixFooter from './AgentMatrixFooter';
import AgentDetailView from './AgentDetailView';

interface AgentMatrixViewProps {
  onGoHome: () => void;
}

const AgentMatrixView: React.FC<AgentMatrixViewProps> = ({ onGoHome }) => {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [summary, setSummary] = useState<AgentMatrixSummary>({ total: 0, active: 0, degraded: 0, offline: 0 });
  const [activeTab, setActiveTab] = useState<'app_diagnostics' | 'cluster_diagnostics'>('app_diagnostics');
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getAgents();
      setAgents(data.agents);
      setSummary(data.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const filteredAgents = agents.filter(a => a.workflow === activeTab);

  if (selectedAgent) {
    return (
      <AgentDetailView
        agent={selectedAgent}
        onBack={() => setSelectedAgent(null)}
      />
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      <AgentMatrixHeader summary={summary} onGoHome={onGoHome} />

      <div className="flex items-center justify-between px-6 py-3 border-b" style={{ borderColor: '#224349' }}>
        <WorkflowTabs activeTab={activeTab} onTabChange={setActiveTab} />
        <div className="flex items-center gap-2 text-xs font-mono" style={{ color: '#07b6d5' }}>
          <span>{summary.total} AGENTS</span>
          <span className="opacity-40">|</span>
          <span>{summary.active} UP</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && (
          <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
            <span className="material-symbols-outlined animate-spin mr-2" style={{ fontFamily: 'Material Symbols Outlined' }}>progress_activity</span>
            Probing agent health...
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <p className="text-red-400 text-sm">{error}</p>
            <button onClick={fetchAgents} className="text-xs px-3 py-1.5 rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors">
              Retry
            </button>
          </div>
        )}

        {!loading && !error && <AgentGrid agents={filteredAgents} onSelectAgent={setSelectedAgent} />}
      </div>

      <AgentMatrixFooter summary={summary} />
    </div>
  );
};

export default AgentMatrixView;
```

2. **`AgentMatrixHeader.tsx`**:

```tsx
import React from 'react';
import type { AgentMatrixSummary } from '../../types';

interface Props {
  summary: AgentMatrixSummary;
  onGoHome: () => void;
}

const AgentMatrixHeader: React.FC<Props> = ({ onGoHome }) => {
  return (
    <div className="px-6 pt-5 pb-3 border-b" style={{ borderColor: '#224349' }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={onGoHome}
            className="flex items-center gap-1.5 text-slate-400 hover:text-white transition-colors text-sm"
          >
            <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
            Home
          </button>
          <div>
            <h1 className="text-white text-xl font-bold tracking-tight flex items-center gap-2">
              <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>smart_toy</span>
              NEURAL DIRECTORY HUD
            </h1>
            <p className="text-[10px] font-mono uppercase tracking-[0.3em] mt-0.5" style={{ color: 'rgba(7,182,213,0.6)' }}>
              /// LIVE WORKFORCE MATRIX /// AUTONOMOUS DIAGNOSTICS ///
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AgentMatrixHeader;
```

3. **`WorkflowTabs.tsx`**:

```tsx
import React from 'react';

interface Props {
  activeTab: 'app_diagnostics' | 'cluster_diagnostics';
  onTabChange: (tab: 'app_diagnostics' | 'cluster_diagnostics') => void;
}

const tabs = [
  { id: 'app_diagnostics' as const, label: 'App Diagnostics', icon: 'bug_report' },
  { id: 'cluster_diagnostics' as const, label: 'Cluster Diagnostics', icon: 'cloud' },
];

const WorkflowTabs: React.FC<Props> = ({ activeTab, onTabChange }) => {
  return (
    <div className="flex gap-1">
      {tabs.map(tab => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all border ${
              isActive
                ? 'text-[#07b6d5] border-[rgba(7,182,213,0.3)]'
                : 'text-slate-400 border-transparent hover:text-white hover:border-slate-700'
            }`}
            style={isActive ? { backgroundColor: 'rgba(7,182,213,0.1)' } : {}}
          >
            <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined' }}>{tab.icon}</span>
            {tab.label}
          </button>
        );
      })}
    </div>
  );
};

export default WorkflowTabs;
```

4. **`AgentGrid.tsx`** — Groups agents by role and renders cards:

```tsx
import React from 'react';
import type { AgentInfo } from '../../types';
import AgentCard from './AgentCard';

interface Props {
  agents: AgentInfo[];
  onSelectAgent: (agent: AgentInfo) => void;
}

const ROLE_ORDER = ['orchestrator', 'analysis', 'domain_expert', 'validation', 'fix_generation'] as const;

const ROLE_LABELS: Record<string, string> = {
  orchestrator: 'ORCHESTRATORS',
  analysis: 'ANALYSIS AGENTS',
  domain_expert: 'DOMAIN EXPERTS',
  validation: 'VALIDATION',
  fix_generation: 'FIX GENERATION',
};

const AgentGrid: React.FC<Props> = ({ agents, onSelectAgent }) => {
  const grouped = ROLE_ORDER
    .map(role => ({
      role,
      label: ROLE_LABELS[role],
      agents: agents.filter(a => a.role === role),
    }))
    .filter(g => g.agents.length > 0);

  return (
    <div className="space-y-6">
      {grouped.map(group => (
        <div key={group.role}>
          <div className="flex items-center gap-3 mb-3">
            <span className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-slate-500">
              ── {group.label} ──
            </span>
            <div className="flex-1 h-px" style={{ backgroundColor: '#224349' }} />
            <span className="text-[10px] font-mono text-slate-600">{group.agents.length}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {group.agents.map(agent => (
              <AgentCard key={agent.id} agent={agent} onClick={() => onSelectAgent(agent)} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default AgentGrid;
```

5. **`AgentCard.tsx`** — Individual agent card matching wireframe:

```tsx
import React from 'react';
import type { AgentInfo } from '../../types';

interface Props {
  agent: AgentInfo;
  onClick: () => void;
}

const STATUS_STYLES: Record<string, { color: string; glow: string; label: string }> = {
  active: { color: '#07b6d5', glow: '0 0 6px rgba(7,182,213,0.4)', label: 'ACTIVE' },
  degraded: { color: '#f59e0b', glow: '0 0 6px rgba(245,158,11,0.4)', label: 'DEGRADED' },
  offline: { color: '#ef4444', glow: '0 0 6px rgba(239,68,68,0.4)', label: 'OFFLINE' },
};

const ROLE_LABELS: Record<string, string> = {
  orchestrator: 'Orchestrator',
  analysis: 'Analysis',
  domain_expert: 'Domain Expert',
  validation: 'Validation',
  fix_generation: 'Fix Generation',
};

const AgentCard: React.FC<Props> = ({ agent, onClick }) => {
  const statusStyle = STATUS_STYLES[agent.status] || STATUS_STYLES.active;

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-4 rounded-lg border transition-all duration-200 hover:border-[#07b6d5]/50 group cursor-pointer"
      style={{
        backgroundColor: '#0a1214',
        borderColor: '#224349',
      }}
    >
      {/* Header: icon + name + status */}
      <div className="flex items-start justify-between mb-1">
        <div className="flex items-center gap-2.5">
          <span
            className="material-symbols-outlined text-xl"
            style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}
          >
            {agent.icon}
          </span>
          <div>
            <span className="font-mono text-sm font-bold text-white tracking-wide">
              {agent.name}
            </span>
            <p className="text-[10px] uppercase tracking-[0.15em] text-slate-500 mt-0.5">
              {ROLE_LABELS[agent.role] || agent.role}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] font-mono" style={{ color: statusStyle.color }}>
            {statusStyle.label}
          </span>
          <div
            className={`w-2 h-2 rounded-full ${agent.status === 'degraded' ? 'animate-pulse' : ''}`}
            style={{ backgroundColor: statusStyle.color, boxShadow: statusStyle.glow }}
          />
        </div>
      </div>

      {/* Description */}
      <p className="text-xs text-slate-400 mt-2 leading-relaxed line-clamp-2">
        {agent.description}
      </p>

      {/* Equipped Tools */}
      {agent.tools.length > 0 && (
        <div className="mt-3">
          <p className="text-[9px] font-mono uppercase tracking-[0.15em] text-slate-600 mb-1.5">
            ─── EQUIPPED TOOLS ───
          </p>
          <div className="flex flex-wrap gap-1">
            {agent.tools.map(tool => (
              <span
                key={tool}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded border"
                style={{
                  backgroundColor: 'rgba(7,182,213,0.1)',
                  color: '#07b6d5',
                  borderColor: 'rgba(7,182,213,0.2)',
                }}
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Degraded tools warning */}
      {agent.degraded_tools.length > 0 && (
        <div className="mt-2 flex items-center gap-1 text-[10px] text-amber-400">
          <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>warning</span>
          {agent.degraded_tools.join(', ')} unreachable
        </div>
      )}
    </button>
  );
};

export default AgentCard;
```

6. **`AgentMatrixFooter.tsx`**:

```tsx
import React from 'react';
import type { AgentMatrixSummary } from '../../types';

interface Props {
  summary: AgentMatrixSummary;
}

const AgentMatrixFooter: React.FC<Props> = ({ summary }) => {
  const syncPct = summary.total > 0 ? Math.round((summary.active / summary.total) * 100) : 0;

  return (
    <div className="px-6 py-2.5 border-t flex items-center justify-center gap-4 text-[10px] font-mono" style={{ borderColor: '#224349', color: '#64748b' }}>
      <span>{summary.total} AGENTS</span>
      <span style={{ color: '#07b6d5' }}>{summary.active} ACTIVE</span>
      {summary.degraded > 0 && <span style={{ color: '#f59e0b' }}>{summary.degraded} DEGRADED</span>}
      {summary.offline > 0 && <span style={{ color: '#ef4444' }}>{summary.offline} OFFLINE</span>}
      <span className="opacity-40">|</span>
      <span>NEURAL SYNC {syncPct}%</span>
    </div>
  );
};

export default AgentMatrixFooter;
```

**Note:** Also create a stub `AgentDetailView.tsx` so TypeScript doesn't complain (it will be fully built in Task 5):

```tsx
import React from 'react';
import type { AgentInfo } from '../../types';

interface Props {
  agent: AgentInfo;
  onBack: () => void;
}

const AgentDetailView: React.FC<Props> = ({ agent, onBack }) => {
  return (
    <div className="flex flex-col h-full" style={{ backgroundColor: '#0f2023' }}>
      <div className="px-6 py-4 border-b" style={{ borderColor: '#224349' }}>
        <button onClick={onBack} className="text-slate-400 hover:text-white text-sm flex items-center gap-1">
          <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
          Back to Grid
        </button>
        <h2 className="text-white font-mono text-lg font-bold mt-2">{agent.name}</h2>
      </div>
      <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
        Detail view — implemented in next task
      </div>
    </div>
  );
};

export default AgentDetailView;
```

**Verification:** `npx tsc --noEmit` passes. Navigate to Agent Matrix in sidebar, grid renders.

---

## Task 5: Agent Detail View (Full Two-Column Layout)

**Files:**
- Replace: `frontend/src/components/AgentMatrix/AgentDetailView.tsx` (full implementation)
- Create: `frontend/src/components/AgentMatrix/NeuralArchitectureDiagram.tsx`
- Create: `frontend/src/components/AgentMatrix/CoreConfigPanel.tsx`
- Create: `frontend/src/components/AgentMatrix/ToolbeltPanel.tsx`
- Create: `frontend/src/components/AgentMatrix/ExecutionTracePanel.tsx`
- Create: `frontend/src/components/AgentMatrix/RecentCasesPanel.tsx`

**What this task does:** Build the complete agent detail view matching the design wireframe — two columns (40%/60%) with neural architecture diagram, config panel, toolbelt, execution trace, and recent cases.

**Context:**
- Left column (40%): Agent header → Neural Architecture → Core Config → Toolbelt
- Right column (60%): Execution Trace (last/live) → Recent Cases
- `getAgentExecutions(agentId)` from `services/api.ts` fetches execution history with traces
- No live WebSocket stream needed for MVP — just show last execution trace
- Architecture stages come from `agent.architecture_stages` array
- LLM config from `agent.llm_config`
- Tool health from `agent.degraded_tools`

**Changes:**

1. **`AgentDetailView.tsx`** — Full two-column layout:

```tsx
import React, { useState, useEffect } from 'react';
import type { AgentInfo, AgentExecution } from '../../types';
import { getAgentExecutions } from '../../services/api';
import NeuralArchitectureDiagram from './NeuralArchitectureDiagram';
import CoreConfigPanel from './CoreConfigPanel';
import ToolbeltPanel from './ToolbeltPanel';
import ExecutionTracePanel from './ExecutionTracePanel';
import RecentCasesPanel from './RecentCasesPanel';

interface Props {
  agent: AgentInfo;
  onBack: () => void;
}

const STATUS_STYLES: Record<string, { color: string; label: string }> = {
  active: { color: '#07b6d5', label: 'SYSTEM ACTIVE' },
  degraded: { color: '#f59e0b', label: 'DEGRADED' },
  offline: { color: '#ef4444', label: 'OFFLINE' },
};

const AgentDetailView: React.FC<Props> = ({ agent, onBack }) => {
  const [executions, setExecutions] = useState<AgentExecution[]>([]);
  const [loadingExec, setLoadingExec] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await getAgentExecutions(agent.id);
        if (!cancelled) setExecutions(data.executions);
      } catch {
        // Silently fail — empty executions
      } finally {
        if (!cancelled) setLoadingExec(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [agent.id]);

  const statusStyle = STATUS_STYLES[agent.status] || STATUS_STYLES.active;
  const lastExecution = executions[0] || null;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ backgroundColor: '#0f2023' }}>
      {/* Top bar */}
      <div className="px-6 py-4 border-b flex items-center justify-between" style={{ borderColor: '#224349' }}>
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="text-slate-400 hover:text-white text-sm flex items-center gap-1 transition-colors">
            <span className="material-symbols-outlined text-lg" style={{ fontFamily: 'Material Symbols Outlined' }}>arrow_back</span>
            Back to Grid
          </button>
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-2xl" style={{ fontFamily: 'Material Symbols Outlined', color: '#07b6d5' }}>{agent.icon}</span>
            <div>
              <h2 className="text-white font-mono text-lg font-bold tracking-wide">{agent.name}</h2>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded border" style={{ backgroundColor: 'rgba(7,182,213,0.1)', borderColor: 'rgba(7,182,213,0.2)', color: '#07b6d5' }}>
                  LVL {agent.level}
                </span>
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
                  {agent.role.replace('_', ' ')}
                </span>
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2.5 h-2.5 rounded-full ${agent.status === 'degraded' ? 'animate-pulse' : ''}`}
            style={{ backgroundColor: statusStyle.color, boxShadow: `0 0 8px ${statusStyle.color}40` }}
          />
          <span className="text-xs font-mono" style={{ color: statusStyle.color }}>{statusStyle.label}</span>
        </div>
      </div>

      {/* Two-column body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left column — 40% */}
        <div className="w-2/5 border-r overflow-y-auto p-5 space-y-5" style={{ borderColor: '#224349' }}>
          <NeuralArchitectureDiagram stages={agent.architecture_stages} />
          <CoreConfigPanel agent={agent} />
          <ToolbeltPanel agent={agent} />
        </div>

        {/* Right column — 60% */}
        <div className="w-3/5 overflow-y-auto p-5 space-y-5">
          <ExecutionTracePanel execution={lastExecution} loading={loadingExec} />
          <RecentCasesPanel executions={executions} loading={loadingExec} />
        </div>
      </div>
    </div>
  );
};

export default AgentDetailView;
```

2. **`NeuralArchitectureDiagram.tsx`** — Vertical flow of architecture stages:

```tsx
import React from 'react';

interface Props {
  stages: string[];
}

const NeuralArchitectureDiagram: React.FC<Props> = ({ stages }) => {
  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
      <h3 className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-slate-500 mb-3">
        ── NEURAL ARCHITECTURE ──
      </h3>
      <div className="flex flex-col items-center gap-0">
        {stages.map((stage, i) => (
          <React.Fragment key={i}>
            <div className="w-full px-3 py-2 rounded border text-center text-xs font-mono text-slate-200"
              style={{ backgroundColor: '#162a2e', borderColor: 'rgba(7,182,213,0.2)' }}>
              {stage}
            </div>
            {i < stages.length - 1 && (
              <div className="flex flex-col items-center py-1">
                <div className="w-px h-3" style={{ backgroundColor: 'rgba(7,182,213,0.3)' }} />
                <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined', color: 'rgba(7,182,213,0.4)' }}>arrow_downward</span>
                <div className="w-px h-1" style={{ backgroundColor: 'rgba(7,182,213,0.3)' }} />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

export default NeuralArchitectureDiagram;
```

3. **`CoreConfigPanel.tsx`**:

```tsx
import React from 'react';
import type { AgentInfo } from '../../types';

interface Props {
  agent: AgentInfo;
}

const CoreConfigPanel: React.FC<Props> = ({ agent }) => {
  const config = agent.llm_config;
  const rows = [
    { label: 'MODEL', value: config.model },
    { label: 'TEMPERATURE', value: String(config.temperature) },
    { label: 'CONTEXT', value: config.context_window > 0 ? `${(config.context_window / 1000).toFixed(0)}K tokens` : 'N/A' },
    { label: 'MODE', value: config.mode.toUpperCase() },
    { label: 'TIMEOUT', value: `${agent.timeout_s}s` },
  ];

  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
      <h3 className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-slate-500 mb-3">
        ── CORE CONFIGURATION ──
      </h3>
      <div className="space-y-2">
        {rows.map(row => (
          <div key={row.label} className="flex items-center justify-between">
            <span className="text-[10px] font-mono text-slate-500">{row.label}</span>
            <span className="text-xs font-mono text-slate-200">{row.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CoreConfigPanel;
```

4. **`ToolbeltPanel.tsx`**:

```tsx
import React from 'react';
import type { AgentInfo } from '../../types';

interface Props {
  agent: AgentInfo;
}

const ToolbeltPanel: React.FC<Props> = ({ agent }) => {
  const healthyCount = agent.tools.length - agent.degraded_tools.length;
  const degradedSet = new Set(agent.degraded_tools);

  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-slate-500">
          ── ACTIVE TOOLBELT ──
        </h3>
        <span className="text-[10px] font-mono" style={{ color: '#07b6d5' }}>
          {healthyCount}/{agent.tools.length}
        </span>
      </div>
      {agent.tools.length === 0 ? (
        <p className="text-xs text-slate-600 font-mono">No external tools — LLM-only agent</p>
      ) : (
        <div className="space-y-1.5">
          {agent.tools.map(tool => {
            const isHealthy = !degradedSet.has(tool);
            return (
              <div key={tool} className="flex items-center gap-2 px-2 py-1.5 rounded" style={{ backgroundColor: '#162a2e' }}>
                <div
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: isHealthy ? '#22c55e' : '#ef4444' }}
                />
                <span className="text-xs font-mono text-slate-300">{tool}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ToolbeltPanel;
```

5. **`ExecutionTracePanel.tsx`**:

```tsx
import React from 'react';
import type { AgentExecution } from '../../types';

interface Props {
  execution: AgentExecution | null;
  loading: boolean;
}

const LEVEL_COLORS: Record<string, string> = {
  info: '#07b6d5',
  warn: '#f59e0b',
  error: '#ef4444',
};

const ExecutionTracePanel: React.FC<Props> = ({ execution, loading }) => {
  return (
    <div className="rounded-lg border p-4 flex flex-col" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-slate-500">
          ── EXECUTION TRACE ──
        </h3>
        <span className="text-[9px] font-mono px-2 py-0.5 rounded" style={{ backgroundColor: 'rgba(7,182,213,0.1)', color: 'rgba(7,182,213,0.6)' }}>
          {execution ? 'LAST EXECUTION' : 'AWAITING DISPATCH'}
        </span>
      </div>

      <div className="font-mono text-xs min-h-[200px] max-h-[400px] overflow-y-auto rounded p-3" style={{ backgroundColor: '#060d0f' }}>
        {loading && <p className="text-slate-600">Loading trace...</p>}
        {!loading && !execution && (
          <p className="text-slate-600 text-center py-8">AWAITING DISPATCH — No execution trace available</p>
        )}
        {!loading && execution && (
          <>
            <div className="text-slate-500 mb-3 pb-2 border-b border-slate-800">
              Session: {execution.session_id} | {execution.status} | {execution.duration_ms}ms | Confidence: {execution.confidence}%
            </div>
            {execution.trace && execution.trace.length > 0 ? (
              execution.trace.map((entry, i) => (
                <div key={i} className="flex gap-2 py-0.5">
                  <span className="text-slate-600 flex-shrink-0">{entry.timestamp}</span>
                  <span style={{ color: LEVEL_COLORS[entry.level] || '#07b6d5' }} className="flex-shrink-0">
                    [{entry.level.toUpperCase()}]
                  </span>
                  <span className="text-slate-300">{entry.message}</span>
                </div>
              ))
            ) : (
              <p className="text-slate-600">{execution.summary}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ExecutionTracePanel;
```

6. **`RecentCasesPanel.tsx`**:

```tsx
import React from 'react';
import type { AgentExecution } from '../../types';

interface Props {
  executions: AgentExecution[];
  loading: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  SUCCESS: '#22c55e',
  PARTIAL: '#f59e0b',
  FAILED: '#ef4444',
  SKIPPED: '#64748b',
};

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

const RecentCasesPanel: React.FC<Props> = ({ executions, loading }) => {
  return (
    <div className="rounded-lg border p-4" style={{ backgroundColor: '#0a1214', borderColor: '#224349' }}>
      <h3 className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-slate-500 mb-3">
        ── RECENT CASES ──
      </h3>

      {loading && <p className="text-xs text-slate-600 font-mono">Loading...</p>}

      {!loading && executions.length === 0 && (
        <p className="text-xs text-slate-600 font-mono text-center py-4">No recent executions</p>
      )}

      {!loading && executions.length > 0 && (
        <div className="space-y-2">
          {executions.map((exec, i) => (
            <div key={i} className="flex items-center justify-between px-3 py-2 rounded" style={{ backgroundColor: '#162a2e' }}>
              <div className="flex items-center gap-3 min-w-0">
                <span
                  className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded flex-shrink-0"
                  style={{
                    color: STATUS_COLORS[exec.status] || '#64748b',
                    backgroundColor: `${STATUS_COLORS[exec.status] || '#64748b'}15`,
                  }}
                >
                  {exec.status}
                </span>
                <span className="text-xs text-slate-300 truncate">{exec.summary}</span>
              </div>
              <span className="text-[10px] font-mono text-slate-600 flex-shrink-0 ml-3">
                {timeAgo(exec.timestamp)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default RecentCasesPanel;
```

**Verification:** `npx tsc --noEmit` passes. Clicking an agent card opens the full detail view.

---

## Task 6: Backend Tests + Verification

**Files:**
- Verify: `backend/tests/test_agent_registry.py` (from Task 1)
- Verify: `backend/tests/test_agent_endpoints.py` (from Task 2)
- Verify: Frontend TypeScript compilation

**What this task does:** Run all backend tests, ensure no regressions, verify frontend compiles.

**Changes:**

1. Run backend tests:
```bash
cd backend && python3 -m pytest --tb=short -q
```
Expected: All tests pass (existing + new agent registry + endpoint tests).

2. Run frontend TypeScript check:
```bash
cd frontend && npx tsc --noEmit
```
Expected: 0 errors.

3. Verify API manually (if backend is running):
```bash
curl http://localhost:8000/api/v4/agents | python3 -m json.tool | head -50
curl http://localhost:8000/api/v4/agents/node_agent/executions | python3 -m json.tool
```

---

## Task 7: Final Integration + Commit

**What this task does:** Verify end-to-end integration, run all tests, commit all changes.

**Verification checklist:**
1. Backend: `python3 -m pytest --tb=short -q` — all tests pass
2. Frontend: `npx tsc --noEmit` — 0 errors
3. Navigate to Agent Matrix via sidebar → grid loads with 25 agents
4. Switch between App Diagnostics / Cluster Diagnostics tabs → agents filter correctly
5. Click an agent card → detail view opens with architecture diagram, config, tools
6. Back button returns to grid
7. Footer shows correct summary stats
8. Agents without tool health checks show "ACTIVE" status
