#!/usr/bin/env bash
# Session-start wrapper: invokes the harness loader against the repo root.
# Stdout is consumed by Claude Code as system context per its hook contract.
#
# Per H-2/H-4: load_harness.py reads .harness/* (canonical state) plus the
# generated/* files (auto-derived inventories) and emits a single bundled
# context block describing the project's contracts to the AI session.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Use load_harness.py's "global" mode (no --target) — emits the root +
# cross-cutting context. Per-file context is fetched on demand from the
# AI session loop. `|| true` so a transient loader failure never blocks
# the session.
python3 "${REPO_ROOT}/tools/load_harness.py" || true
