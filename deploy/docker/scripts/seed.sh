#!/usr/bin/env bash
# Loads fixture data into the running compose stack — a few sample
# investigations + completed runs + critic findings so the UI demos populated.
#
# Idempotent: safe to re-run; truncates seeded rows before inserting.
# Won't run unless the stack is already up.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "${ROOT}"

# shellcheck disable=SC1091
set -a; source .env; set +a

if ! docker compose -f deploy/docker/compose.dev.yml ps postgres --status running --quiet | grep -q .; then
  echo "✗ Stack is not running. Run 'make up' first." >&2
  exit 1
fi

echo "→ Seeding fixture investigations…"

# Run the seed script through the backend container so it has access to
# SQLAlchemy models and the right env. The actual fixture-loader module
# lives in backend/src/scripts/seed_fixtures.py and is implemented in PR 2
# alongside the worker dispatcher.
docker compose -f deploy/docker/compose.dev.yml exec -T backend-web \
  python -m src.scripts.seed_fixtures

echo "✓ Seeded. Browse to http://localhost:${FRONTEND_PORT:-5173}/sessions"
