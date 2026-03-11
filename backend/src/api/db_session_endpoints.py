"""Database diagnostics session endpoints -- extracted from routes_v4.py.

Contains the DB-session creation helper and the background diagnosis task.
Pure refactor: no behaviour or API changes.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import BackgroundTasks

from src.api.models import StartSessionResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public helper -- called by routes_v4.start_session when
# capability == "database_diagnostics"
# ---------------------------------------------------------------------------

async def create_db_session(
    session_id: str,
    request,
    incident_id: str,
    emitter,
    background_tasks: BackgroundTasks,
) -> StartSessionResponse:
    """Handle database_diagnostics capability for start_session.

    Imports shared state from routes_v4 at call time to avoid circular imports.
    """
    from src.api.routes_v4 import sessions, session_locks, _link_sessions, _UUID4_RE

    extra = request.extra or {}
    db_profile_id = request.profileId or extra.get("profile_id", "")

    sessions[session_id] = {
        "service_name": request.serviceName or f"db-{db_profile_id}",
        "incident_id": incident_id,
        "phase": "initial",
        "confidence": 0,
        "capability": "database_diagnostics",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "emitter": emitter,
        "state": None,
        "profile_id": db_profile_id,
        "chat_history": [],
        "db_context": {
            "profile_id": db_profile_id,
            "time_window": extra.get("time_window", "1h"),
            "focus": extra.get("focus", ["queries", "connections", "storage"]),
            "database_type": extra.get("database_type", "postgres"),
            "sampling_mode": extra.get("sampling_mode", "standard"),
            "include_explain_plans": extra.get("include_explain_plans", False),
            "parent_session_id": extra.get("parent_session_id"),
            "table_filter": extra.get("table_filter"),
            "connection_uri": extra.get("connection_uri"),
        },
    }

    # Bidirectional session linking
    parent_sid = extra.get("parent_session_id")
    if parent_sid and _UUID4_RE.match(parent_sid) and parent_sid in sessions:
        _link_sessions(session_id, parent_sid)
        sessions[session_id]["investigation_mode"] = "contextual"
    else:
        sessions[session_id]["investigation_mode"] = "standalone"

    logger.info(
        "DB diagnostics session created",
        extra={
            "session_id": session_id,
            "action": "session_created",
            "extra": "database_diagnostics",
        },
    )

    background_tasks.add_task(
        run_db_diagnosis,
        session_id,
        sessions[session_id]["db_context"],
        emitter,
    )

    return StartSessionResponse(
        session_id=session_id,
        incident_id=incident_id,
        status="started",
        message="Database diagnostics session created",
        service_name=request.serviceName or f"db-{db_profile_id}",
        created_at=sessions[session_id]["created_at"],
        capability="database_diagnostics",
    )


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def run_db_diagnosis(session_id: str, db_context: dict, emitter):
    """Background task: run LangGraph V2 database diagnostics."""
    from src.agents.database.graph_v2 import build_db_diagnostic_graph_v2
    from src.api.routes_v4 import sessions, session_locks

    lock = session_locks.get(session_id, asyncio.Lock())
    try:
        graph = build_db_diagnostic_graph_v2()

        investigation_mode = (
            "contextual" if db_context.get("parent_session_id") else "standalone"
        )

        # Resolve profile to get actual engine/host/port/database
        profile = None
        try:
            from src.database.profile_store import DBProfileStore

            _ps = DBProfileStore(
                db_path=os.environ.get("DB_DIAGNOSTICS_DB_PATH", "data/debugduck.db")
            )
            profile = _ps.get(db_context["profile_id"])
        except Exception:
            pass

        initial_state = {
            "run_id": f"R-{session_id[:8]}",
            "session_id": session_id,
            "profile_id": db_context["profile_id"],
            "profile_name": (
                profile.get("name", db_context["profile_id"])
                if profile
                else db_context["profile_id"]
            ),
            "host": profile.get("host", "") if profile else "",
            "port": profile.get("port", 5432) if profile else 5432,
            "database": profile.get("database", "") if profile else "",
            "engine": (
                profile.get("engine", db_context.get("database_type", "postgresql"))
                if profile
                else db_context.get("database_type", "postgresql")
            ),
            "investigation_mode": investigation_mode,
            "sampling_mode": db_context.get("sampling_mode", "standard"),
            "focus": db_context.get("focus", ["queries", "connections", "storage"]),
            "table_filter": db_context.get("table_filter", []),
            "include_explain_plans": db_context.get("include_explain_plans", False),
            "parent_session_id": db_context.get("parent_session_id", ""),
            "_context_fetcher": lambda sid: sessions.get(sid),
            "status": "running",
            "findings": [],
            "query_findings": [],
            "health_findings": [],
            "schema_findings": [],
            "summary": "",
            "_emitter": emitter,
        }

        # Try to resolve adapter from registry, fallback to creating from profile
        adapter = None
        try:
            from src.database.adapters.registry import adapter_registry

            adapter = adapter_registry.get_by_profile(db_context["profile_id"])
        except ImportError:
            pass

        if not adapter and profile:
            try:
                from src.api.db_endpoints import _create_adapter_from_profile

                adapter = await _create_adapter_from_profile(profile)
            except Exception as e:
                logger.error("Failed to create adapter from profile: %s", e)
                await emitter.emit(
                    "supervisor", "error", f"Failed to connect: {e}"
                )
                async with lock:
                    if session_id in sessions:
                        sessions[session_id]["phase"] = "error"
                return

        if not adapter:
            await emitter.emit(
                "supervisor",
                "error",
                f"No adapter found for profile {db_context['profile_id']}",
            )
            async with lock:
                if session_id in sessions:
                    sessions[session_id]["phase"] = "error"
            return

        initial_state["_adapter"] = adapter

        result = await asyncio.wait_for(graph.ainvoke(initial_state), timeout=180)

        async with lock:
            if session_id in sessions:
                sessions[session_id]["state"] = result
                sessions[session_id]["phase"] = (
                    "complete" if result.get("status") == "completed" else "error"
                )
                sessions[session_id]["confidence"] = 85

    except asyncio.TimeoutError:
        logger.error("DB diagnosis timed out for session %s", session_id)
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit(
            "supervisor", "error", "DB diagnosis timed out after 180s"
        )
    except Exception as e:
        logger.error("DB diagnosis failed: %s", e)
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit("supervisor", "error", f"DB diagnosis failed: {e}")
