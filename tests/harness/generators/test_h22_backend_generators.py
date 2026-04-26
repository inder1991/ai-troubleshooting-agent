"""H.2.2 — backend generators tests (combined)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GEN_DIR = REPO_ROOT / ".harness" / "generators"
FIXTURE_ROOT = REPO_ROOT / "tests" / "harness" / "fixtures" / "generators"


def _run(generator: str, root: Path = FIXTURE_ROOT) -> dict:
    result = subprocess.run(
        [sys.executable, str(GEN_DIR / f"{generator}.py"),
         "--root", str(root), "--print"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"{generator} failed: {result.stderr}"
    return json.loads(result.stdout)


def _twice(generator: str, root: Path = FIXTURE_ROOT) -> tuple[str, str]:
    cmd = [sys.executable, str(GEN_DIR / f"{generator}.py"),
           "--root", str(root), "--print"]
    a = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    b = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    return a, b


def test_extract_backend_routes() -> None:
    payload = _run("extract_backend_routes")
    paths = {(r["method"], r["path"]) for r in payload["routes"]}
    assert paths == {("GET", "/api/v4/incidents"), ("POST", "/api/v4/incidents")}
    by_method = {r["method"]: r for r in payload["routes"]}
    assert by_method["POST"]["auth_dep"] == "require_user"
    assert by_method["POST"]["rate_limit"] is True
    assert by_method["GET"]["auth_dep"] is None


def test_extract_backend_routes_deterministic() -> None:
    a, b = _twice("extract_backend_routes")
    assert a == b


def test_extract_db_models() -> None:
    payload = _run("extract_db_models")
    by_class = {m["class_name"]: m for m in payload["models"]}
    assert "Incident" in by_class
    assert by_class["Incident"]["table_name"] == "incidents"
    field_names = {f["name"] for f in by_class["Incident"]["fields"]}
    assert {"id", "title", "severity"} <= field_names


def test_extract_storage_gateway_methods() -> None:
    payload = _run("extract_storage_gateway_methods")
    by_name = {m["name"]: m for m in payload["methods"]}
    assert "get_incident" in by_name
    assert "create_incident" in by_name
    assert by_name["get_incident"]["kind"] == "read"
    assert by_name["create_incident"]["kind"] == "write"
    assert by_name["create_incident"]["audited"] is True
    assert by_name["create_incident"]["timed"] is True


def test_extract_test_coverage_required_paths() -> None:
    payload = _run("extract_test_coverage_required_paths", root=REPO_ROOT)
    assert payload["rationale"] == "Q19"
    assert "backend/src/storage" in payload["required_paths"]


def test_extract_test_inventory() -> None:
    payload = _run("extract_test_inventory")
    by_path = {f["path"]: f for f in payload["files"]}
    dummy = next((v for k, v in by_path.items() if "test_dummy" in k), None)
    assert dummy is not None, payload
    assert dummy["test_count"] == 2
    assert dummy["hypothesis_count"] == 1
