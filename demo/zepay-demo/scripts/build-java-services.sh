#!/usr/bin/env bash
# Builds the Java service images (payment-service + its shared lib).
#
# The Dockerfile expects both shared-finance-models and payment-service
# sources in a single build context — Maven needs to install the lib
# into the local .m2 before the service pom resolves against it.
# This script stages both into a tmp dir and runs one docker build.
#
# Usage:
#   ./scripts/build-java-services.sh             # builds payment-service
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICES_DIR="$ROOT/services"
TAG="${TAG:-demo-0.1.0}"

ctx="$(mktemp -d)"
trap 'rm -rf "$ctx"' EXIT

cp -R "$SERVICES_DIR/shared-finance-models" "$ctx/shared-finance-models"
cp -R "$SERVICES_DIR/payment-service"       "$ctx/payment-service"
cp    "$SERVICES_DIR/payment-service/Dockerfile" "$ctx/Dockerfile"

echo "=== building zepay/payment-service:$TAG ==="
docker build -t "zepay/payment-service:$TAG" "$ctx"
echo "Done. Built zepay/payment-service:$TAG"
