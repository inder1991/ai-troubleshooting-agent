"""H.2.1 — frontend generators tests (combined for the four H.2.1 generators)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GEN_DIR = REPO_ROOT / ".harness" / "generators"
FIXTURE_ROOT = REPO_ROOT / "tests" / "harness" / "fixtures" / "generators"


def _run(generator: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(GEN_DIR / f"{generator}.py"),
         "--root", str(FIXTURE_ROOT), "--print"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"{generator} failed: {result.stderr}"
    return json.loads(result.stdout)


def _run_twice(generator: str) -> tuple[str, str]:
    cmd = [sys.executable, str(GEN_DIR / f"{generator}.py"),
           "--root", str(FIXTURE_ROOT), "--print"]
    a = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    b = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    return a, b


def test_extract_api_endpoints() -> None:
    payload = _run("extract_api_endpoints")
    by_name = {e["name"]: e for e in payload["endpoints"]}
    assert set(by_name) == {"fetchFoo", "createFoo"}
    assert by_name["fetchFoo"]["method"] == "GET"
    assert by_name["createFoo"]["method"] == "POST"
    assert by_name["fetchFoo"]["response_type"] == "FooResponse"


def test_extract_api_endpoints_deterministic() -> None:
    a, b = _run_twice("extract_api_endpoints")
    assert a == b


def test_extract_ui_primitives() -> None:
    payload = _run("extract_ui_primitives")
    by_file = {p["file"]: p for p in payload["primitives"]}
    assert any("button.tsx" in f for f in by_file), payload
    btn = next(p for p in payload["primitives"] if "button" in p["file"])
    assert "Button" in btn["exports"]
    assert "Spacer" in btn["exports"]
    assert btn["uses_radix"] is True


def test_extract_ui_primitives_deterministic() -> None:
    a, b = _run_twice("extract_ui_primitives")
    assert a == b


def test_extract_routes() -> None:
    payload = _run("extract_routes")
    by_path = {r["path"]: r for r in payload["routes"]}
    assert set(by_path) == {"/", "/incidents", "/settings"}
    assert by_path["/"]["lazy_imported"] is False
    assert by_path["/incidents"]["lazy_imported"] is True
    assert by_path["/settings"]["lazy_imported"] is True


def test_extract_routes_deterministic() -> None:
    a, b = _run_twice("extract_routes")
    assert a == b


def test_extract_test_coverage_targets() -> None:
    payload = _run("extract_test_coverage_targets")
    by_glob = {t["glob"]: t for t in payload["thresholds"]}
    assert "frontend/src/services/api/**" in by_glob
    assert by_glob["frontend/src/services/api/**"]["lines"] == 0.9
    assert by_glob["frontend/src/hooks/**"]["branches"] == 0.8


def test_extract_test_coverage_targets_deterministic() -> None:
    a, b = _run_twice("extract_test_coverage_targets")
    assert a == b
