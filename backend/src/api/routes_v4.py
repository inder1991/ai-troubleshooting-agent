import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, BackgroundTasks, HTTPException
from typing import Dict, Any

from src.api.models import (
    ChatRequest, ChatResponse, StartSessionRequest, StartSessionResponse, SessionSummary
)
from src.agents.supervisor import SupervisorAgent
from src.utils.event_emitter import EventEmitter
from src.api.websocket import manager

logger = logging.getLogger(__name__)

router_v4 = APIRouter(prefix="/api/v4", tags=["v4"])

# In-memory session store
sessions: Dict[str, Dict[str, Any]] = {}
supervisors: Dict[str, SupervisorAgent] = {}

SESSION_TTL_HOURS = 24
SESSION_CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


async def _session_cleanup_loop():
    """Background task to remove sessions older than SESSION_TTL_HOURS."""
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=SESSION_TTL_HOURS)
            expired = []
            for sid, data in sessions.items():
                created = data.get("created_at", "")
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if created_dt < cutoff:
                        expired.append(sid)
                except (ValueError, AttributeError):
                    continue

            for sid in expired:
                sessions.pop(sid, None)
                supervisors.pop(sid, None)

            if expired:
                logger.info(
                    "Session cleanup: removed %d expired sessions, %d remaining",
                    len(expired), len(sessions),
                )
        except Exception as e:
            logger.error("Session cleanup error: %s", e)


def start_cleanup_task():
    """Start the session cleanup background loop."""
    asyncio.create_task(_session_cleanup_loop())


@router_v4.post("/session/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest, background_tasks: BackgroundTasks):
    session_id = str(uuid.uuid4())[:8]

    # Resolve connection config from profile
    connection_config = None
    profile_id = request.profileId
    try:
        from src.integrations.connection_config import resolve_active_profile
        connection_config = resolve_active_profile(profile_id)
    except Exception as e:
        logger.warning("Could not resolve profile config: %s", e)

    supervisor = SupervisorAgent(connection_config=connection_config)
    emitter = EventEmitter(session_id=session_id, websocket_manager=manager)

    sessions[session_id] = {
        "service_name": request.serviceName,
        "phase": "initial",
        "confidence": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "emitter": emitter,
        "state": None,
        "profile_id": profile_id,
    }
    supervisors[session_id] = supervisor

    initial_input = {
        "session_id": session_id,
        "service_name": request.serviceName,
        "elk_index": request.elkIndex,
        "time_start": f"now-{request.timeframe}",
        "time_end": "now",
        "trace_id": request.traceId,
        "namespace": request.namespace,
        "cluster_url": request.clusterUrl,
        "repo_url": request.repoUrl,
    }

    background_tasks.add_task(run_diagnosis, session_id, supervisor, initial_input, emitter)

    return StartSessionResponse(
        session_id=session_id,
        status="started",
        message=f"Diagnosis started for {request.serviceName}"
    )


async def run_diagnosis(session_id: str, supervisor: SupervisorAgent, initial_input: dict, emitter: EventEmitter):
    try:
        state = await supervisor.run(initial_input, emitter)
        sessions[session_id]["state"] = state
        sessions[session_id]["phase"] = state.phase.value
        sessions[session_id]["confidence"] = state.overall_confidence
    except Exception as e:
        sessions[session_id]["phase"] = "error"
        await emitter.emit("supervisor", "error", f"Diagnosis failed: {str(e)}")


@router_v4.post("/session/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    supervisor = supervisors.get(session_id)
    state = sessions[session_id].get("state")

    if not supervisor:
        raise HTTPException(status_code=404, detail="Session supervisor not found")

    if state:
        response_text = await supervisor.handle_user_message(request.message, state)
    else:
        response_text = "Analysis is still starting up. Please wait a moment."

    return ChatResponse(
        response=response_text,
        phase=sessions[session_id].get("phase", "initial"),
        confidence=sessions[session_id].get("confidence", 0),
    )


@router_v4.get("/sessions", response_model=list[SessionSummary])
async def list_sessions():
    return [
        SessionSummary(
            session_id=sid,
            service_name=data["service_name"],
            phase=data["phase"],
            confidence=data["confidence"],
            created_at=data["created_at"],
        )
        for sid, data in sessions.items()
    ]


@router_v4.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    state = session.get("state")

    result = {
        "session_id": session_id,
        "service_name": session["service_name"],
        "phase": session["phase"],
        "confidence": session["confidence"],
        "created_at": session.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": session.get("updated_at", session.get("created_at", datetime.now(timezone.utc).isoformat())),
        "breadcrumbs": [],
        "findings_count": 0,
        "token_usage": [],
    }

    if state:
        result["agents_completed"] = state.agents_completed
        result["findings_count"] = len(state.all_findings)
        result["token_usage"] = [t.model_dump() for t in state.token_usage]
        if hasattr(state, 'breadcrumbs') and state.breadcrumbs:
            result["breadcrumbs"] = [b.model_dump(mode="json") for b in state.breadcrumbs]

    return result


@router_v4.get("/session/{session_id}/findings")
async def get_findings(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    state = sessions[session_id].get("state")
    if not state:
        return {
            "findings": [],
            "negative_findings": [],
            "critic_verdicts": [],
            "error_patterns": [],
            "metric_anomalies": [],
            "pod_statuses": [],
            "k8s_events": [],
            "trace_spans": [],
            "impacted_files": [],
            "message": "Analysis not yet complete",
        }

    return {
        "findings": [f.model_dump(mode="json") for f in state.all_findings],
        "negative_findings": [nf.model_dump(mode="json") for nf in state.all_negative_findings],
        "critic_verdicts": [cv.model_dump(mode="json") for cv in state.critic_verdicts],
        "error_patterns": [ep.model_dump(mode="json") for ep in getattr(state, 'error_patterns', [])],
        "metric_anomalies": [ma.model_dump(mode="json") for ma in getattr(state, 'metric_anomalies', [])],
        "pod_statuses": [ps.model_dump(mode="json") for ps in getattr(state, 'pod_statuses', [])],
        "k8s_events": [ke.model_dump(mode="json") for ke in getattr(state, 'k8s_events', [])],
        "trace_spans": [ts.model_dump(mode="json") for ts in getattr(state, 'trace_spans', [])],
        "impacted_files": [ci.model_dump(mode="json") for ci in getattr(state, 'impacted_files', [])],
    }


@router_v4.get("/session/{session_id}/events")
async def get_events(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    emitter = sessions[session_id].get("emitter")
    if not emitter:
        return {"events": []}

    return {"events": [e.model_dump(mode="json") for e in emitter.get_all_events()]}
