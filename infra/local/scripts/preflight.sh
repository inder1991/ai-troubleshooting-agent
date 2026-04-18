#!/usr/bin/env bash
# Pre-flight checks before `make up`. Catches the boring stuff loudly so the
# user doesn't get a confusing 30-line docker error.
#
# Exits 0 on success, non-zero with a human-readable error on failure.
set -euo pipefail

# Resolve repo root from this script's location (infra/local/scripts/).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "${ROOT}"

red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }

fail() {
  red "✗ $1"
  exit 1
}

# 1. Docker daemon
if ! docker info >/dev/null 2>&1; then
  fail "Docker daemon not reachable. Start Docker Desktop / colima / dockerd."
fi

# 2. Compose v2
if ! docker compose version >/dev/null 2>&1; then
  fail "docker compose v2 not found. Install: https://docs.docker.com/compose/install/"
fi

# 3. .env file
if [[ ! -f .env ]]; then
  yellow "⚠ No .env file found. Bootstrapping from .env.example…"
  cp .env.example .env
  yellow "  Created .env. Edit it to set ANTHROPIC_API_KEY, then re-run 'make up'."
  exit 1
fi

# 4. ANTHROPIC_API_KEY set
# shellcheck disable=SC1091
set -a; source .env; set +a
if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  fail "ANTHROPIC_API_KEY is empty in .env. Get a key at https://console.anthropic.com/ and re-run."
fi

# 5. Ports free
check_port() {
  local port="$1" name="$2"
  if lsof -iTCP:"${port}" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    local proc
    proc="$(lsof -iTCP:"${port}" -sTCP:LISTEN -n -P | awk 'NR==2 {print $1, "(pid", $2 ")"}')"
    fail "Port ${port} (${name}) is in use by ${proc}. Stop that process or set ${name}_PORT in .env."
  fi
}
check_port "${POSTGRES_PORT:-5432}"  POSTGRES
check_port "${REDIS_PORT:-6379}"     REDIS
check_port "${BACKEND_PORT:-8000}"   BACKEND
check_port "${FRONTEND_PORT:-5173}"  FRONTEND

green "✓ pre-flight passed"
