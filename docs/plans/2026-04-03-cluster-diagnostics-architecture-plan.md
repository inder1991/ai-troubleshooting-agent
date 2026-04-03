# Cluster Diagnostics Architecture Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all architectural gaps in the cluster diagnostic workflow so that cluster selection, credentials, metrics, and logs flow correctly end-to-end.

**Architecture:** Backend data model extended with role/auth_method/kubeconfig_content fields; frontend form gains ClusterProfileSelector (with status/env/role badges) and temporary cluster inline panel; execution gaps closed by wiring RBAC preflight into dispatch_router, fixing client lifecycle, adding Prometheus auto-detection, and injecting PrometheusClient + ElasticsearchClient into LangGraph config so domain agents can query real metrics.

**Tech Stack:** FastAPI + Python + LangGraph (backend), React + TypeScript + Tailwind (frontend), KubernetesClient, Prometheus HTTP API, Elasticsearch HTTP API.

**Design doc:** `docs/plans/2026-04-03-cluster-diagnostics-architecture-design.md`

---

## Task 1: Add `role` field to ClusterProfile + update profile API

**Files:**
- Modify: `backend/src/integrations/profile_models.py:51-87`
- Modify: `backend/src/api/routes_profiles.py:74-168`
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_cluster_routing.py`:
```python
def test_create_profile_with_role(client):
    resp = client.post("/api/v5/profiles", json={
        "name": "test-cluster",
        "cluster_url": "https://api.example.com:6443",
        "cluster_type": "openshift",
        "role": "cluster-admin",
    })
    assert resp.status_code == 200
    assert resp.json()["role"] == "cluster-admin"

def test_update_profile_role(client, created_profile_id):
    resp = client.put(f"/api/v5/profiles/{created_profile_id}", json={"role": "view"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "view"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_create_profile_with_role -xvs 2>&1 | tail -20
```
Expected: FAIL — `role` field not on ClusterProfile model.

**Step 3: Add `role` to ClusterProfile**

In `backend/src/integrations/profile_models.py`, add to the `ClusterProfile` class after the `environment` field (around line 58):
```python
role: str = ""   # RBAC role metadata, e.g. "cluster-admin", "view", "edit"
```

**Step 4: Update `create_profile()` in routes_profiles.py**

In `backend/src/api/routes_profiles.py`, locate `create_profile()` (around line 74). Find where `ClusterProfile(...)` is constructed and add `role=body.get("role", "")`. Also locate `update_profile()` (around line 126) and add handling for `role` in the update block:
```python
if "role" in body:
    updated_profile.role = body["role"]
```

**Step 5: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_create_profile_with_role tests/test_cluster_routing.py::test_update_profile_role -xvs 2>&1 | tail -20
```
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/integrations/profile_models.py backend/src/api/routes_profiles.py backend/tests/test_cluster_routing.py
git commit -m "feat(cluster): add role field to ClusterProfile model and profile API"
```

---

## Task 2: Extend ResolvedConnectionConfig with auth_method, kubeconfig_content, role

**Files:**
- Modify: `backend/src/integrations/connection_config.py:17-63`
- Modify: `backend/src/integrations/connection_config.py:66-254` (resolve_active_profile)
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write the failing test**

```python
def test_resolved_config_has_auth_method():
    from src.integrations.connection_config import ResolvedConnectionConfig
    cfg = ResolvedConnectionConfig(cluster_url="https://x.com", cluster_token="tok", auth_method="token")
    assert cfg.auth_method == "token"
    assert cfg.kubeconfig_content == ""
    assert cfg.role == ""

def test_resolved_config_kubeconfig_content():
    from src.integrations.connection_config import ResolvedConnectionConfig
    cfg = ResolvedConnectionConfig(auth_method="kubeconfig", kubeconfig_content="apiVersion: v1")
    assert cfg.auth_method == "kubeconfig"
    assert cfg.kubeconfig_content == "apiVersion: v1"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_resolved_config_has_auth_method -xvs 2>&1 | tail -10
```
Expected: FAIL — `auth_method` not on `ResolvedConnectionConfig`.

**Step 3: Add fields to ResolvedConnectionConfig**

In `backend/src/integrations/connection_config.py`, add these three fields to the `ResolvedConnectionConfig` dataclass after `verify_ssl`:
```python
# Auth method and kubeconfig content
auth_method: str = "token"          # "token" | "kubeconfig" | "service_account"
kubeconfig_content: str = ""        # raw kubeconfig YAML when auth_method == "kubeconfig"
role: str = ""                      # RBAC role metadata
```

**Step 4: Update `resolve_active_profile()` to populate new fields**

In `resolve_active_profile()`, find the block that constructs `ResolvedConnectionConfig(...)` from a profile (search for `cluster_token=`). Add:
```python
auth_method=profile.auth_method,
role=getattr(profile, "role", ""),
```
Note: `kubeconfig_content` is NOT read from the profile (it's temp-only). Leave it as `""`.

**Step 5: Update `_config_from_env()` to read new env vars**

Find `_config_from_env()` in the same file and add:
```python
auth_method=os.environ.get("K8S_AUTH_METHOD", "token"),
kubeconfig_content=os.environ.get("KUBECONFIG_CONTENT", ""),
```

**Step 6: Run tests to verify pass**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_resolved_config_has_auth_method tests/test_cluster_routing.py::test_resolved_config_kubeconfig_content -xvs 2>&1 | tail -10
```
Expected: PASS

**Step 7: Commit**

```bash
git add backend/src/integrations/connection_config.py backend/tests/test_cluster_routing.py
git commit -m "feat(cluster): add auth_method, kubeconfig_content, role to ResolvedConnectionConfig"
```

---

## Task 3: Update `create_cluster_client()` for kubeconfig content + temp file handling

**Files:**
- Modify: `backend/src/api/routes_v4.py:225-268`
- Modify: `backend/src/api/routes_v4.py:588-604` (finally block of run_cluster_diagnosis)
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write failing test**

```python
def test_create_cluster_client_kubeconfig_content(tmp_path, monkeypatch):
    """When auth_method=kubeconfig and kubeconfig_content is set, creates temp file."""
    from src.api.routes_v4 import create_cluster_client
    from src.integrations.connection_config import ResolvedConnectionConfig

    calls = []
    def mock_k8s_client(**kwargs):
        calls.append(kwargs)
        return object()
    monkeypatch.setattr("src.api.routes_v4.KubernetesClient", mock_k8s_client)

    cfg = ResolvedConnectionConfig(
        auth_method="kubeconfig",
        kubeconfig_content="apiVersion: v1\nkind: Config\n",
    )
    client, temp_path = create_cluster_client(cfg)
    assert temp_path is not None
    assert "kubeconfig_path" in calls[0]
    # Cleanup
    if temp_path:
        import os; os.unlink(temp_path)
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_create_cluster_client_kubeconfig_content -xvs 2>&1 | tail -15
```
Expected: FAIL

**Step 3: Rewrite `create_cluster_client()` in `routes_v4.py`**

Replace the current `create_cluster_client()` (lines 225–268) with:

```python
def create_cluster_client(connection_config=None):
    """
    Create a cluster client from connection config.
    Returns (client, temp_kubeconfig_path or None).
    Resolution order:
    1. bearer token (cluster_url + cluster_token)
    2. kubeconfig content (write to temp file)
    3. KUBECONFIG env var or ~/.kube/config
    4. MockClusterClient
    """
    import tempfile, os
    from pathlib import Path

    temp_path = None
    cluster_url = getattr(connection_config, "cluster_url", "") if connection_config else ""
    cluster_token = getattr(connection_config, "cluster_token", "") if connection_config else ""
    auth_method = getattr(connection_config, "auth_method", "token") if connection_config else "token"
    kubeconfig_content = getattr(connection_config, "kubeconfig_content", "") if connection_config else ""
    verify_ssl = getattr(connection_config, "verify_ssl", False) if connection_config else False

    # 1. Bearer token
    if cluster_url or cluster_token:
        try:
            return KubernetesClient(
                api_url=cluster_url or None,
                token=cluster_token or None,
                verify_ssl=verify_ssl,
            ), None
        except Exception as e:
            logger.warning("Failed to create KubernetesClient with bearer token: %s", e)

    # 2. Kubeconfig content (temp file)
    if auth_method == "kubeconfig" and kubeconfig_content:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write(kubeconfig_content)
                temp_path = f.name
            return KubernetesClient(kubeconfig_path=temp_path), temp_path
        except Exception as e:
            logger.warning("Failed to create KubernetesClient from kubeconfig content: %s", e)
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
                temp_path = None

    # 3. KUBECONFIG env var or ~/.kube/config
    kubeconfig_env = os.environ.get("KUBECONFIG", "")
    default_kubeconfig = Path.home() / ".kube" / "config"
    if kubeconfig_env or default_kubeconfig.exists():
        try:
            kubeconfig_path = kubeconfig_env or str(default_kubeconfig)
            return KubernetesClient(kubeconfig_path=kubeconfig_path), None
        except Exception as e:
            logger.warning("Failed to create KubernetesClient from kubeconfig file: %s", e)

    # 4. Mock fallback
    logger.info("No cluster credentials found, using MockClusterClient")
    return MockClusterClient(platform="openshift"), None
```

**Step 4: Update all callers of `create_cluster_client()`**

Search routes_v4.py for all calls to `create_cluster_client(`. They currently unpack a single return value. Update them to unpack a tuple:
```python
cluster_client, kubeconfig_temp_path = create_cluster_client(connection_config)
```
Store `kubeconfig_temp_path` in the session dict:
```python
sessions[session_id]["kubeconfig_temp_path"] = kubeconfig_temp_path
```

**Step 5: Clean up temp kubeconfig in `run_cluster_diagnosis` finally block**

In the `finally` block of `run_cluster_diagnosis` (around line 602), add BEFORE `await cluster_client.close()`:
```python
temp_path = sessions.get(session_id, {}).pop("kubeconfig_temp_path", None)
if temp_path:
    from pathlib import Path
    Path(temp_path).unlink(missing_ok=True)
```

**Step 6: Run tests**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py -xvs -k "cluster_client" 2>&1 | tail -20
```
Expected: PASS

**Step 7: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_routing.py
git commit -m "feat(cluster): support kubeconfig content in create_cluster_client with temp file handling"
```

---

## Task 4: Extend StartSessionRequest with new fields + update start_session()

**Files:**
- Modify: `backend/src/api/routes_v4.py:65-86` (StartSessionRequest)
- Modify: `backend/src/api/routes_v4.py:295-355` (start_session cluster_diagnostics branch)
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write failing test**

```python
def test_start_session_with_auth_method_and_elk_index(client):
    resp = client.post("/api/v4/session/start", json={
        "capability": "cluster_diagnostics",
        "cluster_url": "https://api.example.com:6443",
        "auth_method": "token",
        "auth_token": "mytoken",
        "elk_index": "cluster-logs-*",
        "role": "cluster-admin",
    })
    assert resp.status_code == 200
    sid = resp.json()["session_id"]
    assert sid
    # elk_index stored in session
    from src.api.routes_v4 import sessions
    assert sessions[sid].get("elk_index") == "cluster-logs-*"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_start_session_with_auth_method_and_elk_index -xvs 2>&1 | tail -15
```
Expected: FAIL

**Step 3: Add fields to StartSessionRequest**

In `backend/src/api/routes_v4.py`, update `StartSessionRequest` (around line 65) to add:
```python
kubeconfig_content: Optional[str] = Field(default=None, alias="kubeconfig_content")
role: Optional[str] = Field(default=None, alias="role")
# Note: auth_method already exists (line 75), elk_index already exists (line 67)
# Confirm elk_index default is None (not "app-logs-*") for cluster_diagnostics:
# Change existing: elkIndex: str = Field(default="app-logs-*", alias="elk_index")
# To:             elkIndex: Optional[str] = Field(default=None, alias="elk_index")
```

**Step 4: Update the `cluster_diagnostics` branch in `start_session()`**

Locate the ad-hoc config block inside `start_session()` where `ResolvedConnectionConfig(...)` is built for ad-hoc cluster access (search for `"ad_hoc"` or `auth_token`). Add the new fields:
```python
connection_config = ResolvedConnectionConfig(
    cluster_url=request.clusterUrl or "",
    cluster_token=request.authToken or "",
    auth_method=request.authMethod or "token",
    kubeconfig_content=request.kubeconfig_content or "",
    role=request.role or "",
    verify_ssl=False,
)
```

Store elk_index in session:
```python
sessions[session_id]["elk_index"] = request.elkIndex or ""
```

**Step 5: Run test**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_start_session_with_auth_method_and_elk_index -xvs 2>&1 | tail -15
```
Expected: PASS

**Step 6: Run full test suite to check for regressions**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py -x 2>&1 | tail -20
```

**Step 7: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_routing.py
git commit -m "feat(cluster): add auth_method, kubeconfig_content, role, elk_index to StartSessionRequest"
```

---

## Task 5: Add POST /api/v5/profiles/test-connection endpoint

**Files:**
- Modify: `backend/src/api/routes_profiles.py`
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write failing test**

```python
def test_test_connection_endpoint_connected(client, monkeypatch):
    """POST /api/v5/profiles/test-connection returns status=connected."""
    import time

    async def mock_detect_platform(self):
        return {"platform": "openshift", "version": "4.14.0"}

    async def mock_get_api_health(self):
        return {"healthy": True}

    async def mock_close(self):
        pass

    monkeypatch.setattr("src.agents.cluster_client.k8s_client.KubernetesClient.detect_platform", mock_detect_platform)
    monkeypatch.setattr("src.agents.cluster_client.k8s_client.KubernetesClient.close", mock_close)

    resp = client.post("/api/v5/profiles/test-connection", json={
        "cluster_url": "https://api.example.com:6443",
        "auth_method": "token",
        "credential": "mytoken",
        "verify_ssl": False,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "connected"
    assert body["platform"] == "openshift"
    assert body["version"] == "4.14.0"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_test_connection_endpoint_connected -xvs 2>&1 | tail -15
```
Expected: 404 — endpoint does not exist.

**Step 3: Add Pydantic models and endpoint to routes_profiles.py**

In `backend/src/api/routes_profiles.py`, add after the existing imports:

```python
class TestConnectionRequest(BaseModel):
    cluster_url: str
    auth_method: str = "token"
    credential: str = ""       # token string or kubeconfig YAML content
    verify_ssl: bool = False


class TestConnectionResponse(BaseModel):
    status: str                # "connected" | "unreachable" | "auth_failed" | "permission_denied"
    platform: str = ""
    version: str = ""
    latency_ms: int = 0
    error: Optional[str] = None
```

Add the endpoint (before the last router line):

```python
@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(body: TestConnectionRequest):
    """Test cluster connectivity without creating a profile."""
    import time, tempfile
    from pathlib import Path
    from src.agents.cluster_client.k8s_client import KubernetesClient
    from src.agents.cluster_client.mock_client import MockClusterClient

    temp_path = None
    start = time.monotonic()
    try:
        if body.auth_method == "kubeconfig" and body.credential:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                f.write(body.credential)
                temp_path = f.name
            client = KubernetesClient(kubeconfig_path=temp_path)
        else:
            client = KubernetesClient(
                api_url=body.cluster_url,
                token=body.credential or None,
                verify_ssl=body.verify_ssl,
            )

        platform_info = await client.detect_platform()
        latency_ms = int((time.monotonic() - start) * 1000)
        await client.close()
        return TestConnectionResponse(
            status="connected",
            platform=platform_info.get("platform", ""),
            version=platform_info.get("version", ""),
            latency_ms=latency_ms,
        )

    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        err_str = str(e).lower()
        if "401" in err_str or "unauthorized" in err_str:
            status = "auth_failed"
        elif "403" in err_str or "forbidden" in err_str:
            status = "permission_denied"
        else:
            status = "unreachable"
        return TestConnectionResponse(status=status, latency_ms=latency_ms, error=str(e))
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
```

**Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_test_connection_endpoint_connected -xvs 2>&1 | tail -15
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_profiles.py backend/tests/test_cluster_routing.py
git commit -m "feat(cluster): add POST /api/v5/profiles/test-connection endpoint"
```

---

## Task 6: Wire RBAC preflight results into dispatch_router

**Files:**
- Modify: `backend/src/agents/cluster/graph.py:85-117` (dispatch_router function)
- Test: `backend/tests/test_cluster_graph.py`

**Step 1: Write failing test**

```python
def test_dispatch_router_skips_nodes_when_nodes_rbac_denied():
    """dispatch_router excludes node_agent domain when 'nodes' permission is denied."""
    from src.agents.cluster.graph import dispatch_router

    state = {
        "diagnostic_scope": None,
        "rbac_check": {"granted": ["pods", "events"], "denied": ["nodes"]},
    }
    result = dispatch_router(state)
    assert "node" not in result["dispatch_domains"]

def test_dispatch_router_skips_storage_when_pvc_denied():
    from src.agents.cluster.graph import dispatch_router

    state = {
        "diagnostic_scope": None,
        "rbac_check": {"granted": ["nodes", "pods"], "denied": ["persistentvolumeclaims"]},
    }
    result = dispatch_router(state)
    assert "storage" not in result["dispatch_domains"]

def test_dispatch_router_no_rbac_check_runs_all():
    from src.agents.cluster.graph import dispatch_router

    state = {"diagnostic_scope": None, "rbac_check": None}
    result = dispatch_router(state)
    assert "node" in result["dispatch_domains"]
    assert "storage" in result["dispatch_domains"]
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py::test_dispatch_router_skips_nodes_when_nodes_rbac_denied -xvs 2>&1 | tail -10
```
Expected: FAIL

**Step 3: Update `dispatch_router` in graph.py**

Replace the `dispatch_router` function (lines 90–117):

```python
# Mapping from denied resource name → domains to skip
_RBAC_DOMAIN_GATES = {
    "nodes": ["node"],
    "pods": ["ctrl_plane", "node"],
    "routes": ["network"],
    "persistentvolumeclaims": ["storage"],
}


def dispatch_router(state: dict) -> dict:
    """Determine which domain agents should run based on DiagnosticScope and RBAC."""
    scope_data = state.get("diagnostic_scope")
    rbac_check = state.get("rbac_check") or {}
    denied_resources = set(rbac_check.get("denied", []))

    if not scope_data:
        domains = list(ALL_DOMAINS)
    else:
        scope = DiagnosticScope(**scope_data)
        if scope.level == "cluster":
            domains = list(scope.domains)
        elif scope.level == "namespace":
            domains = list(scope.domains)
            if not scope.include_control_plane:
                domains = [d for d in domains if d != "ctrl_plane"]
        elif scope.level == "workload":
            domains = [d for d in scope.domains if d in ("node", "network")]
            if scope.include_control_plane:
                domains.append("ctrl_plane")
        elif scope.level == "component":
            domains = list(scope.domains)
        else:
            domains = list(ALL_DOMAINS)

    # Gate domains based on RBAC denials
    rbac_skipped = []
    for resource, skipped_domains in _RBAC_DOMAIN_GATES.items():
        if resource in denied_resources:
            for d in skipped_domains:
                if d in domains:
                    domains.remove(d)
                    rbac_skipped.append({"domain": d, "reason": f"{resource} permission denied"})

    scope_coverage = len(domains) / len(ALL_DOMAINS) if ALL_DOMAINS else 1.0
    result = {"dispatch_domains": domains, "scope_coverage": scope_coverage}
    if rbac_skipped:
        result["rbac_skipped"] = rbac_skipped
    return result
```

Also add `rbac_skipped` to the State TypedDict (around line 83):
```python
rbac_skipped: Annotated[list[dict], operator.add]
```

**Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py -xvs -k "dispatch_router" 2>&1 | tail -20
```
Expected: PASS

**Step 5: Run full graph test suite**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py -x 2>&1 | tail -10
```

**Step 6: Commit**

```bash
git add backend/src/agents/cluster/graph.py backend/tests/test_cluster_graph.py
git commit -m "feat(cluster): wire RBAC preflight results into dispatch_router to skip denied domains"
```

---

## Task 7: Fix client lifecycle — store cluster_client in session, no close() at end

**Files:**
- Modify: `backend/src/api/routes_v4.py:503-604` (run_cluster_diagnosis)
- Modify: `backend/src/api/routes_v4.py` (session cleanup logic)
- Test: `backend/tests/test_cluster_routing.py`

**Step 1: Write failing test**

```python
def test_cluster_client_stored_in_session_after_diagnosis(client, mock_cluster_client):
    """cluster_client should be stored in session after diagnosis runs."""
    resp = client.post("/api/v4/session/start", json={
        "capability": "cluster_diagnostics",
        "cluster_url": "https://api.example.com:6443",
        "auth_token": "tok",
    })
    sid = resp.json()["session_id"]
    # Give background task time to start
    import time; time.sleep(0.1)
    from src.api.routes_v4 import sessions
    assert "cluster_client" in sessions.get(sid, {})
```

**Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py::test_cluster_client_stored_in_session_after_diagnosis -xvs 2>&1 | tail -10
```

**Step 3: Update `run_cluster_diagnosis` to store client, not close it**

In `run_cluster_diagnosis` (around line 503), change the function signature to also accept `connection_config`:
```python
async def run_cluster_diagnosis(session_id, graph, cluster_client, emitter, scan_mode="diagnostic", connection_config=None):
```

At the start of the `try` block, store the client in the session:
```python
sessions[session_id]["cluster_client"] = cluster_client
```

In the `finally` block, **remove** `await cluster_client.close()`.

Instead, add a `get_or_create_cluster_client(session_id)` helper function ABOVE `run_cluster_diagnosis`:
```python
async def get_or_create_cluster_client(session_id: str):
    """Return cached cluster client from session, or create a new one."""
    session = sessions.get(session_id, {})
    client = session.get("cluster_client")
    if client is not None:
        return client
    connection_config = session.get("connection_config")
    if connection_config:
        client, temp_path = create_cluster_client(connection_config)
        sessions[session_id]["cluster_client"] = client
        if temp_path:
            sessions[session_id]["kubeconfig_temp_path"] = temp_path
        return client
    return None
```

**Step 4: Add client cleanup to session delete endpoint**

Find the session DELETE endpoint (search for `delete_session` or `DELETE /api/v4/session`). Add cleanup:
```python
client = sessions[session_id].get("cluster_client")
if client:
    try:
        await client.close()
    except Exception:
        pass
temp_path = sessions[session_id].get("kubeconfig_temp_path")
if temp_path:
    from pathlib import Path
    Path(temp_path).unlink(missing_ok=True)
```

**Step 5: Run test**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py -xvs -k "cluster_client" 2>&1 | tail -15
```
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_routing.py
git commit -m "feat(cluster): store cluster_client in session for reuse, remove close() from run_cluster_diagnosis"
```

---

## Task 8: Add cluster metadata to graph state + connection resilience retry wrapper

**Files:**
- Modify: `backend/src/api/routes_v4.py` (run_cluster_diagnosis initial_state)
- Create: `backend/src/agents/cluster/retry_utils.py`
- Test: `backend/tests/test_cluster_graph.py`

**Step 1: Write failing test for cluster metadata in state**

```python
def test_initial_state_includes_cluster_url():
    """run_cluster_diagnosis should put cluster_url in initial_state."""
    # This tests the state construction logic; inspect the initial_state dict
    from unittest.mock import MagicMock, AsyncMock, patch
    import asyncio

    mock_client = MagicMock()
    mock_client.detect_platform = AsyncMock(return_value={"platform": "openshift", "version": "4.14"})
    mock_client.list_namespaces = AsyncMock(return_value=MagicMock(data=["default"]))
    mock_client.list_nodes = AsyncMock(return_value=MagicMock(data=[]))
    mock_client.close = AsyncMock()

    captured_state = {}
    async def mock_graph_invoke(state, config):
        captured_state.update(state)
        return state

    mock_graph = MagicMock()
    mock_graph.ainvoke = mock_graph_invoke

    from src.api.routes_v4 import run_cluster_diagnosis, sessions
    from src.integrations.connection_config import ResolvedConnectionConfig

    session_id = "test-meta-session"
    cfg = ResolvedConnectionConfig(cluster_url="https://api.example.com:6443", role="cluster-admin")
    sessions[session_id] = {"diagnostic_scope": {}, "connection_config": cfg}

    asyncio.get_event_loop().run_until_complete(
        run_cluster_diagnosis(session_id, mock_graph, mock_client, MagicMock(), connection_config=cfg)
    )
    assert captured_state.get("cluster_url") == "https://api.example.com:6443"
    assert captured_state.get("cluster_role") == "cluster-admin"
```

**Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py::test_initial_state_includes_cluster_url -xvs 2>&1 | tail -10
```

**Step 3: Add cluster metadata fields to initial_state in run_cluster_diagnosis**

In `run_cluster_diagnosis`, after existing `initial_state` dict construction, add:
```python
initial_state["cluster_url"] = getattr(connection_config, "cluster_url", "") if connection_config else ""
initial_state["cluster_type"] = getattr(connection_config, "cluster_type", "") if connection_config else ""
initial_state["cluster_role"] = getattr(connection_config, "role", "") if connection_config else ""
```

Also add these fields to the `State` TypedDict in `graph.py`:
```python
cluster_url: str
cluster_type: str
cluster_role: str
```

**Step 4: Create retry utility**

Create `backend/src/agents/cluster/retry_utils.py`:
```python
"""Retry wrapper for cluster client calls."""
from __future__ import annotations
import asyncio
import functools
import logging

logger = logging.getLogger(__name__)


def with_retry(retries: int = 2, backoff: float = 1.5):
    """Decorator: retry async function on exception with exponential backoff."""
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < retries:
                        wait = backoff ** attempt
                        logger.warning(
                            "Cluster call %s failed (attempt %d/%d), retrying in %.1fs: %s",
                            fn.__name__, attempt + 1, retries + 1, wait, exc,
                        )
                        await asyncio.sleep(wait)
            raise last_exc
        return wrapper
    return decorator
```

**Step 5: Write and run test for retry**

```python
def test_with_retry_succeeds_on_second_attempt():
    import asyncio
    from src.agents.cluster.retry_utils import with_retry

    call_count = [0]

    @with_retry(retries=2, backoff=0.01)
    async def flaky():
        call_count[0] += 1
        if call_count[0] < 2:
            raise ConnectionError("transient")
        return "ok"

    result = asyncio.get_event_loop().run_until_complete(flaky())
    assert result == "ok"
    assert call_count[0] == 2
```

```bash
cd backend && python -m pytest tests/test_cluster_graph.py -xvs -k "retry" 2>&1 | tail -10
```
Expected: PASS

**Step 6: Run tests**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py -x 2>&1 | tail -10
```

**Step 7: Commit**

```bash
git add backend/src/api/routes_v4.py backend/src/agents/cluster/graph.py backend/src/agents/cluster/retry_utils.py backend/tests/test_cluster_graph.py
git commit -m "feat(cluster): add cluster metadata to graph state + connection resilience retry utility"
```

---

## Task 9: Prometheus auto-detection from cluster

**Files:**
- Create: `backend/src/agents/cluster/prometheus_detector.py`
- Modify: `backend/src/api/routes_v4.py` (run_cluster_diagnosis — call detector before graph)
- Test: `backend/tests/test_cluster_graph.py`

**Step 1: Write failing test**

```python
def test_detect_prometheus_openshift():
    """detect_prometheus_endpoint returns thanos-querier route URL for OpenShift."""
    import asyncio
    from unittest.mock import MagicMock, AsyncMock
    from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

    mock_client = MagicMock()
    mock_client.get_routes = AsyncMock(return_value=MagicMock(data=[
        {"namespace": "openshift-monitoring", "name": "thanos-querier", "host": "thanos.apps.cluster.example.com"},
    ]))

    url = asyncio.get_event_loop().run_until_complete(
        detect_prometheus_endpoint(mock_client, "openshift")
    )
    assert url == "https://thanos.apps.cluster.example.com"

def test_detect_prometheus_returns_empty_on_no_routes():
    import asyncio
    from unittest.mock import MagicMock, AsyncMock
    from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

    mock_client = MagicMock()
    mock_client.get_routes = AsyncMock(return_value=MagicMock(data=[]))
    mock_client.list_services = AsyncMock(return_value=MagicMock(data=[]))

    url = asyncio.get_event_loop().run_until_complete(
        detect_prometheus_endpoint(mock_client, "kubernetes")
    )
    assert url == ""
```

**Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py::test_detect_prometheus_openshift -xvs 2>&1 | tail -10
```

**Step 3: Create `prometheus_detector.py`**

Create `backend/src/agents/cluster/prometheus_detector.py`:

```python
"""Prometheus endpoint auto-detection from cluster routes/services."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

_OPENSHIFT_PROMETHEUS_NAMES = ("thanos-querier", "prometheus-k8s")
_K8S_MONITORING_NAMESPACES = ("monitoring", "kube-monitoring", "prometheus", "kube-system")


async def detect_prometheus_endpoint(cluster_client, platform: str) -> str:
    """
    Auto-detect Prometheus endpoint from cluster.
    Returns URL string or "" if not found.
    """
    try:
        if platform == "openshift":
            return await _detect_openshift(cluster_client)
        else:
            return await _detect_kubernetes(cluster_client)
    except Exception as exc:
        logger.warning("Prometheus auto-detection failed: %s", exc)
        return ""


async def _detect_openshift(cluster_client) -> str:
    """Detect thanos-querier or prometheus-k8s route in openshift-monitoring."""
    try:
        result = await cluster_client.get_routes(namespace="openshift-monitoring")
        routes = result.data if hasattr(result, "data") else []
        for route in routes:
            name = route.get("name", "") if isinstance(route, dict) else getattr(route, "name", "")
            host = route.get("host", "") if isinstance(route, dict) else getattr(route, "host", "")
            ns = route.get("namespace", "") if isinstance(route, dict) else getattr(route, "namespace", "")
            if ns == "openshift-monitoring" and name in _OPENSHIFT_PROMETHEUS_NAMES and host:
                return f"https://{host}"
    except Exception as exc:
        logger.debug("OpenShift route detection failed: %s", exc)
    return ""


async def _detect_kubernetes(cluster_client) -> str:
    """Detect prometheus service in common monitoring namespaces."""
    for ns in _K8S_MONITORING_NAMESPACES:
        try:
            result = await cluster_client.list_services(namespace=ns)
            services = result.data if hasattr(result, "data") else []
            for svc in services:
                name = svc.get("name", "") if isinstance(svc, dict) else getattr(svc, "name", "")
                if "prometheus" in name.lower():
                    # Prefer LoadBalancer IP, else NodePort
                    ip = svc.get("external_ip", "") if isinstance(svc, dict) else getattr(svc, "external_ip", "")
                    port = svc.get("port", 9090) if isinstance(svc, dict) else getattr(svc, "port", 9090)
                    if ip:
                        return f"http://{ip}:{port}"
        except Exception:
            continue
    return ""
```

**Step 4: Integrate detection into `run_cluster_diagnosis`**

In `run_cluster_diagnosis`, after `initial_state["platform"]` is set and before `graph.ainvoke`, add:

```python
from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint

# Resolve Prometheus URL: profile first, then auto-detect
prometheus_url = getattr(connection_config, "prometheus_url", "") if connection_config else ""
if not prometheus_url:
    prometheus_url = await detect_prometheus_endpoint(cluster_client, initial_state["platform"])
    if prometheus_url:
        logger.info("Auto-detected Prometheus at %s", prometheus_url)
        sessions[session_id]["prometheus_url"] = prometheus_url
```

**Step 5: Run tests**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py -xvs -k "prometheus" 2>&1 | tail -15
```
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/agents/cluster/prometheus_detector.py backend/src/api/routes_v4.py backend/tests/test_cluster_graph.py
git commit -m "feat(cluster): auto-detect Prometheus endpoint from cluster routes/services"
```

---

## Task 10: Inject PrometheusClient and ElasticsearchClient into LangGraph config

**Files:**
- Modify: `backend/src/api/routes_v4.py` (run_cluster_diagnosis config block)
- Test: `backend/tests/test_cluster_graph.py`

**Step 1: Write failing test**

```python
def test_prometheus_client_injected_when_url_available():
    """When prometheus_url is resolved, a PrometheusClient is injected into config."""
    import asyncio
    from unittest.mock import MagicMock, AsyncMock, patch

    captured_config = {}

    async def mock_graph_invoke(state, config):
        captured_config.update(config.get("configurable", {}))
        return state

    mock_graph = MagicMock()
    mock_graph.ainvoke = mock_graph_invoke
    mock_client = MagicMock()
    mock_client.detect_platform = AsyncMock(return_value={"platform": "kubernetes", "version": "1.28"})
    mock_client.list_namespaces = AsyncMock(return_value=MagicMock(data=["default"]))
    mock_client.list_nodes = AsyncMock(return_value=MagicMock(data=[]))
    mock_client.close = AsyncMock()

    from src.api.routes_v4 import run_cluster_diagnosis, sessions
    from src.integrations.connection_config import ResolvedConnectionConfig

    session_id = "test-prom-inject"
    cfg = ResolvedConnectionConfig(cluster_url="https://x.com", prometheus_url="http://prom:9090")
    sessions[session_id] = {"diagnostic_scope": {}, "connection_config": cfg, "elk_index": ""}

    with patch("src.agents.cluster.prometheus_detector.detect_prometheus_endpoint", AsyncMock(return_value="")):
        asyncio.get_event_loop().run_until_complete(
            run_cluster_diagnosis(session_id, mock_graph, mock_client, MagicMock(), connection_config=cfg)
        )

    assert "prometheus_client" in captured_config
    assert captured_config["prometheus_client"] is not None
    assert "elk_client" in captured_config
    assert captured_config["elk_client"] is None  # no elk_index
```

**Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py::test_prometheus_client_injected_when_url_available -xvs 2>&1 | tail -15
```

**Step 3: Check what PrometheusClient and ElasticsearchClient look like**

Read the first 60 lines of `backend/src/agents/metrics_agent.py` and `backend/src/agents/log_agent.py` to find the class constructors. Then update `run_cluster_diagnosis` config block:

```python
# Resolve ELK index and URL
elk_index = sessions.get(session_id, {}).get("elk_index", "")
elk_url = getattr(connection_config, "elasticsearch_url", "") if connection_config else ""
if elk_index and not elk_url:
    # Try global integrations
    try:
        from src.integrations.profile_store import ProfileStore
        store = ProfileStore()
        integrations = store.list_global_integrations()
        elk_integration = next((i for i in integrations if getattr(i, "service_type", "") == "elk"), None)
        elk_url = getattr(elk_integration, "url", "") if elk_integration else ""
    except Exception:
        pass
    if not elk_url:
        elk_index = ""  # Skip ELK if no URL available

# Build prometheus_client and elk_client
from src.agents.metrics_agent import PrometheusClient
from src.agents.log_agent import ElasticsearchClient

cluster_token = getattr(connection_config, "cluster_token", "") if connection_config else ""
verify_ssl = getattr(connection_config, "verify_ssl", False) if connection_config else False

prometheus_client = None
if prometheus_url:
    try:
        prometheus_client = PrometheusClient(
            url=prometheus_url,
            token=cluster_token,  # OpenShift reuses cluster token for Prometheus
            verify_ssl=verify_ssl,
        )
    except Exception as exc:
        logger.warning("Failed to create PrometheusClient: %s", exc)

elk_client = None
if elk_url and elk_index:
    try:
        elk_auth_method = getattr(connection_config, "elasticsearch_auth_method", "none") if connection_config else "none"
        elk_creds = getattr(connection_config, "elasticsearch_credentials", "") if connection_config else ""
        elk_client = ElasticsearchClient(
            url=elk_url,
            auth_method=elk_auth_method,
            credentials=elk_creds,
        )
    except Exception as exc:
        logger.warning("Failed to create ElasticsearchClient: %s", exc)

config = {
    "configurable": {
        "cluster_client": cluster_client,
        "prometheus_client": prometheus_client,
        "elk_client": elk_client,
        "elk_index": elk_index,
        "emitter": emitter,
        "budget": budget,
        "telemetry": telemetry,
    }
}
```

**Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py::test_prometheus_client_injected_when_url_available -xvs 2>&1 | tail -15
```

Adjust PrometheusClient/ElasticsearchClient constructor args to match actual signatures if test fails for wrong reason.

**Step 5: Run full suite**

```bash
cd backend && python -m pytest tests/test_cluster_graph.py tests/test_cluster_routing.py -x 2>&1 | tail -10
```

**Step 6: Commit**

```bash
git add backend/src/api/routes_v4.py backend/tests/test_cluster_graph.py
git commit -m "feat(cluster): inject PrometheusClient and ElasticsearchClient into LangGraph config"
```

---

## Task 11: Update node_agent to use injected prometheus_client

**Files:**
- Modify: `backend/src/agents/cluster/node_agent.py`
- Test: `backend/tests/test_cluster_agents.py`

**Context:** node_agent signature is `async def node_agent(state, config)`. It already extracts `cluster_client` from `config["configurable"]`. We add Prometheus queries for node CPU/memory utilization after the existing cluster data collection.

**Step 1: Write failing test**

```python
def test_node_agent_uses_prometheus_client_when_available():
    """node_agent should call prometheus_client.query() when client is injected."""
    import asyncio
    from unittest.mock import MagicMock, AsyncMock

    mock_prom = MagicMock()
    mock_prom.query = MagicMock(return_value={"data": {"result": []}})

    mock_cluster = MagicMock()
    mock_cluster.list_nodes = AsyncMock(return_value=MagicMock(data=[]))
    mock_cluster.list_pods = AsyncMock(return_value=MagicMock(data=[]))
    mock_cluster.list_events = AsyncMock(return_value=MagicMock(data=[]))
    mock_cluster.list_deployments = AsyncMock(return_value=MagicMock(data=[]))

    config = {"configurable": {
        "cluster_client": mock_cluster,
        "prometheus_client": mock_prom,
        "elk_client": None,
        "elk_index": "",
        "emitter": MagicMock(),
        "budget": MagicMock(should_skip=MagicMock(return_value=False)),
        "telemetry": MagicMock(),
    }}
    state = {"platform": "kubernetes", "platform_version": "1.28", "namespaces": ["default"],
             "diagnostic_scope": None, "dispatch_domains": ["node"], "scan_mode": "diagnostic"}

    from src.agents.cluster.node_agent import node_agent
    asyncio.get_event_loop().run_until_complete(node_agent(state, config))
    # prometheus_client.query should have been called
    assert mock_prom.query.called
```

**Step 2: Run to verify fail**

```bash
cd backend && python -m pytest tests/test_cluster_agents.py::test_node_agent_uses_prometheus_client_when_available -xvs 2>&1 | tail -15
```

**Step 3: Extract prometheus_client in node_agent and query node metrics**

In `backend/src/agents/cluster/node_agent.py`, locate the `node_agent` function (around line 303). After the existing cluster data collection (nodes, pods, events, deployments), add:

```python
# Query Prometheus for node resource utilization (if available)
prometheus_client = config.get("configurable", {}).get("prometheus_client")
if prometheus_client:
    try:
        cpu_result = prometheus_client.query(
            'sum by (node) (rate(node_cpu_seconds_total{mode!="idle"}[5m])) / '
            'sum by (node) (machine_cpu_cores) * 100'
        )
        data_payload["prometheus_node_cpu"] = cpu_result.get("data", {}).get("result", [])
    except Exception as exc:
        logger.debug("Prometheus node CPU query failed: %s", exc)
    try:
        mem_result = prometheus_client.query(
            '(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / '
            'node_memory_MemTotal_bytes * 100'
        )
        data_payload["prometheus_node_memory"] = mem_result.get("data", {}).get("result", [])
    except Exception as exc:
        logger.debug("Prometheus node memory query failed: %s", exc)
```

**Step 4: Run test**

```bash
cd backend && python -m pytest tests/test_cluster_agents.py -xvs -k "prometheus_client" 2>&1 | tail -15
```
Expected: PASS

**Step 5: Run full agent test suite**

```bash
cd backend && python -m pytest tests/test_cluster_agents.py -x 2>&1 | tail -10
```

**Step 6: Commit**

```bash
git add backend/src/agents/cluster/node_agent.py backend/tests/test_cluster_agents.py
git commit -m "feat(cluster): node_agent queries Prometheus for CPU/memory utilization when client is available"
```

---

## Task 12: Frontend — ClusterProfileSelector shared component + temporary cluster panel

**Files:**
- Create: `frontend/src/components/ActionCenter/forms/ClusterProfileSelector.tsx`
- Modify: `frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx`
- Modify: `frontend/src/types/index.ts`

**Step 1: Update ClusterDiagnosticsForm interface in types/index.ts**

Find `ClusterDiagnosticsForm` (around line 597) and add:
```typescript
export interface ClusterDiagnosticsForm {
  capability: 'cluster_diagnostics';
  cluster_url: string;
  namespace?: string;
  symptoms?: string;
  auth_token?: string;
  auth_method?: 'token' | 'kubeconfig' | 'service_account';
  kubeconfig_content?: string;
  role?: string;
  resource_type?: string;
  workload?: string;
  include_control_plane?: boolean;
  profile_id?: string;
  // Temporary cluster entry (session-only)
  use_temp_cluster?: boolean;
  // ELK
  elk_index?: string;
}
```

**Step 2: Create ClusterProfileSelector component**

Create `frontend/src/components/ActionCenter/forms/ClusterProfileSelector.tsx`:

```tsx
import React from 'react';
import { ClusterProfile } from '../../../types';

interface Props {
  profiles: ClusterProfile[];
  selectedId: string | null;
  onSelect: (profileId: string | null) => void;
  loading?: boolean;
}

const STATUS_DOT: Record<string, string> = {
  connected: '#22c55e',
  warning: '#f59e0b',
  unreachable: '#ef4444',
  pending_setup: '#64748b',
};

const ENV_COLORS: Record<string, { bg: string; text: string }> = {
  prod:    { bg: 'rgba(239,68,68,0.15)',   text: '#ef4444' },
  staging: { bg: 'rgba(245,158,11,0.15)', text: '#f59e0b' },
  dev:     { bg: 'rgba(100,116,139,0.15)', text: '#94a3b8' },
};

export function ClusterProfileSelector({ profiles, selectedId, onSelect, loading }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{ fontSize: 11, fontWeight: 600, color: '#9a9080', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Cluster
      </label>
      <select
        value={selectedId ?? '__temp__'}
        onChange={e => onSelect(e.target.value === '__temp__' ? null : e.target.value)}
        disabled={loading}
        style={{
          background: '#080f12',
          border: '1px solid #1e2a2e',
          color: '#e8e0d4',
          borderRadius: 6,
          padding: '7px 10px',
          fontSize: 13,
          width: '100%',
        }}
      >
        {profiles.map(p => {
          const env = ENV_COLORS[p.environment] ?? ENV_COLORS.dev;
          const dot = STATUS_DOT[p.status] ?? '#64748b';
          return (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.environment ? ` [${p.environment}]` : ''}
              {(p as any).role ? ` · ${(p as any).role}` : ''}
              {p.cluster_version ? ` · ${p.cluster_version}` : ''}
              {' · ' + (p.status === 'connected' ? '✓ connected' :
                         p.status === 'warning' ? '⚠ warning' :
                         p.status === 'unreachable' ? '✗ unreachable' : '─ pending')}
            </option>
          );
        })}
        <option value="__temp__">Use a different cluster (one-time)</option>
      </select>
    </div>
  );
}
```

**Step 3: Update ClusterDiagnosticsFields.tsx to use ClusterProfileSelector and add temp cluster panel + ELK index**

The full updated form structure in `ClusterDiagnosticsFields.tsx`:

1. Replace the existing profile dropdown with `<ClusterProfileSelector>`.
2. When `selectedId === null` (user chose "Use a different cluster"), render an inline panel with:
   - Cluster API URL (text input, required)
   - Auth Method (toggle: token / kubeconfig / service_account)
   - Credentials (token textarea OR kubeconfig textarea based on auth_method)
   - Role (text input, optional)
   - Test Connection button (calls `POST /api/v5/profiles/test-connection`)
   - "Start Diagnostics" button disabled until test connection passes
3. Add ELK Log Index field (optional text input, below namespace) with placeholder `e.g. cluster-logs-* or leave blank to skip log analysis`.
4. If elk_index provided but no ELK endpoint in profile → show inline warning (check `profile.endpoints.elasticsearch_url`).

Key state variables to add:
```tsx
const [tempCluster, setTempCluster] = useState({
  cluster_url: '', auth_method: 'token' as const, credential: '', role: '',
});
const [testResult, setTestResult] = useState<{status: string; platform: string} | null>(null);
const [testing, setTesting] = useState(false);
const [elkIndex, setElkIndex] = useState('');
```

Test connection handler:
```tsx
const handleTestConnection = async () => {
  setTesting(true);
  try {
    const resp = await fetch('/api/v5/profiles/test-connection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cluster_url: tempCluster.cluster_url,
        auth_method: tempCluster.auth_method,
        credential: tempCluster.credential,
        verify_ssl: false,
      }),
    });
    const data = await resp.json();
    setTestResult(data);
    // Update form data
    onChange({ ...formData, cluster_url: tempCluster.cluster_url,
      auth_method: tempCluster.auth_method,
      auth_token: tempCluster.auth_method === 'token' ? tempCluster.credential : undefined,
      kubeconfig_content: tempCluster.auth_method === 'kubeconfig' ? tempCluster.credential : undefined,
      role: tempCluster.role,
    });
  } finally {
    setTesting(false);
  }
};
```

The "Start Diagnostics" submit button should be disabled if `!selectedProfileId && testResult?.status !== 'connected'`.

**Step 4: Build TypeScript to verify no errors**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: zero errors.

**Step 5: Commit**

```bash
git add frontend/src/components/ActionCenter/forms/ClusterProfileSelector.tsx frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx frontend/src/types/index.ts
git commit -m "feat(cluster): ClusterProfileSelector component + temporary cluster inline panel + ELK index field"
```

---

## Task 13: Frontend — Form submission changes in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx:292-350` (cluster_diagnostics submission)

**Step 1: Update App.tsx submission**

Find the `cluster_diagnostics` case in `handleCapabilitySubmit` (around line 292). Update the `startSessionV4()` call to include the new fields:

```typescript
const session = await startSessionV4({
  service_name: 'Cluster Diagnostics',
  time_window: '1h',
  namespace: clusterData.namespace || '',
  capability: 'cluster_diagnostics',
  // Profile or temp cluster
  profile_id: clusterData.profile_id || undefined,
  // Ad-hoc auth (only when no saved profile)
  ...((!clusterData.profile_id && clusterData.cluster_url) ? {
    cluster_url: clusterData.cluster_url,
    auth_method: clusterData.auth_method || 'token',
    auth_token: clusterData.auth_token,
    kubeconfig_content: clusterData.kubeconfig_content,
    role: clusterData.role,
  } : {}),
  // ELK index (always pass, backend skips if empty)
  elk_index: clusterData.elk_index || '',
  // Scope
  scope: {
    level: 'cluster',
    namespaces: clusterData.namespace ? [clusterData.namespace] : [],
    domains: clusterData.include_control_plane !== false
      ? ['ctrl_plane', 'node', 'network', 'storage']
      : ['node', 'network', 'storage'],
    include_control_plane: clusterData.include_control_plane !== false,
  },
});
```

**Step 2: Build TypeScript**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: zero errors.

**Step 3: Vite build**

```bash
cd frontend && npx vite build 2>&1 | tail -10
```
Expected: no errors.

**Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(cluster): update App.tsx cluster_diagnostics submission with new auth/ELK fields"
```

---

## Task 14: Run full test suite and verify everything passes

**Step 1: Backend tests**

```bash
cd backend && python -m pytest tests/test_cluster_routing.py tests/test_cluster_graph.py tests/test_cluster_agents.py tests/test_cluster_probe.py -x --tb=short 2>&1 | tail -30
```
Expected: all pass.

**Step 2: Frontend type check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: zero errors.

**Step 3: Frontend build**

```bash
cd frontend && npx vite build 2>&1 | tail -10
```
Expected: build succeeds.

**Step 4: If any tests fail, fix them before committing**

Common issues:
- `PrometheusClient` or `ElasticsearchClient` constructor args differ from what's in `metrics_agent.py` / `log_agent.py` → read actual constructors and adjust Task 10 code.
- `ClusterProfile` SQLite schema needs migration for new `role` field → check if `ProfileStore` uses Alembic or raw SQL; if raw SQL, add `role TEXT DEFAULT ''` column in `CREATE TABLE` statement or add migration.

**Step 5: Final commit if any fixes needed**

```bash
git add -p  # stage only the fix files
git commit -m "fix(cluster): reconcile PrometheusClient args and schema migration for role field"
```
