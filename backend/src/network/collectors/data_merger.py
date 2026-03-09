"""Fidelity-based data merger — gNMI > RESTCONF > SNMP > SSH."""
from __future__ import annotations

from .base import CollectorProtocol
from .models import CollectedData

# Fidelity scores: higher = more trusted for overlapping fields
FIDELITY = {
    CollectorProtocol.GNMI.value: 10,
    CollectorProtocol.RESTCONF.value: 9,
    CollectorProtocol.SNMP.value: 5,
    CollectorProtocol.SSH_CLI.value: 3,
    CollectorProtocol.CLOUD_API.value: 8,
}


def merge_collected_data(results: list[CollectedData]) -> CollectedData | None:
    """Merge collected data from multiple protocols for the same device.

    Higher-fidelity protocol wins for overlapping fields.
    Returns None if results is empty.
    """
    if not results:
        return None
    if len(results) == 1:
        return results[0]

    # Sort by fidelity (highest first)
    sorted_results = sorted(
        results,
        key=lambda r: FIDELITY.get(r.protocol, 0),
        reverse=True,
    )

    primary = sorted_results[0]

    # Start with copy of primary
    merged = CollectedData(
        device_id=primary.device_id,
        protocol=primary.protocol,
        timestamp=primary.timestamp,
        cpu_pct=primary.cpu_pct,
        mem_pct=primary.mem_pct,
        uptime_seconds=primary.uptime_seconds,
        temperature=primary.temperature,
        interface_metrics=dict(primary.interface_metrics),
        metadata=dict(primary.metadata),
        custom_metrics=dict(primary.custom_metrics),
        raw=dict(primary.raw),
    )

    # Fill gaps from lower-fidelity sources
    for result in sorted_results[1:]:
        if merged.cpu_pct is None and result.cpu_pct is not None:
            merged.cpu_pct = result.cpu_pct
        if merged.mem_pct is None and result.mem_pct is not None:
            merged.mem_pct = result.mem_pct
        if merged.uptime_seconds is None and result.uptime_seconds is not None:
            merged.uptime_seconds = result.uptime_seconds
        if merged.temperature is None and result.temperature is not None:
            merged.temperature = result.temperature

        # Merge interface metrics (add interfaces not seen in higher-fidelity sources)
        for if_name, if_data in result.interface_metrics.items():
            if if_name not in merged.interface_metrics:
                merged.interface_metrics[if_name] = if_data

        # Merge metadata (fill gaps only)
        for k, v in result.metadata.items():
            if k not in merged.metadata:
                merged.metadata[k] = v

        # Merge custom metrics (fill gaps only)
        for k, v in result.custom_metrics.items():
            if k not in merged.custom_metrics:
                merged.custom_metrics[k] = v

    return merged
