# Zepay Demo — Live-Cluster Infrastructure

This directory holds everything needed to run the Zepay fintech demo
scenario on a local Kubernetes cluster with ELK, Prometheus, Jaeger,
and Istio already installed.

Storyboard:
[`docs/plans/2026-04-19-zepay-fintech-demo-scenario.md`](../../docs/plans/2026-04-19-zepay-fintech-demo-scenario.md).

## Layout

```
demo/zepay-demo/
├── charts/zepay-base/           ← PR-K2 — this chart
│   Base infrastructure: namespaces, Postgres (6 schemas),
│   Redis, Istio base (mTLS + Gateway), RBAC for the workflow
│   backend. Apply ONCE per cluster.
│
├── istio/
│   └── inventory-timeout-fault.yaml
│       ← The 15s fault-injection VirtualService. NOT part of the
│       base chart. Applied on demand by the demo-controller.
│
├── scripts/
│   └── port-forwards.sh
│       ← Opens the four kubectl port-forwards the workflow
│       backend needs when it runs on your laptop.
│
├── sql/        ← reserved for future migrations; empty in PR-K2.
└── docs/       ← reserved for operator docs; empty in PR-K2.
```

Future PRs add:

- `charts/api-gateway`, `charts/auth-service`, … (PR-K3: 6 Go services)
- `charts/payment-service`, `charts/shared-finance-models` (PR-K4: Java)
- `charts/reconciliation-job` (PR-K5: Python CronJob)
- `charts/demo-controller` + `k6/` (PR-K6)

## Install the base chart

```bash
# Optional: preview what will be created
helm template zepay-base ./charts/zepay-base

# Install (or upgrade)
helm upgrade --install zepay-base ./charts/zepay-base \
  --create-namespace

# Verify
kubectl get ns payments-prod demo-ctrl
kubectl get deploy,svc,secret,cm -n payments-prod
kubectl get peerauthentication,gateway -n payments-prod
```

### What you get

- `payments-prod` namespace (istio-injection=enabled)
- `demo-ctrl` namespace (istio-injection=enabled)
- Postgres with 6 schemas (`auth`, `wallet`, `ledger`, `inventory`,
  `cart`, `notif`) and the core tables
- Redis
- Istio `PeerAuthentication STRICT` on `payments-prod`
- Istio `Gateway` named `zepay-gateway` (used by k6 + external curl)
- `ServiceAccount` + read-only `ClusterRole` for the workflow backend

### What this chart deliberately does NOT include

- **The 9 microservices** — they ship in PR-K3/K4/K5 as separate charts.
- **The Istio fault-injection VirtualService** — applied on demand
  by the demo-controller so the cluster is clean between runs
  (storyboard §4).
- **Prometheus + Jaeger + ELK + Istio itself** — you already have
  these in your cluster; we don't redeploy them.
- **The demo-controller + k6 + operator HTML page** — PR-K6.

## Open the port-forwards

Run this in a dedicated terminal before starting a demo. Leave it
open for the duration of the session.

```bash
./scripts/port-forwards.sh
```

If your namespaces differ from the defaults (`elk`, `monitoring`,
`observability`), override via env vars:

```bash
ES_NS=logging PROM_NS=mon JAEGER_NS=tracing ./scripts/port-forwards.sh
```

## Fault-injection on demand (manual test — later will be driven by demo-controller)

```bash
# Turn the 15s delay on
kubectl apply -f istio/inventory-timeout-fault.yaml

# ...run traffic, observe the bug reproduce...

# Turn it off
kubectl delete -f istio/inventory-timeout-fault.yaml
```

In PR-K6 the demo-controller wraps these two calls behind `POST /demo/inject-fault`
and `POST /demo/reset` so the operator clicks buttons instead of running kubectl.

## Uninstall

```bash
helm uninstall zepay-base
kubectl delete ns payments-prod demo-ctrl
```
