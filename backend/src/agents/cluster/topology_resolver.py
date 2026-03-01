"""Topology Snapshot Resolver — LangGraph node that reads or builds cached topology."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from src.agents.cluster.state import TopologySnapshot
from src.agents.cluster.traced_node import traced_node
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Module-level cache: session_id -> (TopologySnapshot, timestamp)
_topology_cache: dict[str, tuple[TopologySnapshot, float]] = {}
TOPOLOGY_TTL_SECONDS = 300  # 5 minutes


def clear_topology_cache(session_id: str) -> None:
    """Clear cached topology for a session. Called on session cleanup."""
    _topology_cache.pop(session_id, None)


@traced_node(timeout_seconds=30)
async def topology_snapshot_resolver(state: dict, config: dict) -> dict:
    """LangGraph node: resolve or build topology snapshot."""
    session_id = state.get("diagnostic_id", "")
    client = config.get("configurable", {}).get("cluster_client")

    if not client:
        logger.warning("No cluster_client in config, skipping topology")
        return {
            "topology_graph": TopologySnapshot(stale=True).model_dump(mode="json"),
            "topology_freshness": {"timestamp": "", "stale": True},
        }

    # Check cache (atomic get avoids TOCTOU race with clear_topology_cache)
    cached = _topology_cache.get(session_id)
    if cached is not None:
        snapshot, cached_at = cached
        if (time.monotonic() - cached_at) < TOPOLOGY_TTL_SECONDS:
            logger.info("Using cached topology", extra={"action": "cache_hit", "node_count": len(snapshot.nodes)})
            return {
                "topology_graph": snapshot.model_dump(mode="json"),
                "topology_freshness": {"timestamp": snapshot.built_at, "stale": False},
            }

    # Build fresh
    snapshot = await client.build_topology_snapshot()
    _topology_cache[session_id] = (snapshot, time.monotonic())

    logger.info("Built fresh topology", extra={
        "action": "topology_built",
        "node_count": len(snapshot.nodes),
        "edge_count": len(snapshot.edges),
    })

    return {
        "topology_graph": snapshot.model_dump(mode="json"),
        "topology_freshness": {"timestamp": snapshot.built_at, "stale": False},
    }
