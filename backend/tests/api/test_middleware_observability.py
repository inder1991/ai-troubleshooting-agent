"""PR-J — tests for request_id middleware + structured error envelopes.

These are unit tests that exercise the FastAPI app directly, not a
live server. A minimal app is assembled with the middleware + handlers
so tests don't boot the full production `main.create_app()` stack.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.middleware_observability import (
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
    get_request_id,
    register_error_envelope_handlers,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    register_error_envelope_handlers(app)

    @app.get("/ok")
    async def ok():
        return {"ok": True, "rid": get_request_id()}

    @app.get("/boom")
    async def boom():
        raise HTTPException(status_code=418, detail="teapot is unplugged")

    @app.get("/crash")
    async def crash():
        raise RuntimeError("this should not reach the client")

    @app.post("/echo")
    async def echo(body: dict):
        return {"echo": body}

    return app


# ── Request-ID middleware ────────────────────────────────────────────


def test_middleware_stamps_request_id_on_response():
    client = TestClient(_app())
    r = client.get("/ok")
    assert r.status_code == 200
    assert REQUEST_ID_HEADER in r.headers
    rid = r.headers[REQUEST_ID_HEADER]
    assert len(rid) >= 8
    # Also available to handlers via contextvar
    assert r.json()["rid"] == rid


def test_middleware_respects_caller_supplied_request_id():
    client = TestClient(_app())
    rid = "req-abc123-trace_456.789"
    r = client.get("/ok", headers={REQUEST_ID_HEADER: rid})
    assert r.headers[REQUEST_ID_HEADER] == rid
    assert r.json()["rid"] == rid


def test_middleware_rejects_garbage_request_id_and_mints_fresh_uuid():
    client = TestClient(_app())
    r = client.get("/ok", headers={REQUEST_ID_HEADER: "!!! very bad $$$"})
    # Minted ID is 32-char hex (uuid4.hex), not the garbage input.
    rid = r.headers[REQUEST_ID_HEADER]
    assert rid != "!!! very bad $$$"
    assert len(rid) == 32
    assert all(c in "0123456789abcdef" for c in rid)


def test_middleware_clamps_oversized_request_id():
    client = TestClient(_app())
    r = client.get("/ok", headers={REQUEST_ID_HEADER: "a" * 500})
    assert r.headers[REQUEST_ID_HEADER] != "a" * 500


# ── HTTPException envelope ──────────────────────────────────────────


def test_http_exception_renders_structured_envelope():
    client = TestClient(_app())
    r = client.get("/boom")
    assert r.status_code == 418
    body = r.json()
    assert body["error"] == "HTTPException"
    assert body["detail"] == "teapot is unplugged"
    assert body["status_code"] == 418
    assert body["request_id"]  # non-empty


# ── RequestValidationError envelope ──────────────────────────────────


def test_request_validation_error_renders_422_with_errors_list():
    client = TestClient(_app())
    # POST /echo expects a JSON body; send nothing
    r = client.post("/echo", content="not a json", headers={"Content-Type": "text/plain"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "RequestValidationError"
    assert body["status_code"] == 422
    assert body["request_id"]
    assert isinstance(body["errors"], list)


# ── Unhandled exception envelope ─────────────────────────────────────


def test_unhandled_exception_renders_sanitized_500():
    """Raw exception messages must NOT leak to the client."""
    client = TestClient(_app(), raise_server_exceptions=False)
    r = client.get("/crash")
    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "InternalServerError"
    # The raw RuntimeError message is NOT echoed.
    assert "this should not reach the client" not in body["detail"]
    assert body["request_id"]


# ── Cross-request independence ──────────────────────────────────────


def test_request_ids_are_unique_across_requests():
    client = TestClient(_app())
    rids = {client.get("/ok").headers[REQUEST_ID_HEADER] for _ in range(5)}
    assert len(rids) == 5


def test_get_request_id_returns_empty_outside_a_request():
    # No request frame → contextvar default is empty.
    assert get_request_id() == ""
