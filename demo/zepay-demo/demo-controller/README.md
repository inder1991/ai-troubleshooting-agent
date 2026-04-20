# Zepay Demo Controller

FastAPI app + minimal HTML operator page that orchestrates the live-
cluster demo. Runs on the operator's laptop, not in the cluster.

Storyboard: [../../../docs/plans/2026-04-19-zepay-fintech-demo-scenario.md](../../../docs/plans/2026-04-19-zepay-fintech-demo-scenario.md)

## Layout

```
demo-controller/
├── app/
│   ├── main.py         FastAPI endpoints
│   ├── kube.py         kubectl wrapper (apply fault, scale k6, pg reset)
│   ├── trigger.py      deterministic race-trigger for 47 customers
│   ├── state.py        in-process demo state
│   └── healthcheck.py  pings ES / Prom / Jaeger / K8s
├── operator-ui/
│   └── index.html      6-button operator page (served at /)
├── fixtures/
│   ├── historical-incident.json            seeded into workflow-backend archive
│   └── remediation/
│       ├── pr-8427-payment-service.json    the hero fix (Bug #1)
│       ├── pr-1203-shared-finance-models.json  amplifier (Bug #2)
│       └── pr-294-reconciliation-job.json       suppressor (Bug #3)
└── requirements.txt
```

## Starting it

```bash
# Open four port-forwards in one terminal:
./demo/zepay-demo/scripts/port-forwards.sh

# Start the controller in a second terminal:
./demo/zepay-demo/scripts/start-demo-controller.sh
# → http://localhost:7777/
```

## Endpoints (from the operator page or curl)

| Method | Path                       | Purpose                             |
|--------|----------------------------|-------------------------------------|
| GET    | /                          | operator HTML                       |
| GET    | /demo/state                | current demo state                  |
| POST   | /demo/healthcheck          | ES + Prom + Jaeger + K8s reachable? |
| POST   | /demo/reset                | truncate tables, remove fault       |
| POST   | /demo/start-traffic?rps=N  | scale k6 + rollout                  |
| POST   | /demo/inject-fault         | apply the 15s Istio VirtualService  |
| POST   | /demo/trigger-incident     | deterministic race for 47 customers |
| POST   | /demo/spike?rps=500        | bump k6 for 60s, then revert        |
| POST   | /demo/historical-seed      | inject Feb-2026 sibling incident    |
| GET    | /remediation/{pr_id}       | pre-baked fix diff (8427/1203/294)  |

## The three fix bundles

When the workflow-backend's RemediationCampaign UI wants to display
the fix diffs, it fetches them from this controller (storyboard §8).
The bundles include file-level diffs, line-count deltas, verification
notes (unit tests added, CI-green predicted, rollback plans), and
realistic commit SHAs.
