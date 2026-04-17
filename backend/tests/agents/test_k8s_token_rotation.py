"""Task 1.7 — K8s SA token watcher + 401 reload-and-retry wrapper.

Kubernetes mounts a ServiceAccount token at
``/var/run/secrets/kubernetes.io/serviceaccount/token`` and rotates it
periodically. Our agent was reading it once at startup, which means a
long-lived process hits 401 forever after the first rotation.

K8sTokenWatcher polls the file (mtime-checked) and exposes the latest
token to callers. K8sAuthenticatedClient wraps API calls: on 401/403 it
calls ``token_watcher.refresh_now()`` once and retries — still 401
raises K8sAuthError (no infinite retry).

These are pure-Python unit tests; they don't contact a real cluster.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kubernetes.client.rest import ApiException


# ── K8sTokenWatcher ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_watcher_reads_initial_token(tmp_path: Path):
    from src.agents.k8s_token_watcher import K8sTokenWatcher

    token_file = tmp_path / "token"
    token_file.write_text("initial-token")

    watcher = K8sTokenWatcher(path=str(token_file), interval_s=0.05)
    try:
        await watcher.start()
        assert watcher.current() == "initial-token"
    finally:
        await watcher.stop()


@pytest.mark.asyncio
async def test_token_watcher_reloads_on_file_change(tmp_path: Path):
    from src.agents.k8s_token_watcher import K8sTokenWatcher

    token_file = tmp_path / "token"
    token_file.write_text("v1")

    watcher = K8sTokenWatcher(path=str(token_file), interval_s=0.05)
    try:
        await watcher.start()
        assert watcher.current() == "v1"

        # Rotate: write new content, bump mtime.
        token_file.write_text("v2")
        import os
        import time
        os.utime(token_file, (time.time() + 1, time.time() + 1))

        # Give the poller a few ticks.
        await asyncio.sleep(0.3)
        assert watcher.current() == "v2"
    finally:
        await watcher.stop()


@pytest.mark.asyncio
async def test_token_watcher_refresh_now_is_synchronous(tmp_path: Path):
    """refresh_now() re-reads immediately without waiting for the poll tick."""
    from src.agents.k8s_token_watcher import K8sTokenWatcher

    token_file = tmp_path / "token"
    token_file.write_text("v1")

    # Long poll interval so we know refresh_now is what updated it.
    watcher = K8sTokenWatcher(path=str(token_file), interval_s=3600)
    try:
        await watcher.start()
        assert watcher.current() == "v1"

        token_file.write_text("v2")
        await watcher.refresh_now()
        assert watcher.current() == "v2"
    finally:
        await watcher.stop()


@pytest.mark.asyncio
async def test_token_watcher_raises_when_file_missing(tmp_path: Path):
    from src.agents.k8s_token_watcher import K8sTokenWatcher

    watcher = K8sTokenWatcher(path=str(tmp_path / "does-not-exist"), interval_s=0.05)
    with pytest.raises(FileNotFoundError):
        await watcher.start()


@pytest.mark.asyncio
async def test_token_watcher_strips_whitespace(tmp_path: Path):
    from src.agents.k8s_token_watcher import K8sTokenWatcher

    token_file = tmp_path / "token"
    token_file.write_text("  tok-with-space  \n")

    watcher = K8sTokenWatcher(path=str(token_file), interval_s=3600)
    try:
        await watcher.start()
        assert watcher.current() == "tok-with-space"
    finally:
        await watcher.stop()


# ── K8sAuthenticatedClient ──────────────────────────────────────────────


class _FakeTokenWatcher:
    def __init__(self, initial: str = "t0") -> None:
        self._val = initial
        self.refresh_calls = 0
        self._next_after_refresh: str | None = None

    def current(self) -> str:
        return self._val

    async def refresh_now(self) -> None:
        self.refresh_calls += 1
        if self._next_after_refresh is not None:
            self._val = self._next_after_refresh

    def queue_next_token(self, val: str) -> None:
        self._next_after_refresh = val


@pytest.mark.asyncio
async def test_client_passes_through_when_call_succeeds():
    from src.agents.k8s_client import K8sAuthenticatedClient

    watcher = _FakeTokenWatcher("t0")

    async def api_call(token: str):
        return {"ok": True, "token_seen": token}

    client = K8sAuthenticatedClient(token_watcher=watcher)
    result = await client.call(api_call)
    assert result == {"ok": True, "token_seen": "t0"}
    assert watcher.refresh_calls == 0


@pytest.mark.asyncio
async def test_client_reloads_token_on_401_then_retries_once():
    from src.agents.k8s_client import K8sAuthenticatedClient

    watcher = _FakeTokenWatcher("t0")
    watcher.queue_next_token("t1")

    attempt = {"n": 0}

    async def api_call(token: str):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise ApiException(status=401, reason="Unauthorized")
        return {"ok": True, "token_seen": token}

    client = K8sAuthenticatedClient(token_watcher=watcher)
    result = await client.call(api_call)

    assert attempt["n"] == 2
    assert watcher.refresh_calls == 1
    assert result == {"ok": True, "token_seen": "t1"}


@pytest.mark.asyncio
async def test_client_retries_on_403():
    from src.agents.k8s_client import K8sAuthenticatedClient

    watcher = _FakeTokenWatcher("t0")
    watcher.queue_next_token("t1")

    attempt = {"n": 0}

    async def api_call(token: str):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise ApiException(status=403, reason="Forbidden")
        return "ok"

    client = K8sAuthenticatedClient(token_watcher=watcher)
    result = await client.call(api_call)
    assert attempt["n"] == 2
    assert watcher.refresh_calls == 1
    assert result == "ok"


@pytest.mark.asyncio
async def test_client_raises_auth_error_after_second_401():
    from src.agents.k8s_client import K8sAuthenticatedClient, K8sAuthError

    watcher = _FakeTokenWatcher("t0")
    # Refresh doesn't actually change the token server-side, so still 401.

    async def api_call(token: str):
        raise ApiException(status=401, reason="Unauthorized")

    client = K8sAuthenticatedClient(token_watcher=watcher)
    with pytest.raises(K8sAuthError):
        await client.call(api_call)

    assert watcher.refresh_calls == 1  # exactly one retry, no infinite loop


@pytest.mark.asyncio
async def test_client_does_not_retry_on_non_auth_errors():
    from src.agents.k8s_client import K8sAuthenticatedClient

    watcher = _FakeTokenWatcher("t0")

    async def api_call(token: str):
        raise ApiException(status=500, reason="Server Error")

    client = K8sAuthenticatedClient(token_watcher=watcher)
    with pytest.raises(ApiException):
        await client.call(api_call)

    assert watcher.refresh_calls == 0


@pytest.mark.asyncio
async def test_client_supports_sync_callable():
    """Some kubernetes-client methods are synchronous; the wrapper should
    handle a plain function too."""
    from src.agents.k8s_client import K8sAuthenticatedClient

    watcher = _FakeTokenWatcher("t0")
    watcher.queue_next_token("t1")

    attempt = {"n": 0}

    def sync_api_call(token: str):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise ApiException(status=401, reason="Unauthorized")
        return {"token_seen": token}

    client = K8sAuthenticatedClient(token_watcher=watcher)
    result = await client.call(sync_api_call)
    assert result == {"token_seen": "t1"}
    assert attempt["n"] == 2
