"""Integration tests for scope-governed diagnostics.

These tests exercise real code paths across multiple modules:
- dispatch_router (graph.py) — domain selection per scope
- _prune_topology (topology_resolver.py) — topology pruning
- _wrap_domain_agent (graph.py) — SKIP / RUN wrapping
- _should_redispatch (graph.py) — re-dispatch scope filtering
- _compute_data_completeness (synthesizer.py) — SKIPPED exclusion
- Route handler validation (routes_v4.py) — guard mode rejection

External dependencies (cluster client, LLM) are mocked; internal logic is real.
"""

from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, patch

from src.agents.cluster.state import (
    DiagnosticScope,
    DomainReport,
    DomainStatus,
    TopologySnapshot,
)
from src.agents.cluster.graph import (
    build_cluster_diagnostic_graph,
    dispatch_router,
    _wrap_domain_agent,
    _should_redispatch,
    ALL_DOMAINS,
)
from src.agents.cluster.topology_resolver import (
    _prune_topology,
    _topology_cache,
)
from src.agents.cluster.synthesizer import _compute_data_completeness
from src.agents.cluster_client.mock_client import MockClusterClient
from src.api.routes_v4 import sessions, get_findings


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear topology cache before/after each test."""
    _topology_cache.clear()
    yield
    _topology_cache.clear()


def _mock_llm_patches():
    """Return a dict of mock LLM patches for full-graph integration tests."""
    mock_analysis = {
        "anomalies": [
            {"domain": "test", "anomaly_id": "t-1",
             "description": "test issue", "evidence_ref": "ev-1"}
        ],
        "ruled_out": [],
        "confidence": 80,
    }
    mock_causal = {"causal_chains": [], "uncorrelated_findings": []}
    mock_verdict = {
        "platform_health": "HEALTHY",
        "blast_radius": {
            "summary": "No issues",
            "affected_namespaces": 0,
            "affected_pods": 0,
            "affected_nodes": 0,
        },
        "remediation": {"immediate": [], "long_term": []},
        "re_dispatch_needed": False,
    }
    return mock_analysis, mock_causal, mock_verdict


def _build_rich_topology() -> dict:
    """Build a multi-namespace topology for integration tests.

    Nodes:
        cluster-scoped: node/worker-1 (Node), sc/gp2 (StorageClass),
                        pv/pv-data (PersistentVolume), operator/dns (ClusterOperator)
        production:     deploy/prod/api (Deployment), pod/prod/api-pod (Pod),
                        svc/prod/api-svc (Service), pvc/prod/data (PVC)
        staging:        deploy/stg/web (Deployment), pod/stg/web-pod (Pod)
    """
    nodes = {
        "node/worker-1":       {"kind": "Node", "name": "worker-1", "namespace": None, "status": "Ready"},
        "sc/gp2":              {"kind": "StorageClass", "name": "gp2", "namespace": None},
        "pv/pv-data":          {"kind": "PersistentVolume", "name": "pv-data", "namespace": None},
        "operator/dns":        {"kind": "ClusterOperator", "name": "dns", "namespace": None, "status": "Available"},
        "deploy/prod/api":     {"kind": "Deployment", "name": "api", "namespace": "production"},
        "pod/prod/api-pod":    {"kind": "Pod", "name": "api-pod", "namespace": "production", "status": "Running"},
        "svc/prod/api-svc":    {"kind": "Service", "name": "api-svc", "namespace": "production"},
        "pvc/prod/data":       {"kind": "PersistentVolumeClaim", "name": "data", "namespace": "production"},
        "deploy/stg/web":      {"kind": "Deployment", "name": "web", "namespace": "staging"},
        "pod/stg/web-pod":     {"kind": "Pod", "name": "web-pod", "namespace": "staging", "status": "Running"},
    }
    edges = [
        {"from_key": "deploy/prod/api",   "to_key": "pod/prod/api-pod", "relation": "owns"},
        {"from_key": "svc/prod/api-svc",  "to_key": "pod/prod/api-pod", "relation": "routes_to"},
        {"from_key": "pvc/prod/data",     "to_key": "pv/pv-data",       "relation": "mounted_by"},
        {"from_key": "pv/pv-data",        "to_key": "sc/gp2",           "relation": "depends_on"},
        {"from_key": "node/worker-1",     "to_key": "pod/prod/api-pod", "relation": "hosts"},
        {"from_key": "node/worker-1",     "to_key": "pod/stg/web-pod",  "relation": "hosts"},
        {"from_key": "deploy/stg/web",    "to_key": "pod/stg/web-pod",  "relation": "owns"},
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "built_at": "2026-03-01T00:00:00Z",
        "stale": False,
        "resource_version": "12345",
    }


# ===========================================================================
# 1. test_full_cluster_runs_all_agents — no SKIPPED reports
# ===========================================================================


@pytest.mark.asyncio
async def test_full_cluster_runs_all_agents():
    """Full cluster scope: all 4 domain agents run (none SKIPPED).

    Integration across: dispatch_router -> _wrap_domain_agent -> synthesizer.
    """
    mock_analysis, mock_causal, mock_verdict = _mock_llm_patches()

    graph = build_cluster_diagnostic_graph()
    client = MockClusterClient(platform="openshift")
    emitter = AsyncMock()
    emitter.emit = AsyncMock()

    scope = DiagnosticScope(level="cluster")
    initial_state = {
        "diagnostic_id": "DIAG-FULL-CLUSTER",
        "platform": "openshift",
        "platform_version": "4.14.2",
        "namespaces": ["default", "production"],
        "exclude_namespaces": [],
        "domain_reports": [],
        "causal_chains": [],
        "uncorrelated_findings": [],
        "health_report": None,
        "phase": "pre_flight",
        "re_dispatch_count": 0,
        "re_dispatch_domains": [],
        "data_completeness": 0.0,
        "error": None,
        "_trace": [],
        "topology_graph": {},
        "topology_freshness": {},
        "issue_clusters": [],
        "causal_search_space": {},
        "scan_mode": "diagnostic",
        "previous_scan": None,
        "guard_scan_result": None,
        "diagnostic_scope": scope.model_dump(mode="json"),
        "scoped_topology_graph": None,
        "dispatch_domains": ["ctrl_plane", "node", "network", "storage"],
        "scope_coverage": 1.0,
    }

    config = {"configurable": {"cluster_client": client, "emitter": emitter}}

    with patch("src.agents.cluster.ctrl_plane_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.node_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.network_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.storage_agent._llm_analyze", new_callable=AsyncMock, return_value=mock_analysis), \
         patch("src.agents.cluster.synthesizer._llm_causal_reasoning", new_callable=AsyncMock, return_value=mock_causal), \
         patch("src.agents.cluster.synthesizer._llm_verdict", new_callable=AsyncMock, return_value=mock_verdict):

        result = await graph.ainvoke(initial_state, config=config)

    # All 4 domain agents should have run — none SKIPPED
    reports = result.get("domain_reports", [])
    statuses = {r["domain"]: r["status"] for r in reports}
    for domain in ALL_DOMAINS:
        assert domain in statuses, f"Domain {domain} should have a report"
        assert statuses[domain] != "SKIPPED", f"Domain {domain} should NOT be SKIPPED in cluster scope"

    assert result.get("phase") == "complete"
    assert result.get("health_report") is not None


# ===========================================================================
# 2. test_namespace_scoped_diagnosis — topology pruned, infra kept, dispatch works
# ===========================================================================


def test_namespace_scoped_diagnosis():
    """Namespace scope prunes topology but keeps infra parents, and dispatches correctly.

    Integration across: _prune_topology + dispatch_router.
    """
    topo = _build_rich_topology()
    scope = DiagnosticScope(level="namespace", namespaces=["production"])

    # -- Topology pruning --
    pruned = _prune_topology(topo, scope)
    kept_ids = set(pruned["nodes"].keys())

    # Production resources must be present
    assert "pod/prod/api-pod" in kept_ids
    assert "svc/prod/api-svc" in kept_ids

    # Infra parents kept
    assert "node/worker-1" in kept_ids, "Node should be kept as infra parent"
    assert "pv/pv-data" in kept_ids, "PV should be kept as infra parent"
    assert "operator/dns" in kept_ids, "ClusterOperator should be kept as infra parent"

    # Staging deployment (non-infra, not in target NS) should be pruned
    # UNLESS it's an edge neighbor of a kept node
    # node/worker-1 hosts pod/stg/web-pod, so pod/stg/web-pod is an edge neighbor
    assert "pod/stg/web-pod" in kept_ids, "Staging pod on shared node should be edge neighbor"

    # -- Dispatch --
    state = {"diagnostic_scope": scope.model_dump(mode="json")}
    dispatch_result = dispatch_router(state)
    # Namespace scope with default include_control_plane=True: all domains
    assert set(dispatch_result["dispatch_domains"]) == set(ALL_DOMAINS)


# ===========================================================================
# 3. test_workload_scoped_diagnosis — BFS pruning, limited dispatch, < 1.0 coverage
# ===========================================================================


def test_workload_scoped_diagnosis():
    """Workload scope: BFS prunes topology, only node+network dispatched, coverage < 1.0.

    Integration across: _prune_topology + dispatch_router + _wrap_domain_agent logic.
    """
    topo = _build_rich_topology()
    scope = DiagnosticScope(
        level="workload",
        namespaces=["production"],
        workload_key="Deployment/api",
        include_control_plane=False,
    )

    # -- Topology pruning --
    pruned = _prune_topology(topo, scope)
    kept_ids = set(pruned["nodes"].keys())

    # Workload root must be found and kept
    assert "deploy/prod/api" in kept_ids, "Workload root Deployment must be in BFS result"
    # BFS reaches: deploy -> pod (owns), pod -> node (hosts), node -> pod/stg (Node-to-Pod only)
    assert "pod/prod/api-pod" in kept_ids
    assert "node/worker-1" in kept_ids

    # -- Dispatch --
    state = {"diagnostic_scope": scope.model_dump(mode="json")}
    dispatch_result = dispatch_router(state)
    # Workload with include_control_plane=False: only node + network
    assert set(dispatch_result["dispatch_domains"]) == {"node", "network"}
    assert dispatch_result["scope_coverage"] == pytest.approx(2 / 4)
    assert dispatch_result["scope_coverage"] < 1.0

    # -- Verify wrapper would skip ctrl_plane and storage --
    # (Unit logic check: domain not in dispatch_domains => SKIPPED)
    for skipped_domain in ["ctrl_plane", "storage"]:
        assert skipped_domain not in dispatch_result["dispatch_domains"]


# ===========================================================================
# 4. test_component_scoped_diagnosis — only specified domain kinds, limited dispatch
# ===========================================================================


def test_component_scoped_diagnosis():
    """Component scope: topology keeps only domain-relevant kinds, dispatch matches.

    Integration across: _prune_topology + dispatch_router.
    """
    topo = _build_rich_topology()
    scope = DiagnosticScope(level="component", domains=["network"])

    # -- Topology pruning --
    pruned = _prune_topology(topo, scope)
    kept_kinds = {n["kind"] for n in pruned["nodes"].values()}

    # Network domain kinds: Service, Ingress, Route, NetworkPolicy, Pod
    allowed_kinds = {"Service", "Ingress", "Route", "NetworkPolicy", "Pod"}
    assert kept_kinds <= allowed_kinds, (
        f"Only network-relevant kinds expected, got extra: {kept_kinds - allowed_kinds}"
    )
    # Service should be kept (it's a network kind)
    assert any(n["kind"] == "Service" for n in pruned["nodes"].values())
    # Pod should be kept (shared across domains)
    assert any(n["kind"] == "Pod" for n in pruned["nodes"].values())
    # Node should NOT be kept (it's not a network-relevant kind)
    assert "Node" not in kept_kinds

    # -- Dispatch --
    state = {"diagnostic_scope": scope.model_dump(mode="json")}
    dispatch_result = dispatch_router(state)
    assert dispatch_result["dispatch_domains"] == ["network"]
    assert dispatch_result["scope_coverage"] == pytest.approx(1 / 4)


# ===========================================================================
# 5. test_guard_mode_rejects_non_cluster_scope — HTTP 400
# ===========================================================================


@pytest.mark.asyncio
async def test_guard_mode_rejects_non_cluster_scope():
    """Guard mode + namespace scope should raise HTTP 400.

    Integration across: route validation logic in routes_v4.py.
    """
    from fastapi import HTTPException
    from src.api.routes_v4 import start_session
    from src.api.models import StartSessionRequest
    from fastapi import BackgroundTasks

    request = StartSessionRequest(
        serviceName="test",
        capability="cluster_diagnostics",
        scan_mode="guard",
        scope={"level": "namespace", "namespaces": ["prod"]},
    )

    with pytest.raises(HTTPException) as exc_info:
        await start_session(request, BackgroundTasks())

    assert exc_info.value.status_code == 400
    assert "Guard mode requires cluster-level scope" in str(exc_info.value.detail)


# ===========================================================================
# 6. test_guard_mode_allows_cluster_scope — no error
# ===========================================================================


@pytest.mark.asyncio
async def test_guard_mode_allows_cluster_scope():
    """Guard mode + cluster scope should succeed (no validation error).

    Integration across: route validation logic + session creation in routes_v4.py.
    """
    from src.api.routes_v4 import start_session, sessions as route_sessions
    from src.api.models import StartSessionRequest
    from fastapi import BackgroundTasks

    request = StartSessionRequest(
        serviceName="test-guard-cluster",
        capability="cluster_diagnostics",
        scan_mode="guard",
        scope={"level": "cluster"},
    )

    # Mock BackgroundTasks.add_task to prevent actual diagnosis from running
    bg = BackgroundTasks()
    bg.add_task = lambda *args, **kwargs: None  # no-op

    response = await start_session(request, bg)

    assert response.status == "started"
    assert response.session_id is not None
    # Verify session was stored with correct scope
    session = route_sessions.get(response.session_id)
    assert session is not None
    assert session["diagnostic_scope"]["level"] == "cluster"
    assert session["scan_mode"] == "guard"

    # Cleanup
    route_sessions.pop(response.session_id, None)


# ===========================================================================
# 7. test_scope_preserved_in_findings — scope visible in findings response
# ===========================================================================


@pytest.mark.asyncio
async def test_scope_preserved_in_findings():
    """The diagnostic_scope should be visible in the findings response.

    Integration across: findings endpoint + session state.
    """
    sid = str(uuid.uuid4())
    scope = DiagnosticScope(level="namespace", namespaces=["prod"])
    try:
        sessions[sid] = {
            "capability": "cluster_diagnostics",
            "scan_mode": "diagnostic",
            "state": {
                "diagnostic_scope": scope.model_dump(mode="json"),
                "scope_coverage": 0.75,
                "issue_clusters": [],
                "causal_search_space": None,
                "topology_graph": {},
                "platform": "openshift",
                "platform_version": "4.14",
                "data_completeness": 0.9,
                "causal_chains": [],
                "uncorrelated_findings": [],
                "domain_reports": [],
                "health_report": {
                    "platform_health": "HEALTHY",
                    "blast_radius": {},
                    "remediation": {},
                    "execution_metadata": {},
                },
            },
            "created_at": "2026-03-01T00:00:00+00:00",
        }

        findings = await get_findings(sid)

        assert findings["diagnostic_scope"] is not None
        assert findings["diagnostic_scope"]["level"] == "namespace"
        assert findings["diagnostic_scope"]["namespaces"] == ["prod"]
        assert findings["scope_coverage"] == 0.75
    finally:
        sessions.pop(sid, None)


# ===========================================================================
# 8. test_backward_compat_no_scope — defaults to cluster-level
# ===========================================================================


def test_backward_compat_no_scope():
    """When no scope is provided, dispatch_router defaults to all domains (cluster behavior).

    Integration across: dispatch_router backward compatibility.
    """
    # No diagnostic_scope in state at all
    result_none = dispatch_router({})
    assert set(result_none["dispatch_domains"]) == set(ALL_DOMAINS)
    assert result_none["scope_coverage"] == 1.0

    # diagnostic_scope is explicitly None
    result_explicit_none = dispatch_router({"diagnostic_scope": None})
    assert set(result_explicit_none["dispatch_domains"]) == set(ALL_DOMAINS)
    assert result_explicit_none["scope_coverage"] == 1.0

    # Also verify topology pruning with default scope returns full topology
    topo = _build_rich_topology()
    default_scope = DiagnosticScope()  # defaults to cluster level
    pruned = _prune_topology(topo, default_scope)
    assert pruned is topo, "Cluster scope should return topology unchanged (same reference)"


# ===========================================================================
# 9. test_redispatch_respects_scope — only targets dispatched domains
# ===========================================================================


def test_redispatch_respects_scope():
    """Re-dispatch only targets domains that are in the active dispatch set.

    Integration across: _should_redispatch + dispatch_router.
    """
    # Simulate workload scope: only node + network dispatched
    scope = DiagnosticScope(
        level="workload",
        namespaces=["prod"],
        workload_key="Deployment/api",
        include_control_plane=False,
    )
    dispatch_result = dispatch_router({"diagnostic_scope": scope.model_dump(mode="json")})
    dispatch_domains = dispatch_result["dispatch_domains"]
    assert set(dispatch_domains) == {"node", "network"}

    # Now simulate synthesizer requesting re-dispatch of ctrl_plane + node
    state = {
        "re_dispatch_domains": ["ctrl_plane", "node"],
        "re_dispatch_count": 0,
        "dispatch_domains": dispatch_domains,
    }
    targets = _should_redispatch(state)
    # ctrl_plane is NOT in dispatch_domains, so only node gets re-dispatched
    assert "dispatch_node" in targets
    assert "dispatch_ctrl_plane" not in targets

    # Re-dispatch all excluded domains: should fall through to guard_formatter
    state_all_excluded = {
        "re_dispatch_domains": ["ctrl_plane", "storage"],
        "re_dispatch_count": 0,
        "dispatch_domains": dispatch_domains,
    }
    targets_excluded = _should_redispatch(state_all_excluded)
    assert targets_excluded == ["to_guard_formatter"]


# ===========================================================================
# 10. test_scope_coverage_in_findings — scope_coverage float in response
# ===========================================================================


@pytest.mark.asyncio
async def test_scope_coverage_in_findings():
    """scope_coverage should be a float between 0.0 and 1.0 in findings response.

    Integration across: dispatch_router -> synthesizer -> findings endpoint.
    """
    # Step 1: compute scope_coverage via dispatch_router
    scope = DiagnosticScope(level="component", domains=["network", "storage"])
    dispatch_result = dispatch_router({"diagnostic_scope": scope.model_dump(mode="json")})
    coverage = dispatch_result["scope_coverage"]
    assert isinstance(coverage, float)
    assert 0.0 < coverage < 1.0  # 2 of 4 domains = 0.5
    assert coverage == pytest.approx(0.5)

    # Step 2: verify data_completeness respects SKIPPED for scoped runs
    reports = [
        DomainReport(domain="ctrl_plane", status=DomainStatus.SKIPPED, confidence=0),
        DomainReport(domain="node", status=DomainStatus.SKIPPED, confidence=0),
        DomainReport(domain="network", status=DomainStatus.SUCCESS, confidence=85),
        DomainReport(domain="storage", status=DomainStatus.SUCCESS, confidence=90),
    ]
    completeness = _compute_data_completeness(reports)
    # 2 active (network=SUCCESS, storage=SUCCESS) => 2/2 = 1.0
    assert completeness == pytest.approx(1.0)

    # Step 3: verify findings endpoint returns scope_coverage
    sid = str(uuid.uuid4())
    try:
        sessions[sid] = {
            "capability": "cluster_diagnostics",
            "scan_mode": "diagnostic",
            "state": {
                "diagnostic_scope": scope.model_dump(mode="json"),
                "scope_coverage": coverage,
                "issue_clusters": [],
                "causal_search_space": None,
                "topology_graph": {},
                "platform": "k8s",
                "platform_version": "1.28",
                "data_completeness": completeness,
                "causal_chains": [],
                "uncorrelated_findings": [],
                "domain_reports": [r.model_dump(mode="json") for r in reports],
                "health_report": {
                    "platform_health": "HEALTHY",
                    "blast_radius": {},
                    "remediation": {},
                    "execution_metadata": {},
                },
            },
            "created_at": "2026-03-01T00:00:00+00:00",
        }

        findings = await get_findings(sid)
        assert findings["scope_coverage"] == pytest.approx(0.5)
        assert isinstance(findings["scope_coverage"], float)
    finally:
        sessions.pop(sid, None)
