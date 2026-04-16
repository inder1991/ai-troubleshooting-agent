"""Durable persistence for investigation virtual DAGs."""
from __future__ import annotations

import json
from typing import Any

from src.workflows.investigation_types import VirtualDag
from src.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_TTL = 86400  # 24 hours


class InvestigationStore:
    def __init__(self, redis_client: Any | None = None, ttl: int = DEFAULT_TTL):
        self._redis = redis_client
        self._ttl = ttl
        self._memory: dict[str, str] = {}

    def _key(self, run_id: str) -> str:
        return f"investigation:{run_id}:dag"

    async def save_dag(self, dag: VirtualDag) -> None:
        serialized = json.dumps(dag.to_dict())
        if self._redis is not None:
            try:
                await self._redis.set(self._key(dag.run_id), serialized, ex=self._ttl)
            except Exception as e:
                logger.warning("Redis save failed, using in-memory fallback: %s", e)
                self._memory[dag.run_id] = serialized
        else:
            self._memory[dag.run_id] = serialized

    async def load_dag(self, run_id: str) -> VirtualDag | None:
        raw: str | None = None
        if self._redis is not None:
            try:
                raw = await self._redis.get(self._key(run_id))
                if isinstance(raw, bytes):
                    raw = raw.decode()
            except Exception as e:
                logger.warning("Redis load failed, trying in-memory: %s", e)
                raw = self._memory.get(run_id)
        else:
            raw = self._memory.get(run_id)

        if raw is None:
            return None
        return VirtualDag.from_dict(json.loads(raw))

    async def delete_dag(self, run_id: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(self._key(run_id))
            except Exception:
                pass
        self._memory.pop(run_id, None)
