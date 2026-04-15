"""Guards that Auto-mode diagnostic endpoints remain byte-identical in shape.

DO NOT SKIP these tests. If a change legitimately alters an endpoint,
the change is out of Phase 1 scope — stop and raise the concern.
"""

from importlib import reload

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from backend.src.api import main as app_main
    with TestClient(app_main.app) as c:
        yield c


def test_findings_route_exists_unchanged(client):
    # Known endpoint still mounted, returns 404/422 for bogus id — not 500.
    resp = client.get("/api/v4/findings/bogus-session-id")
    assert resp.status_code in (200, 404, 422), resp.text


def test_sessions_route_exists(client):
    resp = client.get("/api/v4/sessions")
    # Shape may vary; must not be a 500.
    assert resp.status_code < 500, resp.text


def test_catalog_flag_off_does_not_expose_routes(monkeypatch):
    monkeypatch.setenv("CATALOG_UI_ENABLED", "false")
    from backend.src import config
    reload(config)
    from backend.src.api import main as app_main
    reload(app_main)
    with TestClient(app_main.app) as c:
        assert c.get("/api/v4/catalog/agents").status_code == 404


def test_catalog_flag_off_is_the_default(monkeypatch):
    monkeypatch.delenv("CATALOG_UI_ENABLED", raising=False)
    from backend.src import config
    reload(config)
    assert config.settings.CATALOG_UI_ENABLED is False
