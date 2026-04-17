"""Distributed per-run_id lock backed by Redis (Task 1.6).

One investigation run_id must be owned by at most one worker across all
replicas. Implementation:

- Acquire: ``SET investigation:<run_id>:lock <token> NX EX <ttl_s>``.
- Heartbeat: a background task re-EXPIREs the key every ``heartbeat_s``
  seconds, but only if our token still owns it (Lua CAS), so a stolen
  lock cannot be refreshed by the losing holder.
- Release: Lua CAS delete — ``DEL`` only if the current value matches our
  token, so an expired holder can never delete a fresh holder's lock.

Acquisition failure surfaces as ``RunLocked``; routes map it to HTTP 409.
"""
from __future__ import annotations

import asyncio
import secrets
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


# Atomic: delete the key only if its current value equals our token.
_LUA_RELEASE = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

# Atomic: extend TTL only if our token still owns the key.
_LUA_HEARTBEAT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("pexpire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class RunLocked(Exception):
    """Raised when another worker already owns the lock for this run_id."""

    def __init__(self, key: str) -> None:
        super().__init__(f"run lock already held: {key}")
        self.key = key


class RunLock:
    def __init__(
        self,
        run_id: str,
        *,
        redis: Any,
        ttl_s: int = 15,
        heartbeat_s: float = 5.0,
        wait_ms: int = 0,
    ) -> None:
        if heartbeat_s >= ttl_s:
            raise ValueError(
                f"heartbeat_s={heartbeat_s} must be < ttl_s={ttl_s} to avoid lock loss"
            )
        self._run_id = run_id
        self._key = f"investigation:{run_id}:lock"
        self._redis = redis
        self._ttl_s = ttl_s
        self._heartbeat_s = heartbeat_s
        self._wait_ms = wait_ms
        self._token: str | None = None
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def key(self) -> str:
        return self._key

    async def acquire(self) -> None:
        token = secrets.token_urlsafe(16)
        ok = await self._redis.set(self._key, token, ex=self._ttl_s, nx=True)
        if not ok and self._wait_ms > 0:
            loop = asyncio.get_event_loop()
            deadline = loop.time() + self._wait_ms / 1000.0
            while loop.time() < deadline and not ok:
                await asyncio.sleep(0.05)
                ok = await self._redis.set(
                    self._key, token, ex=self._ttl_s, nx=True
                )
        if not ok:
            raise RunLocked(self._key)
        self._token = token
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def release(self) -> None:
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        token = self._token
        self._token = None
        if token is None:
            return
        try:
            await self._redis.eval(_LUA_RELEASE, 1, self._key, token)
        except Exception:
            logger.warning(
                "run_lock release eval failed; TTL will reclaim",
                extra={"run_id": self._run_id, "key": self._key},
            )

    async def __aenter__(self) -> "RunLock":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()

    async def _heartbeat_loop(self) -> None:
        ttl_ms = int(self._ttl_s * 1000)
        try:
            while True:
                await asyncio.sleep(self._heartbeat_s)
                try:
                    extended = await self._redis.eval(
                        _LUA_HEARTBEAT, 1, self._key, self._token, ttl_ms
                    )
                except Exception:
                    logger.warning(
                        "run_lock heartbeat eval failed",
                        extra={"run_id": self._run_id, "key": self._key},
                    )
                    return
                if not extended:
                    logger.warning(
                        "run_lock heartbeat: token no longer owns key (lock lost)",
                        extra={"run_id": self._run_id, "key": self._key},
                    )
                    return
        except asyncio.CancelledError:
            raise
