# Diagnostic Coverage Hardening — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close detection gaps across the cluster diagnostic workflow for OpenShift-specific failures, Kubernetes-generic edge cases, causal chain completeness, and proactive risk detection.

**Architecture:** Add 3 new cluster_client methods, expand tool subsets for 2 agents, add heuristic rules to 3 agents, add 8 signal extraction rules + 8 failure patterns + 5 causal link types, and add 4 proactive checks. All changes are additive — no existing behavior is modified.

**Tech Stack:** Python 3.11, Pydantic, asyncio, pytest

**Design doc:** `docs/plans/2026-04-05-diagnostic-coverage-hardening-design.md`

---

### Task 1: Add `list_webhooks` to cluster_client

**Files:**
- Modify: `backend/src/agents/cluster_client/base.py:193` (before `build_topology_snapshot`)
- Modify: `backend/src/agents/cluster_client/mock_client.py` (add mock method)
- Test: `backend/tests/test_cluster_client_new.py`

**Step 1: Write the failing test**

Create `backend/tests/test_cluster_client_new.py`:

```python
"""Tests for new cluster_client methods: list_webhooks, list_routes, list_ingresses."""

import pytest
from src.agents.cluster_client.mock_client import MockClusterClient


@pytest.mark.asyncio
async def test_list_webhooks_returns_query_result():
    client = MockClusterClient(platform="openshift")
    result = await client.list_webhooks()
    assert hasattr(result, "data")
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    webhook = result.data[0]
    assert "name" in webhook
    assert "failure_policy" in webhook
    assert "timeout_seconds" in webhook
    assert "client_config" in webhook
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_cluster_client_new.py::test_list_webhooks_returns_query_result -v`
Expected: FAIL with `AttributeError`

**Step 3: Add `list_webhooks` to base class**

In `backend/src/agents/cluster_client/base.py`, add before `build_topology_snapshot`:

```python
    async def list_webhooks(self) -> QueryResult:
        """List ValidatingWebhookConfiguration + MutatingWebhookConfiguration."""
        return QueryResult()
```

**Step 4: Add mock implementation**

In `backend/src/agents/cluster_client/mock_client.py`, add method to `MockClusterClient`:

```python
    async def list_webhooks(self) -> QueryResult:
        data = [
            {
                "name": "validation.example.com",
                "kind": "ValidatingWebhookConfiguration",
                "failure_policy": "Fail",
                "timeout_seconds": 30,
                "client_config": {"url": "https://external-webhook.example.com/validate"},
                "rules": [{"apiGroups": [""], "resources": ["pods"], "operations": ["CREATE"]}],
            },
            {
                "name": "mutation.internal.svc",
                "kind": "MutatingWebhookConfiguration",
                "failure_policy": "Ignore",
                "timeout_seconds": 5,
                "client_config": {"service": {"name": "webhook-svc", "namespace": "webhook-system"}},
                "rules": [{"apiGroups": ["apps"], "resources": ["deployments"], "operations": ["CREATE", "UPDATE"]}],
            },
        ]
        return QueryResult(data=data, total_available=len(data), returned=len(data))
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_cluster_client_new.py::test_list_webhooks_returns_query_result -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/agents/cluster_client/base.py backend/src/agents/cluster_client/mock_client.py backend/tests/test_cluster_client_new.py
git commit -m "feat(cluster_client): add list_webhooks method"
```

---

### Task 2: Add `list_routes` and `list_ingresses` to cluster_client

**Files:**
- Modify: `backend/src/agents/cluster_client/base.py` (add `list_ingresses`)
- Modify: `backend/src/agents/cluster_client/mock_client.py` (add mock methods for routes + ingresses)
- Test: `backend/tests/test_cluster_client_new.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_cluster_client_new.py`:

```python
@pytest.mark.asyncio
async def test_list_routes_returns_query_result():
    client = MockClusterClient(platform="openshift")
    result = await client.list_routes()
    assert hasattr(result, "data")
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    route = result.data[0]
    assert "name" in route
    assert "host" in route
    assert "backend_service" in route
    assert "admitted" in route


@pytest.mark.asyncio
async def test_list_ingresses_returns_query_result():
    client = MockClusterClient(platform="openshift")
    result = await client.list_ingresses()
    assert hasattr(result, "data")
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    ingress = result.data[0]
    assert "name" in ingress
    assert "hosts" in ingress
    assert "backend_services" in ingress
    assert "ingress_class" in ingress
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_cluster_client_new.py -v -k "routes or ingresses"`
Expected: FAIL

**Step 3: Add `list_ingresses` to base class**

In `backend/src/agents/cluster_client/base.py`, add before `build_topology_snapshot`:

```python
    async def list_ingresses(self, namespace: str = "") -> QueryResult:
        """List Kubernetes Ingresses."""
        return QueryResult()
```

Note: `get_routes` already exists in `base.py:109` — we reuse it. The mock just needs data.

**Step 4: Add mock implementations**

In `backend/src/agents/cluster_client/mock_client.py`, add to `MockClusterClient`:

```python
    async def list_routes(self) -> QueryResult:
        data = [
            {
                "name": "app-route",
                "namespace": "production",
                "host": "app.example.com",
                "tls_termination": "edge",
                "backend_service": "app-svc",
                "admitted": True,
            },
            {
                "name": "api-route-broken",
                "namespace": "production",
                "host": "api.example.com",
                "tls_termination": "passthrough",
                "backend_service": "missing-svc",
                "admitted": False,
            },
        ]
        return QueryResult(data=data, total_available=len(data), returned=len(data))

    async def list_ingresses(self) -> QueryResult:
        data = [
            {
                "name": "web-ingress",
                "namespace": "production",
                "hosts": ["web.example.com"],
                "tls_secrets": ["web-tls"],
                "backend_services": ["web-svc"],
                "ingress_class": "nginx",
            },
            {
                "name": "api-ingress-no-class",
                "namespace": "staging",
                "hosts": ["api.staging.example.com"],
                "tls_secrets": [],
                "backend_services": ["api-svc"],
                "ingress_class": None,
            },
        ]
        return QueryResult(data=data, total_available=len(data), returned=len(data))
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_cluster_client_new.py -v`
Expected: 3 PASS

**Step 6: Commit**

```bash
git add backend/src/agents/cluster_client/base.py backend/src/agents/cluster_client/mock_client.py backend/tests/test_cluster_client_new.py
git commit -m "feat(cluster_client): add list_routes, list_ingresses methods"
```

---

### Task 3: Update tool subsets in `tools.py`

**Files:**
- Modify: `backend/src/agents/cluster/tools.py:212-214`

**Step 1: Write the failing test**

Create `backend/tests/test_tool_subsets.py`:

```python
"""Tests for updated agent tool subsets."""

from src.agents.cluster.tools import CTRL_PLANE_TOOLS, NETWORK_TOOLS, get_tools_for_agent


def test_ctrl_plane_has_list_deployments():
    assert "list_deployments" in CTRL_PLANE_TOOLS


def test_ctrl_plane_has_list_pods():
    assert "list_pods" in CTRL_PLANE_TOOLS


def test_network_has_list_routes():
    assert "list_routes" in NETWORK_TOOLS


def test_network_has_list_ingresses():
    assert "list_ingresses" in NETWORK_TOOLS


def test_get_tools_for_ctrl_plane_includes_new_tools():
    tools = get_tools_for_agent("ctrl_plane")
    tool_names = [t["name"] for t in tools]
    assert "list_deployments" in tool_names
    assert "list_pods" in tool_names
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_tool_subsets.py -v`
Expected: FAIL (list_deployments not in CTRL_PLANE_TOOLS)

**Step 3: Update tool subsets and add new tool schemas**

In `backend/src/agents/cluster/tools.py`, update line 212:

```python
CTRL_PLANE_TOOLS = ["list_nodes", "list_pods", "list_deployments", "list_events", "query_prometheus", "submit_findings"]
```

For NETWORK_TOOLS (line 214), add `list_routes` and `list_ingresses`. Also add the two new tool schemas to CLUSTER_TOOLS:

```python
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
```

Update NETWORK_TOOLS:
```python
NETWORK_TOOLS = ["list_services", "list_pods", "list_events", "list_network_policies", "list_routes", "list_ingresses", "query_prometheus", "get_pod_logs", "submit_findings"]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_tool_subsets.py -v`
Expected: 5 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/tools.py backend/tests/test_tool_subsets.py
git commit -m "feat(tools): add list_routes, list_ingresses, list_webhooks schemas; update agent tool subsets"
```

---

### Task 4: ctrl_plane_agent heuristic additions

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py:105-169` (`_heuristic_analyze`)
- Test: `backend/tests/test_ctrl_plane_heuristic.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_ctrl_plane_heuristic.py`:

```python
"""Tests for ctrl_plane_agent heuristic additions."""

import pytest
from src.agents.cluster.ctrl_plane_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_operator_progressing_detected():
    data = {
        "cluster_operators": [
            {"name": "kube-apiserver", "degraded": False, "available": True, "progressing": True},
        ],
        "api_health": {"status": "ok"},
        "events": [],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("progressing" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_scc_privileged_non_system():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "security_context_constraints": [
            {"name": "my-scc", "allowPrivilegedContainer": True, "users": ["system:serviceaccount:production:default"]},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("scc" in d.lower() or "privileged" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_mcp_mismatch_detected():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "machine_config_pools": [
            {"name": "worker", "degraded": False, "machineCount": 6, "updatedMachineCount": 4},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("mismatch" in d.lower() or "updating" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_etcd_pod_not_running():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "etcd_pods": [
            {"name": "etcd-master-0", "namespace": "openshift-etcd", "status": "CrashLoopBackOff", "restarts": 5},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    severities = {a["description"]: a["severity"] for a in result["anomalies"]}
    etcd_anomalies = [d for d in descs if "etcd" in d.lower()]
    assert len(etcd_anomalies) > 0
    # Etcd pod not running should be critical
    for d in etcd_anomalies:
        assert severities[d] in ("high", "critical")


@pytest.mark.asyncio
async def test_webhook_fail_external_detected():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "webhooks": [
            {
                "name": "external-validator",
                "failure_policy": "Fail",
                "timeout_seconds": 30,
                "client_config": {"url": "https://external.example.com/validate"},
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("webhook" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_webhook_high_timeout():
    data = {
        "cluster_operators": [],
        "api_health": {"status": "ok"},
        "events": [],
        "webhooks": [
            {
                "name": "slow-webhook",
                "failure_policy": "Ignore",
                "timeout_seconds": 15,
                "client_config": {"service": {"name": "svc", "namespace": "ns"}},
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("timeout" in d.lower() or "webhook" in d.lower() for d in descs)
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_ctrl_plane_heuristic.py -v`
Expected: FAIL

**Step 3: Add heuristic rules to `_heuristic_analyze`**

In `backend/src/agents/cluster/ctrl_plane_agent.py`, add after the MCP degraded check block (after line ~167, before `confidence = ...`):

```python
    # Check operator progressing
    for op in data_payload.get("cluster_operators", []):
        op_name = op.get("name", "unknown")
        if op.get("progressing"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Operator {op_name} upgrade in progress",
                "evidence_ref": f"operator/{op_name}",
                "severity": "medium",
            })

    # Check SCC with allowPrivilegedContainer for non-system namespaces
    system_prefixes = ("openshift-", "kube-", "default")
    for scc in data_payload.get("security_context_constraints", []):
        scc_name = scc.get("name", "unknown")
        if scc.get("allowPrivilegedContainer"):
            users = scc.get("users", [])
            non_system = [u for u in users if not any(u.startswith(f"system:serviceaccount:{p}") for p in system_prefixes)]
            if non_system:
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"SCC {scc_name} allows privileged containers for non-system users: {', '.join(non_system[:3])}",
                    "evidence_ref": f"scc/{scc_name}",
                    "severity": "medium",
                })

    # Check MCP machine count mismatch (update in progress)
    for mcp in data_payload.get("machine_config_pools", []):
        mcp_name = mcp.get("name", "unknown")
        machine_count = mcp.get("machineCount", 0)
        updated_count = mcp.get("updatedMachineCount", 0)
        if machine_count and machine_count != updated_count and not mcp.get("degraded"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"MachineConfigPool {mcp_name} updating: {updated_count}/{machine_count} machines updated (mismatch)",
                "evidence_ref": f"mcp/{mcp_name}",
                "severity": "medium",
            })

    # Check etcd pods
    for pod in data_payload.get("etcd_pods", []):
        pod_name = pod.get("name", "unknown")
        status = pod.get("status", "")
        restarts = pod.get("restarts", 0)
        if status not in ("Running",):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Etcd pod {pod_name} is not running (status: {status})",
                "evidence_ref": f"pod/openshift-etcd/{pod_name}",
                "severity": "critical",
            })
        elif restarts and restarts > 3:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Etcd pod {pod_name} has high restart count ({restarts})",
                "evidence_ref": f"pod/openshift-etcd/{pod_name}",
                "severity": "high",
            })

    # Check webhooks
    for wh in data_payload.get("webhooks", []):
        wh_name = wh.get("name", "unknown")
        failure_policy = wh.get("failure_policy", "Ignore")
        timeout = wh.get("timeout_seconds", 10)
        client_config = wh.get("client_config", {})
        is_external = "url" in client_config

        if failure_policy == "Fail" and is_external:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Webhook {wh_name} has failurePolicy=Fail with external URL — can block API operations if external service is down",
                "evidence_ref": f"webhook/{wh_name}",
                "severity": "high",
            })
        if timeout and timeout > 10:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Webhook {wh_name} has high timeout ({timeout}s > 10s) — can cause API latency",
                "evidence_ref": f"webhook/{wh_name}",
                "severity": "medium",
            })
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_ctrl_plane_heuristic.py -v`
Expected: 6 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py backend/tests/test_ctrl_plane_heuristic.py
git commit -m "feat(ctrl_plane): add operator progressing, SCC, MCP mismatch, etcd pod, webhook heuristics"
```

---

### Task 5: network_agent heuristic additions

**Files:**
- Modify: `backend/src/agents/cluster/network_agent.py:103-176` (`_heuristic_analyze`)
- Test: `backend/tests/test_network_heuristic.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_network_heuristic.py`:

```python
"""Tests for network_agent heuristic additions."""

import pytest
from src.agents.cluster.network_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_endpoint_not_ready_detected():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "endpoints": [
            {"name": "app-ep", "namespace": "production", "ready_addresses": 2, "not_ready_addresses": 3},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("not_ready" in d.lower() or "not ready" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_route_missing_backend():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "routes": [
            {"name": "broken-route", "namespace": "production", "host": "app.example.com",
             "backend_service": "missing-svc", "backend_endpoints": 0, "admitted": True},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("route" in d.lower() and ("missing" in d.lower() or "0 endpoint" in d.lower()) for d in descs)


@pytest.mark.asyncio
async def test_ingress_missing_backend():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "ingresses": [
            {"name": "broken-ingress", "namespace": "staging", "hosts": ["api.staging.example.com"],
             "backend_services": ["missing-svc"], "missing_backends": ["missing-svc"],
             "ingress_class": "nginx"},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("ingress" in d.lower() and "missing" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_ingress_no_class():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "ingresses": [
            {"name": "no-class-ingress", "namespace": "staging", "hosts": ["test.example.com"],
             "backend_services": ["svc"], "missing_backends": [],
             "ingress_class": None},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("ingress" in d.lower() and "class" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_dns_replicas_zero():
    data = {
        "services": [],
        "logs": [],
        "network_policies": [],
        "dns_deployments": [
            {"name": "dns-default", "namespace": "openshift-dns", "replicas_desired": 2, "replicas_ready": 0},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    severities = {a["description"]: a["severity"] for a in result["anomalies"]}
    dns_anomalies = [d for d in descs if "dns" in d.lower()]
    assert len(dns_anomalies) > 0
    for d in dns_anomalies:
        assert severities[d] == "critical"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_network_heuristic.py -v`
Expected: FAIL

**Step 3: Add heuristic rules to `_heuristic_analyze`**

In `backend/src/agents/cluster/network_agent.py`, add before `confidence = ...` (line ~175):

```python
    # Check endpoints with not_ready_addresses
    for ep in data_payload.get("endpoints", []):
        ep_name = ep.get("name", "unknown")
        ns = ep.get("namespace", "default")
        not_ready = ep.get("not_ready_addresses", 0)
        if not_ready and not_ready > 0:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Endpoints {ns}/{ep_name} has {not_ready} not_ready addresses",
                "evidence_ref": f"endpoints/{ns}/{ep_name}",
                "severity": "medium",
            })

    # Check Routes (OpenShift)
    for route in data_payload.get("routes", []):
        route_name = route.get("name", "unknown")
        ns = route.get("namespace", "default")
        backend_ep = route.get("backend_endpoints", -1)
        if backend_ep == 0:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Route {ns}/{route_name} backend has 0 endpoints — traffic will fail",
                "evidence_ref": f"route/{ns}/{route_name}",
                "severity": "high",
            })

    # Check Ingresses
    for ing in data_payload.get("ingresses", []):
        ing_name = ing.get("name", "unknown")
        ns = ing.get("namespace", "default")
        missing_backends = ing.get("missing_backends", [])
        ingress_class = ing.get("ingress_class")
        if missing_backends:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Ingress {ns}/{ing_name} has missing backend services: {', '.join(missing_backends)}",
                "evidence_ref": f"ingress/{ns}/{ing_name}",
                "severity": "high",
            })
        if ingress_class is None:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Ingress {ns}/{ing_name} has no ingress class — may not be picked up by any controller",
                "evidence_ref": f"ingress/{ns}/{ing_name}",
                "severity": "medium",
            })

    # Check DNS deployment replicas
    for dns_dep in data_payload.get("dns_deployments", []):
        dep_name = dns_dep.get("name", "unknown")
        ns = dns_dep.get("namespace", "")
        desired = dns_dep.get("replicas_desired", 0)
        ready = dns_dep.get("replicas_ready", 0)
        if desired and ready == 0:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"DNS deployment {ns}/{dep_name} has 0 ready replicas — cluster DNS is down",
                "evidence_ref": f"deployment/{ns}/{dep_name}",
                "severity": "critical",
            })
        elif desired and ready < desired:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"DNS deployment {ns}/{dep_name} has {ready}/{desired} replicas ready — DNS capacity reduced",
                "evidence_ref": f"deployment/{ns}/{dep_name}",
                "severity": "high",
            })
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_network_heuristic.py -v`
Expected: 5 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/network_agent.py backend/tests/test_network_heuristic.py
git commit -m "feat(network): add endpoint not_ready, route, ingress, DNS replica heuristics"
```

---

### Task 6: node_agent heuristic additions

**Files:**
- Modify: `backend/src/agents/cluster/node_agent.py:113-209` (`_heuristic_analyze`)
- Test: `backend/tests/test_node_heuristic.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_node_heuristic.py`:

```python
"""Tests for node_agent heuristic additions."""

import pytest
from src.agents.cluster.node_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_init_container_stuck():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [],
        "pods": [
            {
                "name": "app-pod",
                "namespace": "production",
                "init_containers": [
                    {"name": "init-db", "state": "waiting", "reason": "CrashLoopBackOff"},
                ],
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("init" in d.lower() and ("stuck" in d.lower() or "crash" in d.lower()) for d in descs)


@pytest.mark.asyncio
async def test_probe_misconfiguration():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [],
        "pods": [
            {
                "name": "slow-start-pod",
                "namespace": "production",
                "status": "Running",
                "ready": False,
                "running_not_ready_minutes": 10,
            },
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("probe" in d.lower() or "not ready" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_mount_failure_event():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [
            {"type": "Warning", "reason": "FailedMount", "object": "pod/app-pod", "message": "MountVolume.SetUp failed for volume config-vol"},
        ],
        "pods": [],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("mount" in d.lower() or "failedmount" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_quota_blocking_event():
    data = {
        "nodes": [],
        "deployments": [],
        "daemonsets": [],
        "events": [
            {"type": "Warning", "reason": "FailedCreate", "object": "replicaset/app-rs",
             "message": "Error creating: pods is forbidden: exceeded quota: compute-quota"},
        ],
        "pods": [],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("quota" in d.lower() for d in descs)
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_node_heuristic.py -v`
Expected: FAIL

**Step 3: Add heuristic rules to `_heuristic_analyze`**

In `backend/src/agents/cluster/node_agent.py`, add before `confidence = ...` (line ~208):

```python
    # Check init containers stuck
    for pod in data_payload.get("pods", data_payload.get("top_pods", [])):
        pod_name = pod.get("name", "unknown")
        ns = pod.get("namespace", "default")
        for init_c in pod.get("init_containers", []):
            init_name = init_c.get("name", "unknown")
            state = init_c.get("state", "")
            reason = init_c.get("reason", "")
            if state == "waiting" and reason in ("CrashLoopBackOff", "Error", "ImagePullBackOff"):
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"Init container {init_name} stuck in pod {ns}/{pod_name} (reason: {reason})",
                    "evidence_ref": f"pod/{ns}/{pod_name}",
                    "severity": "high",
                })

    # Check probe misconfiguration: Running but not Ready for > 5min
    for pod in data_payload.get("pods", data_payload.get("top_pods", [])):
        pod_name = pod.get("name", "unknown")
        ns = pod.get("namespace", "default")
        status = pod.get("status", "")
        ready = pod.get("ready", True)
        not_ready_minutes = pod.get("running_not_ready_minutes", 0)
        if status == "Running" and not ready and not_ready_minutes and not_ready_minutes > 5:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Pod {ns}/{pod_name} is Running but not Ready for {not_ready_minutes}min — possible probe misconfiguration",
                "evidence_ref": f"pod/{ns}/{pod_name}",
                "severity": "medium",
            })

    # Check for FailedMount events
    for event in data_payload.get("events", []):
        reason = event.get("reason", "")
        msg = event.get("message", "")
        obj = event.get("object", "")
        if reason == "FailedMount" or ("MountVolume.SetUp failed" in msg):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"ConfigMap/Secret mount failure on {obj}: {msg}",
                "evidence_ref": f"event/{obj}",
                "severity": "high",
            })

    # Check for quota exceeded events
    for event in data_payload.get("events", []):
        reason = event.get("reason", "")
        msg = event.get("message", "").lower()
        obj = event.get("object", "")
        if reason == "FailedCreate" and "exceeded quota" in msg:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"ResourceQuota blocking pod creation on {obj}: {event.get('message', '')}",
                "evidence_ref": f"event/{obj}",
                "severity": "high",
            })
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_node_heuristic.py -v`
Expected: 4 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/node_agent.py backend/tests/test_node_heuristic.py
git commit -m "feat(node): add init container, probe, mount failure, quota blocking heuristics"
```

---

### Task 7: Signal normalizer — 8 new signal rules

**Files:**
- Modify: `backend/src/agents/cluster/signal_normalizer.py:54-159` (`extract_signals`)
- Test: `backend/tests/test_signal_normalizer_new.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_signal_normalizer_new.py`:

```python
"""Tests for 8 new signal extraction rules in signal_normalizer."""

import pytest
from src.agents.cluster.signal_normalizer import extract_signals


def _make_report(domain: str, desc: str, ref: str = "test/ref") -> list[dict]:
    return [{"domain": domain, "status": "SUCCESS", "anomalies": [
        {"description": desc, "evidence_ref": ref, "severity": "high"},
    ]}]


def test_operator_degraded_signal():
    signals = extract_signals(_make_report("ctrl_plane", "Operator kube-apiserver is degraded and unavailable"))
    types = {s.signal_type for s in signals}
    assert "OPERATOR_DEGRADED" in types


def test_operator_progressing_signal():
    signals = extract_signals(_make_report("ctrl_plane", "Operator monitoring is progressing with upgrade"))
    types = {s.signal_type for s in signals}
    assert "OPERATOR_PROGRESSING" in types


def test_init_container_stuck_signal():
    signals = extract_signals(_make_report("node", "Init container init-db is stuck waiting with crash"))
    types = {s.signal_type for s in signals}
    assert "INIT_CONTAINER_STUCK" in types


def test_webhook_failure_signal():
    signals = extract_signals(_make_report("ctrl_plane", "Webhook validation.example.com failed with timeout"))
    types = {s.signal_type for s in signals}
    assert "WEBHOOK_FAILURE" in types


def test_mount_failure_signal():
    signals = extract_signals(_make_report("node", "FailedMount: MountVolume.SetUp failed for volume config"))
    types = {s.signal_type for s in signals}
    assert "MOUNT_FAILURE" in types


def test_pdb_blocking_signal():
    signals = extract_signals(_make_report("node", "PDB my-pdb blocking evictions, disruptionsAllowed is 0"))
    types = {s.signal_type for s in signals}
    assert "PDB_BLOCKING" in types


def test_quota_exceeded_signal():
    signals = extract_signals(_make_report("node", "ResourceQuota exceeded, pods blocked from creation"))
    types = {s.signal_type for s in signals}
    assert "QUOTA_EXCEEDED" in types


def test_probe_misconfigured_signal():
    signals = extract_signals(_make_report("node", "Pod is Running but probe failing, not ready for 10 minutes"))
    types = {s.signal_type for s in signals}
    assert "PROBE_MISCONFIGURED" in types
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_signal_normalizer_new.py -v`
Expected: FAIL

**Step 3: Add 8 new signal extraction rules**

In `backend/src/agents/cluster/signal_normalizer.py`, add inside `extract_signals` after the RBAC signal block (after line ~158, before the dedup section):

```python
            # Operator degraded/unavailable
            if "operator" in desc and ("unavailable" in desc or "degraded" in desc):
                signals.append(_make_signal("OPERATOR_DEGRADED", ref, domain, "deployment_status", namespace=ns))

            # Operator progressing
            if "operator" in desc and "progressing" in desc:
                signals.append(_make_signal("OPERATOR_PROGRESSING", ref, domain, "deployment_status", namespace=ns))

            # Init container stuck
            if "init container" in desc and ("stuck" in desc or "waiting" in desc or "crash" in desc):
                signals.append(_make_signal("INIT_CONTAINER_STUCK", ref, domain, "pod_phase", namespace=ns))

            # Webhook failure
            if "webhook" in desc and ("fail" in desc or "timeout" in desc or "blocked" in desc):
                signals.append(_make_signal("WEBHOOK_FAILURE", ref, domain, "k8s_event_warning", namespace=ns))

            # Mount failure
            if ("mount" in desc and ("fail" in desc or "error" in desc)) or "failedmount" in desc:
                signals.append(_make_signal("MOUNT_FAILURE", ref, domain, "k8s_event_warning", namespace=ns))

            # PDB blocking
            if "pdb" in desc and ("block" in desc or "disruptionsallowed" in desc):
                signals.append(_make_signal("PDB_BLOCKING", ref, domain, "k8s_event_warning", namespace=ns))

            # Quota exceeded
            if "quota" in desc and ("exceeded" in desc or "blocked" in desc):
                signals.append(_make_signal("QUOTA_EXCEEDED", ref, domain, "k8s_event_warning", namespace=ns))

            # Probe misconfigured
            if "probe" in desc and ("fail" in desc or "unhealthy" in desc or "not ready" in desc):
                signals.append(_make_signal("PROBE_MISCONFIGURED", ref, domain, "pod_phase", namespace=ns))
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_signal_normalizer_new.py -v`
Expected: 8 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/signal_normalizer.py backend/tests/test_signal_normalizer_new.py
git commit -m "feat(signals): add 8 new signal extraction rules"
```

---

### Task 8: Failure patterns — 8 new patterns

**Files:**
- Modify: `backend/src/agents/cluster/failure_patterns.py:21-166` (append to `FAILURE_PATTERNS`)
- Test: `backend/tests/test_failure_patterns_new.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_failure_patterns_new.py`:

```python
"""Tests for 8 new failure patterns."""

from src.agents.cluster.failure_patterns import match_patterns, FAILURE_PATTERNS


def _make_signals(*signal_types: str) -> list[dict]:
    return [{"signal_id": f"s{i}", "signal_type": st, "resource_key": f"test/{st.lower()}",
             "source_domain": "test", "raw_value": None, "reliability": 0.8,
             "timestamp": "2026-04-05T00:00:00Z", "namespace": "test"}
            for i, st in enumerate(signal_types)]


def test_operator_scaled_down():
    signals = _make_signals("OPERATOR_DEGRADED")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "OPERATOR_SCALED_DOWN" in ids


def test_operator_upgrade_stuck():
    signals = _make_signals("OPERATOR_PROGRESSING")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "OPERATOR_UPGRADE_STUCK" in ids


def test_etcd_quorum_loss():
    signals = _make_signals("OPERATOR_DEGRADED", "NODE_NOT_READY")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "ETCD_QUORUM_LOSS" in ids


def test_webhook_blocking():
    signals = _make_signals("WEBHOOK_FAILURE")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "WEBHOOK_BLOCKING" in ids


def test_init_container_stuck_pattern():
    signals = _make_signals("INIT_CONTAINER_STUCK")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "INIT_CONTAINER_STUCK_PATTERN" in ids


def test_config_mount_failure():
    signals = _make_signals("MOUNT_FAILURE")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "CONFIG_MOUNT_FAILURE" in ids


def test_netpol_blocks_dns():
    signals = _make_signals("NETPOL_EMPTY_INGRESS", "DNS_FAILURE")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "NETPOL_BLOCKS_DNS" in ids


def test_quota_scheduling_failure():
    signals = _make_signals("QUOTA_EXCEEDED", "FAILED_SCHEDULING")
    matches = match_patterns([], signals)
    ids = {m.pattern_id for m in matches}
    assert "QUOTA_SCHEDULING_FAILURE" in ids
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_failure_patterns_new.py -v`
Expected: FAIL

**Step 3: Add 8 new failure patterns**

In `backend/src/agents/cluster/failure_patterns.py`, append to `FAILURE_PATTERNS` list (after the `NODE_MEMORY_EVICTION` pattern, before the closing `]`):

```python
    FailurePattern(
        pattern_id="OPERATOR_SCALED_DOWN",
        name="Operator degraded or scaled down",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "OPERATOR_DEGRADED"}],
        probable_causes=["Operator pods scaled to zero", "Operator uninstalled", "CVO issue"],
        known_fixes=["Check operator pods", "Check ClusterVersion status", "Restart operator pod"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="OPERATOR_UPGRADE_STUCK",
        name="Operator upgrade stuck progressing",
        version="1.0", scope="cluster", priority=7,
        conditions=[{"signal": "OPERATOR_PROGRESSING"}],
        probable_causes=["Cluster version upgrade in progress", "Operator pod OOM during upgrade", "Node drain stuck"],
        known_fixes=["Wait for upgrade to complete", "Check operator logs", "Check node drain status"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="ETCD_QUORUM_LOSS",
        name="Etcd quorum loss (operator degraded + node down)",
        version="1.0", scope="cluster", priority=10,
        conditions=[{"signal": "OPERATOR_DEGRADED"}, {"signal": "NODE_NOT_READY"}],
        probable_causes=["Control plane node failure", "Network partition", "Etcd disk full"],
        known_fixes=["Restore failed node", "Check etcd member health", "Check disk space on control plane nodes"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="WEBHOOK_BLOCKING",
        name="Webhook blocking API operations",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "WEBHOOK_FAILURE"}],
        probable_causes=["Webhook backend down", "External service unreachable", "Certificate expired"],
        known_fixes=["Change failurePolicy to Ignore", "Fix webhook backend", "Delete stale webhook config"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="INIT_CONTAINER_STUCK_PATTERN",
        name="Init container stuck preventing pod start",
        version="1.0", scope="resource", priority=7,
        conditions=[{"signal": "INIT_CONTAINER_STUCK"}],
        probable_causes=["Init container image missing", "Init script failing", "Dependency not available"],
        known_fixes=["Check init container logs", "Verify init container image", "Check dependency availability"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="CONFIG_MOUNT_FAILURE",
        name="ConfigMap/Secret mount failure",
        version="1.0", scope="resource", priority=7,
        conditions=[{"signal": "MOUNT_FAILURE"}],
        probable_causes=["ConfigMap/Secret deleted", "Key not found in ConfigMap", "RBAC blocking secret access"],
        known_fixes=["Verify ConfigMap/Secret exists", "Check key names in mount spec", "Check RBAC permissions"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="NETPOL_BLOCKS_DNS",
        name="NetworkPolicy blocking DNS resolution",
        version="1.0", scope="namespace", priority=9,
        conditions=[{"signal": "NETPOL_EMPTY_INGRESS"}, {"signal": "DNS_FAILURE"}],
        probable_causes=["Default-deny egress blocking DNS port 53", "NetworkPolicy missing DNS allow rule"],
        known_fixes=["Add egress rule allowing UDP/TCP port 53 to kube-dns", "Review NetworkPolicy egress rules"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="QUOTA_SCHEDULING_FAILURE",
        name="Quota exceeded causing scheduling failure",
        version="1.0", scope="namespace", priority=8,
        conditions=[{"signal": "QUOTA_EXCEEDED"}, {"signal": "FAILED_SCHEDULING"}],
        probable_causes=["Resource quota exhausted", "Too many pods", "Over-provisioned resource requests"],
        known_fixes=["Increase quota limits", "Reduce resource requests", "Delete unused pods"],
        severity="high", confidence_boost=0.25,
    ),
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_failure_patterns_new.py -v`
Expected: 8 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/failure_patterns.py backend/tests/test_failure_patterns_new.py
git commit -m "feat(patterns): add 8 new failure patterns"
```

---

### Task 9: Synthesizer — 5 new causal link types

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py:36-50` (`CONSTRAINED_LINK_TYPES`)
- Test: `backend/tests/test_causal_links.py`

**Step 1: Write the failing test**

Create `backend/tests/test_causal_links.py`:

```python
"""Tests for 5 new causal link types in CONSTRAINED_LINK_TYPES."""

from src.agents.cluster.synthesizer import CONSTRAINED_LINK_TYPES


def test_operator_degraded_rescheduling_link():
    assert "operator_degraded -> workload_rescheduling" in CONSTRAINED_LINK_TYPES


def test_quota_exceeded_scheduling_link():
    assert "quota_exceeded -> scheduling_failure" in CONSTRAINED_LINK_TYPES


def test_webhook_failure_pod_blocked_link():
    assert "webhook_failure -> pod_creation_blocked" in CONSTRAINED_LINK_TYPES


def test_mount_failure_crash_link():
    assert "mount_failure -> container_crash" in CONSTRAINED_LINK_TYPES


def test_probe_failure_service_link():
    assert "probe_failure -> service_degradation" in CONSTRAINED_LINK_TYPES
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_causal_links.py -v`
Expected: FAIL (3 of 5 fail — `quota_exceeded -> scheduling_failure` already exists)

**Step 3: Add the new causal link types**

In `backend/src/agents/cluster/synthesizer.py`, add to `CONSTRAINED_LINK_TYPES` (before `"unknown"`):

```python
    "operator_degraded -> workload_rescheduling",
    "webhook_failure -> pod_creation_blocked",
    "mount_failure -> container_crash",
    "probe_failure -> service_degradation",
```

Note: `quota_exceeded -> scheduling_failure` already exists in the list.

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_causal_links.py -v`
Expected: 5 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/synthesizer.py backend/tests/test_causal_links.py
git commit -m "feat(synthesizer): add 4 new causal link types"
```

---

### Task 10: Proactive analyzer — 4 new checks

**Files:**
- Modify: `backend/src/agents/cluster/proactive_analyzer.py` (add 4 new checks + evaluators)
- Test: `backend/tests/test_proactive_new.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_proactive_new.py`:

```python
"""Tests for 4 new proactive checks."""

from src.agents.cluster.proactive_analyzer import (
    _check_dns_replica,
    _check_webhook_risk,
    _check_pv_reclaim_delete,
    _check_ingress_spof,
)


def test_dns_zero_replicas_critical():
    data = [{"name": "dns-default", "namespace": "openshift-dns", "replicas_desired": 2, "replicas_ready": 0}]
    findings = _check_dns_replica(data)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_dns_single_replica_high():
    data = [{"name": "coredns", "namespace": "kube-system", "replicas_desired": 2, "replicas_ready": 1}]
    findings = _check_dns_replica(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_dns_healthy_no_findings():
    data = [{"name": "coredns", "namespace": "kube-system", "replicas_desired": 2, "replicas_ready": 2}]
    findings = _check_dns_replica(data)
    assert len(findings) == 0


def test_webhook_fail_external():
    data = [
        {
            "name": "external-validator",
            "failure_policy": "Fail",
            "client_config": {"url": "https://external.example.com/validate"},
            "timeout_seconds": 10,
        },
    ]
    findings = _check_webhook_risk(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_webhook_ignore_no_finding():
    data = [
        {
            "name": "safe-webhook",
            "failure_policy": "Ignore",
            "client_config": {"url": "https://external.example.com/validate"},
            "timeout_seconds": 5,
        },
    ]
    findings = _check_webhook_risk(data)
    assert len(findings) == 0


def test_pv_reclaim_delete_on_stateful():
    data = [
        {
            "name": "data-pvc",
            "namespace": "production",
            "reclaim_policy": "Delete",
            "owner_kind": "StatefulSet",
            "storage_class": "gp2",
        },
    ]
    findings = _check_pv_reclaim_delete(data)
    assert len(findings) == 1
    assert findings[0].severity == "medium"


def test_pv_retain_no_finding():
    data = [
        {
            "name": "data-pvc",
            "namespace": "production",
            "reclaim_policy": "Retain",
            "owner_kind": "StatefulSet",
            "storage_class": "gp2",
        },
    ]
    findings = _check_pv_reclaim_delete(data)
    assert len(findings) == 0


def test_ingress_single_replica():
    data = [{"name": "router-default", "namespace": "openshift-ingress", "replicas_desired": 1, "replicas_ready": 1}]
    findings = _check_ingress_spof(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_ingress_multi_replica_no_finding():
    data = [{"name": "router-default", "namespace": "openshift-ingress", "replicas_desired": 3, "replicas_ready": 3}]
    findings = _check_ingress_spof(data)
    assert len(findings) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_proactive_new.py -v`
Expected: FAIL (functions don't exist)

**Step 3: Add 4 new evaluator functions and check definitions**

In `backend/src/agents/cluster/proactive_analyzer.py`, add the 4 new evaluator functions after `_check_hpa_vpa_limits` (before the `_EVALUATORS` dict):

```python
def _check_dns_replica(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag DNS deployments with < 2 ready replicas."""
    findings: list[ProactiveFinding] = []

    for dep in data:
        dep_name = dep.get("name", "unknown")
        ns = dep.get("namespace", "")
        desired = dep.get("replicas_desired", 0)
        ready = dep.get("replicas_ready", 0)
        resource_key = f"deployment/{ns}/{dep_name}"

        if ready == 0:
            severity = "critical"
            title = f"DNS deployment '{dep_name}' has 0 ready replicas — cluster DNS is down"
        elif ready < 2:
            severity = "high"
            title = f"DNS deployment '{dep_name}' has only {ready} replica — single point of failure"
        else:
            continue

        findings.append(ProactiveFinding(
            finding_id=_fid(),
            check_type="dns_replica_check",
            severity=severity,
            lifecycle_state="NEW",
            title=title,
            description=(
                f"DNS deployment {resource_key} has {ready}/{desired} ready replicas. "
                f"DNS is critical infrastructure — loss affects all service discovery."
            ),
            affected_resources=[resource_key],
            affected_workloads=[],
            days_until_impact=-1,
            recommendation=(
                f"Scale DNS deployment '{dep_name}' to at least 2 replicas for redundancy."
            ),
            commands=[
                f"kubectl get deployment {dep_name} -n {ns}",
                f"kubectl scale deployment {dep_name} -n {ns} --replicas=2",
            ],
            dry_run_command=f"kubectl scale deployment {dep_name} -n {ns} --replicas=2 --dry-run=client",
            confidence=0.95,
            source="proactive",
        ))

    return findings


def _check_webhook_risk(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag webhooks with failurePolicy=Fail and external URLs."""
    findings: list[ProactiveFinding] = []

    for wh in data:
        wh_name = wh.get("name", "unknown")
        failure_policy = wh.get("failure_policy", "Ignore")
        client_config = wh.get("client_config", {})
        is_external = "url" in client_config

        if failure_policy == "Fail" and is_external:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="webhook_risk",
                severity="high",
                lifecycle_state="NEW",
                title=f"Webhook '{wh_name}' has failurePolicy=Fail with external URL",
                description=(
                    f"Webhook {wh_name} uses failurePolicy=Fail and calls an external URL "
                    f"({client_config.get('url', 'unknown')}). If the external service is "
                    f"unreachable, all matching API operations will be blocked."
                ),
                affected_resources=[f"webhook/{wh_name}"],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation=(
                    f"Consider changing failurePolicy to 'Ignore' or moving the webhook "
                    f"service in-cluster for reliability."
                ),
                commands=[
                    f"kubectl get validatingwebhookconfigurations {wh_name} -o yaml",
                    f"kubectl get mutatingwebhookconfigurations {wh_name} -o yaml",
                ],
                dry_run_command=f"kubectl get validatingwebhookconfigurations {wh_name} -o yaml",
                confidence=0.90,
                source="proactive",
            ))

    return findings


def _check_pv_reclaim_delete(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag PVCs with reclaimPolicy=Delete on stateful workloads."""
    findings: list[ProactiveFinding] = []
    stateful_kinds = {"StatefulSet", "statefulset"}

    for pvc in data:
        pvc_name = pvc.get("name", "unknown")
        ns = pvc.get("namespace", "default")
        reclaim_policy = pvc.get("reclaim_policy", "")
        owner_kind = pvc.get("owner_kind", "")
        resource_key = f"pvc/{ns}/{pvc_name}"

        if reclaim_policy == "Delete" and owner_kind in stateful_kinds:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="pv_reclaim_delete",
                severity="medium",
                lifecycle_state="NEW",
                title=f"PVC '{pvc_name}' uses reclaimPolicy=Delete on stateful workload",
                description=(
                    f"PVC {resource_key} bound to a {owner_kind} uses reclaimPolicy=Delete. "
                    f"Deleting the PVC will permanently destroy the underlying data volume."
                ),
                affected_resources=[resource_key],
                affected_workloads=[f"{owner_kind}/{ns}/{pvc_name}"],
                days_until_impact=-1,
                recommendation=(
                    f"Change the reclaimPolicy to 'Retain' on the underlying PV to prevent "
                    f"accidental data loss."
                ),
                commands=[
                    f"kubectl get pvc {pvc_name} -n {ns} -o jsonpath='{{.spec.volumeName}}'",
                    f"kubectl get pv $(kubectl get pvc {pvc_name} -n {ns} -o jsonpath='{{.spec.volumeName}}') -o yaml",
                ],
                dry_run_command=f"kubectl get pvc {pvc_name} -n {ns} -o yaml",
                confidence=0.85,
                source="proactive",
            ))

    return findings


def _check_ingress_spof(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag ingress controller deployments with single replica."""
    findings: list[ProactiveFinding] = []

    for dep in data:
        dep_name = dep.get("name", "unknown")
        ns = dep.get("namespace", "")
        desired = dep.get("replicas_desired", 0)
        ready = dep.get("replicas_ready", 0)
        resource_key = f"deployment/{ns}/{dep_name}"

        if desired == 1:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="ingress_spof",
                severity="high",
                lifecycle_state="NEW",
                title=f"Ingress controller '{dep_name}' has single replica — SPOF",
                description=(
                    f"Ingress controller {resource_key} has only 1 replica. "
                    f"If it fails, all ingress traffic will be interrupted."
                ),
                affected_resources=[resource_key],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation=(
                    f"Scale ingress controller '{dep_name}' to at least 2 replicas for HA."
                ),
                commands=[
                    f"kubectl get deployment {dep_name} -n {ns}",
                    f"kubectl scale deployment {dep_name} -n {ns} --replicas=2",
                ],
                dry_run_command=f"kubectl scale deployment {dep_name} -n {ns} --replicas=2 --dry-run=client",
                confidence=0.90,
                source="proactive",
            ))

    return findings
```

Then add the 4 new check definitions to `PROACTIVE_CHECKS` (append before `]`):

```python
    CheckDefinition(
        check_id="dns_replica_check",
        name="DNS Deployment Replica Check",
        category="reliability",
        data_source="list_deployments",
        severity_rules=(
            SeverityRule(field="replicas_ready", op="==", value=0, severity="critical"),
            SeverityRule(field="replicas_ready", op="<=", value=1, severity="high"),
        ),
    ),
    CheckDefinition(
        check_id="webhook_risk",
        name="Webhook Risk Assessment",
        category="reliability",
        data_source="list_webhooks",
        severity_rules=(
            SeverityRule(field="failure_policy", op="==", value="Fail", severity="high"),
        ),
    ),
    CheckDefinition(
        check_id="pv_reclaim_delete",
        name="PV Reclaim Policy Risk",
        category="reliability",
        data_source="list_pvcs",
        severity_rules=(
            SeverityRule(field="reclaim_policy", op="==", value="Delete", severity="medium"),
        ),
    ),
    CheckDefinition(
        check_id="ingress_spof",
        name="Ingress Controller SPOF",
        category="reliability",
        data_source="list_deployments",
        severity_rules=(
            SeverityRule(field="replicas_desired", op="==", value=1, severity="high"),
        ),
    ),
```

Then register the evaluators in `_EVALUATORS`:

```python
    "dns_replica_check": _check_dns_replica,
    "webhook_risk": _check_webhook_risk,
    "pv_reclaim_delete": _check_pv_reclaim_delete,
    "ingress_spof": _check_ingress_spof,
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_proactive_new.py -v`
Expected: 10 PASS

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/proactive_analyzer.py backend/tests/test_proactive_new.py
git commit -m "feat(proactive): add DNS replica, webhook risk, PV reclaim, ingress SPOF checks"
```

---

### Task 11: Run full test suite and verify no regressions

**Step 1: Run all new tests**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_cluster_client_new.py backend/tests/test_tool_subsets.py backend/tests/test_ctrl_plane_heuristic.py backend/tests/test_network_heuristic.py backend/tests/test_node_heuristic.py backend/tests/test_signal_normalizer_new.py backend/tests/test_failure_patterns_new.py backend/tests/test_causal_links.py backend/tests/test_proactive_new.py -v`
Expected: All pass

**Step 2: Run existing test files to verify no regressions**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python3 -m pytest backend/tests/test_traced_node_defaults.py backend/tests/test_agent_error_handling.py backend/tests/test_synthesizer_error_handling.py backend/tests/test_tool_executor_input_validation.py -v`
Expected: All pass

**Step 3: If any tests fail, fix them before proceeding**

If a test fails, investigate root cause and fix. Do not skip.
