# Production Deployment Runbook

How to install, upgrade, rollback, back up, and troubleshoot the AI Troubleshooting System on Kubernetes 1.28+ or OpenShift 4.x.

## Architecture at a glance

```
                    Ingress / Route
                         │
                  ┌──────▼───────┐
                  │  web (n)     │  FastAPI + UI
                  │  Deployment  │  /healthz /readyz
                  └──────┬───────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼───┐       ┌────▼────┐      ┌────▼────┐
   │ worker │       │postgres │      │  redis  │
   │  (n)   │       │ bundled │      │ bundled │
   └────────┘       └─────────┘      └─────────┘
        │                                  ▲
        │ outbox relay → Redis Streams ────┘
        │ resume scan
        │ scheduler
```

Two Deployments share one image (different `command:`). External integrations (OpenSearch, target Prometheus, target K8s, Jira/Confluence/Remedy/GitHub) are added via the Settings UI after install — none required to start.

## Pre-install

### 1. Pre-create required Secrets

```bash
NS=ai-tshoot
kubectl create namespace "$NS"

# REQUIRED — chart fails install if missing.
kubectl -n "$NS" create secret generic anthropic-default \
  --from-literal=api_key=sk-ant-...

# Optional — additional named keys for multi-billing setups.
kubectl -n "$NS" create secret generic anthropic-premium \
  --from-literal=api_key=sk-ant-premium-...
```

### 2. (Optional) external Postgres / Redis credentials

Only when using external mode:

```bash
kubectl -n "$NS" create secret generic ext-pg-creds   --from-literal=password=...
kubectl -n "$NS" create secret generic ext-redis-creds --from-literal=password=...
```

## Install

### Vanilla Kubernetes

```bash
helm dependency update charts/ai-troubleshooting

helm install ai-tshoot charts/ai-troubleshooting \
  -n ai-tshoot \
  -f charts/ai-troubleshooting/values-prod.yaml \
  --set anthropic.defaultKey.existingSecret=anthropic-default \
  --set ingress.enabled=true \
  --set ingress.host=ai-tshoot.example.com \
  --wait --timeout 10m
```

### OpenShift

```bash
helm install ai-tshoot charts/ai-troubleshooting \
  -n ai-tshoot \
  -f charts/ai-troubleshooting/values-openshift.yaml \
  -f charts/ai-troubleshooting/values-prod.yaml \
  --set anthropic.defaultKey.existingSecret=anthropic-default \
  --set route.host=ai-tshoot.apps.cluster.example.com \
  --wait --timeout 10m
```

### Verify

```bash
kubectl -n ai-tshoot get pods -l app.kubernetes.io/instance=ai-tshoot
helm test ai-tshoot -n ai-tshoot
curl -fsS https://ai-tshoot.example.com/healthz
curl -fsS https://ai-tshoot.example.com/readyz
```

## Upgrade

```bash
helm upgrade ai-tshoot charts/ai-troubleshooting \
  -n ai-tshoot \
  -f charts/ai-troubleshooting/values-prod.yaml \
  --set anthropic.defaultKey.existingSecret=anthropic-default \
  --set image.tag=0.1.1 \
  --wait --timeout 10m
```

### What happens during upgrade

1. Helm runs the `migrate` Job (pre-upgrade hook). Alembic upgrades schema.
2. **If migration fails, the upgrade aborts.** Existing pods stay untouched.
3. Web Deployment rolls (RollingUpdate, maxSurge 25%, maxUnavailable 0).
4. Worker Deployment rolls one pod at a time. Each old worker gets up to `terminationGracePeriodSeconds: 120` to checkpoint in-flight investigations.

### Migration compatibility window

App version N must boot against schema produced by N-1. Breaking schema changes are split into two releases:

- **N**: adds the column nullable; reads + writes both old and new shape.
- **N+1**: makes the column required; drops backwards-compat reads.

This means N+1 must never deploy without N's schema present. Skipping versions during upgrade is unsupported.

## Rollback

### Via Helm (break-glass)

```bash
helm history ai-tshoot -n ai-tshoot
helm rollback ai-tshoot <revision> -n ai-tshoot
```

### Via ArgoCD GitOps (recommended)

```bash
# In the gitops repo
git revert <bad-promotion-commit>
git push
# ArgoCD detects and rolls back automatically.
```

## Backups (bundled Postgres only)

The chart ships a `pg_dump` CronJob writing to a PVC. Defaults: daily 02:00 UTC, 7-day retention.

### Trigger manually

```bash
kubectl -n ai-tshoot create job --from=cronjob/ai-tshoot-backup ai-tshoot-backup-now
kubectl -n ai-tshoot logs job/ai-tshoot-backup-now
```

### Restore

```bash
# Find the backup file inside the PVC.
kubectl -n ai-tshoot exec -it <any-backup-pod> -- ls -la /backup

# Restore (DESTRUCTIVE — drops existing schema).
kubectl -n ai-tshoot exec -it <any-postgres-pod> -- bash -c '
  PGPASSWORD=$POSTGRES_PASSWORD pg_restore -d $POSTGRES_DB --clean --if-exists /backup/ai_tshoot-YYYYMMDDTHHMMSSZ.sql.gz
'
```

For external DB, backups are your DBA team's job — chart's CronJob auto-skips.

## Secrets rotation

### Rotate Anthropic API key

```bash
kubectl -n ai-tshoot create secret generic anthropic-default-new \
  --from-literal=api_key=sk-ant-NEW... \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade ai-tshoot charts/ai-troubleshooting -n ai-tshoot \
  --reuse-values \
  --set anthropic.defaultKey.existingSecret=anthropic-default-new

kubectl -n ai-tshoot delete secret anthropic-default
```

(Pods reload env on restart — `helm upgrade` triggers a rolling restart automatically.)

### Rotate bundled Postgres password

The Bitnami subchart documents this — see `charts/ai-troubleshooting/charts/postgresql/README.md` after `helm dep build`.

## Troubleshooting

### "Validation guard fired"

Chart prints a clear error. Common causes:

| Error | Fix |
|---|---|
| `anthropic.defaultKey.existingSecret is required` | Pre-create the Secret + set the value |
| `Cannot enable both postgresql.enabled AND externalDatabase.enabled` | Pick one |
| `externalDatabase.existingSecret is required` | Pre-create credentials Secret + reference it |
| `Cannot enable both ingress.enabled AND route.enabled` | Pick one (Ingress for vanilla, Route for OpenShift) |

### Web pod CrashLoopBackOff

```bash
kubectl -n ai-tshoot logs deploy/ai-tshoot-web --previous --tail=100
```

Most common: migration not run or DB unreachable. Check:

```bash
kubectl -n ai-tshoot get jobs
kubectl -n ai-tshoot logs job/ai-tshoot-migrate-<rev>
```

### Worker pod stuck draining

`terminationGracePeriodSeconds: 120` is paired with `WORKER_DRAIN_GRACE_S=110`. If an investigation runs longer than 110s, it gets force-killed.

To bump the window for long-running investigations:

```yaml
worker:
  terminationGracePeriodSeconds: 300
```

Then in ConfigMap (override via `worker.extraEnv`):

```yaml
worker:
  extraEnv:
    - name: WORKER_DRAIN_GRACE_S
      value: "290"
```

### `/readyz` returns 503

Either Postgres or Redis is unreachable. Check the per-check field in the response:

```bash
kubectl -n ai-tshoot exec deploy/ai-tshoot-web -- curl -s http://localhost:8000/readyz | jq
```

The `checks` object names the failing dependency.

### Outbox lag growing

Worker can't keep up. Either scale workers or check Redis connectivity:

```bash
kubectl -n ai-tshoot logs deploy/ai-tshoot-worker --tail=100 | grep -i outbox
kubectl -n ai-tshoot scale deploy/ai-tshoot-worker --replicas=4
```

If `worker.hpa.enabled=true`, this should self-correct under CPU pressure.

### `helm upgrade` says "another operation is in progress"

```bash
helm history ai-tshoot -n ai-tshoot
# If the last revision is in 'pending-install' or 'pending-upgrade':
helm rollback ai-tshoot <last-good-revision> -n ai-tshoot --no-hooks
```

## Capacity planning

| Component | CPU req / limit | Memory req / limit | Per-pod throughput |
|---|---|---|---|
| Web | 200m / 1 | 512Mi / 2Gi | ~50 concurrent HTTP req |
| Worker | 500m / 2 | 1Gi / 4Gi | ~50 concurrent investigations (Phase 4 budget) |
| Postgres | 200m / 1 | 512Mi / 2Gi (default) | Scale via subchart values |
| Redis | 100m / 250m | 128Mi / 512Mi | Scale via subchart values |

Production overlay (`values-prod.yaml`) doubles defaults across the board.

## Egress allowlist

When `networkPolicy.enabled=true`, allow only:

| Destination | Why |
|---|---|
| Anthropic API CIDR | LLM calls |
| Customer's Jira / Confluence / Remedy / GitHub hosts | ITSM + code integrations |
| Customer's OpenSearch / Prometheus / K8s API | Agent target backends |
| Bundled Postgres + Redis (in-cluster) | Auto-allowed by chart |
| DNS (port 53) | Auto-allowed by chart |

Set in `networkPolicy.egressAllowlist.cidrs`.

## Observability

| Metric/log/trace | Where it ends up |
|---|---|
| `/metrics` (Prometheus format) | Scraped by Prometheus Operator via `ServiceMonitor` (off by default; enable in values) |
| stdout JSON logs | Picked up by cluster log collector (Loki / EFK / Splunk) |
| OTel spans | Skipped in v1 (B.10) — `OTEL_EXPORTER_OTLP_ENDPOINT` env var space reserved for future opt-in |

Enable observability in production overlay:

```yaml
serviceMonitor: { enabled: true }
prometheusRule: { enabled: true }
dashboards:    { enabled: true }
```

## Auth — explicitly NOT included

Default chart deploys without authentication (D.23). Recommended:

1. NetworkPolicy to lock external reachability
2. OAuth proxy in front of Ingress / Route (oauth2-proxy, OpenShift OAuth proxy)
3. Service mesh mTLS for east-west

`oauth2Proxy.enabled` is reserved as a future toggle.

## Local-dev parallel

Same Dockerfile, same env vars, same migration step — see `docs/local-dev.md`.
