# Zepay Demo — Operator Runbook

End-to-end runbook for the 90-second CXO demo. Assumes you've already
merged PR-K1 through PR-K7 and the images are built.

Storyboard: [`docs/plans/2026-04-19-zepay-fintech-demo-scenario.md`](../../../docs/plans/2026-04-19-zepay-fintech-demo-scenario.md)

---

## 0. One-time setup

### 0.1 Cluster prerequisites (you already have these)

- Kubernetes 1.28+
- Istio (sidecar injection on)
- ELK (namespace `elk` by default; override via env)
- Prometheus + kube-prometheus-stack (namespace `monitoring`)
- Jaeger-Operator (namespace `observability`)

### 0.2 Build all images locally

```bash
cd demo/zepay-demo

./scripts/build-go-services.sh       # 8 Go images
./scripts/build-java-services.sh     # payment-service + shared lib
./scripts/build-python-services.sh   # reconciliation-job
```

Tag (`demo-0.1.0`) is fixed in the Helm values. If you push to a
registry, bump the tag in each `services/*/values.yaml`.

### 0.3 Install the base infrastructure

```bash
helm upgrade --install zepay-base ./charts/zepay-base --create-namespace
```

Creates `payments-prod` + `demo-ctrl` namespaces, Postgres (6 schemas),
Redis, Istio PeerAuthentication + Gateway, and a read-only
ServiceAccount for the workflow backend.

### 0.4 Install the 9 microservices

```bash
for svc in api-gateway auth-service cart-service checkout-service \
           inventory-service fraud-adapter wallet-service \
           notification-service payment-service; do
  helm upgrade --install "$svc" ./charts/zepay-service \
    -f "services/$svc/values.yaml"
done

helm upgrade --install reconciliation-job ./charts/reconciliation-job
```

Verify:
```bash
kubectl get deploy -n payments-prod
# expect 9 Deployments + postgres + redis, all Ready
```

### 0.5 Install k6 (background traffic)

```bash
# Paste the traffic.js contents into the ConfigMap manifest first —
# the k8s manifest references it by file for readability.
kubectl create configmap k6-script \
  --from-file=traffic.js=./k6/traffic.js \
  -n demo-ctrl --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f ./k6/k6-deployment.yaml
```

### 0.6 Enable DEMO_MODE on the workflow backend

The backend gates `/api/v4/demo/seed` behind `DEMO_MODE=on`. In your
existing backend process (or its Helm values), set:

```bash
export DEMO_MODE=on
# then restart the backend so the env var applies
```

This is the **only** production-affecting change in the demo PRs. No
other endpoint's behavior changes when `DEMO_MODE` is off.

---

## 1. Per-demo setup (run before every demo)

### Terminal 1 — open the four port-forwards

```bash
cd demo/zepay-demo
./scripts/port-forwards.sh
# Leave this open.
```

If your cluster uses different namespaces for ELK / Prom / Jaeger,
override:
```bash
ES_NS=logging PROM_NS=mon JAEGER_NS=tracing ./scripts/port-forwards.sh
```

### Terminal 2 — start the demo-controller

```bash
cd demo/zepay-demo
./scripts/start-demo-controller.sh
# → http://localhost:7777/
```

The launcher auto-creates a venv and installs FastAPI + uvicorn +
httpx. First run takes ~30 seconds; subsequent runs are instant.

### Terminal 3 — start the workflow backend (your usual command)

```bash
cd backend
DEMO_MODE=on uvicorn src.api.main:app --port 8000
```

### Terminal 4 — start the War Room frontend

```bash
cd frontend
npm run dev
# → http://localhost:5173
```

---

## 2. Before the CXO walks in

Open http://localhost:7777/ and click these in order:

1. **Re-check health** — four dots must go green.
2. **Reset** — truncate tables, remove any prior fault.
3. **Start Traffic (50 RPS)** — background traffic begins landing.
4. **Seed History** — Feb-2026 sibling incident lands in the archive.

State line now reads:
```
Traffic: on · Fault: off · Incident: — · History seeded: yes
```

Now open the War Room at `http://localhost:5173` in a second browser
tab, kept blank/idle. You're ready.

---

## 3. The 90-second demo (verbatim script)

Storyboard §9 has the full verbatim operator voice-over. Summary:

```
[t=0]    Click "Inject Fault"
[t=0]    Click "Trigger Incident"
         NARRATE: "47 customers being double-charged right now.
                   Every dashboard is still green."

[t=10]   Switch to War Room tab. Start a new session with:
           service_name: checkout-service  ← wrong on purpose
           namespace:    payments-prod
           time_window:  last 4h

[t=25]   Patient Zero banner flips checkout → payment-service.
         NARRATE: "Log Agent just reframed Patient Zero."

[t=35]   fraud-adapter lights up red.
         NARRATE: "Any human would chase this first. Watch."

[t=55]   EliminationLog surfaces H1 (fraud) eliminated.
         NARRATE: "1.6% of incident latency. Not it.
                   The 15s Istio timeout is."

[t=75]   Tracing Agent — double wallets.UPDATE spans visible.
         DisagreementStrip — metrics ↔ tracing disagreement.
         NARRATE: "Our own instrumentation contradicts itself.
                   The truth is in the traces."

[t=90]   Verdict lands.
         NARRATE: "92% confidence. Acme Logistics SLA penalty
                   triggered. Three repos. Fix ready."

[t=95]   Click Open PR on FixReadyBar.
         NARRATE: "One PR stops the bleeding. Two more close
                   the blind spot."

[t=100]  PAUSE. Wait for first CXO question.
```

---

## 4. After the demo (reset for next run)

1. Click **Reset** on the operator page.
2. Any uncommitted demo changes in the cluster are cleaned up:
   - `inventory-timeout-fault` VirtualService is deleted.
   - ledger.txns / wallet.balances / inventory.items / notif.outbox
     are truncated.
   - State dict reset.
3. The workflow backend's archive still holds the Feb-2026 incident
   (that's fine; leave it — re-seeding is idempotent).

---

## 5. Troubleshooting

### "Cluster health" shows a red dot

- **ES red**: `kubectl -n elk get svc elasticsearch` — check the
  service exists; then re-run `./scripts/port-forwards.sh`.
- **Prom red**: Prometheus may still be booting. Wait 20s and
  click Re-check.
- **Jaeger red**: does your cluster install call it `jaeger-query`
  under `observability`? If not, export the overrides:
  `JAEGER_NS=tracing JAEGER_SVC=jaeger ./scripts/port-forwards.sh`
- **K8s red**: your kubeconfig isn't pointing at the demo cluster.
  `kubectl config current-context` to check.

### Triggered 47 checkouts but only 2 double-charged

The Istio fault is 20%, so 47 × 0.2 ≈ 9-10 double-charges is the
expected steady-state number. If you got just 2:

- Verify `inventory-timeout-fault` VirtualService actually applied:
  `kubectl get vs -n payments-prod inventory-timeout-fault -o yaml`
- Check that `payment-service` is calling through the sidecar:
  `kubectl logs -n payments-prod deploy/payment-service --tail=20`
  should show `RetryAttempt=2 for inventory-reserve` for the
  affected transactions.

### Workflow backend verdict doesn't land in 90s

- Check `DEMO_MODE=on` is set on the backend process.
- Verify all four port-forwards are still alive (`ps aux | grep port-forward`).
- Look at `backend/logs/...` for agent errors — typically Jaeger
  connectivity, which the port-forward script is supposed to
  handle.

### Reset doesn't fully clean up

```bash
kubectl delete vs -n payments-prod inventory-timeout-fault --ignore-not-found
kubectl exec -n payments-prod deploy/postgres -- \
  psql -U zepay -d zepay -c \
  'TRUNCATE ledger.txns, wallet.balances, inventory.items, notif.outbox;'
```

---

## 6. Tearing down the cluster

```bash
helm uninstall reconciliation-job
for svc in payment-service notification-service wallet-service \
           fraud-adapter inventory-service checkout-service \
           cart-service auth-service api-gateway; do
  helm uninstall "$svc"
done
helm uninstall zepay-base
kubectl delete ns payments-prod demo-ctrl
```
