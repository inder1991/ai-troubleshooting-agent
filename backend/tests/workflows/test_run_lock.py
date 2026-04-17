"""RunLock: distributed per-run_id lock backed by Redis SET NX EX + heartbeat.

Spec (Task 1.6):
- Acquire is atomic (only one holder across replicas).
- Release is token-safe via Lua CAS — never deletes someone else's lock.
- Heartbeat extends TTL so long-running investigations don't lose the lock.
- Failure to acquire raises ``RunLocked``; the API layer maps to HTTP 409.

These tests use a live Redis (matching the pattern in
``test_outbox_relay.py``) and are skipped if Redis is unreachable. Each test
uses a uuid-suffixed run_id so parallel runs don't collide.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio

try:
    import redis.asyncio as aredis
    import redis as _redis_sync
    _REDIS_IMPORT_OK = True
except Exception:  # pragma: no cover
    _REDIS_IMPORT_OK = False


def _redis_reachable() -> bool:
    if not _REDIS_IMPORT_OK:
        return False
    try:
        c = _redis_sync.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            socket_connect_timeout=1,
        )
        c.ping()
        c.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_reachable(), reason="Redis unreachable; RunLock tests require live Redis"
)


@pytest_asyncio.fixture
async def redis_client():
    client = aredis.Redis(
        host=os.environ.get("REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
    )
    try:
        yield client
    finally:
        await client.aclose()


def _run_id() -> str:
    return f"lock-test-{uuid4().hex}"


@pytest.mark.asyncio
async def test_lock_acquires_when_key_free(redis_client):
    from src.workflows.run_lock import RunLock

    run_id = _run_id()
    async with RunLock(run_id, redis=redis_client, ttl_s=5, heartbeat_s=1) as lock:
        assert lock.token is not None
        # The key exists in Redis with our token as the value.
        value = await redis_client.get(f"investigation:{run_id}:lock")
        assert value is not None
        assert value.decode() == lock.token

    # After exit, key is gone.
    value = await redis_client.get(f"investigation:{run_id}:lock")
    assert value is None


@pytest.mark.asyncio
async def test_lock_blocks_second_acquirer(redis_client):
    from src.workflows.run_lock import RunLock, RunLocked

    run_id = _run_id()
    async with RunLock(run_id, redis=redis_client, ttl_s=5, heartbeat_s=1):
        with pytest.raises(RunLocked):
            async with RunLock(
                run_id, redis=redis_client, ttl_s=5, heartbeat_s=1, wait_ms=0
            ):
                pass  # pragma: no cover — should not reach here


@pytest.mark.asyncio
async def test_lock_releases_on_context_exit(redis_client):
    from src.workflows.run_lock import RunLock

    run_id = _run_id()
    async with RunLock(run_id, redis=redis_client, ttl_s=5, heartbeat_s=1):
        pass
    # Re-acquire succeeds.
    async with RunLock(run_id, redis=redis_client, ttl_s=5, heartbeat_s=1):
        pass


@pytest.mark.asyncio
async def test_lock_release_is_token_safe(redis_client):
    """If our TTL expired and someone else now holds the key, our release
    must NOT delete their lock (Lua CAS on token)."""
    from src.workflows.run_lock import RunLock

    run_id = _run_id()
    key = f"investigation:{run_id}:lock"

    # Use heartbeat just below ttl, then cancel it before it fires so the
    # TTL can really expire.
    lock = RunLock(run_id, redis=redis_client, ttl_s=2, heartbeat_s=1.9)
    await lock.acquire()
    assert lock._heartbeat_task is not None
    lock._heartbeat_task.cancel()
    try:
        await lock._heartbeat_task
    except (asyncio.CancelledError, BaseException):
        pass

    # Wait past TTL, then a third party grabs the key.
    await asyncio.sleep(2.5)
    other_token = "other-holder-token"
    ok = await redis_client.set(key, other_token, ex=5, nx=True)
    assert ok

    # Now "release" our old lock — must not delete the other holder's entry.
    await lock.__aexit__(None, None, None)

    value = await redis_client.get(key)
    assert value is not None, "release stole another holder's lock (CAS broken)"
    assert value.decode() == other_token

    # Cleanup.
    await redis_client.delete(key)


@pytest.mark.asyncio
async def test_lock_heartbeat_extends_ttl(redis_client):
    """With ttl=2s and heartbeat every 0.5s, the lock must still be held
    after sleeping 3s (well past the original TTL)."""
    from src.workflows.run_lock import RunLock, RunLocked

    run_id = _run_id()
    key = f"investigation:{run_id}:lock"

    async with RunLock(run_id, redis=redis_client, ttl_s=2, heartbeat_s=0.5):
        await asyncio.sleep(3.0)
        value = await redis_client.get(key)
        assert value is not None, "heartbeat failed: lock expired"
        # A second acquirer still cannot take it.
        with pytest.raises(RunLocked):
            async with RunLock(
                run_id, redis=redis_client, ttl_s=2, heartbeat_s=0.5, wait_ms=0
            ):
                pass  # pragma: no cover


@pytest.mark.asyncio
async def test_lock_wait_ms_acquires_after_release(redis_client):
    """With wait_ms>0, the second acquirer should succeed once the first
    context exits (within the wait budget)."""
    from src.workflows.run_lock import RunLock

    run_id = _run_id()

    async def first_holder():
        async with RunLock(run_id, redis=redis_client, ttl_s=5, heartbeat_s=1):
            await asyncio.sleep(0.3)

    async def second_acquirer():
        # Give the first holder a head start.
        await asyncio.sleep(0.05)
        async with RunLock(
            run_id, redis=redis_client, ttl_s=5, heartbeat_s=1, wait_ms=1500
        ) as lock:
            assert lock.token is not None

    await asyncio.gather(first_holder(), second_acquirer())


@pytest.mark.asyncio
async def test_lock_rejects_bad_heartbeat_config(redis_client):
    from src.workflows.run_lock import RunLock

    with pytest.raises(ValueError):
        RunLock("irrelevant", redis=redis_client, ttl_s=5, heartbeat_s=5)

    with pytest.raises(ValueError):
        RunLock("irrelevant", redis=redis_client, ttl_s=5, heartbeat_s=6)
