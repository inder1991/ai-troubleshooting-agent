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
| Tune SLO alert thresholds | `helm/ai-troubleshooting/values.yaml` → `prometheusRule.rules` |

## Sub-directories

### `docker/` — local development
Multi-arch Dockerfile, docker-compose stacks (dev + prod-like), nginx config for the served frontend, and pre-flight + seed scripts. Driven from the root `Makefile`. **Not used in production**.

### `helm/ai-troubleshooting/` — production install
Helm chart that runs on **Kubernetes 1.28+** and **OpenShift 4.x** from the same templates. Bundled Bitnami `postgresql` + `redis` subcharts (toggleable). 5 categories of fail-fast validation guards. See `helm/ai-troubleshooting/README.md`.

### `gitops/` — ArgoCD skeleton
Per-env values and `Application` CRDs for dev / staging / prod. Designed to be **copied into a separate gitops repo** (typically one per customer). Promotion = bump chart version pin in the next env's values.

### `ci/` — Customer-internal Jenkins
`Jenkinsfile` that builds the multi-arch image, packages the Helm chart, pushes both to a customer Nexus (or any OCI registry), and triggers an ArgoCD sync. Mirrors what `.github/workflows/release.yml` does for the open-source side.

## What's NOT in `deploy/`

| Path | Why it's elsewhere |
|---|---|
| `Makefile` (root) | UX entry point — same convention as `Vagrantfile`, `Dockerfile` |
| `.github/workflows/` | GitHub-mandated path |
| `.env.example` (root) | Standard convention for `.env`-based config |
| `docs/local-dev.md`, `docs/deployment.md` | All docs live under `docs/` |
