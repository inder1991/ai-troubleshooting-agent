"""Tests for /healthz + /readyz.

Liveness is a pure 200; readiness exercises the Postgres + Redis probes
through the helpers so we don't need real services running.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.health import router as health_router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


def test_healthz_returns_200(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_200_when_both_deps_ok(client: TestClient):
    with patch("src.api.health._check_postgres", new=AsyncMock(return_value=None)), \
         patch("src.api.health._check_redis",    new=AsyncMock(return_value=None)):
        r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["checks"] == {"postgres": "ok", "redis": "ok"}


def test_readyz_503_when_postgres_fails(client: TestClient):
    failing = AsyncMock(side_effect=RuntimeError("connection refused"))
    with patch("src.api.health._check_postgres", new=failing), \
         patch("src.api.health._check_redis",    new=AsyncMock(return_value=None)):
        r = client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert body["checks"]["postgres"].startswith("error: RuntimeError")
    assert body["checks"]["redis"] == "ok"


def test_readyz_503_when_redis_fails(client: TestClient):
    with patch("src.api.health._check_postgres", new=AsyncMock(return_value=None)), \
         patch("src.api.health._check_redis",    new=AsyncMock(side_effect=ConnectionError("nope"))):
        r = client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["ready"] is False
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["redis"].startswith("error: ConnectionError")


def test_readyz_503_when_probe_times_out(client: TestClient):
    async def slow_probe():
        await asyncio.sleep(5)  # well past HEALTH_PROBE_TIMEOUT_S default 0.8

    with patch("src.api.health._check_postgres", new=slow_probe), \
         patch("src.api.health._check_redis",    new=AsyncMock(return_value=None)):
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["postgres"].startswith("error: timeout")
