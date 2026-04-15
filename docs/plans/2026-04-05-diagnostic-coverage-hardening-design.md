# Diagnostic Coverage Hardening — Design

**Goal:** Close detection gaps across the cluster diagnostic workflow for OpenShift-specific failures, Kubernetes-generic edge cases, causal chain completeness, and proactive risk detection.

**Scope:** All enhancements except BuildConfig/ImageStream analysis.

**Decisions made during design:**
- etcd health: Both Prometheus-based (detailed) and pod-based (fallback)
- Admission webhooks: Reactive + proactive
- Route/Ingress: Both OpenShift Routes and Kubernetes Ingresses
- No etcd backup freshness check (too environment-specific)

---

## Section 1: ctrl_plane_agent Enhancements

**Add tools:** `list_deployments`, `list_pods` to `CTRL_PLANE_TOOLS` in `tools.py`.

**Heuristic additions:**
- Operator `progressing=true` → "Operator {name} upgrade in progress" (medium)
- SCC with `allowPrivilegedContainer: true` for non-system namespaces (medium)
- MCP `machineCount != updatedMachineCount` (currently LLM-only, add to heuristic)

**Etcd health check** (`_check_etcd_health`):
- Pod-based: query pods in `openshift-etcd` / `kube-system` with label `component=etcd`, check status/restarts
- Prometheus: `etcd_server_has_leader`, `etcd_disk_wal_fsync_duration_seconds_bucket`, `etcd_network_peer_round_trip_time_seconds_bucket`
- Etcd pod not running = CRITICAL, no leader = CRITICAL, high WAL fsync = HIGH, high peer RTT = MEDIUM

**Webhook check** (`_check_webhooks`):
- New `list_webhooks` method on cluster_client
- `failurePolicy=Fail` with external URL = HIGH
- Timeout > 10s = MEDIUM
- Events containing "webhook call failed" = HIGH

---

## Section 2: network_agent Enhancements

**Add tools:** `list_routes`, `list_ingresses` to `NETWORK_TOOLS` in `tools.py`.

**New cluster_client methods:**
- `list_routes()` — OpenShift Routes (host, TLS config, backend, admitted status)
- `list_ingresses()` — K8s Ingresses (hosts, TLS secrets, backends, ingress class)

**Heuristic additions:**
- Endpoints with `not_ready_addresses > 0` = MEDIUM
- Routes: backend service missing/0 endpoints = HIGH; expired TLS cert = HIGH
- Ingresses: missing backend = HIGH; missing TLS secret = HIGH; no ingress class = MEDIUM
- DNS deployment replicas: `replicas_ready < desired` = HIGH, `== 0` = CRITICAL

**Pre-fetch additions:** `list_routes()` (OpenShift), `list_ingresses()`, DNS deployment query.

---

## Section 3: node_agent Enhancements

**Heuristic additions (no new tools needed):**
- Init container stuck: pod with init container in `waiting` state, reason CrashLoopBackOff or runtime > 5min = HIGH
- Probe misconfiguration: pod Running but not Ready for > 5min = MEDIUM
- ConfigMap/Secret mount failure: events with `FailedMount` / `MountVolume.SetUp failed` = HIGH
- ResourceQuota blocking: events with `FailedCreate` + "exceeded quota" = HIGH

**Pre-fetch:** events with `reason=FailedMount,FailedCreate` field selector.

---

## Section 4: Signal Normalizer + Failure Patterns + Causal Links

**8 new signal extraction rules** in `signal_normalizer.py`:

| Text Match | Signal |
|---|---|
| "operator" + ("unavailable" / "degraded") | OPERATOR_DEGRADED |
| "operator" + "progressing" | OPERATOR_PROGRESSING |
| "init container" + ("stuck" / "waiting" / "crash") | INIT_CONTAINER_STUCK |
| "webhook" + ("fail" / "timeout" / "blocked") | WEBHOOK_FAILURE |
| "mount" + ("fail" / "error") OR "FailedMount" | MOUNT_FAILURE |
| "pdb" + ("block" / "disruptionsAllowed") | PDB_BLOCKING |
| "quota" + ("exceeded" / "blocked") | QUOTA_EXCEEDED |
| "probe" + ("fail" / "unhealthy" / "not ready") | PROBE_MISCONFIGURED |

**8 new failure patterns** in `failure_patterns.py`:

| Pattern ID | Conditions | Severity |
|---|---|---|
| OPERATOR_SCALED_DOWN | OPERATOR_DEGRADED | critical |
| OPERATOR_UPGRADE_STUCK | OPERATOR_PROGRESSING | high |
| ETCD_QUORUM_LOSS | OPERATOR_DEGRADED + NODE_NOT_READY | critical |
| WEBHOOK_BLOCKING | WEBHOOK_FAILURE | critical |
| INIT_CONTAINER_STUCK | INIT_CONTAINER_STUCK | high |
| CONFIG_MOUNT_FAILURE | MOUNT_FAILURE | high |
| NETPOL_BLOCKS_DNS | NETPOL_EMPTY_INGRESS + DNS_FAILURE | critical |
| QUOTA_SCHEDULING_FAILURE | QUOTA_EXCEEDED + FAILED_SCHEDULING | high |

**5 new causal link types** in `synthesizer.py` `CONSTRAINED_LINK_TYPES`:
- `operator_degraded -> workload_rescheduling`
- `quota_exceeded -> scheduling_failure`
- `webhook_failure -> pod_creation_blocked`
- `mount_failure -> container_crash`
- `probe_failure -> service_degradation`

---

## Section 5: Proactive Analyzer Enhancements

4 new proactive checks:

| Check ID | Data Source | Flags | Severity |
|---|---|---|---|
| dns_replica_check | list_deployments (coredns/dns-default) | replicas < 2 | high (1), critical (0) |
| webhook_risk | list_webhooks | failurePolicy=Fail + external URL | high |
| pv_reclaim_delete | list_pvcs | reclaimPolicy=Delete on stateful workloads | medium |
| ingress_spof | list_deployments (ingress controller) | single replica | high |

---

## Section 6: cluster_client New Methods

| Method | API Resource | Returns |
|---|---|---|
| list_webhooks() | ValidatingWebhookConfiguration + MutatingWebhookConfiguration | name, failurePolicy, clientConfig, timeoutSeconds, rules |
| list_routes() | Route (route.openshift.io/v1) | name, host, tls_termination, backend_service, admitted, namespace |
| list_ingresses() | Ingress (networking.k8s.io/v1) | name, hosts, tls_secrets, backend_services, ingress_class, namespace |

MockClusterClient gets corresponding mock fixtures.

---

## Section 7: Testing Strategy

| Area | Test File | Coverage |
|---|---|---|
| ctrl_plane heuristic | test_ctrl_plane_heuristic.py | Progressing, SCC, MCP, etcd, webhooks |
| network heuristic | test_network_heuristic.py | Routes, Ingresses, endpoints, DNS replicas |
| node heuristic | test_node_heuristic.py | Init container, probes, mounts, quota |
| signal normalizer | test_signal_normalizer_new.py | 8 new signal rules |
| failure patterns | test_failure_patterns_new.py | 8 new patterns |
| proactive checks | test_proactive_new.py | DNS SPOF, webhook, PV, ingress |
| cluster_client | test_cluster_client_new.py | list_webhooks, list_routes, list_ingresses |
| causal links | test_causal_links.py | 5 new link types |

All tests use mocked data.
