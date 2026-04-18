# AI Troubleshooting System

Multi-agent diagnostic platform that investigates production incidents — pulls logs, metrics, K8s state, traces, and code, runs deterministic + LLM-driven analysis, and returns evidence-backed root-cause findings with calibrated confidence.

## Quick start

```bash
cp .env.example .env       # set ANTHROPIC_API_KEY
make up                    # build + migrate + start the full stack
```

→ http://localhost:5173

Full local-dev guide: [`docs/local-dev.md`](docs/local-dev.md)

## Production install

Helm chart for Kubernetes 1.28+ and OpenShift 4.x:

```bash
helm dependency update deploy/helm/ai-troubleshooting
helm install ai-tshoot deploy/helm/ai-troubleshooting \
  -n ai-tshoot \
  --set anthropic.defaultKey.existingSecret=anthropic-default
```

Full operator runbook: [`docs/deployment.md`](docs/deployment.md)

## Repo layout

```
backend/     Python 3.14 + FastAPI + LangGraph; multi-agent supervisor
frontend/    React + TypeScript + Vite + Tailwind; War Room investigation UI
deploy/      Docker, Helm, GitOps, CI — see deploy/README.md
docs/        Architecture + plans + runbooks
scripts/     Operational scripts; scripts/historical/ holds one-shot migrations
.github/     GitHub Actions (CI + release)
```

## What this product does

- **Investigates incidents end-to-end.** User describes a symptom; agents fan out across logs (ELK / OpenSearch), metrics (Prometheus), K8s state, traces, and source code.
- **Returns evidence-backed root cause.** Phase-4 signature library catches known patterns instantly; CriticEnsemble adversarially reviews findings; SelfConsistency re-runs to detect disagreement.
- **Calibrated confidence.** "70% confident" actually means "right ~70% of the time" — measured via ECE on a labelled eval set.
- **Honest about uncertainty.** Coverage gaps surface as first-class UI elements (`/readyz` reports which dependency is unreachable), not hidden behind a confident wrong answer.

## Architecture phases shipped

| Phase | Focus | Status |
|---|---|---|
| 0 | Eval seed + bench | ✅ |
| 1 | Idempotency, outbox, locks, prompt safety | ✅ |
| 2 | Deterministic causal + confidence rebuild | ✅ |
| 3 | Coverage, integrations, tools | ✅ |
| 4 | Patterns, eval, learning, trust UX | ✅ |

Plans archived under `docs/plans/`.

## Contributing

- Backend tests: `cd backend && pytest -q`
- Frontend tests: `cd frontend && npx vitest`
- Full local stack tests: `make test`
- Linting: `make lint`

## License

[Internal — set per company policy]
