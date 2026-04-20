#!/usr/bin/env bash
# Builds the Python reconciliation-job image.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICES_DIR="$ROOT/services"
TAG="${TAG:-demo-0.1.0}"

echo "=== building zepay/reconciliation-job:$TAG ==="
docker build -t "zepay/reconciliation-job:$TAG" "$SERVICES_DIR/reconciliation-job"
echo "Done. Built zepay/reconciliation-job:$TAG"
