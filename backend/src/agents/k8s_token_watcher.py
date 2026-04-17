"""K8s ServiceAccount token watcher (Task 1.7).

Kubernetes mounts the pod's SA token at
``/var/run/secrets/kubernetes.io/serviceaccount/token`` and rotates it
(OpenShift too). A long-lived process that reads the token once at
startup will hit 401 Unauthorized forever after the first rotation.

This watcher polls the token file at ``interval_s`` seconds, re-reading
only when the file's mtime has changed. Callers access the current
value via ``current()``; the retry-wrapper calls ``refresh_now()`` to
force an immediate re-read on 401/403.
"""
from __future__ import annotations

import asyncio
import os

from src.utils.logger import get_logger

logger = get_logger(__name__)


DEFAULT_SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"


class K8sTokenWatcher:
    def __init__(self, *, path: str = DEFAULT_SA_TOKEN_PATH, interval_s: float = 60.0) -> None:
        self._path = path
        self._interval_s = interval_s
        self._token: str | None = None
        self._last_mtime: float | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def current(self) -> str:
        if self._token is None:
            raise RuntimeError("K8sTokenWatcher.start() has not completed successfully")
        return self._token

    async def start(self) -> None:
        # Read once synchronously so current() is valid the moment start returns.
        await self._read_if_changed(force=True)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    async def refresh_now(self) -> None:
        await self._read_if_changed(force=True)

    async def _poll_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval_s)
                try:
                    await self._read_if_changed(force=False)
                except Exception:
                    logger.exception("K8sTokenWatcher poll failed", extra={"path": self._path})
        except asyncio.CancelledError:
            raise

    async def _read_if_changed(self, *, force: bool) -> None:
        async with self._lock:
            try:
                st = os.stat(self._path)
            except FileNotFoundError:
                # Let the caller see the first-read failure; subsequent poll
                # iterations silently retry rather than crash the watcher.
                if force:
                    raise
                logger.warning("K8sTokenWatcher: token file missing", extra={"path": self._path})
                return
            mtime = st.st_mtime
            if not force and self._last_mtime == mtime:
                return
            with open(self._path, "r", encoding="utf-8") as f:
                raw = f.read()
            new_token = raw.strip()
            if new_token != self._token:
                logger.info(
                    "K8sTokenWatcher: token reloaded",
                    extra={"path": self._path, "token_len": len(new_token)},
                )
            self._token = new_token
            self._last_mtime = mtime
