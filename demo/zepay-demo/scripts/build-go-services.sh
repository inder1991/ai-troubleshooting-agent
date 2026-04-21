#!/usr/bin/env bash
# Builds all 8 Go service images locally.
#
# Each service's build context is staged into a tmp dir that contains
# BOTH the service source and go-common — because go.mod's local
# `replace` needs both in the build context.
#
# Usage:
#   ./scripts/build-go-services.sh              # build all
#   ./scripts/build-go-services.sh api-gateway  # build one
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICES_DIR="$ROOT/services"
TAG="${TAG:-demo-0.1.0}"

ALL_SERVICES=(
  api-gateway
  auth-service
  cart-service
  checkout-service
  fraud-adapter
  inventory-service
  notification-service
  wallet-service
)

targets=("$@")
if [ ${#targets[@]} -eq 0 ]; then
  targets=("${ALL_SERVICES[@]}")
fi

build_one() {
  local svc="$1"
  local ctx
  ctx="$(mktemp -d)"
  # Dockerfile.in expects two sibling dirs in the build context:
  #   service/      — the service's own source (go.mod has `replace ../go-common`)
  #   go-common/    — the shared module the replace points at
  mkdir -p "$ctx/service"
  cp -R "$SERVICES_DIR/$svc/"* "$ctx/service/"
  cp -R "$SERVICES_DIR/go-common"  "$ctx/go-common"
  cp    "$SERVICES_DIR/Dockerfile.in" "$ctx/Dockerfile"
  echo "=== building zepay/$svc:$TAG ==="
  docker build -t "zepay/$svc:$TAG" "$ctx"
  rm -rf "$ctx"
}

for svc in "${targets[@]}"; do
  build_one "$svc"
done

echo "Done. Built:"
for svc in "${targets[@]}"; do
  echo "  zepay/$svc:$TAG"
done
