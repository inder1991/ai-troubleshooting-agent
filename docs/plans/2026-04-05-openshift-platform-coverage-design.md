# OpenShift Platform-Layer Coverage — Design

**Goal:** Close diagnostic gaps for OpenShift platform-layer resources: OLM ecosystem, ClusterVersion, Machine lifecycle, and Proxy/OAuth configuration.

**Scope:** All enhancements fold into `ctrl_plane_agent`. BuildConfig/ImageStream deferred to a future phase.

**Decisions made during design:**
- Extend ctrl_plane_agent rather than creating a new agent (avoids new LangGraph node)
- BuildConfig/ImageStream deferred — methods exist but wiring postponed
- OAuth/Console consolidated under proxy config check (same failure domain)
- No InstallPlan auto-approval — informational only

---

## Section 1: New cluster_client Methods

6 new non-abstract methods on `ClusterClientBase` (return empty `QueryResult` by default):

| Method | API Resource | Returns |
|---|---|---|
| `get_cluster_version()` | `config.openshift.io/v1/clusterversions/version` | version, desired, history[], conditions (Available, Progressing, Failing) |
| `list_subscriptions(namespace)` | `operators.coreos.com/v1alpha1/subscriptions` | name, namespace, package, channel, currentCSV, installedCSV, state |
| `list_csvs(namespace)` | `operators.coreos.com/v1alpha1/clusterserviceversions` | name, namespace, phase, reason, message |
| `list_install_plans(namespace)` | `operators.coreos.com/v1alpha1/installplans` | name, namespace, approval, approved, phase, csvNames |
| `list_machines()` | `machine.openshift.io/v1beta1/machines` | name, phase, providerID, node_ref, conditions, creation_timestamp |
| `get_proxy_config()` | `config.openshift.io/v1/proxies/cluster` | httpProxy, httpsProxy, noProxy, trustedCA |

MockClusterClient gets corresponding mock fixtures. KubernetesClient gets real implementations.

---

## Section 2: ctrl_plane_agent Enhancements

**Tool subset expansion** — add to `CTRL_PLANE_TOOLS`:
`list_subscriptions`, `list_csvs`, `list_install_plans`, `list_machines`, `get_cluster_version`, `get_proxy_config`

**New heuristic checks in `_heuristic_analyze()`:**

| Check | Condition | Severity |
|---|---|---|
| ClusterVersion upgrade stuck | condition `Progressing=True` for > 30min OR `Failing=True` | critical |
| ClusterVersion available | condition `Available=False` | critical |
| OLM Subscription state | state != `AtLatestKnown` (e.g., `UpgradePending`, `UpgradeFailed`) | high |
| CSV phase failure | phase in (`Failed`, `Unknown`, `Replacing`) | high |
| InstallPlan not approved | `approval=Manual` + `approved=False` (informational) | low |
| InstallPlan stuck | phase = `Installing` for extended period | medium |
| Machine not Running | phase != `Running` (e.g., `Provisioning`, `Failed`, `Deleting`) | high |
| Machine no node ref | phase = `Provisioned` but no `node_ref` | medium |
| Proxy misconfigured | `httpProxy` set but `noProxy` missing cluster/service CIDRs | medium |

**Pre-fetch additions:** `get_cluster_version()`, `list_subscriptions()`, `list_csvs()`, `list_machines()`, `get_proxy_config()`.

---

## Section 3: Signal Normalizer + Failure Patterns + Causal Links

**6 new signal extraction rules** in `signal_normalizer.py`:

| Text Match | Signal |
|---|---|
| "cluster version" + ("failing" / "stuck" / "progressing") | CLUSTER_UPGRADE_STUCK |
| "subscription" + ("failed" / "degraded" / "pending") | OLM_SUBSCRIPTION_FAILURE |
| "csv" + ("failed" / "unknown" / "replacing") OR "clusterserviceversion" + ("failed") | OLM_CSV_FAILURE |
| "installplan" + ("stuck" / "failed" / "not approved") | OLM_INSTALLPLAN_STUCK |
| "machine" + ("failed" / "provisioning" / "not running") | MACHINE_FAILURE |
| "proxy" + ("misconfigured" / "unreachable" / "blocked") | PROXY_MISCONFIGURED |

**6 new failure patterns** in `failure_patterns.py`:

| Pattern ID | Conditions | Severity | Priority |
|---|---|---|---|
| CLUSTER_UPGRADE_FAILURE | CLUSTER_UPGRADE_STUCK | critical | 10 |
| OLM_OPERATOR_INSTALL_FAILURE | OLM_SUBSCRIPTION_FAILURE + OLM_CSV_FAILURE | critical | 9 |
| OLM_UPGRADE_STUCK | OLM_SUBSCRIPTION_FAILURE + OLM_INSTALLPLAN_STUCK | high | 8 |
| MACHINE_PROVISIONING_FAILURE | MACHINE_FAILURE + NODE_NOT_READY | critical | 9 |
| PROXY_BLOCKS_IMAGE_PULL | PROXY_MISCONFIGURED + IMAGE_PULL_ERROR | critical | 9 |
| MACHINE_NODE_MISMATCH | MACHINE_FAILURE | high | 7 |

**4 new causal link types** in `synthesizer.py` `CONSTRAINED_LINK_TYPES`:
- `cluster_upgrade_stuck -> operator_degraded`
- `olm_failure -> operator_degraded`
- `machine_failure -> node_not_ready`
- `proxy_misconfigured -> image_pull_failure`

---

## Section 4: Proactive Analyzer Enhancements

4 new proactive checks:

| Check ID | Data Source | Flags | Severity |
|---|---|---|---|
| `cluster_version_check` | `get_cluster_version()` | `Failing=True` (critical), `Progressing=True` + desired != current (high) | critical/high |
| `olm_subscription_health` | `list_subscriptions()` | `currentCSV != installedCSV` (high), state = `UpgradeFailed` (critical) | critical/high |
| `machine_health` | `list_machines()` | phase = `Failed` (critical), phase != `Running` (high) | critical/high |
| `proxy_config_check` | `get_proxy_config()` | httpProxy set but noProxy empty (medium), trustedCA missing with https proxy (high) | high/medium |

---

## Section 5: Testing Strategy

| Area | Test File | Coverage |
|---|---|---|
| cluster_client methods | `test_cluster_client_platform.py` | 6 new methods (mock fixtures) |
| ctrl_plane heuristic | `test_ctrl_plane_platform.py` | ClusterVersion, OLM, Machine, Proxy checks |
| signal normalizer | `test_signal_normalizer_platform.py` | 6 new signal rules |
| failure patterns | `test_failure_patterns_platform.py` | 6 new patterns |
| causal links | `test_causal_links_platform.py` | 4 new link types |
| proactive checks | `test_proactive_platform.py` | 4 new checks |

All tests use mocked data. TDD — red then green.
