# Cluster Diagnostics — Full-Stack Architecture Redesign

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to create the implementation plan.

**Goal:** Fix all architectural gaps in the cluster diagnostic workflow — from form entry through workflow execution — so that cluster selection, credentials, metrics, and logs all flow correctly end-to-end.

**Users:** Engineers and SREs running cluster health investigations on OpenShift and Kubernetes clusters.

**Architecture:** Four concern areas: (1) cluster registration consistency, (2) frontend form UX, (3) backend execution correctness, (4) metrics and logs wiring.

**Tech Stack:** React + TypeScript + Tailwind (frontend), FastAPI + Python + LangGraph (backend), KubernetesClient (cluster access), Prometheus HTTP API, Elasticsearch HTTP API.

---

## 1. Backend Data Model & Cluster Client

### 1a. Role field on ClusterProfile

Add `role: str = ""` to the `ClusterProfile` model in `profile_models.py`. Represents the RBAC role level the credential operates with (e.g. `cluster-admin`, `view`, `edit`). Stored as plain metadata — not enforced by the system, used for display and diagnostic context.

Also add `role` to the API payload in `routes_profiles.py` (create and update endpoints).

### 1b. ResolvedConnectionConfig — new fields

Add to the frozen dataclass in `connection_config.py`:

```python
auth_method: str = "token"          # "token" | "kubeconfig" | "service_account"
kubeconfig_content: str = ""        # raw kubeconfig YAML when auth_method == "kubeconfig"
role: str = ""                      # RBAC role metadata
```

Update `resolve_active_profile()` to populate `auth_method`, `kubeconfig_content`, and `role` from the profile's stored fields.

Update `_config_from_env()` to read:
- `K8S_AUTH_METHOD` → auth_method (default: "token")
- `KUBECONFIG_CONTENT` → kubeconfig_content

### 1c. create_cluster_client() — kubeconfig content handling

When `auth_method == "kubeconfig"` and `kubeconfig_content` is non-empty:
- Write `kubeconfig_content` to a `tempfile.NamedTemporaryFile(suffix=".yaml", delete=False)`
- Pass the temp file path to `KubernetesClient(kubeconfig_path=temp_path)`
- Store `temp_path` in the session dict under `"kubeconfig_temp_path"`
- Clean up the temp file in the `finally` block of `run_cluster_diagnosis` (after `cluster_client.close()`)

Full resolution order (already partially implemented, now complete):
1. `connection_config` has `cluster_url` or `cluster_token` → `KubernetesClient` (bearer token)
2. `connection_config.auth_method == "kubeconfig"` and `kubeconfig_content` non-empty → `KubernetesClient` (temp kubeconfig file)
3. `KUBECONFIG` env var set or `~/.kube/config` exists → `KubernetesClient` (kubeconfig)
4. Fallback → `MockClusterClient`

### 1d. StartSessionRequest — new fields

Add to the Pydantic model in `routes_v4.py`:

```python
auth_method: Optional[str] = None          # "token" | "kubeconfig" | "service_account"
kubeconfig_content: Optional[str] = None   # kubeconfig YAML content (not persisted)
role: Optional[str] = None                 # RBAC role metadata
elk_index: Optional[str] = None            # ELK log index for this session
```

Update the ad-hoc config block in `start_session` to use these fields when building `ResolvedConnectionConfig`.

### 1e. Test-connection endpoint (no profile creation)

New endpoint: `POST /api/v5/profiles/test-connection`

Request:
```python
class TestConnectionRequest(BaseModel):
    cluster_url: str
    auth_method: str = "token"
    credential: str = ""        # token string or kubeconfig YAML content
    verify_ssl: bool = False
```

Response:
```python
class TestConnectionResponse(BaseModel):
    status: str                 # "connected" | "unreachable" | "auth_failed" | "permission_denied"
    platform: str = ""          # "openshift" | "kubernetes"
    version: str = ""           # cluster version
    latency_ms: int = 0
    error: Optional[str] = None
```

Implementation: create a temporary `KubernetesClient`, call `get_api_health()` + `detect_platform()`, return result. No profile created. Temp kubeconfig file cleaned up after response.

---

## 2. Frontend Form — Cluster Selector & Session Entry

### 2a. Enhanced profile selector (shared component)

Extract a `ClusterProfileSelector` component used in both `ClusterDiagnosticsFields` and `TroubleshootAppFields`.

Each option in the dropdown shows:
```
● production-ocp   [prod]  cluster-admin  v4.14  ✓ connected
● staging-k8s      [stg]   view           v1.28  ⚠ warning
● dev-cluster      [dev]   —              v1.27  ─ pending
```

Fields shown per profile: status dot (green/amber/red/grey) + name + environment badge + role + version + connection status label.

Loaded via `GET /api/v5/profiles`. No change to the API.

### 2b. Temporary cluster entry (Cluster Diagnostics only)

When user selects "Use a different cluster (one-time)" from the dropdown, an inline panel expands below. This is **session-only — nothing is saved**.

Fields in the temporary entry panel:
| Field | Required | Notes |
|-------|----------|-------|
| Cluster API URL | Yes | `https://api.cluster.example.com:6443` |
| Cluster Type | No | openshift / kubernetes, default openshift |
| Auth Method | No | Token / Kubeconfig / Service Account, default token |
| Role | No | cluster-admin / view / edit / custom — metadata only |
| Credentials | Yes | Dynamic: token input or kubeconfig textarea |
| Test Connection | Button | Must succeed before "Start Diagnostics" enables |

No name, no environment, no Prometheus/Jaeger URLs — those belong in permanent profiles (Settings > Integrations).

"Start Diagnostics" button is **disabled** until Test Connection passes for a temporary cluster. For a saved profile, it is enabled immediately (connectivity was verified at profile creation).

### 2c. ELK index field

Add an optional `ELK Log Index` field to `ClusterDiagnosticsFields`:

```
ELK Log Index   [ my-cluster-logs-* ]   (optional)
```

Placeholder: `e.g. cluster-logs-* or leave blank to skip log analysis`

If empty → ELK queries are skipped entirely in the workflow. No warning shown — skipping is the expected default.

If provided but no ELK endpoint in profile or global integrations → show inline warning:
`"ELK index provided but no ELK endpoint configured. Add one in Settings → Integrations → ELK. Log analysis will be skipped."`

### 2d. Form submission changes

Update `App.tsx` cluster_diagnostics submission to include:
- `auth_method` from the temporary entry panel
- `kubeconfig_content` when `auth_method == "kubeconfig"`
- `role` from the panel
- `elk_index` from the new field

For saved profile selection, pass only `profile_id` and `elk_index` — credentials are resolved server-side from the profile.

---

## 3. Execution & Runtime Gap Fixes

### 3a. Client lifecycle — no more close() at end of session

Remove `await cluster_client.close()` from the `finally` block of `run_cluster_diagnosis`.

Instead:
- Store the live `cluster_client` in the session dict under `"cluster_client"`
- Add a `get_or_create_cluster_client(session_id)` helper that returns the cached client if alive, or creates a new one from `session["connection_config"]`
- Clean up (close + remove) the client only when the session itself is deleted (existing session cleanup loop)

This enables follow-up cluster queries from chat without reconnecting.

### 3b. RBAC preflight gates domain dispatch

`rbac_preflight` already runs and produces `rbac_check.granted` and `rbac_check.denied`. Wire its output into `dispatch_router`:

- If `list_nodes` denied → skip `node_agent`
- If `list_pods` denied → skip `ctrl_plane_agent` and `node_agent`
- If `get_routes` denied (OpenShift) → skip network route checks in `network_agent`
- If `list_persistentvolumeclaims` denied → skip `storage_agent`

Emit a `rbac_skip` event to the frontend for each skipped domain with the reason:
```json
{"type": "rbac_skip", "domain": "node_agent", "reason": "list_nodes permission denied"}
```

### 3c. Connection resilience — retry wrapper

Add a `with_retry(retries=2, backoff=1.5)` decorator to all `cluster_client.*` calls inside domain agents. If all retries fail:
- Set `failure_reason = "CONNECTION_LOST"` in the domain report
- Log the cluster URL and error for debugging
- Emit a `domain_failed` event with `reason: "connection_lost"` to the frontend

Do NOT re-raise — the graph continues with remaining domains.

### 3d. Cluster metadata in graph state

Add non-sensitive cluster metadata to `initial_state` in `run_cluster_diagnosis`:

```python
initial_state = {
    ...existing fields...
    "cluster_url": getattr(connection_config, "cluster_url", ""),
    "cluster_type": getattr(connection_config, "cluster_type", ""),
    "cluster_role": getattr(connection_config, "role", ""),
}
```

No tokens or credentials in state. Agents use `state["cluster_url"]` in log messages for context-rich errors.

### 3e. RBAC-aware 403 error handling

In `tool_executor.py`, when a kubernetes API call returns HTTP 403:
- Emit a `rbac_denied` event:
  ```json
  {"type": "rbac_denied", "resource": "nodes", "cluster_url": "https://..."}
  ```
- Return a structured error result instead of raising, so the agent can continue with partial data

### 3f. Temp kubeconfig cleanup

In the `finally` block of `run_cluster_diagnosis`, after graph completion:
```python
temp_path = sessions.get(session_id, {}).pop("kubeconfig_temp_path", None)
if temp_path:
    Path(temp_path).unlink(missing_ok=True)
```

---

## 4. Metrics & Logs Wiring

### 4a. Prometheus auto-detection from cluster

Run `detect_prometheus_endpoint(cluster_client, platform)` immediately after the pre-flight checks in `run_cluster_diagnosis`, before graph invocation.

**OpenShift detection:**
```python
# List routes in openshift-monitoring namespace
routes = await cluster_client.get_routes()  # existing method
for route in routes:
    if route.namespace == "openshift-monitoring" and route.name in ("thanos-querier", "prometheus-k8s"):
        return f"https://{route.host}"
```

**Kubernetes detection:**
```python
# List services in common monitoring namespaces
for ns in ("monitoring", "kube-monitoring", "prometheus", "kube-system"):
    svcs = await cluster_client.list_services(namespace=ns)
    for svc in svcs:
        if "prometheus" in svc.name.lower():
            # Return NodePort or LoadBalancer IP if externally reachable
            return build_prometheus_url(svc)
```

**Resolution order:**
1. Profile has `prometheus_url` → use it
2. Auto-detect from cluster (above) → use detected URL
3. Detection fails → set `prometheus_url = ""`, log warning, continue without metrics

**Two-level caching:**
- Detected URL stored in `session["prometheus_url"]` for this run
- If profile exists and profile had no URL → update profile with detected URL (`PUT /api/v5/profiles/{id}`) so future sessions skip detection

**Auth for Prometheus:**
- OpenShift: same bearer token as cluster (Prometheus is behind OpenShift OAuth)
- Kubernetes: pass no auth by default; support bearer token from profile endpoint config if present

### 4b. ELK resolution

```python
elk_url = ""
elk_index = request.elk_index or ""

if elk_index:
    # Try profile endpoint
    elk_url = getattr(connection_config, "elasticsearch_url", "")
    # Try global integrations
    if not elk_url:
        from src.integrations.profile_store import GlobalIntegrationStore
        elk_integration = GlobalIntegrationStore().get_by_service_type("elk")
        elk_url = getattr(elk_integration, "url", "") if elk_integration else ""
    # If still no URL, emit warning and clear index
    if not elk_url:
        await emitter.emit("elk_skip", {"reason": "no_endpoint", "index": elk_index})
        elk_index = ""
```

### 4c. Inject Prometheus and ELK clients into LangGraph config

Create lightweight HTTP clients at session start and pass them through `config["configurable"]`:

```python
from src.agents.metrics_agent import PrometheusClient
from src.agents.log_agent import ElasticsearchClient

prometheus_client = PrometheusClient(
    url=prometheus_url,
    token=getattr(connection_config, "cluster_token", ""),
    verify_ssl=getattr(connection_config, "verify_ssl", False),
) if prometheus_url else None

elk_client = ElasticsearchClient(
    url=elk_url,
    auth_method=getattr(connection_config, "elasticsearch_auth_method", "none"),
    credentials=getattr(connection_config, "elasticsearch_credentials", ""),
) if elk_url and elk_index else None

config = {
    "configurable": {
        "cluster_client": cluster_client,
        "prometheus_client": prometheus_client,   # None if not available
        "elk_client": elk_client,                 # None if not available
        "elk_index": elk_index,
        "emitter": emitter,
        "budget": budget,
        "telemetry": telemetry,
    }
}
```

### 4d. Agent updates — use injected clients

Update `node_agent`, `network_agent`, `storage_agent` to:
1. Extract `prometheus_client` from `config["configurable"]`
2. If `prometheus_client` is not None → call `prometheus_client.query(promql)` directly
3. If None → skip metrics section, log "metrics unavailable"
4. For `network_agent` with logs: extract `elk_client` and `elk_index`; if either None → skip log queries

Remove the current `cluster_client.query_prometheus()` and `cluster_client.query_logs()` calls from agents — they have always returned empty and should be removed to avoid confusion.

---

## 5. Consistency: Integration Form vs Cluster Diagnostic Form

The integration cluster form (Settings > Integrations > Add Cluster) remains unchanged — it is the permanent registration path with all fields.

The cluster diagnostic "Use a different cluster" panel is deliberately minimal — session-only, no persistence. Fields collected: URL, cluster type, auth method, role, credentials.

Both forms use:
- Same `ClusterProfileSelector` dropdown component
- Same auth method options (token / kubeconfig / service_account)
- Same "Test Connection" button (different endpoints: profile probe vs ad-hoc test-connection)
- Same role field (metadata only)

The role field and `service_account` auth method are **added to the integration form** to match — currently the integration form supports token and kubeconfig but not service_account, and has no role field.

---

## 6. Out of Scope

- `scan_mode` (diagnostic vs guard) UI — deferred
- Prometheus/Jaeger URL overrides in cluster diagnostic form — profile stores these; auto-detection covers the gap
- Multi-cluster parallel diagnostics
- Cluster version upgrade recommendations
