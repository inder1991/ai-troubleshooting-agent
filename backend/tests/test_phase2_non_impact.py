"""Phase 2 non-impact snapshot.

Guard test that fails if Phase 2 work has leaked into forbidden files or
regressed Phase 1 behaviors. See design §9 (non-impact invariants).
"""

from __future__ import annotations

import subprocess
from importlib import reload
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _resolve_base_ref() -> str | None:
    """Return a resolvable base ref for ``git diff``, or None if neither
    ``main`` nor ``origin/main`` is available (shallow clone / CI fork)."""
    for ref in ("main", "origin/main"):
        p = _git("rev-parse", "--verify", ref)
        if p.returncode == 0:
            return ref
    return None


@pytest.mark.parametrize("forbidden_path", [
    "backend/src/agents/supervisor.py",
    "backend/src/api/routes_v4.py",
    "backend/src/models/schemas.py",
])
def test_forbidden_backend_file_unchanged(forbidden_path: str):
    base = _resolve_base_ref()
    if base is None:
        pytest.skip("neither main nor origin/main resolvable — shallow clone")
    diff = _git("diff", f"{base}..HEAD", "--", forbidden_path)
    assert diff.returncode == 0, diff.stderr
    assert diff.stdout == "", (
        f"Phase 2 leaked into forbidden path {forbidden_path!r}:\n{diff.stdout}"
    )


def test_forbidden_frontend_investigation_unchanged():
    base = _resolve_base_ref()
    if base is None:
        pytest.skip("neither main nor origin/main resolvable — shallow clone")
    diff = _git(
        "diff", f"{base}..HEAD", "--",
        "frontend/src/components/Investigation/",
    )
    assert diff.returncode == 0, diff.stderr
    assert diff.stdout == "", (
        "Phase 2 leaked into frontend/src/components/Investigation/:\n"
        + diff.stdout
    )


def _build_client(monkeypatch, tmp_path, *, workflows: bool, catalog: bool):
    monkeypatch.setenv("WORKFLOWS_DB_PATH", str(tmp_path / "wf.db"))
    monkeypatch.setenv("WORKFLOWS_ENABLED", "true" if workflows else "false")
    monkeypatch.setenv("CATALOG_UI_ENABLED", "true" if catalog else "false")
    from src import config
    reload(config)
    from src.api import routes_workflows
    reload(routes_workflows)
    from src.api import main as app_main
    reload(app_main)
    return TestClient(app_main.app)


def test_phase1_catalog_still_works(monkeypatch, tmp_path):
    with _build_client(monkeypatch, tmp_path, workflows=False, catalog=True) as c:
        resp = c.get("/api/v4/catalog/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert "agents" in data
        assert len(data["agents"]) >= 10


# All workflow / run endpoints must 404 when the flag is off.
_WORKFLOW_ENDPOINTS: list[tuple[str, str, dict]] = [
    ("POST", "/api/v4/workflows", {"json": {"name": "x"}}),
    ("GET", "/api/v4/workflows", {}),
    ("GET", "/api/v4/workflows/any-id", {}),
    ("POST", "/api/v4/workflows/any-id/versions", {"json": {}}),
    ("GET", "/api/v4/workflows/any-id/versions/1", {}),
    ("POST", "/api/v4/workflows/any-id/runs", {"json": {"inputs": {}}}),
    ("GET", "/api/v4/runs/any-id", {}),
    ("GET", "/api/v4/runs/any-id/events", {}),
    ("POST", "/api/v4/runs/any-id/cancel", {}),
]


@pytest.mark.parametrize("method,path,kwargs", _WORKFLOW_ENDPOINTS)
def test_workflow_endpoints_404_when_disabled(
    monkeypatch, tmp_path, method: str, path: str, kwargs: dict
):
    with _build_client(monkeypatch, tmp_path, workflows=False, catalog=False) as c:
        resp = c.request(method, path, **kwargs)
        assert resp.status_code == 404, (
            f"{method} {path} returned {resp.status_code}, expected 404 with flag off"
        )
