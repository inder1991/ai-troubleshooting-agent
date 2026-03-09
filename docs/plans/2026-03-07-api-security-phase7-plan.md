# Phase 7: API Security Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add API key authentication with role-based access control to protect all endpoints from unauthorized access.

**Architecture:** API keys stored in SQLite with hashed secrets. FastAPI dependency injection validates `X-API-Key` header. Two roles: `admin` (full access) and `viewer` (read-only). A bootstrap key is generated on first startup. Public endpoints (`/metrics`, `/health`, `/docs`) are exempt.

**Tech Stack:** Python hashlib (SHA-256), FastAPI Security dependencies, SQLite

---

### Task 1: API Key Store

**Files:**
- Create: `backend/src/auth/api_key_store.py`
- Create: `backend/src/auth/__init__.py`
- Test: `backend/tests/test_api_key_store.py`

**Context:**
- Store API keys in SQLite (same DB as topology or separate `auth.db`).
- Keys are hashed with SHA-256 before storage — never store plaintext.
- Each key has: `id`, `name`, `hashed_key`, `role` (admin/viewer), `created_at`, `enabled`.
- Provide `create_key()` which returns the plaintext key once, `validate_key()` which hashes input and looks up, `list_keys()` (redacted), `revoke_key()`.

**Step 1: Write the failing tests**

Create `backend/tests/test_api_key_store.py`:

```python
"""Tests for API key store."""
import pytest
from src.auth.api_key_store import APIKeyStore


@pytest.fixture
def store(tmp_path):
    return APIKeyStore(str(tmp_path / "auth.db"))


class TestAPIKeyStore:
    def test_create_key_returns_plaintext(self, store):
        result = store.create_key("Test Key", role="admin")
        assert "key" in result
        assert "id" in result
        assert len(result["key"]) >= 32

    def test_validate_valid_key(self, store):
        result = store.create_key("Test Key", role="admin")
        info = store.validate_key(result["key"])
        assert info is not None
        assert info["name"] == "Test Key"
        assert info["role"] == "admin"

    def test_validate_invalid_key(self, store):
        info = store.validate_key("invalid-key-12345")
        assert info is None

    def test_list_keys_redacted(self, store):
        store.create_key("Key1", role="admin")
        store.create_key("Key2", role="viewer")
        keys = store.list_keys()
        assert len(keys) == 2
        # Keys should not contain plaintext or full hash
        for k in keys:
            assert "key" not in k
            assert "hashed_key" not in k
            assert "name" in k
            assert "role" in k
            assert "prefix" in k  # Show first 8 chars for identification

    def test_revoke_key(self, store):
        result = store.create_key("ToRevoke", role="admin")
        assert store.validate_key(result["key"]) is not None
        store.revoke_key(result["id"])
        assert store.validate_key(result["key"]) is None

    def test_disabled_key_rejected(self, store):
        result = store.create_key("Disabled", role="admin")
        store.disable_key(result["id"])
        assert store.validate_key(result["key"]) is None

    def test_create_viewer_key(self, store):
        result = store.create_key("Viewer", role="viewer")
        info = store.validate_key(result["key"])
        assert info["role"] == "viewer"

    def test_bootstrap_key_created_if_empty(self, store):
        """First init should create a bootstrap admin key."""
        keys = store.list_keys()
        assert len(keys) == 1
        assert keys[0]["name"] == "bootstrap"
        assert keys[0]["role"] == "admin"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_api_key_store.py -v`
Expected: FAIL — module doesn't exist.

**Step 3: Implement**

Create `backend/src/auth/__init__.py` (empty).

Create `backend/src/auth/api_key_store.py`:

```python
"""API Key storage with SHA-256 hashing."""
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone


class APIKeyStore:
    """SQLite-backed API key management."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_tables()
        self._ensure_bootstrap_key()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    prefix TEXT NOT NULL,
                    hashed_key TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'viewer',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _ensure_bootstrap_key(self) -> None:
        conn = self._conn()
        try:
            count = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
            if count == 0:
                result = self.create_key("bootstrap", role="admin")
                # Log the bootstrap key to stdout on first run
                import logging
                logging.getLogger(__name__).warning(
                    "Bootstrap API key created: %s (save this, it won't be shown again)",
                    result["key"],
                )
        finally:
            conn.close()

    @staticmethod
    def _hash_key(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode()).hexdigest()

    def create_key(self, name: str, role: str = "viewer") -> dict:
        key_id = secrets.token_hex(8)
        plaintext = secrets.token_urlsafe(32)
        prefix = plaintext[:8]
        hashed = self._hash_key(plaintext)
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO api_keys (id, name, prefix, hashed_key, role, enabled, created_at) VALUES (?,?,?,?,?,1,?)",
                (key_id, name, prefix, hashed, role, now),
            )
            conn.commit()
        finally:
            conn.close()
        return {"id": key_id, "key": plaintext, "name": name, "role": role}

    def validate_key(self, plaintext: str) -> dict | None:
        hashed = self._hash_key(plaintext)
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT id, name, role, enabled FROM api_keys WHERE hashed_key = ?",
                (hashed,),
            ).fetchone()
            if not row or not row["enabled"]:
                return None
            return {"id": row["id"], "name": row["name"], "role": row["role"]}
        finally:
            conn.close()

    def list_keys(self) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT id, name, prefix, role, enabled, created_at FROM api_keys ORDER BY created_at"
            ).fetchall()
            return [
                {"id": r["id"], "name": r["name"], "prefix": r["prefix"],
                 "role": r["role"], "enabled": bool(r["enabled"]),
                 "created_at": r["created_at"]}
                for r in rows
            ]
        finally:
            conn.close()

    def revoke_key(self, key_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            conn.commit()
        finally:
            conn.close()

    def disable_key(self, key_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("UPDATE api_keys SET enabled = 0 WHERE id = ?", (key_id,))
            conn.commit()
        finally:
            conn.close()
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_api_key_store.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/auth/__init__.py src/auth/api_key_store.py tests/test_api_key_store.py
git commit -m "feat(auth): add API key store with SHA-256 hashing and bootstrap key"
```

---

### Task 2: Auth Middleware

**Files:**
- Create: `backend/src/auth/dependencies.py`
- Modify: `backend/src/api/main.py` (add auth middleware)
- Test: `backend/tests/test_auth_middleware.py`

**Context:**
- FastAPI middleware that checks `X-API-Key` header on every request.
- Public endpoints exempt: `/metrics`, `/health`, `/docs`, `/redoc`, `/openapi.json`.
- On invalid/missing key: return 401 Unauthorized.
- On valid key: attach `request.state.api_key_info` with `{id, name, role}` for downstream use.
- Use Starlette middleware (not FastAPI Depends) so it applies globally without modifying every router.

**Step 1: Write the failing tests**

Create `backend/tests/test_auth_middleware.py`:

```python
"""Tests for API key auth middleware."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def api_key_and_client(tmp_path):
    """Create app with auth middleware and return (api_key, client)."""
    from src.auth.api_key_store import APIKeyStore
    store = APIKeyStore(str(tmp_path / "auth.db"))
    result = store.create_key("test-key", role="admin")

    from src.api.main import app
    from src.auth import dependencies
    original_store = dependencies._api_key_store
    dependencies._api_key_store = store
    client = TestClient(app)
    yield result["key"], client
    dependencies._api_key_store = original_store


class TestAuthMiddleware:
    def test_request_without_key_returns_401(self, api_key_and_client):
        _, client = api_key_and_client
        response = client.get("/api/v4/network/monitor/snapshot")
        assert response.status_code == 401

    def test_request_with_invalid_key_returns_401(self, api_key_and_client):
        _, client = api_key_and_client
        response = client.get(
            "/api/v4/network/monitor/snapshot",
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_request_with_valid_key_succeeds(self, api_key_and_client):
        key, client = api_key_and_client
        response = client.get(
            "/api/v4/network/monitor/snapshot",
            headers={"X-API-Key": key},
        )
        # May be 200 or 500 (monitor not started), but NOT 401
        assert response.status_code != 401

    def test_metrics_endpoint_exempt(self, api_key_and_client):
        _, client = api_key_and_client
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_docs_endpoint_exempt(self, api_key_and_client):
        _, client = api_key_and_client
        response = client.get("/docs")
        # Docs returns 200 (HTML page)
        assert response.status_code == 200

    def test_health_endpoint_exempt(self, api_key_and_client):
        _, client = api_key_and_client
        response = client.get("/api/v4/network/monitor/health")
        # Health should be accessible without auth
        assert response.status_code != 401
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_auth_middleware.py -v`
Expected: FAIL — no auth middleware exists, all requests pass.

**Step 3: Implement**

Create `backend/src/auth/dependencies.py`:

```python
"""FastAPI auth dependencies and middleware."""
from __future__ import annotations

import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .api_key_store import APIKeyStore

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "auth.db")

_api_key_store: APIKeyStore | None = None

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
}

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = (
    "/api/v4/network/monitor/health",
)


def get_api_key_store() -> APIKeyStore:
    global _api_key_store
    if _api_key_store is None:
        _api_key_store = APIKeyStore(DB_PATH)
    return _api_key_store


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validates X-API-Key header on all non-public requests."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public endpoints
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        # Allow WebSocket upgrade (handled separately)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Check API key
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-API-Key header"},
            )

        store = get_api_key_store()
        info = store.validate_key(api_key)
        if not info:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or disabled API key"},
            )

        # Attach key info for downstream use
        request.state.api_key_info = info
        return await call_next(request)
```

**Modify `backend/src/api/main.py`** — add middleware AFTER CORS (order matters):

```python
from src.auth.dependencies import APIKeyMiddleware

# Inside create_app(), after CORS middleware:
app.add_middleware(APIKeyMiddleware)
```

**IMPORTANT:** Middleware is applied in reverse order in Starlette. Add `APIKeyMiddleware` AFTER `CORSMiddleware` so CORS headers are set before auth check (preflight OPTIONS requests need CORS headers even on 401).

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_auth_middleware.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/auth/dependencies.py src/api/main.py tests/test_auth_middleware.py
git commit -m "feat(auth): add API key middleware with public endpoint exemptions"
```

---

### Task 3: Role-Based Access Control

**Files:**
- Modify: `backend/src/auth/dependencies.py` (add role check helper)
- Modify: `backend/src/api/monitor_endpoints.py` (protect write endpoints)
- Modify: `backend/src/api/network_endpoints.py` (protect DELETE endpoints)
- Test: `backend/tests/test_rbac.py`

**Context:**
- Two roles: `admin` (read + write) and `viewer` (read only).
- Write operations = POST, PUT, PATCH, DELETE.
- Add a `require_role()` FastAPI dependency OR check `request.state.api_key_info["role"]` in the middleware.
- Simplest approach: extend middleware to reject non-admin write requests with 403 Forbidden.
- Admin can do everything. Viewer can only GET.

**Step 1: Write the failing tests**

Create `backend/tests/test_rbac.py`:

```python
"""Tests for role-based access control."""
import pytest
from fastapi.testclient import TestClient

from src.auth.api_key_store import APIKeyStore


@pytest.fixture
def keys_and_client(tmp_path):
    store = APIKeyStore(str(tmp_path / "auth.db"))
    admin = store.create_key("admin-key", role="admin")
    viewer = store.create_key("viewer-key", role="viewer")

    from src.api.main import app
    from src.auth import dependencies
    original = dependencies._api_key_store
    dependencies._api_key_store = store
    client = TestClient(app)
    yield admin["key"], viewer["key"], client
    dependencies._api_key_store = original


class TestRBAC:
    def test_admin_can_read(self, keys_and_client):
        admin_key, _, client = keys_and_client
        resp = client.get(
            "/api/v4/network/monitor/snapshot",
            headers={"X-API-Key": admin_key},
        )
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_viewer_can_read(self, keys_and_client):
        _, viewer_key, client = keys_and_client
        resp = client.get(
            "/api/v4/network/monitor/snapshot",
            headers={"X-API-Key": viewer_key},
        )
        assert resp.status_code != 401
        assert resp.status_code != 403

    def test_viewer_cannot_post(self, keys_and_client):
        _, viewer_key, client = keys_and_client
        resp = client.post(
            "/api/v4/network/dns/servers",
            headers={"X-API-Key": viewer_key},
            json={"id": "s1", "name": "DNS1", "ip": "8.8.8.8"},
        )
        assert resp.status_code == 403

    def test_admin_can_post(self, keys_and_client):
        admin_key, _, client = keys_and_client
        resp = client.post(
            "/api/v4/network/dns/servers",
            headers={"X-API-Key": admin_key},
            json={"id": "s1", "name": "DNS1", "ip": "8.8.8.8"},
        )
        assert resp.status_code != 403

    def test_viewer_cannot_delete(self, keys_and_client):
        _, viewer_key, client = keys_and_client
        resp = client.delete(
            "/api/v4/network/dns/servers/nonexistent",
            headers={"X-API-Key": viewer_key},
        )
        assert resp.status_code == 403

    def test_admin_can_delete(self, keys_and_client):
        admin_key, _, client = keys_and_client
        resp = client.delete(
            "/api/v4/network/dns/servers/nonexistent",
            headers={"X-API-Key": admin_key},
        )
        # May be 404 (server doesn't exist), but NOT 403
        assert resp.status_code != 403
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_rbac.py -v`
Expected: FAIL — viewer can POST/DELETE (no role check).

**Step 3: Implement**

**Modify `backend/src/auth/dependencies.py`** — add role check to `APIKeyMiddleware.dispatch()`:

After validating the key and getting `info`, before calling `call_next`:

```python
# Role-based access control
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
if request.method in WRITE_METHODS and info["role"] != "admin":
    return JSONResponse(
        status_code=403,
        content={"detail": "Insufficient permissions: admin role required for write operations"},
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_rbac.py -v`
Expected: PASS

Also run: `python3 -m pytest tests/test_auth_middleware.py -v` for regressions.

**Step 5: Commit**

```bash
git add src/auth/dependencies.py tests/test_rbac.py
git commit -m "feat(auth): add role-based access control (admin=read+write, viewer=read-only)"
```

---

### Task 4: API Key Management Endpoints

**Files:**
- Create: `backend/src/api/auth_endpoints.py`
- Modify: `backend/src/api/main.py` (register auth router)
- Test: `backend/tests/test_auth_endpoints.py`

**Context:**
- Admin-only endpoints to manage API keys: list, create, revoke.
- `GET /api/v4/auth/keys` — list all keys (redacted)
- `POST /api/v4/auth/keys` — create new key (returns plaintext once)
- `DELETE /api/v4/auth/keys/{key_id}` — revoke key
- These endpoints themselves require admin auth (chicken-and-egg solved by bootstrap key).

**Step 1: Write the failing tests**

Create `backend/tests/test_auth_endpoints.py`:

```python
"""Tests for API key management endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.auth.api_key_store import APIKeyStore


@pytest.fixture
def admin_and_client(tmp_path):
    store = APIKeyStore(str(tmp_path / "auth.db"))
    admin = store.create_key("admin", role="admin")

    from src.api.main import app
    from src.auth import dependencies
    original = dependencies._api_key_store
    dependencies._api_key_store = store
    client = TestClient(app)
    yield admin["key"], client
    dependencies._api_key_store = original


class TestAuthEndpoints:
    def test_list_keys(self, admin_and_client):
        key, client = admin_and_client
        resp = client.get("/api/v4/auth/keys", headers={"X-API-Key": key})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1  # bootstrap + admin

    def test_create_key(self, admin_and_client):
        key, client = admin_and_client
        resp = client.post(
            "/api/v4/auth/keys",
            headers={"X-API-Key": key},
            json={"name": "new-key", "role": "viewer"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "key" in data  # plaintext returned once
        assert data["role"] == "viewer"

    def test_revoke_key(self, admin_and_client):
        key, client = admin_and_client
        # Create a key to revoke
        create_resp = client.post(
            "/api/v4/auth/keys",
            headers={"X-API-Key": key},
            json={"name": "to-revoke", "role": "viewer"},
        )
        key_id = create_resp.json()["id"]

        resp = client.delete(
            f"/api/v4/auth/keys/{key_id}",
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 200

    def test_viewer_cannot_manage_keys(self, admin_and_client):
        admin_key, client = admin_and_client
        # Create viewer key
        create_resp = client.post(
            "/api/v4/auth/keys",
            headers={"X-API-Key": admin_key},
            json={"name": "viewer", "role": "viewer"},
        )
        viewer_key = create_resp.json()["key"]

        # Viewer can't list keys (POST is blocked by RBAC, GET /keys requires admin)
        resp = client.post(
            "/api/v4/auth/keys",
            headers={"X-API-Key": viewer_key},
            json={"name": "sneaky", "role": "admin"},
        )
        assert resp.status_code == 403
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_auth_endpoints.py -v`
Expected: FAIL — no auth endpoints exist.

**Step 3: Implement**

Create `backend/src/api/auth_endpoints.py`:

```python
"""API key management endpoints."""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from src.auth.dependencies import get_api_key_store

auth_router = APIRouter(prefix="/api/v4/auth", tags=["auth"])


class CreateKeyRequest(BaseModel):
    name: str
    role: str = "viewer"


@auth_router.get("/keys")
def list_keys(request: Request):
    store = get_api_key_store()
    return store.list_keys()


@auth_router.post("/keys", status_code=201)
def create_key(body: CreateKeyRequest, request: Request):
    store = get_api_key_store()
    if body.role not in ("admin", "viewer"):
        from fastapi import HTTPException
        raise HTTPException(400, "Role must be 'admin' or 'viewer'")
    return store.create_key(body.name, role=body.role)


@auth_router.delete("/keys/{key_id}")
def revoke_key(key_id: str, request: Request):
    store = get_api_key_store()
    store.revoke_key(key_id)
    return {"status": "revoked", "id": key_id}
```

**Modify `backend/src/api/main.py`:**
```python
from .auth_endpoints import auth_router

# In create_app(), with other include_router calls:
app.include_router(auth_router)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/test_auth_endpoints.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/api/auth_endpoints.py src/api/main.py tests/test_auth_endpoints.py
git commit -m "feat(auth): add API key management endpoints (list, create, revoke)"
```

---

### Task 5: Final Verification

**Files:** None (read-only verification)

**Step 1: Run all Phase 7 tests**

```bash
cd backend && python3 -m pytest tests/test_api_key_store.py tests/test_auth_middleware.py tests/test_rbac.py tests/test_auth_endpoints.py -v
```

**Step 2: Run full test suite**

```bash
python3 -m pytest tests/ --tb=line -q 2>&1 | tail -5
```

**IMPORTANT:** Many existing tests will now fail because they don't pass `X-API-Key` headers. The auth middleware needs to handle the test scenario. Two approaches:
- Set an environment variable `DEBUGDUCK_AUTH_DISABLED=1` that skips auth in test mode
- OR have the middleware check for TestClient (not recommended)

**The recommended approach:** In `dependencies.py`, check for env var:
```python
import os
if os.getenv("DEBUGDUCK_AUTH_DISABLED") == "1":
    # Skip auth (for testing/development)
    return await call_next(request)
```

Add to existing test conftest or pytest env: `DEBUGDUCK_AUTH_DISABLED=1`.

BUT for the auth-specific tests (test_auth_middleware.py, test_rbac.py, test_auth_endpoints.py), they should NOT set this env var — they explicitly test auth behavior.

**Step 3: Verify imports**

```bash
python3 -c "
from src.auth.api_key_store import APIKeyStore
from src.auth.dependencies import APIKeyMiddleware, get_api_key_store
from src.api.auth_endpoints import auth_router
print('All Phase 7 imports verified')
"
```
