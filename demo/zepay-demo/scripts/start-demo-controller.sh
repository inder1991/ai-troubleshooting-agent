#!/usr/bin/env bash
# Launches the demo-controller on the operator's laptop.
#
# Prereqs (storyboard §9):
#   1. The 4 kubectl port-forwards (scripts/port-forwards.sh) are open
#      in a separate terminal.
#   2. The workflow backend is running at WORKFLOW_BACKEND_URL
#      (default http://localhost:8000).
#   3. kubectl's default context points at the demo cluster.
#
# Usage:
#   ./scripts/start-demo-controller.sh
#
# The page lands at http://localhost:7777/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTROLLER="$ROOT/demo-controller"

# Use a local venv so we don't pollute the system python.
VENV="$CONTROLLER/.venv"
if [ ! -d "$VENV" ]; then
  echo "→ creating venv at $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$CONTROLLER/requirements.txt"
fi

export PYTHONPATH="$CONTROLLER"
exec "$VENV/bin/uvicorn" app.main:app \
    --host 127.0.0.1 --port 7777 \
    --app-dir "$CONTROLLER"
