# OpenShift Platform-Layer Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close diagnostic gaps for OLM ecosystem, ClusterVersion, Machine lifecycle, and Proxy/OAuth configuration by extending `ctrl_plane_agent`.

**Architecture:** All 6 new `cluster_client` methods are non-abstract (return empty `QueryResult` by default). MockClusterClient provides fixture data. New heuristic checks are added to `ctrl_plane_agent._heuristic_analyze()`. Signal normalizer, failure patterns, synthesizer causal links, and proactive checks are extended with platform-layer rules.

**Tech Stack:** Python 3.11, pytest, pydantic, asyncio

---

### Task 1: Add `get_cluster_version()` and `list_machines()` to cluster_client

**Files:**
- Modify: `backend/src/agents/cluster_client/base.py:102-127`
- Modify: `backend/src/agents/cluster_client/mock_client.py`
- Create: `backend/tests/test_cluster_client_platform.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_cluster_client_platform.py`:

```python
"""Tests for platform-layer cluster_client methods."""

import pytest
from src.agents.cluster_client.mock_client import MockClusterClient


@pytest.fixture
def client():
    return MockClusterClient(platform="openshift")


@pytest.fixture
def k8s_client():
    return MockClusterClient(platform="kubernetes")


@pytest.mark.asyncio
async def test_get_cluster_version_returns_data(client):
    result = await client.get_cluster_version()
    assert result.data
    cv = result.data[0]
    assert "version" in cv
    assert "desired" in cv
    assert "conditions" in cv
    assert "history" in cv


@pytest.mark.asyncio
async def test_get_cluster_version_empty_on_k8s(k8s_client):
    result = await k8s_client.get_cluster_version()
    assert result.data == []


@pytest.mark.asyncio
async def test_list_machines_returns_data(client):
    result = await client.list_machines()
    assert len(result.data) >= 2
    machine = result.data[0]
    assert "name" in machine
    assert "phase" in machine
    assert "node_ref" in machine


@pytest.mark.asyncio
async def test_list_machines_empty_on_k8s(k8s_client):
    result = await k8s_client.list_machines()
    assert result.data == []
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cluster_client_platform.py -v`
Expected: FAIL — `get_cluster_version` and `list_machines` not found

**Step 3: Add methods to base.py**

Add after `get_machine_config_pools()` (line 126) in `backend/src/agents/cluster_client/base.py`:

```python
    async def get_cluster_version(self) -> QueryResult:
        """OpenShift ClusterVersion object."""
        return QueryResult()

    async def list_machines(self) -> QueryResult:
        """OpenShift Machines (machine.openshift.io/v1beta1)."""
        return QueryResult()
```

**Step 4: Add mock implementations to mock_client.py**

Add after the `get_machine_config_pools()` method in `backend/src/agents/cluster_client/mock_client.py`:

```python
    async def get_cluster_version(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        cv = {
            "version": "4.14.2",
            "desired": "4.14.3",
            "conditions": [
                {"type": "Available", "status": "True", "message": "Done applying 4.14.2"},
                {"type": "Progressing", "status": "True", "message": "Working towards 4.14.3"},
                {"type": "Failing", "status": "False", "message": ""},
            ],
            "history": [
                {"version": "4.14.2", "state": "Completed"},
                {"version": "4.14.1", "state": "Completed"},
            ],
        }
        return QueryResult(data=[cv], total_available=1, returned=1)

    async def list_machines(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        machines = [
            {
                "name": "master-0",
                "phase": "Running",
                "provider_id": "aws:///us-east-1a/i-abc123",
                "node_ref": "master-0.internal",
                "conditions": [],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
            {
                "name": "worker-0",
                "phase": "Running",
                "provider_id": "aws:///us-east-1a/i-def456",
                "node_ref": "worker-0.internal",
                "conditions": [],
                "creation_timestamp": "2026-01-10T08:00:00Z",
            },
            {
                "name": "worker-2",
                "phase": "Failed",
                "provider_id": "",
                "node_ref": "",
                "conditions": [{"type": "MachineCreation", "status": "False", "reason": "CreateError", "message": "Failed to create instance"}],
                "creation_timestamp": "2026-03-15T10:00:00Z",
            },
        ]
        return QueryResult(data=machines, total_available=len(machines), returned=len(machines))
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_cluster_client_platform.py -v`
Expected: 4 PASSED

**Step 6: Commit**

```bash
git add backend/src/agents/cluster_client/base.py backend/src/agents/cluster_client/mock_client.py backend/tests/test_cluster_client_platform.py
git commit -m "feat(cluster_client): add get_cluster_version and list_machines methods"
```

---

### Task 2: Add OLM methods (`list_subscriptions`, `list_csvs`, `list_install_plans`) to cluster_client

**Files:**
- Modify: `backend/src/agents/cluster_client/base.py`
- Modify: `backend/src/agents/cluster_client/mock_client.py`
- Modify: `backend/tests/test_cluster_client_platform.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_cluster_client_platform.py`:

```python
@pytest.mark.asyncio
async def test_list_subscriptions_returns_data(client):
    result = await client.list_subscriptions()
    assert len(result.data) >= 2
    sub = result.data[0]
    assert "name" in sub
    assert "package" in sub
    assert "state" in sub
    assert "currentCSV" in sub
    assert "installedCSV" in sub


@pytest.mark.asyncio
async def test_list_csvs_returns_data(client):
    result = await client.list_csvs()
    assert len(result.data) >= 2
    csv = result.data[0]
    assert "name" in csv
    assert "phase" in csv


@pytest.mark.asyncio
async def test_list_install_plans_returns_data(client):
    result = await client.list_install_plans()
    assert len(result.data) >= 1
    ip = result.data[0]
    assert "name" in ip
    assert "approval" in ip
    assert "phase" in ip
    assert "csv_names" in ip


@pytest.mark.asyncio
async def test_olm_methods_empty_on_k8s(k8s_client):
    for method_name in ("list_subscriptions", "list_csvs", "list_install_plans"):
        result = await getattr(k8s_client, method_name)()
        assert result.data == [], f"{method_name} should be empty on k8s"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cluster_client_platform.py -v`
Expected: FAIL — methods not found

**Step 3: Add methods to base.py**

Add after `list_machines()` in `backend/src/agents/cluster_client/base.py`:

```python
    async def list_subscriptions(self, namespace: str = "") -> QueryResult:
        """OLM Subscriptions (operators.coreos.com/v1alpha1)."""
        return QueryResult()

    async def list_csvs(self, namespace: str = "") -> QueryResult:
        """OLM ClusterServiceVersions (operators.coreos.com/v1alpha1)."""
        return QueryResult()

    async def list_install_plans(self, namespace: str = "") -> QueryResult:
        """OLM InstallPlans (operators.coreos.com/v1alpha1)."""
        return QueryResult()
```

**Step 4: Add mock implementations to mock_client.py**

Add after `list_machines()` in `backend/src/agents/cluster_client/mock_client.py`:

```python
    async def list_subscriptions(self, namespace: str = "") -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        subs = [
            {
                "name": "elasticsearch-operator",
                "namespace": "openshift-operators-redhat",
                "package": "elasticsearch-operator",
                "channel": "stable-5.8",
                "currentCSV": "elasticsearch-operator.v5.8.1",
                "installedCSV": "elasticsearch-operator.v5.8.1",
                "state": "AtLatestKnown",
            },
            {
                "name": "jaeger-operator",
                "namespace": "openshift-operators",
                "package": "jaeger-product",
                "channel": "stable",
                "currentCSV": "jaeger-operator.v1.51.0",
                "installedCSV": "jaeger-operator.v1.47.0",
                "state": "UpgradePending",
            },
        ]
        if namespace:
            subs = [s for s in subs if s["namespace"] == namespace]
        return QueryResult(data=subs, total_available=len(subs), returned=len(subs))

    async def list_csvs(self, namespace: str = "") -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        csvs = [
            {
                "name": "elasticsearch-operator.v5.8.1",
                "namespace": "openshift-operators-redhat",
                "phase": "Succeeded",
                "reason": "InstallSucceeded",
                "message": "install strategy completed with no errors",
            },
            {
                "name": "jaeger-operator.v1.51.0",
                "namespace": "openshift-operators",
                "phase": "Failed",
                "reason": "ComponentFailed",
                "message": "install strategy failed: Deployment not ready",
            },
        ]
        if namespace:
            csvs = [c for c in csvs if c["namespace"] == namespace]
        return QueryResult(data=csvs, total_available=len(csvs), returned=len(csvs))

    async def list_install_plans(self, namespace: str = "") -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        plans = [
            {
                "name": "install-abc12",
                "namespace": "openshift-operators",
                "approval": "Manual",
                "approved": False,
                "phase": "RequiresApproval",
                "csv_names": ["jaeger-operator.v1.51.0"],
            },
            {
                "name": "install-def34",
                "namespace": "openshift-operators-redhat",
                "approval": "Automatic",
                "approved": True,
                "phase": "Complete",
                "csv_names": ["elasticsearch-operator.v5.8.1"],
            },
        ]
        if namespace:
            plans = [p for p in plans if p["namespace"] == namespace]
        return QueryResult(data=plans, total_available=len(plans), returned=len(plans))
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_cluster_client_platform.py -v`
Expected: 8 PASSED

**Step 6: Commit**

```bash
git add backend/src/agents/cluster_client/base.py backend/src/agents/cluster_client/mock_client.py backend/tests/test_cluster_client_platform.py
git commit -m "feat(cluster_client): add OLM methods — list_subscriptions, list_csvs, list_install_plans"
```

---

### Task 3: Add `get_proxy_config()` to cluster_client

**Files:**
- Modify: `backend/src/agents/cluster_client/base.py`
- Modify: `backend/src/agents/cluster_client/mock_client.py`
- Modify: `backend/tests/test_cluster_client_platform.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_cluster_client_platform.py`:

```python
@pytest.mark.asyncio
async def test_get_proxy_config_returns_data(client):
    result = await client.get_proxy_config()
    assert result.data
    proxy = result.data[0]
    assert "httpProxy" in proxy
    assert "httpsProxy" in proxy
    assert "noProxy" in proxy


@pytest.mark.asyncio
async def test_get_proxy_config_empty_on_k8s(k8s_client):
    result = await k8s_client.get_proxy_config()
    assert result.data == []
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_cluster_client_platform.py::test_get_proxy_config_returns_data -v`
Expected: FAIL

**Step 3: Add method to base.py**

Add after `list_install_plans()` in `backend/src/agents/cluster_client/base.py`:

```python
    async def get_proxy_config(self) -> QueryResult:
        """OpenShift cluster-wide Proxy config (config.openshift.io/v1)."""
        return QueryResult()
```

**Step 4: Add mock implementation to mock_client.py**

Add after `list_install_plans()` in `backend/src/agents/cluster_client/mock_client.py`:

```python
    async def get_proxy_config(self) -> QueryResult:
        if self._platform != "openshift":
            return QueryResult()
        proxy = {
            "httpProxy": "http://proxy.corp.example.com:3128",
            "httpsProxy": "http://proxy.corp.example.com:3128",
            "noProxy": ".cluster.local,.svc,10.128.0.0/14,172.30.0.0/16,localhost",
            "trustedCA": "user-ca-bundle",
        }
        return QueryResult(data=[proxy], total_available=1, returned=1)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_cluster_client_platform.py -v`
Expected: 10 PASSED

**Step 6: Commit**

```bash
git add backend/src/agents/cluster_client/base.py backend/src/agents/cluster_client/mock_client.py backend/tests/test_cluster_client_platform.py
git commit -m "feat(cluster_client): add get_proxy_config method"
```

---

### Task 4: Add tool schemas and update CTRL_PLANE_TOOLS

**Files:**
- Modify: `backend/src/agents/cluster/tools.py:183-247`
- Create: `backend/tests/test_tool_subsets_platform.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_tool_subsets_platform.py`:

```python
"""Tests for platform-layer tool schemas and subsets."""

from src.agents.cluster.tools import CLUSTER_TOOLS, CTRL_PLANE_TOOLS, get_tools_for_agent


def _tool_names():
    return [t["name"] for t in CLUSTER_TOOLS]


def test_cluster_tools_has_get_cluster_version():
    assert "get_cluster_version" in _tool_names()


def test_cluster_tools_has_list_subscriptions():
    assert "list_subscriptions" in _tool_names()


def test_cluster_tools_has_list_csvs():
    assert "list_csvs" in _tool_names()


def test_cluster_tools_has_list_install_plans():
    assert "list_install_plans" in _tool_names()


def test_cluster_tools_has_list_machines():
    assert "list_machines" in _tool_names()


def test_cluster_tools_has_get_proxy_config():
    assert "get_proxy_config" in _tool_names()


def test_ctrl_plane_tools_includes_platform_tools():
    for tool in ("get_cluster_version", "list_subscriptions", "list_csvs",
                 "list_install_plans", "list_machines", "get_proxy_config"):
        assert tool in CTRL_PLANE_TOOLS, f"{tool} missing from CTRL_PLANE_TOOLS"


def test_get_tools_for_agent_ctrl_plane_returns_platform_tools():
    tools = get_tools_for_agent("ctrl_plane")
    names = [t["name"] for t in tools]
    for tool in ("get_cluster_version", "list_subscriptions", "list_csvs",
                 "list_install_plans", "list_machines", "get_proxy_config"):
        assert tool in names, f"{tool} missing from ctrl_plane agent tools"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_tool_subsets_platform.py -v`
Expected: FAIL — tools not in CLUSTER_TOOLS

**Step 3: Add tool schemas and update CTRL_PLANE_TOOLS**

Add 6 new tool schemas to `CLUSTER_TOOLS` in `backend/src/agents/cluster/tools.py` before the `submit_findings` entry (before line 214):

```python
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
```

Update `CTRL_PLANE_TOOLS` (line 243):

```python
CTRL_PLANE_TOOLS = ["list_nodes", "list_pods", "list_deployments", "list_events", "query_prometheus", "get_cluster_version", "list_subscriptions", "list_csvs", "list_install_plans", "list_machines", "get_proxy_config", "submit_findings"]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_tool_subsets_platform.py -v`
Expected: 9 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/tools.py backend/tests/test_tool_subsets_platform.py
git commit -m "feat(tools): add platform-layer tool schemas; update CTRL_PLANE_TOOLS"
```

---

### Task 5: Add ctrl_plane_agent heuristic checks for ClusterVersion and OLM

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py:232-258`
- Create: `backend/tests/test_ctrl_plane_platform.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_ctrl_plane_platform.py`:

```python
"""Tests for platform-layer ctrl_plane_agent heuristic checks."""

import pytest
from src.agents.cluster.ctrl_plane_agent import _heuristic_analyze


@pytest.mark.asyncio
async def test_cluster_version_upgrade_stuck():
    data = {
        "cluster_version": {
            "version": "4.14.2",
            "desired": "4.14.3",
            "conditions": [
                {"type": "Available", "status": "True"},
                {"type": "Progressing", "status": "True", "message": "Working towards 4.14.3"},
                {"type": "Failing", "status": "False"},
            ],
        },
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    assert any("cluster version" in d.lower() and "progressing" in d.lower() for d in descs)


@pytest.mark.asyncio
async def test_cluster_version_failing():
    data = {
        "cluster_version": {
            "version": "4.14.2",
            "desired": "4.14.3",
            "conditions": [
                {"type": "Available", "status": "True"},
                {"type": "Progressing", "status": "True"},
                {"type": "Failing", "status": "True", "message": "Unable to apply 4.14.3"},
            ],
        },
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"] for a in result["anomalies"]]
    severities = {a["description"]: a["severity"] for a in result["anomalies"]}
    failing_anomaly = [d for d in descs if "failing" in d.lower() or "cluster version" in d.lower()]
    assert len(failing_anomaly) > 0
    assert any(severities[d] == "critical" for d in failing_anomaly)


@pytest.mark.asyncio
async def test_cluster_version_available_false():
    data = {
        "cluster_version": {
            "version": "4.14.2",
            "desired": "4.14.2",
            "conditions": [
                {"type": "Available", "status": "False", "message": "Cluster not available"},
                {"type": "Progressing", "status": "False"},
                {"type": "Failing", "status": "False"},
            ],
        },
    }
    result = await _heuristic_analyze(data)
    severities = [a["severity"] for a in result["anomalies"]]
    assert "critical" in severities


@pytest.mark.asyncio
async def test_olm_subscription_not_at_latest():
    data = {
        "subscriptions": [
            {"name": "jaeger", "state": "UpgradePending", "currentCSV": "v1.51", "installedCSV": "v1.47"},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("subscription" in d and "jaeger" in d for d in descs)


@pytest.mark.asyncio
async def test_olm_csv_failed():
    data = {
        "csvs": [
            {"name": "jaeger-operator.v1.51.0", "phase": "Failed", "reason": "ComponentFailed", "message": "deploy failed"},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("csv" in d or "clusterserviceversion" in d for d in descs)


@pytest.mark.asyncio
async def test_olm_install_plan_requires_approval():
    data = {
        "install_plans": [
            {"name": "install-abc", "approval": "Manual", "approved": False, "phase": "RequiresApproval", "csv_names": ["op.v1"]},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("installplan" in d or "install plan" in d for d in descs)
    severities = {a["description"]: a["severity"] for a in result["anomalies"]}
    plan_anomalies = [d for d in descs if "installplan" in d or "install plan" in d]
    assert all(severities[a["description"]] == "low" for a in result["anomalies"] if a["description"].lower() in plan_anomalies)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_ctrl_plane_platform.py -v`
Expected: FAIL — heuristic doesn't check these fields

**Step 3: Add heuristic checks**

Add after the webhook checks block (after line 255) in `backend/src/agents/cluster/ctrl_plane_agent.py` `_heuristic_analyze()`:

```python
    # Check ClusterVersion
    cv = data_payload.get("cluster_version")
    if cv and isinstance(cv, dict):
        conditions = cv.get("conditions", [])
        cv_version = cv.get("version", "unknown")
        cv_desired = cv.get("desired", cv_version)

        for cond in conditions:
            cond_type = cond.get("type", "")
            cond_status = cond.get("status", "")
            cond_msg = cond.get("message", "")

            if cond_type == "Failing" and cond_status == "True":
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"ClusterVersion upgrade failing: {cond_msg or 'upgrade to ' + cv_desired + ' is failing'}",
                    "evidence_ref": "clusterversion/version",
                    "severity": "critical",
                })
            elif cond_type == "Available" and cond_status == "False":
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"ClusterVersion not available: {cond_msg or 'cluster version ' + cv_version + ' is not available'}",
                    "evidence_ref": "clusterversion/version",
                    "severity": "critical",
                })
            elif cond_type == "Progressing" and cond_status == "True" and cv_version != cv_desired:
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"ClusterVersion upgrade progressing: {cv_version} → {cv_desired}",
                    "evidence_ref": "clusterversion/version",
                    "severity": "high",
                })

    # Check OLM Subscriptions
    for sub in data_payload.get("subscriptions", []):
        sub_name = sub.get("name", "unknown")
        state = sub.get("state", "")
        if state and state != "AtLatestKnown":
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"OLM Subscription {sub_name} state is {state} (currentCSV: {sub.get('currentCSV', '?')}, installedCSV: {sub.get('installedCSV', '?')})",
                "evidence_ref": f"subscription/{sub.get('namespace', '')}/{sub_name}",
                "severity": "high",
            })

    # Check OLM CSVs
    failed_phases = ("Failed", "Unknown", "Replacing")
    for csv in data_payload.get("csvs", []):
        csv_name = csv.get("name", "unknown")
        phase = csv.get("phase", "")
        if phase in failed_phases:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"ClusterServiceVersion {csv_name} phase is {phase}: {csv.get('message', '')}",
                "evidence_ref": f"csv/{csv.get('namespace', '')}/{csv_name}",
                "severity": "high",
            })

    # Check OLM InstallPlans
    for ip in data_payload.get("install_plans", []):
        ip_name = ip.get("name", "unknown")
        if ip.get("approval") == "Manual" and not ip.get("approved"):
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"InstallPlan {ip_name} requires manual approval for {', '.join(ip.get('csv_names', []))}",
                "evidence_ref": f"installplan/{ip.get('namespace', '')}/{ip_name}",
                "severity": "low",
            })
        elif ip.get("phase") == "Installing":
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"InstallPlan {ip_name} stuck in Installing phase",
                "evidence_ref": f"installplan/{ip.get('namespace', '')}/{ip_name}",
                "severity": "medium",
            })
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_ctrl_plane_platform.py -v`
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py backend/tests/test_ctrl_plane_platform.py
git commit -m "feat(ctrl_plane): add ClusterVersion and OLM heuristic checks"
```

---

### Task 6: Add ctrl_plane_agent heuristic checks for Machine and Proxy

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py`
- Modify: `backend/tests/test_ctrl_plane_platform.py`

**Step 1: Write the failing tests**

Append to `backend/tests/test_ctrl_plane_platform.py`:

```python
@pytest.mark.asyncio
async def test_machine_not_running():
    data = {
        "machines": [
            {"name": "worker-2", "phase": "Failed", "node_ref": "", "conditions": []},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("machine" in d and "worker-2" in d for d in descs)
    assert result["anomalies"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_machine_provisioned_no_node_ref():
    data = {
        "machines": [
            {"name": "worker-3", "phase": "Provisioned", "node_ref": "", "conditions": []},
        ],
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("machine" in d and "node" in d for d in descs)
    assert result["anomalies"][0]["severity"] == "medium"


@pytest.mark.asyncio
async def test_proxy_misconfigured_no_noproxy():
    data = {
        "proxy_config": {
            "httpProxy": "http://proxy.corp:3128",
            "httpsProxy": "http://proxy.corp:3128",
            "noProxy": "",
            "trustedCA": "",
        },
    }
    result = await _heuristic_analyze(data)
    descs = [a["description"].lower() for a in result["anomalies"]]
    assert any("proxy" in d for d in descs)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_ctrl_plane_platform.py -v`
Expected: 3 new tests FAIL

**Step 3: Add heuristic checks**

Add after the InstallPlan checks in `_heuristic_analyze()`:

```python
    # Check Machines
    for machine in data_payload.get("machines", []):
        m_name = machine.get("name", "unknown")
        phase = machine.get("phase", "")
        node_ref = machine.get("node_ref", "")

        if phase and phase != "Running":
            if phase == "Provisioned" and not node_ref:
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"Machine {m_name} is Provisioned but has no node reference — may be stuck joining cluster",
                    "evidence_ref": f"machine/{m_name}",
                    "severity": "medium",
                })
            elif phase in ("Failed", "Deleting", "Provisioning"):
                anomalies.append({
                    "domain": domain,
                    "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                    "description": f"Machine {m_name} is not Running (phase: {phase})",
                    "evidence_ref": f"machine/{m_name}",
                    "severity": "high",
                })

    # Check Proxy config
    proxy = data_payload.get("proxy_config")
    if proxy and isinstance(proxy, dict):
        http_proxy = proxy.get("httpProxy", "")
        no_proxy = proxy.get("noProxy", "")
        trusted_ca = proxy.get("trustedCA", "")
        https_proxy = proxy.get("httpsProxy", "")

        if http_proxy and not no_proxy:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"Proxy configured (httpProxy={http_proxy}) but noProxy is empty — cluster-internal traffic may be routed through proxy",
                "evidence_ref": "proxy/cluster",
                "severity": "medium",
            })
        if https_proxy and not trusted_ca:
            anomalies.append({
                "domain": domain,
                "anomaly_id": f"{domain}-heur-{len(anomalies)+1}",
                "description": f"HTTPS proxy configured but no trustedCA bundle — TLS interception may fail",
                "evidence_ref": "proxy/cluster",
                "severity": "medium",
            })
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_ctrl_plane_platform.py -v`
Expected: 9 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py backend/tests/test_ctrl_plane_platform.py
git commit -m "feat(ctrl_plane): add Machine and Proxy heuristic checks"
```

---

### Task 7: Add pre-fetch for platform-layer data in ctrl_plane_agent node

**Files:**
- Modify: `backend/src/agents/cluster/ctrl_plane_agent.py:453-467` (the `ctrl_plane_agent()` function)

**Step 1: No new tests needed** — this is wiring existing methods into data_payload. The heuristic tests from Tasks 5-6 already validate the heuristic logic. We verify with a full regression run.

**Step 2: Add pre-fetch calls**

In `backend/src/agents/cluster/ctrl_plane_agent.py`, in the `ctrl_plane_agent()` function, after the existing OpenShift-specific block (after line 466 `data_payload["security_context_constraints"] = sccs.data`), add:

```python
        # Platform-layer pre-fetch
        cluster_version = await client.get_cluster_version()
        if cluster_version.data:
            data_payload["cluster_version"] = cluster_version.data[0]
        subscriptions = await client.list_subscriptions()
        if subscriptions.data:
            data_payload["subscriptions"] = subscriptions.data
        csvs = await client.list_csvs()
        if csvs.data:
            data_payload["csvs"] = csvs.data
        install_plans = await client.list_install_plans()
        if install_plans.data:
            data_payload["install_plans"] = install_plans.data
        machines = await client.list_machines()
        if machines.data:
            data_payload["machines"] = machines.data
        proxy_config = await client.get_proxy_config()
        if proxy_config.data:
            data_payload["proxy_config"] = proxy_config.data[0]
```

**Step 3: Run regression tests**

Run: `cd backend && python3 -m pytest tests/test_ctrl_plane_platform.py tests/test_ctrl_plane_heuristic.py -v`
Expected: All PASSED

**Step 4: Commit**

```bash
git add backend/src/agents/cluster/ctrl_plane_agent.py
git commit -m "feat(ctrl_plane): pre-fetch platform-layer data (ClusterVersion, OLM, Machine, Proxy)"
```

---

### Task 8: Add 6 new signal extraction rules

**Files:**
- Modify: `backend/src/agents/cluster/signal_normalizer.py:188-191`
- Create: `backend/tests/test_signal_normalizer_platform.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_signal_normalizer_platform.py`:

```python
"""Tests for platform-layer signal extraction rules."""

from src.agents.cluster.signal_normalizer import extract_signals


def _make_report(desc: str) -> list[dict]:
    return [{
        "domain": "ctrl_plane",
        "status": "SUCCESS",
        "anomalies": [{"description": desc, "evidence_ref": "test/ref", "severity": "high"}],
    }]


def test_cluster_upgrade_stuck_signal():
    signals = extract_signals(_make_report("ClusterVersion upgrade failing: unable to apply 4.14.3"))
    types = [s.signal_type for s in signals]
    assert "CLUSTER_UPGRADE_STUCK" in types


def test_cluster_upgrade_progressing_signal():
    signals = extract_signals(_make_report("Cluster version upgrade progressing to 4.14.3"))
    types = [s.signal_type for s in signals]
    assert "CLUSTER_UPGRADE_STUCK" in types


def test_olm_subscription_failure_signal():
    signals = extract_signals(_make_report("OLM Subscription jaeger state is UpgradePending"))
    types = [s.signal_type for s in signals]
    assert "OLM_SUBSCRIPTION_FAILURE" in types


def test_olm_csv_failure_signal():
    signals = extract_signals(_make_report("ClusterServiceVersion jaeger-operator.v1.51 phase is Failed"))
    types = [s.signal_type for s in signals]
    assert "OLM_CSV_FAILURE" in types


def test_machine_failure_signal():
    signals = extract_signals(_make_report("Machine worker-2 is not running (phase: Failed)"))
    types = [s.signal_type for s in signals]
    assert "MACHINE_FAILURE" in types


def test_proxy_misconfigured_signal():
    signals = extract_signals(_make_report("Proxy misconfigured — noProxy is empty, traffic may be blocked"))
    types = [s.signal_type for s in signals]
    assert "PROXY_MISCONFIGURED" in types
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_signal_normalizer_platform.py -v`
Expected: FAIL — new signal types not matched

**Step 3: Add signal extraction rules**

Add after the `PROBE_MISCONFIGURED` block (after line 190) in `backend/src/agents/cluster/signal_normalizer.py`, before the dedup section:

```python
            # Cluster version upgrade stuck/failing
            if "cluster version" in desc and ("failing" in desc or "stuck" in desc or "progressing" in desc):
                signals.append(_make_signal("CLUSTER_UPGRADE_STUCK", ref, domain, "deployment_status", namespace=ns))

            # OLM Subscription failure
            if "subscription" in desc and ("failed" in desc or "degraded" in desc or "pending" in desc):
                signals.append(_make_signal("OLM_SUBSCRIPTION_FAILURE", ref, domain, "deployment_status", namespace=ns))

            # OLM CSV failure
            if ("csv" in desc or "clusterserviceversion" in desc) and ("failed" in desc or "unknown" in desc or "replacing" in desc):
                signals.append(_make_signal("OLM_CSV_FAILURE", ref, domain, "deployment_status", namespace=ns))

            # OLM InstallPlan stuck
            if "installplan" in desc and ("stuck" in desc or "failed" in desc or "not approved" in desc):
                signals.append(_make_signal("OLM_INSTALLPLAN_STUCK", ref, domain, "deployment_status", namespace=ns))

            # Machine failure
            if "machine" in desc and ("failed" in desc or "provisioning" in desc or "not running" in desc):
                signals.append(_make_signal("MACHINE_FAILURE", ref, domain, "node_condition", namespace=ns))

            # Proxy misconfigured
            if "proxy" in desc and ("misconfigured" in desc or "unreachable" in desc or "blocked" in desc):
                signals.append(_make_signal("PROXY_MISCONFIGURED", ref, domain, "k8s_event_warning", namespace=ns))
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_signal_normalizer_platform.py -v`
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/signal_normalizer.py backend/tests/test_signal_normalizer_platform.py
git commit -m "feat(signals): add 6 platform-layer signal extraction rules"
```

---

### Task 9: Add 6 new failure patterns

**Files:**
- Modify: `backend/src/agents/cluster/failure_patterns.py:237-238`
- Create: `backend/tests/test_failure_patterns_platform.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_failure_patterns_platform.py`:

```python
"""Tests for platform-layer failure patterns."""

from src.agents.cluster.failure_patterns import match_patterns, FAILURE_PATTERNS
from src.agents.cluster.state import NormalizedSignal


def _signal(signal_type: str, resource_key: str = "test/ref") -> dict:
    return NormalizedSignal(
        signal_id="t1", signal_type=signal_type,
        resource_key=resource_key, source_domain="ctrl_plane",
        reliability=0.9, timestamp="2026-01-01T00:00:00Z",
    ).model_dump(mode="json")


def test_cluster_upgrade_failure_pattern():
    signals = [_signal("CLUSTER_UPGRADE_STUCK")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "CLUSTER_UPGRADE_FAILURE" in ids


def test_olm_operator_install_failure_pattern():
    signals = [_signal("OLM_SUBSCRIPTION_FAILURE"), _signal("OLM_CSV_FAILURE")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "OLM_OPERATOR_INSTALL_FAILURE" in ids


def test_olm_upgrade_stuck_pattern():
    signals = [_signal("OLM_SUBSCRIPTION_FAILURE"), _signal("OLM_INSTALLPLAN_STUCK")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "OLM_UPGRADE_STUCK" in ids


def test_machine_provisioning_failure_pattern():
    signals = [_signal("MACHINE_FAILURE"), _signal("NODE_NOT_READY")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "MACHINE_PROVISIONING_FAILURE" in ids


def test_proxy_blocks_image_pull_pattern():
    signals = [_signal("PROXY_MISCONFIGURED"), _signal("IMAGE_PULL_BACKOFF")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "PROXY_BLOCKS_IMAGE_PULL" in ids


def test_machine_node_mismatch_pattern():
    signals = [_signal("MACHINE_FAILURE")]
    matches = match_patterns([], signals)
    ids = [m.pattern_id for m in matches]
    assert "MACHINE_NODE_MISMATCH" in ids
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_failure_patterns_platform.py -v`
Expected: FAIL — patterns not found

**Step 3: Add failure patterns**

Add after the last `FailurePattern` entry (after `QUOTA_SCHEDULING_FAILURE`, before `]`) in `backend/src/agents/cluster/failure_patterns.py`:

```python
    FailurePattern(
        pattern_id="CLUSTER_UPGRADE_FAILURE",
        name="Cluster version upgrade stuck or failing",
        version="1.0", scope="cluster", priority=10,
        conditions=[{"signal": "CLUSTER_UPGRADE_STUCK"}],
        probable_causes=["Degraded operator blocking upgrade", "Insufficient node capacity", "etcd health issue"],
        known_fixes=["Check ClusterVersion conditions", "Check degraded operators", "Check node capacity"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="OLM_OPERATOR_INSTALL_FAILURE",
        name="OLM operator install/upgrade failure",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "OLM_SUBSCRIPTION_FAILURE"}, {"signal": "OLM_CSV_FAILURE"}],
        probable_causes=["Operator dependency missing", "RBAC insufficient for operator", "Operator image pull failure"],
        known_fixes=["Check CSV status and events", "Check operator namespace events", "Verify CatalogSource health"],
        severity="critical", confidence_boost=0.25,
    ),
    FailurePattern(
        pattern_id="OLM_UPGRADE_STUCK",
        name="OLM operator upgrade stuck",
        version="1.0", scope="cluster", priority=8,
        conditions=[{"signal": "OLM_SUBSCRIPTION_FAILURE"}, {"signal": "OLM_INSTALLPLAN_STUCK"}],
        probable_causes=["InstallPlan requires manual approval", "InstallPlan stuck in Installing", "CatalogSource not synced"],
        known_fixes=["Approve InstallPlan", "Delete and recreate Subscription", "Check CatalogSource pod health"],
        severity="high", confidence_boost=0.2,
    ),
    FailurePattern(
        pattern_id="MACHINE_PROVISIONING_FAILURE",
        name="Machine provisioning failure causing node loss",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "MACHINE_FAILURE"}, {"signal": "NODE_NOT_READY"}],
        probable_causes=["Cloud provider quota exhausted", "Machine spec invalid", "Network/subnet issue"],
        known_fixes=["Check Machine conditions", "Verify cloud provider quota", "Check MachineSet spec"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="PROXY_BLOCKS_IMAGE_PULL",
        name="Proxy misconfiguration blocking image pulls",
        version="1.0", scope="cluster", priority=9,
        conditions=[{"signal": "PROXY_MISCONFIGURED"}, {"signal": "IMAGE_PULL_BACKOFF"}],
        probable_causes=["noProxy missing registry CIDR", "trustedCA not configured for HTTPS interception", "Proxy blocking registry traffic"],
        known_fixes=["Add registry to noProxy", "Configure trustedCA bundle", "Test registry connectivity through proxy"],
        severity="critical", confidence_boost=0.3,
    ),
    FailurePattern(
        pattern_id="MACHINE_NODE_MISMATCH",
        name="Machine not in Running phase",
        version="1.0", scope="cluster", priority=7,
        conditions=[{"signal": "MACHINE_FAILURE"}],
        probable_causes=["Machine stuck in provisioning", "Cloud provider API error", "Machine deleted but not replaced"],
        known_fixes=["Check Machine object conditions", "Delete stuck Machine to trigger MachineSet replacement", "Check cloud provider console"],
        severity="high", confidence_boost=0.2,
    ),
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_failure_patterns_platform.py -v`
Expected: 6 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/failure_patterns.py backend/tests/test_failure_patterns_platform.py
git commit -m "feat(patterns): add 6 platform-layer failure patterns"
```

---

### Task 10: Add 4 new causal link types

**Files:**
- Modify: `backend/src/agents/cluster/synthesizer.py:36-54`
- Create: `backend/tests/test_causal_links_platform.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_causal_links_platform.py`:

```python
"""Tests for platform-layer causal link types."""

from src.agents.cluster.synthesizer import CONSTRAINED_LINK_TYPES


def test_cluster_upgrade_to_operator_degraded():
    assert "cluster_upgrade_stuck -> operator_degraded" in CONSTRAINED_LINK_TYPES


def test_olm_failure_to_operator_degraded():
    assert "olm_failure -> operator_degraded" in CONSTRAINED_LINK_TYPES


def test_machine_failure_to_node_not_ready():
    assert "machine_failure -> node_not_ready" in CONSTRAINED_LINK_TYPES


def test_proxy_misconfigured_to_image_pull_failure():
    assert "proxy_misconfigured -> image_pull_failure" in CONSTRAINED_LINK_TYPES
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_causal_links_platform.py -v`
Expected: FAIL — link types not found

**Step 3: Add causal link types**

Add before `"unknown"` (line 53) in `backend/src/agents/cluster/synthesizer.py` `CONSTRAINED_LINK_TYPES`:

```python
    "cluster_upgrade_stuck -> operator_degraded",
    "olm_failure -> operator_degraded",
    "machine_failure -> node_not_ready",
    "proxy_misconfigured -> image_pull_failure",
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_causal_links_platform.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/synthesizer.py backend/tests/test_causal_links_platform.py
git commit -m "feat(synthesizer): add 4 platform-layer causal link types"
```

---

### Task 11: Add 4 new proactive checks

**Files:**
- Modify: `backend/src/agents/cluster/proactive_analyzer.py`
- Create: `backend/tests/test_proactive_platform.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_proactive_platform.py`:

```python
"""Tests for platform-layer proactive checks."""

from src.agents.cluster.proactive_analyzer import (
    PROACTIVE_CHECKS, _EVALUATORS,
)


def test_cluster_version_check_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "cluster_version_check" in ids
    assert "cluster_version_check" in _EVALUATORS


def test_olm_subscription_health_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "olm_subscription_health" in ids
    assert "olm_subscription_health" in _EVALUATORS


def test_machine_health_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "machine_health" in ids
    assert "machine_health" in _EVALUATORS


def test_proxy_config_check_registered():
    ids = [c.check_id for c in PROACTIVE_CHECKS]
    assert "proxy_config_check" in ids
    assert "proxy_config_check" in _EVALUATORS


# Evaluator logic tests

def test_cluster_version_check_failing():
    evaluator = _EVALUATORS["cluster_version_check"]
    data = [{
        "conditions": [
            {"type": "Available", "status": "True"},
            {"type": "Failing", "status": "True", "message": "Unable to apply"},
        ],
        "version": "4.14.2",
        "desired": "4.14.3",
    }]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "critical"


def test_cluster_version_check_progressing():
    evaluator = _EVALUATORS["cluster_version_check"]
    data = [{
        "conditions": [
            {"type": "Available", "status": "True"},
            {"type": "Progressing", "status": "True"},
            {"type": "Failing", "status": "False"},
        ],
        "version": "4.14.2",
        "desired": "4.14.3",
    }]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "high"


def test_olm_subscription_health_upgrade_failed():
    evaluator = _EVALUATORS["olm_subscription_health"]
    data = [{"name": "jaeger", "namespace": "ns", "state": "UpgradeFailed", "currentCSV": "v2", "installedCSV": "v1"}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "critical"


def test_olm_subscription_health_csv_mismatch():
    evaluator = _EVALUATORS["olm_subscription_health"]
    data = [{"name": "jaeger", "namespace": "ns", "state": "UpgradePending", "currentCSV": "v2", "installedCSV": "v1"}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "high"


def test_machine_health_failed():
    evaluator = _EVALUATORS["machine_health"]
    data = [{"name": "worker-2", "phase": "Failed"}]
    findings = evaluator(data)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_machine_health_not_running():
    evaluator = _EVALUATORS["machine_health"]
    data = [{"name": "worker-3", "phase": "Provisioning"}]
    findings = evaluator(data)
    assert len(findings) == 1
    assert findings[0].severity == "high"


def test_proxy_config_no_noproxy():
    evaluator = _EVALUATORS["proxy_config_check"]
    data = [{"httpProxy": "http://proxy:3128", "httpsProxy": "", "noProxy": "", "trustedCA": ""}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "medium"


def test_proxy_config_no_trusted_ca():
    evaluator = _EVALUATORS["proxy_config_check"]
    data = [{"httpProxy": "", "httpsProxy": "http://proxy:3128", "noProxy": ".svc", "trustedCA": ""}]
    findings = evaluator(data)
    assert len(findings) >= 1
    assert findings[0].severity == "high"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_proactive_platform.py -v`
Expected: FAIL — checks not registered

**Step 3: Add evaluator functions and check definitions**

Add evaluator functions before the `_EVALUATORS` dict in `backend/src/agents/cluster/proactive_analyzer.py` (before line 948):

```python
def _check_cluster_version(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag ClusterVersion upgrade issues."""
    findings: list[ProactiveFinding] = []

    for cv in data:
        version = cv.get("version", "unknown")
        desired = cv.get("desired", version)
        conditions = cv.get("conditions", [])

        for cond in conditions:
            cond_type = cond.get("type", "")
            cond_status = cond.get("status", "")
            cond_msg = cond.get("message", "")

            if cond_type == "Failing" and cond_status == "True":
                findings.append(ProactiveFinding(
                    finding_id=_fid(),
                    check_type="cluster_version_check",
                    severity="critical",
                    lifecycle_state="NEW",
                    title=f"ClusterVersion upgrade failing: {version} → {desired}",
                    description=f"ClusterVersion upgrade is failing: {cond_msg}. The cluster may be in a degraded state.",
                    affected_resources=["clusterversion/version"],
                    affected_workloads=[],
                    days_until_impact=-1,
                    recommendation="Check ClusterVersion conditions and degraded operators. Run 'oc adm upgrade' for status.",
                    commands=["oc get clusterversion", "oc adm upgrade"],
                    dry_run_command="oc get clusterversion -o yaml",
                    confidence=0.95,
                    source="proactive",
                ))
            elif cond_type == "Progressing" and cond_status == "True" and version != desired:
                findings.append(ProactiveFinding(
                    finding_id=_fid(),
                    check_type="cluster_version_check",
                    severity="high",
                    lifecycle_state="NEW",
                    title=f"ClusterVersion upgrade in progress: {version} → {desired}",
                    description=f"Cluster is upgrading from {version} to {desired}. Monitor for stuck operators.",
                    affected_resources=["clusterversion/version"],
                    affected_workloads=[],
                    days_until_impact=-1,
                    recommendation="Monitor upgrade progress. Check for degraded operators that may block completion.",
                    commands=["oc get clusterversion", "oc get co | grep -v Available"],
                    dry_run_command="oc get clusterversion -o yaml",
                    confidence=0.90,
                    source="proactive",
                ))

    return findings


def _check_olm_subscription_health(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag OLM Subscriptions with upgrade issues."""
    findings: list[ProactiveFinding] = []

    for sub in data:
        sub_name = sub.get("name", "unknown")
        ns = sub.get("namespace", "")
        state = sub.get("state", "")
        current_csv = sub.get("currentCSV", "")
        installed_csv = sub.get("installedCSV", "")
        resource_key = f"subscription/{ns}/{sub_name}"

        if state == "UpgradeFailed":
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="olm_subscription_health",
                severity="critical",
                lifecycle_state="NEW",
                title=f"OLM Subscription '{sub_name}' upgrade failed",
                description=f"Subscription {resource_key} state is {state}. Current: {current_csv}, Installed: {installed_csv}.",
                affected_resources=[resource_key],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation=f"Check CSV status in namespace '{ns}'. Delete and recreate Subscription if needed.",
                commands=[f"oc get subscription {sub_name} -n {ns} -o yaml", f"oc get csv -n {ns}"],
                dry_run_command=f"oc get subscription {sub_name} -n {ns} -o yaml",
                confidence=0.90,
                source="proactive",
            ))
        elif current_csv and installed_csv and current_csv != installed_csv:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="olm_subscription_health",
                severity="high",
                lifecycle_state="NEW",
                title=f"OLM Subscription '{sub_name}' has pending upgrade",
                description=f"Subscription {resource_key}: currentCSV ({current_csv}) differs from installedCSV ({installed_csv}). State: {state}.",
                affected_resources=[resource_key],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation=f"Check InstallPlan approval status. Approve or investigate blocking issue.",
                commands=[f"oc get installplan -n {ns}", f"oc get csv -n {ns}"],
                dry_run_command=f"oc get subscription {sub_name} -n {ns} -o yaml",
                confidence=0.85,
                source="proactive",
            ))

    return findings


def _check_machine_health(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag Machines not in Running phase."""
    findings: list[ProactiveFinding] = []

    for machine in data:
        m_name = machine.get("name", "unknown")
        phase = machine.get("phase", "")
        resource_key = f"machine/{m_name}"

        if phase == "Failed":
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="machine_health",
                severity="critical",
                lifecycle_state="NEW",
                title=f"Machine '{m_name}' is in Failed phase",
                description=f"Machine {resource_key} has failed. This node will not join the cluster.",
                affected_resources=[resource_key],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation="Delete the failed Machine to trigger MachineSet replacement, or investigate cloud provider.",
                commands=[f"oc get machine {m_name} -n openshift-machine-api -o yaml", f"oc delete machine {m_name} -n openshift-machine-api"],
                dry_run_command=f"oc get machine {m_name} -n openshift-machine-api -o yaml",
                confidence=0.90,
                source="proactive",
            ))
        elif phase and phase != "Running":
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="machine_health",
                severity="high",
                lifecycle_state="NEW",
                title=f"Machine '{m_name}' is in {phase} phase",
                description=f"Machine {resource_key} is not Running (phase: {phase}). It may be stuck.",
                affected_resources=[resource_key],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation=f"Check Machine conditions and cloud provider status for '{m_name}'.",
                commands=[f"oc get machine {m_name} -n openshift-machine-api -o yaml"],
                dry_run_command=f"oc get machine {m_name} -n openshift-machine-api -o yaml",
                confidence=0.85,
                source="proactive",
            ))

    return findings


def _check_proxy_config(data: list[dict[str, Any]]) -> list[ProactiveFinding]:
    """Flag proxy misconfigurations."""
    findings: list[ProactiveFinding] = []

    for proxy in data:
        http_proxy = proxy.get("httpProxy", "")
        https_proxy = proxy.get("httpsProxy", "")
        no_proxy = proxy.get("noProxy", "")
        trusted_ca = proxy.get("trustedCA", "")

        if http_proxy and not no_proxy:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="proxy_config_check",
                severity="medium",
                lifecycle_state="NEW",
                title="Proxy configured but noProxy is empty",
                description=f"HTTP proxy ({http_proxy}) is set but noProxy is empty. Cluster-internal traffic may be incorrectly routed through the proxy.",
                affected_resources=["proxy/cluster"],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation="Set noProxy to include .cluster.local, .svc, pod CIDR, and service CIDR.",
                commands=["oc get proxy cluster -o yaml"],
                dry_run_command="oc get proxy cluster -o yaml",
                confidence=0.85,
                source="proactive",
            ))

        if https_proxy and not trusted_ca:
            findings.append(ProactiveFinding(
                finding_id=_fid(),
                check_type="proxy_config_check",
                severity="high",
                lifecycle_state="NEW",
                title="HTTPS proxy configured without trustedCA",
                description=f"HTTPS proxy ({https_proxy}) is configured but no trustedCA bundle is set. TLS interception may cause certificate verification failures.",
                affected_resources=["proxy/cluster"],
                affected_workloads=[],
                days_until_impact=-1,
                recommendation="Configure trustedCA with the proxy's CA certificate bundle.",
                commands=["oc get proxy cluster -o yaml", "oc get configmap user-ca-bundle -n openshift-config -o yaml"],
                dry_run_command="oc get proxy cluster -o yaml",
                confidence=0.80,
                source="proactive",
            ))

    return findings
```

Add 4 new `CheckDefinition` entries to `PROACTIVE_CHECKS` (after `ingress_spof`, before `]`):

```python
    CheckDefinition(
        check_id="cluster_version_check",
        name="ClusterVersion Upgrade Status",
        category="lifecycle",
        data_source="get_cluster_version",
        severity_rules=(
            SeverityRule(field="failing", op="==", value=True, severity="critical"),
            SeverityRule(field="progressing", op="==", value=True, severity="high"),
        ),
    ),
    CheckDefinition(
        check_id="olm_subscription_health",
        name="OLM Subscription Health",
        category="lifecycle",
        data_source="list_subscriptions",
        severity_rules=(
            SeverityRule(field="state", op="==", value="UpgradeFailed", severity="critical"),
            SeverityRule(field="csv_mismatch", op="==", value=True, severity="high"),
        ),
    ),
    CheckDefinition(
        check_id="machine_health",
        name="Machine Health",
        category="reliability",
        data_source="list_machines",
        severity_rules=(
            SeverityRule(field="phase", op="==", value="Failed", severity="critical"),
        ),
    ),
    CheckDefinition(
        check_id="proxy_config_check",
        name="Proxy Configuration",
        category="reliability",
        data_source="get_proxy_config",
        severity_rules=(
            SeverityRule(field="no_proxy_empty", op="==", value=True, severity="medium"),
            SeverityRule(field="no_trusted_ca", op="==", value=True, severity="high"),
        ),
    ),
```

Add 4 new entries to `_EVALUATORS` dict:

```python
    "cluster_version_check": _check_cluster_version,
    "olm_subscription_health": _check_olm_subscription_health,
    "machine_health": _check_machine_health,
    "proxy_config_check": _check_proxy_config,
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_proactive_platform.py -v`
Expected: 14 PASSED

**Step 5: Commit**

```bash
git add backend/src/agents/cluster/proactive_analyzer.py backend/tests/test_proactive_platform.py
git commit -m "feat(proactive): add ClusterVersion, OLM subscription, Machine health, Proxy config checks"
```

---

### Task 12: Full regression test

**Files:** None to modify

**Step 1: Run all tests**

Run: `cd backend && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -40`
Expected: All new tests pass (56+ new), no regressions in existing tests.

Specifically verify:
- `tests/test_cluster_client_platform.py` — 10 tests
- `tests/test_tool_subsets_platform.py` — 9 tests
- `tests/test_ctrl_plane_platform.py` — 9 tests
- `tests/test_signal_normalizer_platform.py` — 6 tests
- `tests/test_failure_patterns_platform.py` — 6 tests
- `tests/test_causal_links_platform.py` — 4 tests
- `tests/test_proactive_platform.py` — 14 tests
- All existing tests still pass

**Step 2: Commit (if any final fixes needed)**

No commit needed if all green.
