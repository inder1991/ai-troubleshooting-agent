"""H.2.3 — cross-stack generators tests (combined)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GEN_DIR = REPO_ROOT / ".harness" / "generators"
FIXTURE_ROOT = REPO_ROOT / "tests" / "harness" / "fixtures" / "generators" / "cross-stack"


def _run(generator: str, root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(GEN_DIR / f"{generator}.py"),
         "--root", str(root), "--print"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"{generator} failed: {result.stderr}"
    return json.loads(result.stdout)


def test_extract_validation_inventory() -> None:
    payload = _run("extract_validation_inventory", FIXTURE_ROOT)
    by_class = {m["class"]: m for m in payload["models"]}
    assert "IncidentRequest" in by_class
    assert "Finding" in by_class
    assert by_class["IncidentRequest"]["config"].get("extra") == "forbid"
    assert by_class["IncidentRequest"]["config"].get("frozen") is True
    field_names = {f["name"] for f in by_class["Finding"]["fields"]}
    assert {"summary", "confidence"} <= field_names
    conf = next(f for f in by_class["Finding"]["fields"] if f["name"] == "confidence")
    assert conf.get("ge") == 0.0
    assert conf.get("le") == 1.0


def test_extract_dependency_inventory_runs_against_repo() -> None:
    """Sanity: dependency_inventory runs against the live repo (small enough to be fast)."""
    payload = _run("extract_dependency_inventory", REPO_ROOT)
    assert "python" in payload
    assert "npm" in payload


def test_extract_performance_budgets_runs_against_repo() -> None:
    payload = _run("extract_performance_budgets", REPO_ROOT)
    assert "agent_caps" in payload
    assert payload["agent_caps"].get("tool_calls_max") is not None


def test_extract_security_inventory_runs_against_repo() -> None:
    payload = _run("extract_security_inventory", REPO_ROOT)
    assert "auth_dependency_names" in payload
    assert "routes_summary" in payload
    assert payload["routes_summary"]["total"] >= 0
