"""Multi-instance adapter registry.

Replaces the old single-dict approach with a registry that supports
N instances per vendor and backward-compatible device_id lookups.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .base import FirewallAdapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Registry mapping instance_ids and device_ids to FirewallAdapter objects.

    Supports two lookup dimensions:
      - instance_id → adapter  (primary, every registered adapter has one)
      - device_id   → adapter  (via device bindings, for firewall_evaluator compat)

    The dict-like interface (.get, .items, __contains__, __len__) ensures
    backward compatibility with code that previously used a plain dict.
    """

    def __init__(self) -> None:
        self._instances: dict[str, FirewallAdapter] = {}
        self._device_map: dict[str, str] = {}  # device_id → instance_id
        self._lock = threading.Lock()

    # ── Core API ──

    def register(
        self,
        instance_id: str,
        adapter: FirewallAdapter,
        device_ids: list[str] | None = None,
    ) -> None:
        with self._lock:
            self._instances[instance_id] = adapter
            for did in device_ids or []:
                self._device_map[did] = instance_id
            logger.info("Registered adapter instance %s (%s)", instance_id, adapter.vendor.value)

    def get_by_instance(self, instance_id: str) -> FirewallAdapter | None:
        return self._instances.get(instance_id)

    def get_by_device(self, device_id: str) -> FirewallAdapter | None:
        iid = self._device_map.get(device_id)
        if iid:
            return self._instances.get(iid)
        return None

    def remove(self, instance_id: str) -> None:
        with self._lock:
            self._instances.pop(instance_id, None)
            to_remove = [did for did, iid in self._device_map.items() if iid == instance_id]
            for did in to_remove:
                del self._device_map[did]

    def bind_device(self, device_id: str, instance_id: str) -> None:
        with self._lock:
            self._device_map[device_id] = instance_id

    def unbind_device(self, device_id: str) -> None:
        with self._lock:
            self._device_map.pop(device_id, None)

    def all_instances(self) -> dict[str, FirewallAdapter]:
        with self._lock:
            return dict(self._instances)

    def device_bindings(self) -> dict[str, str]:
        with self._lock:
            return dict(self._device_map)

    # ── Backward-compatible dict-like interface ──

    def get(self, key: str, default: Optional[FirewallAdapter] = None) -> Optional[FirewallAdapter]:
        """Look up by device_id first, then by instance_id."""
        adapter = self.get_by_device(key)
        if adapter:
            return adapter
        adapter = self.get_by_instance(key)
        if adapter:
            return adapter
        return default

    def items(self):
        return self._instances.items()

    def values(self):
        return self._instances.values()

    def __contains__(self, key: str) -> bool:
        return key in self._device_map or key in self._instances

    def __len__(self) -> int:
        return len(self._instances)

    def __bool__(self) -> bool:
        return bool(self._instances)
