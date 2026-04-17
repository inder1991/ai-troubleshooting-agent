"""K8sAuthenticatedClient (Task 1.7).

Thin wrapper that runs a Kubernetes API call, and on 401/403:
  1. Calls ``token_watcher.refresh_now()`` to re-read the rotated SA token
  2. Retries the call EXACTLY ONCE with the new token
  3. If still 401/403, raises ``K8sAuthError`` — no further retry.

Non-auth errors (4xx other than 401/403, 5xx, network) bubble up
unchanged; the caller decides whether to retry them (Task 3.x circuit
breakers).
"""
from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Union

from kubernetes.client.rest import ApiException

from src.agents.k8s_token_watcher import K8sTokenWatcher
from src.utils.logger import get_logger

logger = get_logger(__name__)


class K8sAuthError(Exception):
    """Raised when the K8s API still returns 401/403 after a token reload."""


ApiCall = Callable[[str], Union[Any, Awaitable[Any]]]


class K8sAuthenticatedClient:
    def __init__(self, *, token_watcher: K8sTokenWatcher) -> None:
        self._watcher = token_watcher

    async def call(self, api_call: ApiCall) -> Any:
        """Invoke ``api_call(token)`` with the current token; on 401/403,
        refresh the token and retry once. ``api_call`` may be sync or async.
        """
        token = self._watcher.current()
        try:
            return await self._invoke(api_call, token)
        except ApiException as e:
            if e.status not in (401, 403):
                raise
            logger.warning(
                "K8s %s — refreshing SA token and retrying once",
                e.status,
                extra={"status": e.status, "reason": e.reason},
            )
            await self._watcher.refresh_now()
            new_token = self._watcher.current()
            try:
                return await self._invoke(api_call, new_token)
            except ApiException as e2:
                if e2.status in (401, 403):
                    raise K8sAuthError(
                        f"K8s auth still failing after token reload: {e2.status} {e2.reason}"
                    ) from e2
                raise

    @staticmethod
    async def _invoke(api_call: ApiCall, token: str) -> Any:
        result = api_call(token)
        if inspect.isawaitable(result):
            return await result
        return result
