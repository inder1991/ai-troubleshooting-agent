# Local-dev orchestration for the AI Troubleshooting System.
#
# Day-to-day:   make up     → fresh laptop to running stack
# When stuck:   make help   → list every target

# ─── Configuration ────────────────────────────────────────────────────────────
COMPOSE_DEV       := docker compose -f deploy/docker/compose.dev.yml
COMPOSE_PRODLIKE  := docker compose -f deploy/docker/compose.prod-like.yml
PREFLIGHT         := deploy/docker/scripts/preflight.sh
SEED              := deploy/docker/scripts/seed.sh

# Default service for `make logs SERVICE=...`.
SERVICE ?=

# ─── Phony targets ────────────────────────────────────────────────────────────
.PHONY: help up up-prod-like down stop reset rebuild seed logs ps psql redis-cli \
        migrate test test-backend test-frontend lint shell-web shell-worker \
        clean clean-volumes

.DEFAULT_GOAL := help

# ─── Help ─────────────────────────────────────────────────────────────────────
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} \
	  /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' \
	  $(MAKEFILE_LIST) \
	  | sort

# ─── Lifecycle ────────────────────────────────────────────────────────────────
up: $(PREFLIGHT)  ## Build, migrate, and start the dev stack (default)
	@bash $(PREFLIGHT)
	@$(COMPOSE_DEV) up -d --build
	@echo ""
	@echo "  ✓ Frontend:  http://localhost:$${FRONTEND_PORT:-5173}"
	@echo "  ✓ API:       http://localhost:$${BACKEND_PORT:-8000}"
	@echo "  ✓ Health:    http://localhost:$${BACKEND_PORT:-8000}/healthz"
	@echo ""
	@echo "  Next:    make seed     load demo investigations"
	@echo "           make logs     tail all services"
	@echo "           make psql     drop into Postgres"

up-prod-like:  ## Build + start the prod image locally (no hot reload)
	@bash $(PREFLIGHT)
	@$(COMPOSE_PRODLIKE) up -d --build
	@echo "  ✓ Frontend:  http://localhost:$${FRONTEND_PORT:-5173}"
	@echo "  ✓ API:       http://localhost:$${BACKEND_PORT:-8000}"

down:  ## Stop the dev stack (preserves volumes)
	@$(COMPOSE_DEV) down

stop: down  ## Alias for `down`

reset:  ## Stop + delete all volumes (fresh DB)
	@$(COMPOSE_DEV) down -v
	@$(COMPOSE_PRODLIKE) down -v 2>/dev/null || true
	@echo "  ✓ Stopped + volumes deleted. 'make up' for fresh stack."

rebuild:  ## Force image rebuild (no cache)
	@$(COMPOSE_DEV) build --no-cache

# ─── Data ─────────────────────────────────────────────────────────────────────
seed:  ## Load fixture investigations into running stack
	@bash $(SEED)

migrate:  ## Run Alembic migrations against running Postgres
	@$(COMPOSE_DEV) run --rm backend-migrate

# ─── Inspection ───────────────────────────────────────────────────────────────
ps:  ## Show service status
	@$(COMPOSE_DEV) ps

logs:  ## Tail logs (SERVICE=<name> for one service)
ifeq ($(SERVICE),)
	@$(COMPOSE_DEV) logs -f --tail=100
else
	@$(COMPOSE_DEV) logs -f --tail=100 $(SERVICE)
endif

psql:  ## Drop into psql against bundled Postgres
	@$(COMPOSE_DEV) exec postgres psql -U $${POSTGRES_USER:-ai_tshoot} $${POSTGRES_DB:-ai_tshoot}

redis-cli:  ## Drop into redis-cli against bundled Redis
	@$(COMPOSE_DEV) exec redis redis-cli -a $${REDIS_PASSWORD:-ai_tshoot_dev}

shell-web:  ## Bash into backend-web
	@$(COMPOSE_DEV) exec backend-web bash

shell-worker:  ## Bash into backend-worker
	@$(COMPOSE_DEV) exec backend-worker bash

# ─── Tests ────────────────────────────────────────────────────────────────────
test: test-backend test-frontend  ## Run all tests in containers

test-backend:  ## Run pytest in backend container
	@$(COMPOSE_DEV) exec -T backend-web pytest -q --tb=short

test-frontend:  ## Run vitest in frontend container
	@$(COMPOSE_DEV) exec -T frontend npx vitest run

lint:  ## Run linters (ruff + tsc)
	@$(COMPOSE_DEV) exec -T backend-web ruff check src tests || true
	@$(COMPOSE_DEV) exec -T frontend npx tsc --noEmit || true

# ─── Cleanup ──────────────────────────────────────────────────────────────────
clean:  ## Remove dangling Docker resources
	@docker system prune -f

clean-volumes: reset  ## Alias for `reset`

# ─── AI Harness ───────────────────────────────────────────────────────────────
# Single contract entry point. All five execution contexts (AI loop,
# terminal, pre-commit, CI, autonomous agent) call the same targets.
# Same script, same checks, same output format. Per H-14 / H-20.

.PHONY: validate-fast validate-full validate harness harness-install

validate-fast:  ## Inner-loop gate (< 30 s). Lint + typecheck + custom checks.
	@python3 tools/run_validate.py --fast

validate-full:  ## Pre-commit / CI gate. Fast + tests + heavy audits.
	@python3 tools/run_validate.py --full

validate: validate-full  ## Default validate is the full gate.

harness:  ## Regenerate .harness/generated/ from code (per H-4).
	@python3 tools/run_harness_regen.py

harness-install:  ## One-time installer for the pre-commit hook (per H-18).
	@bash tools/install_pre_commit.sh

harness-typecheck-baseline:  ## Q19 — regenerate mypy + tsc baselines.
	@python3 tools/generate_typecheck_baseline.py

.PHONY: harness-baseline-refresh
harness-baseline-refresh:  ## Regenerate every .harness/baselines/<rule>_baseline.json deterministically.
	@python3 tools/refresh_baselines.py
