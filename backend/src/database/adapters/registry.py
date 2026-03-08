"""Multi-instance database adapter registry.

Mirrors backend/src/network/adapters/registry.py pattern.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .base import DatabaseAdapter

logger = logging.getLogger(__name__)


class DatabaseAdapterRegistry:
    """Registry mapping instance_ids and profile_ids to DatabaseAdapter objects."""

    def __init__(self) -> None:
        self._instances: dict[str, DatabaseAdapter] = {}
        self._profile_map: dict[str, str] = {}  # profile_id -> instance_id
        self._lock = threading.Lock()

    def register(
        self,
        instance_id: str,
        adapter: DatabaseAdapter,
        profile_id: str | None = None,
    ) -> None:
        with self._lock:
            self._instances[instance_id] = adapter
            if profile_id:
                self._profile_map[profile_id] = instance_id
            logger.info(
                "Registered DB adapter %s (%s)", instance_id, adapter.engine
            )

    def get_by_instance(self, instance_id: str) -> DatabaseAdapter | None:
        return self._instances.get(instance_id)

    def get_by_profile(self, profile_id: str) -> DatabaseAdapter | None:
        iid = self._profile_map.get(profile_id)
        return self._instances.get(iid) if iid else None

    def remove(self, instance_id: str) -> None:
        with self._lock:
            self._instances.pop(instance_id, None)
            to_remove = [
                pid
                for pid, iid in self._profile_map.items()
                if iid == instance_id
            ]
            for pid in to_remove:
                del self._profile_map[pid]

    def all_instances(self) -> dict[str, DatabaseAdapter]:
        with self._lock:
            return dict(self._instances)

    def __len__(self) -> int:
        return len(self._instances)

    def __bool__(self) -> bool:
        return bool(self._instances)
