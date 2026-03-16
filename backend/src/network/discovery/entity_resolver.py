"""EntityResolver — canonical identity resolution for network entities.

Given an observation dict (from any discovery source), the resolver
determines the *canonical* device_id by probing the repository with
a priority-ordered list of identifiers:

    serial > cloud_resource_id > management_ip > hostname > device_id

If none match, a new UUID-based identifier is generated.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.interface import TopologyRepository


# ── Source confidence map ────────────────────────────────────────────────────

SOURCE_CONFIDENCE: dict[str, float] = {
    "manual": 1.0,
    "lldp": 0.95,
    "gnmi": 0.95,
    "aws_api": 0.95,
    "azure_api": 0.95,
    "oci_api": 0.95,
    "snmp": 0.90,
    "cdp": 0.90,
    "config_parser": 0.85,
    "ipam": 0.80,
    "netflow": 0.70,
}

_DEFAULT_CONFIDENCE = 0.50


class EntityResolver:
    """Resolve observation dicts to canonical device and interface IDs."""

    def __init__(self, repo: TopologyRepository) -> None:
        self._repo = repo

    # ── Device resolution ────────────────────────────────────────────────

    def resolve_device(self, observation: dict) -> str:
        """Return the canonical device_id for an observation.

        Resolution priority:
          1. serial
          2. cloud_resource_id
          3. management_ip
          4. hostname
          5. device_id (explicit in observation)
          6. generate new UUID
        """
        # 1. serial
        serial = observation.get("serial")
        if serial:
            device = self._repo.find_device_by_serial(serial)
            if device is not None:
                return device.id

        # 2. cloud_resource_id — treated as a serial-like unique key
        cloud_id = observation.get("cloud_resource_id")
        if cloud_id:
            device = self._repo.find_device_by_serial(cloud_id)
            if device is not None:
                return device.id

        # 3. management_ip
        mgmt_ip = observation.get("management_ip")
        if mgmt_ip:
            device = self._repo.find_device_by_ip(mgmt_ip)
            if device is not None:
                return device.id

        # 4. hostname
        hostname = observation.get("hostname")
        if hostname:
            device = self._repo.find_device_by_hostname(hostname)
            if device is not None:
                return device.id

        # 5. explicit device_id already present
        device_id = observation.get("device_id")
        if device_id:
            device = self._repo.get_device(device_id)
            if device is not None:
                return device.id

        # 6. generate new
        return f"dev-{uuid.uuid4().hex[:12]}"

    # ── Interface resolution ─────────────────────────────────────────────

    def resolve_interface(self, device_id: str, iface_name: str) -> str:
        """Return the canonical interface ID: ``device_id:iface_name``."""
        return f"{device_id}:{iface_name}"

    # ── Confidence ───────────────────────────────────────────────────────

    def get_confidence(self, source: str) -> float:
        """Return the confidence score for a discovery source."""
        return SOURCE_CONFIDENCE.get(source, _DEFAULT_CONFIDENCE)
