# ai-troubleshooting

Helm chart for the AI Troubleshooting System. Single-tenant install, runs on **vanilla Kubernetes 1.28+** and **OpenShift 4.x** from the same chart.

## TL;DR

```bash
# 1. Pre-create the required Anthropic API key Secret.
kubectl create namespace ai-tshoot
kubectl -n ai-tshoot create secret generic anthropic-default \
  --from-literal=api_key=sk-ant-...

# 2. Add chart deps + install.
helm dependency update charts/ai-troubleshooting
helm install ai-tshoot charts/ai-troubleshooting \
  -n ai-tshoot \
  --set anthropic.defaultKey.existingSecret=anthropic-default

# 3. (OpenShift) overlay the OpenShift values.
helm install ai-tshoot charts/ai-troubleshooting \
  -n ai-tshoot \
  -f charts/ai-troubleshooting/values-openshift.yaml \
  --set anthropic.defaultKey.existingSecret=anthropic-default
```

## What it deploys

| Resource | Purpose |
|---|---|
| `Deployment/<release>-web` | FastAPI + UI behind ClusterIP Service |
| `Deployment/<release>-worker` | Outbox relay + investigation runner + scheduler + resume scan |
| `Service/<release>-web` | ClusterIP on port 8000 |
| `Ingress` or `Route` | Conditional on `ingress.enabled` / `route.enabled` |
| `ServiceAccount`, `PDB`, `HPA` | Standard envelope |
| `Job/migrate` | Helm pre-install + pre-upgrade Alembic hook |
| `CronJob/backup` | Daily pg_dump (auto-skipped with external DB) |
| `ServiceMonitor`, `PrometheusRule`, `ConfigMap/dashboards` | Observability hooks (off by default) |
| `NetworkPolicy` | Off by default; enable to lock egress |
| `Pod/test-smoke` | `helm test` smoke check (curl `/healthz` + `/readyz`) |
| Bundled subcharts | `bitnami/postgresql` + `bitnami/redis` (toggleable) |

## Required values

| Path | Why |
|---|---|
| `anthropic.defaultKey.existingSecret` | Name of pre-created Secret with the Anthropic API key. **Chart fail-fasts on `helm install` if missing.** |

Everything else has a sensible default.

## Multi-key Anthropic

Operator-named keys (no model names hardcoded — Anthropic ships models faster than chart releases):

```yaml
anthropic:
  defaultKey:
    existingSecret: anthropic-default
    secretKey: api_key
  namedKeys:
    - name: premium
      existingSecret: anthropic-premium
      secretKey: api_key
    - name: cheap
      existingSecret: anthropic-cheap
      secretKey: api_key
```

Renders as env vars `ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_PREMIUM`, `ANTHROPIC_API_KEY_CHEAP` on both web + worker pods. App's `key_resolver` (PR 2) resolves at request time based on the `agent_model_routes` DB table edited via Settings UI.

## External Postgres / Redis

```yaml
postgresql:
  enabled: false
externalDatabase:
  enabled: true
  host: my-pg.internal
  database: ai_tshoot
  username: ai_tshoot
  existingSecret: my-pg-creds   # MUST be pre-created
  existingSecretPasswordKey: password
  sslmode: require
```

Same pattern for Redis (`externalRedis.*`). Mutual exclusion + `existingSecret`-only credentials are enforced at install time.

When external mode is on, the bundled-postgres backup CronJob auto-skips (your managed DB has its own backup story).

## Validation guards (fail-fast at `helm install` / `helm upgrade`)

The chart aborts install with a clear error message if:

- `anthropic.defaultKey.existingSecret` is empty
- Both `postgresql.enabled` and `externalDatabase.enabled` are true (or both false)
- Both `redis.enabled` and `externalRedis.enabled` are true (or both false)
- External DB enabled without `externalDatabase.existingSecret` or `externalDatabase.host`
- External Redis enabled without `externalRedis.existingSecret` or `externalRedis.host`
- Both `ingress.enabled` and `route.enabled` are true
- `openshift.enabled=true` AND `ingress.enabled=true` (use `route.enabled` on OpenShift)
- `anthropic.namedKeys[].name` doesn't match `^[a-z][a-z0-9-]*$`
- Duplicate names in `anthropic.namedKeys`

## Overlays

| File | When |
|---|---|
| `values.yaml` | Always (defaults) |
| `values-openshift.yaml` | On OpenShift — switches Ingress→Route, drops UID specs for SCC compatibility |
| `values-prod.yaml` | Production — bigger resources, HPA on, ServiceMonitor + PrometheusRule + dashboards on, longer backup retention |

Stack overlays at install time:
```bash
helm install ai-tshoot charts/ai-troubleshooting \
  -f charts/ai-troubleshooting/values-openshift.yaml \
  -f charts/ai-troubleshooting/values-prod.yaml \
  -f my-customer-overrides.yaml
```

## Health probes

Liveness `/healthz` (in-process; no external deps).
Readiness `/readyz` (Postgres + Redis ping with `HEALTH_PROBE_TIMEOUT_S` budget).

Both endpoints land in the chart from PR 2 (`backend/src/api/health.py`). `auth.EXEMPT_PATHS` already includes them.

## Drain semantics

| Component | `terminationGracePeriodSeconds` | Reason |
|---|---|---|
| `web` | 30 | HTTP requests are short-lived |
| `worker` | 120 | Investigations checkpoint to DB on SIGTERM (paired with `WORKER_DRAIN_GRACE_S=110` in ConfigMap) |

## Smoke test

```bash
helm test ai-tshoot -n ai-tshoot
```

Curls `/healthz` + `/readyz` from inside the cluster. Fails the test on non-200.

## Versioning

| | |
|---|---|
| `Chart.version` | Bumps when chart templates change |
| `Chart.appVersion` | Bumps when the app image changes |
| Image tag | Defaults to `Chart.appVersion`; override with `image.tag` (immutable, never `:latest`) |

## Upgrade

```bash
helm upgrade ai-tshoot charts/ai-troubleshooting \
  -n ai-tshoot \
  --set image.tag=0.1.1
```

Migration job runs first (Helm pre-upgrade hook). If it fails, the install aborts and the existing Deployment stays untouched.

## Rollback

```bash
helm rollback ai-tshoot -n ai-tshoot
```

Or via ArgoCD: `git revert` on the gitops repo and ArgoCD auto-syncs.

## Auth

⚠ **The chart deploys without authentication by default.** Single-tenant internal install assumed. Recommended next steps:

- Enable `networkPolicy.enabled` to lock egress to known destinations
- Front the Ingress/Route with an OAuth proxy (oauth2-proxy, OpenShift OAuth proxy)
- Service mesh mTLS (Istio, Linkerd)

`oauth2Proxy.enabled` is reserved as a future toggle.
