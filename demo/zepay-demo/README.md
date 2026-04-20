# Zepay Demo — Live-Cluster Scenario

End-to-end demo of the app-diagnostic workflow against a fintech
double-debit incident, deployable to a local Kubernetes cluster.

- **Storyboard:** [`docs/plans/2026-04-19-zepay-fintech-demo-scenario.md`](../../docs/plans/2026-04-19-zepay-fintech-demo-scenario.md)
- **Operator runbook:** [`docs/OPERATOR-RUNBOOK.md`](docs/OPERATOR-RUNBOOK.md)
- **Demo-controller:** [`demo-controller/README.md`](demo-controller/README.md)

## Layout

```
demo/zepay-demo/
├── charts/
│   ├── zepay-base/          PR-K2 — namespaces + Postgres + Redis + Istio + RBAC
│   ├── zepay-service/       PR-K3 — library chart for all 9 microservices
│   └── reconciliation-job/  PR-K5 — CronJob + web Deployment
│
├── services/
│   ├── go-common/              PR-K3 shared Go module
│   ├── api-gateway/            PR-K3 reference Go service
│   ├── auth-service/           PR-K3.5
│   ├── cart-service/           PR-K3.5
│   ├── checkout-service/       PR-K3.5
│   ├── fraud-adapter/          PR-K3.5 — convincing false lead
│   ├── inventory-service/      PR-K3.5 — target of Istio fault
│   ├── notification-service/   PR-K3.5
│   ├── wallet-service/         PR-K3.5 — takes the double-debit
│   ├── payment-service/        PR-K4 — houses Bug #1
│   ├── shared-finance-models/  PR-K4 — houses Bug #2
│   └── reconciliation-job/     PR-K5 — houses Bug #3
│
├── demo-controller/            PR-K6 — FastAPI on laptop
│   ├── app/                    main.py + kube.py + trigger.py + state.py + healthcheck.py
│   ├── operator-ui/            index.html (6-button operator page)
│   └── fixtures/               historical + 3 remediation diff bundles
│
├── k6/                         PR-K6 — traffic generator
│   ├── traffic.js
│   └── k6-deployment.yaml
│
├── istio/
│   └── inventory-timeout-fault.yaml   PR-K2 — on-demand VirtualService
│
├── scripts/
│   ├── build-go-services.sh           PR-K3
│   ├── build-java-services.sh         PR-K4
│   ├── build-python-services.sh       PR-K5
│   ├── start-demo-controller.sh       PR-K6
│   └── port-forwards.sh               PR-K2 — 4 ES/Prom/Jaeger port-forwards
│
└── docs/
    └── OPERATOR-RUNBOOK.md            PR-K7 — end-to-end runbook
```

## PR series

| PR | Ticket | State |
|---|---|---|
| #73 | PR-K1 — storyboard | merged |
| #74 | PR-K2 — base infra | merged |
| #75 | PR-K3 — Go scaffolding + stubs | merged |
| #76 | PR-K3.5 — real Go handlers | merged |
| #77 | PR-K4 — Java payment-service + shared-finance-models | merged |
| #78 | PR-K5 — Python reconciliation-job | merged |
| #79 | PR-K6 — k6 + demo-controller + operator HTML + fix diffs | merged |
| **this** | **PR-K7 — demo-seed endpoint + E2E + operator README** | **in review** |

## Quick start

1. Install base + services (see §0 of the runbook).
2. Terminal 1: `./scripts/port-forwards.sh`
3. Terminal 2: `./scripts/start-demo-controller.sh`
4. Terminal 3: `DEMO_MODE=on uvicorn src.api.main:app --port 8000` (backend)
5. Terminal 4: `npm run dev` (frontend)
6. Browser: http://localhost:7777/ → Reset → Start Traffic → Seed History
7. Proceed with the 90-second demo per the runbook.
