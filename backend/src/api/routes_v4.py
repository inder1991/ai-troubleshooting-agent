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


def _push_to_v5(session_id: str, state):
    """Bridge supervisor results to V5 session store for governance endpoints."""
    try:
        from src.api.routes_v5 import _v5_sessions

        # Build evidence pins from findings
        evidence_pins = []
        for f in state.all_findings:
            evidence_pins.append({
                "claim": f.title,
                "supporting_evidence": f.evidence if hasattr(f, 'evidence') else [],
                "source_agent": f.agent_name,
                "confidence": f.confidence,
                "evidence_type": f.category if hasattr(f, 'category') else "unknown",
            })

        # Build confidence ledger from per-agent data
        confidence_ledger = {
            "weighted_final": state.overall_confidence,
        }
        for tu in state.token_usage:
            agent_key = tu.agent_name.replace("_agent", "") + "_confidence"
            confidence_ledger[agent_key] = state.overall_confidence

        # Build reasoning manifest from supervisor reasoning
        reasoning_steps = []
        if hasattr(state, 'supervisor_reasoning') and state.supervisor_reasoning:
            for i, step in enumerate(state.supervisor_reasoning):
                reasoning_steps.append({
                    "step_number": i + 1,
                    "decision": step.get("decision", "") if isinstance(step, dict) else str(step),
                    "reasoning": step.get("reasoning", "") if isinstance(step, dict) else str(step),
                    "confidence_at_step": step.get("confidence", state.overall_confidence) if isinstance(step, dict) else state.overall_confidence,
                })

        # Build timeline events from task events
        timeline_events = []
        if hasattr(state, 'task_events') and state.task_events:
            for evt in state.task_events:
                timeline_events.append({
                    "timestamp": evt.timestamp if hasattr(evt, 'timestamp') else datetime.now(timezone.utc).isoformat(),
                    "source": evt.agent_name if hasattr(evt, 'agent_name') else "supervisor",
                    "event_type": evt.event_type if hasattr(evt, 'event_type') else "info",
                    "description": evt.message if hasattr(evt, 'message') else str(evt),
                    "severity": "info",
                })

        _v5_sessions[session_id] = {
            "session_id": session_id,
            "evidence_pins": evidence_pins,
            "confidence_ledger": confidence_ledger,
            "reasoning_manifest": {
                "session_id": session_id,
                "steps": reasoning_steps,
            },
            "timeline_events": timeline_events,
        }

        logger.info("Pushed V5 governance data for session %s: %d evidence pins", session_id, len(evidence_pins))
    except Exception as e:
        logger.warning("Failed to push V5 governance data for session %s: %s", session_id, e)


async def run_diagnosis(session_id: str, supervisor: SupervisorAgent, initial_input: dict, emitter: EventEmitter):
    try:
        state = await supervisor.run(initial_input, emitter)
        sessions[session_id]["state"] = state
        sessions[session_id]["phase"] = state.phase.value
        sessions[session_id]["confidence"] = state.overall_confidence
        _push_to_v5(session_id, state)
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
            "change_correlations": [],
            "blast_radius": None,
            "severity_recommendation": None,
            "past_incidents": [],
            "message": "Analysis not yet complete",
        }

    # Extract from nested agent results
    error_patterns = []
    if state.log_analysis:
        if state.log_analysis.primary_pattern:
            error_patterns.append(state.log_analysis.primary_pattern)
        error_patterns.extend(state.log_analysis.secondary_patterns)

    metric_anomalies = state.metrics_analysis.anomalies if state.metrics_analysis else []
    pod_statuses = state.k8s_analysis.pod_statuses if state.k8s_analysis else []
    k8s_events = state.k8s_analysis.events if state.k8s_analysis else []
    trace_spans = state.trace_analysis.call_chain if state.trace_analysis else []
    impacted_files = state.code_analysis.impacted_files if state.code_analysis else []

    return {
        "findings": [f.model_dump(mode="json") for f in state.all_findings],
        "negative_findings": [nf.model_dump(mode="json") for nf in state.all_negative_findings],
        "critic_verdicts": [cv.model_dump(mode="json") for cv in state.critic_verdicts],
        "error_patterns": [ep.model_dump(mode="json") for ep in error_patterns],
        "metric_anomalies": [ma.model_dump(mode="json") for ma in metric_anomalies],
        "pod_statuses": [ps.model_dump(mode="json") for ps in pod_statuses],
        "k8s_events": [ke.model_dump(mode="json") for ke in k8s_events],
        "trace_spans": [ts.model_dump(mode="json") for ts in trace_spans],
        "impacted_files": [ci.model_dump(mode="json") for ci in impacted_files],
        "change_correlations": state.change_analysis.get("change_correlations", []) if state.change_analysis else [],
        "blast_radius": state.blast_radius_result.model_dump(mode="json") if state.blast_radius_result else None,
        "severity_recommendation": state.severity_result.model_dump(mode="json") if state.severity_result else None,
        "past_incidents": state.past_incidents,
    }


@router_v4.get("/session/{session_id}/events")
async def get_events(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    emitter = sessions[session_id].get("emitter")
    if not emitter:
        return {"events": []}

    return {"events": [e.model_dump(mode="json") for e in emitter.get_all_events()]}
