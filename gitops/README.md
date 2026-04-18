# GitOps repo skeleton

Sample structure for ArgoCD-driven multi-environment deployments of the AI
Troubleshooting System. **Copy this `gitops/` directory into a separate
git repo** (typically one per customer, e.g. `acme-platform-gitops`) and
let ArgoCD watch it.

## Layout

```
gitops/
├── envs/
│   ├── dev/
│   │   ├── values.yaml          # env-specific overrides
│   │   └── argocd-app.yaml      # ArgoCD Application CRD
│   ├── staging/
│   │   ├── values.yaml
│   │   └── argocd-app.yaml
│   └── prod/
│       ├── values.yaml
│       └── argocd-app.yaml
└── README.md (this file)
```

## How it works

1. Each `envs/<env>/argocd-app.yaml` is an ArgoCD `Application` CRD pointing
   at the chart in the *app* repo (or an OCI registry) at a **pinned chart
   version** plus the env's `values.yaml`.
2. ArgoCD watches the gitops repo. Any commit re-syncs the matching env.
3. **Promotion = edit the chart-version pin** in the next env's
   `values.yaml` (or change the `targetRevision` in `argocd-app.yaml`) and
   commit. ArgoCD picks it up.

## Apply ArgoCD Applications

After dropping this directory into your gitops repo and updating the URLs:

```bash
# One-time: install ArgoCD into the cluster (out of scope for this chart).
# Then apply the per-env Application CRDs.
kubectl apply -f gitops/envs/dev/argocd-app.yaml
kubectl apply -f gitops/envs/staging/argocd-app.yaml
kubectl apply -f gitops/envs/prod/argocd-app.yaml
```

Or via `argocd-app-of-apps` pattern — declare one parent Application
pointing at `gitops/envs/` and ArgoCD instantiates each child.

## Promotion workflow

```
PR in app repo  →  CI builds image:0.1.2 + chart:0.1.2  →  registry
                                                            │
                                ┌───────────────────────────┘
                                ▼
PR in gitops repo  →  bump targetRevision to 0.1.2 in dev/argocd-app.yaml
                   →  ArgoCD auto-syncs dev
                   →  smoke checks pass
                   →  bump staging
                   →  bump prod
```

## Env conventions

| Env | Chart values | Resources | Replicas | HPA | Backup retention |
|---|---|---|---|---|---|
| dev | `values.yaml` only | small | 1 | off | 3d |
| staging | `values.yaml` + `values-prod.yaml` | medium | 2 | on (low max) | 7d |
| prod | `values.yaml` + `values-openshift.yaml` + `values-prod.yaml` | full | 3+ | on | 30d |

## Why a separate gitops repo (not just folders in app repo)?

- App-repo PRs are about code changes; gitops-repo PRs are about deployments. Different reviewers, different velocity, different CI.
- Customers can fork only the gitops repo to inject their own org-policy mutations without touching app code.
- Compliance: gitops repo is the single source of truth for "what's running where" — no need to grep app-repo CI history.

## Secrets

ArgoCD does NOT see your Anthropic API key or DB credentials. Pre-create
the Secrets in the cluster (or wire ExternalSecrets / sealed-secrets), and
the chart references them by name only.

For the multi-key Anthropic setup:
```bash
kubectl create secret generic anthropic-default --from-literal=api_key=sk-...
kubectl create secret generic anthropic-premium --from-literal=api_key=sk-...
kubectl create secret generic anthropic-cheap   --from-literal=api_key=sk-...
```

## Rollback

```bash
git revert <bad-promotion-commit>
git push
# ArgoCD detects the change and rolls back automatically.
```

For break-glass (ArgoCD itself broken):
```bash
helm rollback ai-tshoot -n ai-tshoot
```
