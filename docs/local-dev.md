# Local Development

Fresh laptop to running stack in **3 commands**.

## Prerequisites

- macOS (Apple Silicon or Intel) or Linux. **Windows is not supported.**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or [colima](https://github.com/abiosoft/colima)) — `docker compose v2` available.
- An [Anthropic API key](https://console.anthropic.com/).
- ~6 GB of free RAM for the stack to run comfortably alongside your IDE + browser.

## Quick start

```bash
git clone <repo-url>
cd ai-troubleshooting-systetm

cp .env.example .env
# Edit .env and paste your ANTHROPIC_API_KEY

make up
```

That's it. After ~60 seconds (first run; cached on subsequent), you'll see:

```
  ✓ Frontend:  http://localhost:5173
  ✓ API:       http://localhost:8000
  ✓ Health:    http://localhost:8000/healthz
```

Open http://localhost:5173 in your browser.

## What's running

| Service | Image | Purpose |
|---|---|---|
| `postgres` | `postgres:15-alpine` | Outbox, audit log, agent priors, eval store, DAG snapshots |
| `redis` | `redis:7-alpine` | Distributed locks + Streams (event bus) |
| `backend-migrate` | (built locally) | One-shot Alembic upgrade; exits when done |
| `backend-web` | (built locally) | FastAPI + uvicorn `--reload` (hot reload on src edits) |
| `backend-worker` | (built locally) | Outbox relay + investigation runner + scheduler + resume scan |
| `frontend` | (built locally) | Vite dev server with HMR |

All five are wired with healthchecks; dependent services wait on `service_healthy`.

## Daily commands

| Command | What it does |
|---|---|
| `make up` | Build + migrate + start everything (default) |
| `make down` | Stop everything; preserve volumes |
| `make reset` | Stop + delete all volumes (fresh DB) |
| `make seed` | Load fixture investigations into running stack |
| `make logs` | Tail all services |
| `make logs SERVICE=backend-web` | Tail one service |
| `make psql` | Drop into psql against bundled Postgres |
| `make redis-cli` | Drop into redis-cli against bundled Redis |
| `make migrate` | Run Alembic migrations only (after pulling new code) |
| `make rebuild` | Force image rebuild (no cache) |
| `make test` | Run backend pytest + frontend vitest in containers |
| `make help` | List every target |

## Hot reload

Both backend and frontend reload **without** restarting the container:

- **Backend** — `uvicorn --reload` watches `backend/src/**/*.py`. Save → ~1s reload. No browser refresh needed; existing requests just see the new code on next call.
- **Frontend** — Vite HMR watches `frontend/src/**/*.{ts,tsx,css}`. Save → ~200ms; the browser surgically swaps the changed module, often preserving form state.

Source is bind-mounted from your laptop into the container, so edits in your IDE are immediately visible to the running services.

**Worker code changes need a manual restart** (long-lived investigations would otherwise survive the reload):

```bash
docker compose -f deploy/docker/compose.dev.yml restart backend-worker
```

## Test the prod image locally

`make up` runs the **dev** image (uvicorn + vite dev server). To test the actual production image (gunicorn + nginx + built dist), use:

```bash
make up-prod-like
```

Same ports, no hot reload, no bind mounts. Useful for catching:
- Missing migration steps that the prod build needs
- CSP / nginx header issues
- gunicorn signal handling differences from uvicorn-reload
- Bundled-asset path issues

## Resetting the database

```bash
make reset    # destroys volumes
make up       # rebuilds with empty DB
make seed     # optional — repopulate with fixtures
```

## Pre-flight checks

`make up` runs `deploy/docker/scripts/preflight.sh` first. It catches:

- Docker daemon not running
- `docker compose v2` not installed
- `.env` missing → bootstraps from `.env.example` and stops
- `ANTHROPIC_API_KEY` empty → tells you where to get one
- Required ports busy → names the conflicting process

You can override default ports in `.env`:

```bash
BACKEND_PORT=8001
FRONTEND_PORT=5174
POSTGRES_PORT=5433
REDIS_PORT=6380
```

## Connecting to the bundled databases from your laptop

While the stack is running, host tools work directly:

```bash
psql postgresql://ai_tshoot:ai_tshoot_dev@localhost:5432/ai_tshoot
redis-cli -h localhost -p 6379 -a ai_tshoot_dev
```

(Adjust passwords/ports if you've overridden them in `.env`.)

## Resource footprint

Default budget (suitable for 16 GB Macs):

| Service | Memory limit | Memory used (idle) |
|---|---|---|
| postgres | 512 MB | ~80 MB |
| redis | 256 MB | ~10 MB |
| backend-web | (no limit) | ~250 MB |
| backend-worker | (no limit) | ~250 MB |
| frontend (vite dev) | (no limit) | ~400 MB |
| **Total idle** | | **~1 GB** |

During an active investigation: spikes to ~2.5 GB total.

## Troubleshooting

### "Port 5173 is in use"

Either another service is using it (`lsof -iTCP:5173 -sTCP:LISTEN`), or a previous `make up` session didn't clean up. Run `make down` to be sure.

### Migrations fail on first `make up`

Pull the latest code, then:

```bash
make reset
make up
```

The schema is regenerated from scratch.

### Worker is "running" but my investigation never starts

Worker code changes need a manual restart:

```bash
docker compose -f deploy/docker/compose.dev.yml restart backend-worker
make logs SERVICE=backend-worker
```

### Frontend HMR stops working

Vite occasionally loses its websocket connection (laptop sleep, network change). Hard-refresh the browser tab once; HMR reconnects.

### Volume corruption / weird state

```bash
make reset    # nukes volumes
make up
```

## What's not in the local stack

The product *integrates with* these external systems via Settings UI; they're not bundled because each customer brings their own:

- OpenSearch / Elasticsearch (log agent target)
- Prometheus (metrics agent target — the cluster being diagnosed)
- Kubernetes API (cluster agent target)
- Jira / Confluence / Remedy / GitHub (ITSM + code integrations)

For local testing of agent code paths against these, point your local stack at a dev instance via the Settings UI. None are required for the app to start.

## Production deployment

This local stack is for development only. Production uses the Helm chart in `deploy/helm/ai-troubleshooting/` — see `docs/deployment.md` (coming in PR 3).
