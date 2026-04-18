# Deployment

Everything related to running this product — locally during development, in production via Helm, and the supporting CI/CD glue.

## Layout

```
deploy/
├── docker/         Local docker-compose stack (`make up`)
├── helm/           Helm chart for production (vanilla K8s + OpenShift)
├── gitops/         ArgoCD repo skeleton — copy into a separate gitops repo
├── ci/             Customer-internal Jenkins pipeline
└── prometheus/     Standalone PrometheusRule alerts (Phase 4 SLOs)
```

## Where to look

| If you want to … | Read |
|---|---|
| Run the stack on your laptop | `../docs/local-dev.md` (uses `deploy/docker/`) |
| Install in production | `../docs/deployment.md` (uses `deploy/helm/`) |
| Promote a release across envs | `gitops/README.md` |
| Wire the customer's Jenkins | `ci/Jenkinsfile` |
| Apply standalone Prom alerts (without the chart) | `prometheus/alerts.yaml` |

## Sub-directories

### `docker/` — local development
Multi-arch Dockerfile, docker-compose stacks (dev + prod-like), nginx config for the served frontend, and pre-flight + seed scripts. Driven from the root `Makefile`. **Not used in production**.

### `helm/ai-troubleshooting/` — production install
Helm chart that runs on **Kubernetes 1.28+** and **OpenShift 4.x** from the same templates. Bundled Bitnami `postgresql` + `redis` subcharts (toggleable). 5 categories of fail-fast validation guards. See `helm/ai-troubleshooting/README.md`.

### `gitops/` — ArgoCD skeleton
Per-env values and `Application` CRDs for dev / staging / prod. Designed to be **copied into a separate gitops repo** (typically one per customer). Promotion = bump chart version pin in the next env's values.

### `ci/` — Customer-internal Jenkins
`Jenkinsfile` that builds the multi-arch image, packages the Helm chart, pushes both to a customer Nexus (or any OCI registry), and triggers an ArgoCD sync. Mirrors what `.github/workflows/release.yml` does for the open-source side.

### `prometheus/` — Standalone SLO alerts
`alerts.yaml` containing PrometheusRule alerts for the Phase 4 SLO metrics (investigation step latency, in-flight cap, etc.). When the Helm chart's `prometheusRule.enabled=true`, equivalent alerts ship via the chart. This standalone file is for clusters where the chart is already installed but the operator wants to roll PrometheusRule changes independently of the chart's upgrade cadence.

> **Future cleanup (separate PR):** the chart's `templates/prometheusrule.yaml` currently uses placeholder metric names. The real names live in `prometheus/alerts.yaml`. Merge them — chart should reference the real names, then this standalone file can be deleted.

## What's NOT in `deploy/`

| Path | Why it's elsewhere |
|---|---|
| `Makefile` (root) | UX entry point — same convention as `Vagrantfile`, `Dockerfile` |
| `.github/workflows/` | GitHub-mandated path |
| `.env.example` (root) | Standard convention for `.env`-based config |
| `docs/local-dev.md`, `docs/deployment.md` | All docs live under `docs/` |
