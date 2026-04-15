"""Task 19: Startup wiring for workflows subsystem behind WORKFLOWS_ENABLED.

The FastAPI app should:
- Expose /api/v4/workflows (200, empty list) when flag=true.
- Return 404 on /api/v4/workflows when flag=false.
- Refuse to boot if init_runners raises (integrity check propagates).
"""

from __future__ import annotations

from importlib import reload

import pytest
from fastapi.testclient import TestClient


def _build_client(monkeypatch, tmp_path, *, enabled: bool):
    # Point the workflow DB at a fresh tmp path so tests are hermetic.
    monkeypatch.setenv("WORKFLOWS_DB_PATH", str(tmp_path / "wf.db"))
    monkeypatch.setenv("WORKFLOWS_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("CATALOG_UI_ENABLED", "false")
    from src import config
    reload(config)
    from src.api import routes_workflows
    reload(routes_workflows)
    from src.api import main as app_main
    reload(app_main)
    return TestClient(app_main.app)


def test_workflows_list_returns_200_when_enabled(monkeypatch, tmp_path):
    with _build_client(monkeypatch, tmp_path, enabled=True) as c:
        resp = c.get("/api/v4/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert "workflows" in data
        assert data["workflows"] == []


def test_workflows_list_returns_404_when_disabled(monkeypatch, tmp_path):
    with _build_client(monkeypatch, tmp_path, enabled=False) as c:
        resp = c.get("/api/v4/workflows")
        assert resp.status_code == 404


def test_startup_raises_if_init_runners_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKFLOWS_DB_PATH", str(tmp_path / "wf.db"))
    monkeypatch.setenv("WORKFLOWS_ENABLED", "true")
    monkeypatch.setenv("CATALOG_UI_ENABLED", "false")
    from src import config
    reload(config)
    from src.workflows import runners as _runners_mod
    reload(_runners_mod)

    def _boom() -> None:
        raise RuntimeError("phase2 startup integrity failure")

    monkeypatch.setattr(_runners_mod, "init_runners", _boom)

    from src.api import routes_workflows
    reload(routes_workflows)
    from src.api import main as app_main
    reload(app_main)

    with pytest.raises(RuntimeError, match="phase2 startup integrity failure"):
        with TestClient(app_main.app):
            pass
