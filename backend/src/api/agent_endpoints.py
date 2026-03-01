"""
Agent Matrix API endpoints.

GET /api/v4/agents          - List all 25 agents with health status + recent executions
GET /api/v4/agents/{id}/executions - Last 5 executions for a specific agent with traces
"""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from typing import Any

from src.api.agent_registry import (
    AGENT_REGISTRY,
    AGENT_REGISTRY_MAP,
    get_agent_status,
    run_all_health_probes,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

agent_router = APIRouter(prefix="/api/v4", tags=["agent-matrix"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_recent_executions(agent_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Scan the in-memory session store for sessions that contain events
    from the given agent. Returns the most recent *limit* sessions."""
    from src.api.routes_v4 import sessions

    results: list[dict[str, Any]] = []

    for session_id, session_data in list(sessions.items()):
        emitter = session_data.get("emitter")
        if emitter is None:
            continue

        agent_events = emitter.get_events_by_agent(agent_id)
        if not agent_events:
            continue

        # Determine execution status and duration from events
        first_event = agent_events[0]
        last_event = agent_events[-1]

        duration_ms = int(
            (last_event.timestamp - first_event.timestamp).total_seconds() * 1000
        )

        has_error = any(e.event_type == "error" for e in agent_events)
        status = "ERROR" if has_error else "SUCCESS"

        # Build summary from the last non-error message
        summary_event = next(
            (e for e in reversed(agent_events) if e.event_type != "error"),
            last_event,
        )

        results.append({
            "session_id": session_id,
            "timestamp": first_event.timestamp.isoformat(),
            "status": status,
            "duration_ms": duration_ms,
            "summary": summary_event.message[:120],
        })

    # Sort by timestamp descending, take last N
    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results[:limit]


def _extract_trace(agent_id: str, session_id: str) -> list[dict[str, Any]]:
    """Extract trace events for a specific agent from a session's emitter."""
    from src.api.routes_v4 import sessions

    session_data = sessions.get(session_id)
    if not session_data:
        return []

    emitter = session_data.get("emitter")
    if emitter is None:
        return []

    agent_events = emitter.get_events_by_agent(agent_id)
    trace: list[dict[str, Any]] = []

    for evt in agent_events:
        level = "info"
        if evt.event_type == "error":
            level = "error"
        elif evt.event_type == "warning":
            level = "warn"

        trace.append({
            "timestamp": evt.timestamp.strftime("%H:%M:%S"),
            "level": level,
            "message": evt.message[:200],
        })

    return trace


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@agent_router.get("/agents")
async def list_agents():
    """Return all 25 agents with live health status and recent executions."""
    health_results = await run_all_health_probes()

    agents_out: list[dict[str, Any]] = []
    summary_counts = {"total": 0, "active": 0, "degraded": 0, "offline": 0}

    for agent in AGENT_REGISTRY:
        status, degraded_tools = get_agent_status(agent, health_results)

        recent = _find_recent_executions(agent["id"], limit=3)

        agents_out.append({
            "id": agent["id"],
            "name": agent["name"],
            "workflow": agent["workflow"],
            "role": agent["role"],
            "description": agent["description"],
            "icon": agent["icon"],
            "level": agent["level"],
            "llm_config": agent["llm_config"],
            "timeout_s": agent["timeout_s"],
            "status": status,
            "degraded_tools": degraded_tools,
            "tools": agent["tools"],
            "architecture_stages": agent["architecture_stages"],
            "recent_executions": recent,
        })

        summary_counts["total"] += 1
        summary_counts[status] += 1

    return {
        "agents": agents_out,
        "summary": summary_counts,
    }


@agent_router.get("/agents/{agent_id}/executions")
async def get_agent_executions(agent_id: str):
    """Return the last 5 executions for a specific agent with trace events."""
    if agent_id not in AGENT_REGISTRY_MAP:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    executions = _find_recent_executions(agent_id, limit=5)

    # Enrich each execution with its trace
    for execution in executions:
        execution["trace"] = _extract_trace(agent_id, execution["session_id"])
        # Extract confidence from trace if available
        execution["confidence"] = None

    return {
        "agent_id": agent_id,
        "executions": executions,
    }
