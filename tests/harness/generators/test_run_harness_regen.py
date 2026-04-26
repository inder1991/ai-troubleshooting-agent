"""H.2.6 — run_harness_regen orchestrator test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = REPO_ROOT / "tools" / "run_harness_regen.py"


def test_orchestrator_runs_typecheck_inventory_only() -> None:
    result = subprocess.run(
        [sys.executable, str(ORCHESTRATOR), "--only", "extract_typecheck_inventory"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode in {0, 1}, result.stderr
    assert "HARNESS_REGEN_SUMMARY" in result.stdout
    assert "[GEN] extract_typecheck_inventory" in result.stdout


def test_orchestrator_topological_order_security_after_routes() -> None:
    """extract_security_inventory must run after extract_backend_routes."""
    result = subprocess.run(
        [sys.executable, str(ORCHESTRATOR), "--only", "extract_security_inventory"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode in {0, 1}
    out = result.stdout
    routes_idx = out.find("[GEN] extract_backend_routes")
    security_idx = out.find("[GEN] extract_security_inventory")
    assert routes_idx >= 0 and security_idx >= 0, out
    assert routes_idx < security_idx, out
