"""Catalog REST endpoints — flag-gated read-only agent contract exposure."""

from importlib import reload

import pytest
from fastapi.testclient import TestClient


def _build_client(monkeypatch, enabled: bool):
    monkeypatch.setenv("CATALOG_UI_ENABLED", "true" if enabled else "false")
    from backend.src import config
    reload(config)
    from backend.src.api import main as app_main
    reload(app_main)
    # Startup lifespan populates the ContractRegistry; TestClient context runs it.
    return TestClient(app_main.app)


@pytest.fixture
def client_enabled(monkeypatch):
    with _build_client(monkeypatch, enabled=True) as c:
        yield c


@pytest.fixture
def client_disabled(monkeypatch):
    with _build_client(monkeypatch, enabled=False) as c:
        yield c


def test_list_agents_when_enabled(client_enabled):
    resp = client_enabled.get("/api/v4/catalog/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    assert len(data["agents"]) >= 10
    sample = data["agents"][0]
    assert {"name", "version", "description", "category"}.issubset(sample.keys())


def test_list_agents_returns_404_when_disabled(client_disabled):
    resp = client_disabled.get("/api/v4/catalog/agents")
    assert resp.status_code == 404
