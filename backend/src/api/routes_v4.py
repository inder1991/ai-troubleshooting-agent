import json
import os
import re
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

from src.api.models import (
    ChatRequest, ChatResponse, StartSessionRequest, StartSessionResponse, SessionSummary,
    FixRequest, FixStatusResponse, FixStatusFileEntry, FixDecisionRequest,
    CampaignStatusResponse, CampaignRepoStatusResponse, CampaignRepoDecisionRequest,
    CampaignExecuteResponse,
)
from src.agents.supervisor import SupervisorAgent
from src.agents.cluster.graph import build_cluster_diagnostic_graph
from src.utils.event_emitter import EventEmitter
from src.utils.llm_client import AnthropicClient
from src.api.websocket import manager
from src.utils.logger import get_logger
from src.tools.router_models import InvestigateRequest, InvestigateResponse
from src.tools.tool_registry import TOOL_REGISTRY
from src.agents.critic_agent import CriticAgent
from src.models.schemas import EvidencePin

logger = get_logger(__name__)

# C1: Per-session locks to prevent concurrent state mutation
session_locks: Dict[str, asyncio.Lock] = {}

# M1: UUID4 format validation
_UUID4_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.IGNORECASE)

# M10: Track background diagnosis tasks for cancellation on cleanup
_diagnosis_tasks: Dict[str, asyncio.Task] = {}

# B3: Track background critic delta tasks per session for cancellation on cleanup
_critic_delta_tasks: Dict[str, list] = {}  # session_id -> list[asyncio.Task]

# B5: Dedup window in seconds for evidence pins (same source_tool + claim)
_PIN_DEDUP_WINDOW_SECONDS = 60

# B6: Valid causal_role values; anything else falls back to "informational"
_VALID_CAUSAL_ROLES = {"root_cause", "cascading_symptom", "correlated", "informational"}


def _is_duplicate_pin(existing_pins: list, new_pin) -> bool:
    """B5: Check if a pin with the same source_tool + claim exists within the dedup window."""
    new_ts = new_pin.timestamp
    for raw in existing_pins:
        if raw.get("source_tool") == new_pin.source_tool and raw.get("claim") == new_pin.claim:
            existing_ts_str = raw.get("timestamp")
            if existing_ts_str:
                try:
                    existing_ts = datetime.fromisoformat(existing_ts_str.replace("Z", "+00:00"))
                    if abs((new_ts - existing_ts).total_seconds()) < _PIN_DEDUP_WINDOW_SECONDS:
                        return True
                except (ValueError, TypeError):
                    continue
    return False


def _validate_causal_role(pin) -> None:
    """B6: Validate causal_role against allowed values; fallback to 'informational'."""
    if pin.causal_role is not None and pin.causal_role not in _VALID_CAUSAL_ROLES:
        pin.causal_role = "informational"


def _validate_session_id(session_id: str) -> None:
    """M1: Validate session_id is a proper UUID4 to prevent DoS via random lookups."""
    if not _UUID4_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")


def _dump(obj):
    """Serialize a Pydantic BaseModel or pass through a dict/primitive unchanged."""
    if obj is None:
        return None
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    return obj


def _dump_list(items: list) -> list:
    """Serialize a list of Pydantic models or dicts."""
    return [_dump(item) for item in items]


def _dump_campaign(campaign) -> dict | None:
    """Serialize RemediationCampaign to frontend-friendly format (repos as list)."""
    if campaign is None:
        return None
    repos_list = []
    for repo_url, fix in campaign.repos.items():
        repos_list.append({
            "repo_url": repo_url,
            "service_name": fix.service_name,
            "status": fix.status.value if hasattr(fix.status, 'value') else str(fix.status),
            "causal_role": fix.causal_role,
            "diff": fix.diff,
            "fix_explanation": fix.fix_explanation,
            "fixed_files": [{"file_path": f.get("file_path", ""), "diff": f.get("diff", "")} for f in fix.fixed_files],
            "pr_url": fix.pr_url,
            "pr_number": fix.pr_number,
            "error_message": fix.error_message,
        })
    return {
        "campaign_id": campaign.campaign_id,
        "overall_status": campaign.overall_status,
        "approved_count": campaign.approved_count,
        "total_count": campaign.total_count,
        "repos": repos_list,
    }

router_v4 = APIRouter(prefix="/api/v4", tags=["v4"])

# In-memory session store
sessions: Dict[str, Dict[str, Any]] = {}
supervisors: Dict[str, SupervisorAgent] = {}

# Investigation routers per session
_investigation_routers: Dict[str, Any] = {}


def _get_investigation_router(session_id: str):
    """Get or create InvestigationRouter for a session.

    B4: Constructor is fully synchronous with no awaits, so CPython's GIL
    guarantees dict check and store are effectively atomic. Do not add
    any awaits in this function.
    """
    existing = _investigation_routers.get(session_id)
    if existing is not None:
        return existing

    from src.tools.investigation_router import InvestigationRouter
    from src.tools.tool_executor import ToolExecutor
    config = sessions[session_id].get("connection_config", {})
    executor = ToolExecutor(config)
    llm = AnthropicClient(agent_name="investigation_router")
    router = InvestigationRouter(tool_executor=executor, llm_client=llm)
    _investigation_routers[session_id] = router
    return router


SESSION_TTL_HOURS = 24
SESSION_CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


async def _session_cleanup_loop():
    """Background task to remove sessions older than SESSION_TTL_HOURS."""
    while True:
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=SESSION_TTL_HOURS)
            expired = []
            for sid, data in list(sessions.items()):
                created = data.get("created_at", "")
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if created_dt < cutoff:
                        expired.append(sid)
                except (ValueError, AttributeError):
                    continue

            for sid in expired:
                # M10: Cancel running diagnosis tasks before removing session
                task = _diagnosis_tasks.pop(sid, None)
                if task and not task.done():
                    task.cancel()
                # B3: Cancel all critic delta tasks for this session
                critic_tasks = _critic_delta_tasks.pop(sid, [])
                for ct in critic_tasks:
                    if not ct.done():
                        ct.cancel()
                # B2: Remove investigation router for this session
                _investigation_routers.pop(sid, None)
                # H1: Use lock during cleanup to prevent races with HTTP handlers
                lock = session_locks.pop(sid, None)
                if lock:
                    async with lock:
                        sessions.pop(sid, None)
                        supervisors.pop(sid, None)
                else:
                    sessions.pop(sid, None)
                    supervisors.pop(sid, None)
                manager.disconnect(sid)

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


def create_cluster_client(connection_config=None):
    """Factory for cluster client. Returns MockClusterClient for now; swappable for real client."""
    from src.agents.cluster_client.mock_client import MockClusterClient
    return MockClusterClient(platform="openshift")


@router_v4.post("/session/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest, background_tasks: BackgroundTasks):
    session_id = str(uuid.uuid4())

    from src.agents.supervisor import generate_incident_id
    incident_id = generate_incident_id()

    # Resolve connection config from profile
    connection_config = None
    profile_id = request.profileId
    try:
        from src.integrations.connection_config import resolve_active_profile
        connection_config = resolve_active_profile(profile_id)
    except Exception as e:
        logger.warning("Could not resolve profile config: %s", e)

    emitter = EventEmitter(session_id=session_id, websocket_manager=manager)

    # C1: Create per-session lock
    session_locks[session_id] = asyncio.Lock()

    capability = request.capability

    # ── Cluster Diagnostics capability ──
    if capability == "cluster_diagnostics":
        # Build connection config: prefer profile, fall back to ad-hoc fields
        if not connection_config and request.clusterUrl:
            try:
                from src.integrations.connection_config import ResolvedConnectionConfig
                connection_config = ResolvedConnectionConfig(
                    cluster_url=request.clusterUrl,
                    cluster_token=request.authToken or "",
                    cluster_type="kubernetes",
                )
            except Exception as e:
                logger.warning("Could not build ad-hoc connection config: %s", e)

        cluster_client = create_cluster_client(connection_config)
        graph = build_cluster_diagnostic_graph()

        sessions[session_id] = {
            "service_name": request.serviceName or "Cluster Diagnostics",
            "incident_id": incident_id,
            "phase": "initial",
            "confidence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "emitter": emitter,
            "state": None,
            "profile_id": profile_id,
            "capability": "cluster_diagnostics",
            "graph": graph,
            "chat_history": [],
            "connection_config": connection_config,
        }

        background_tasks.add_task(
            run_cluster_diagnosis, session_id, graph, cluster_client, emitter
        )

        logger.info("Cluster session created", extra={"session_id": session_id, "action": "session_created", "extra": "cluster_diagnostics"})

        return StartSessionResponse(
            session_id=session_id,
            incident_id=incident_id,
            status="started",
            message="Cluster diagnostics started",
            service_name=request.serviceName or "Cluster Diagnostics",
            created_at=sessions[session_id]["created_at"],
        )

    # ── Default: troubleshoot_app capability ──
    supervisor = SupervisorAgent(connection_config=connection_config)

    sessions[session_id] = {
        "service_name": request.serviceName,
        "incident_id": incident_id,
        "phase": "initial",
        "confidence": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "emitter": emitter,
        "state": None,
        "profile_id": profile_id,
        "chat_history": [],
    }
    supervisors[session_id] = supervisor

    # Fall back to profile values when form doesn't provide them
    cluster_url = request.clusterUrl
    namespace = request.namespace
    if connection_config:
        if not cluster_url and connection_config.cluster_url:
            cluster_url = connection_config.cluster_url
        if not namespace and connection_config.namespace:
            namespace = connection_config.namespace

    initial_input = {
        "session_id": session_id,
        "incident_id": incident_id,
        "service_name": request.serviceName,
        "elk_index": request.elkIndex,
        "time_start": f"now-{request.timeframe}",
        "time_end": "now",
        "trace_id": request.traceId,
        "namespace": namespace,
        "cluster_url": cluster_url,
        "repo_url": request.repoUrl,
    }

    logger.info("Session created", extra={"session_id": session_id, "action": "session_created", "extra": request.serviceName, "profile_id": profile_id})

    background_tasks.add_task(run_diagnosis, session_id, supervisor, initial_input, emitter)

    return StartSessionResponse(
        session_id=session_id,
        incident_id=incident_id,
        status="started",
        message=f"Diagnosis started for {request.serviceName}",
        service_name=request.serviceName,
        created_at=sessions[session_id]["created_at"],
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

        # Build confidence ledger from per-agent findings
        confidence_ledger = {
            "weighted_final": state.overall_confidence,
        }
        agent_confidences: Dict[str, list] = {}
        for f in state.all_findings:
            key = f.agent_name.replace("_agent", "") + "_confidence"
            agent_confidences.setdefault(key, []).append(f.confidence)
        for key, values in agent_confidences.items():
            confidence_ledger[key] = round(sum(values) / len(values)) if values else 0

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
        logger.error("Failed to push V5 governance data for session %s: %s", session_id, e, exc_info=True)


async def run_cluster_diagnosis(session_id, graph, cluster_client, emitter):
    """Background task: run LangGraph cluster diagnostic."""
    try:
        _diagnosis_tasks[session_id] = asyncio.current_task()
    except RuntimeError:
        pass

    lock = session_locks.get(session_id, asyncio.Lock())
    try:
        initial_state = {
            "diagnostic_id": session_id,
            "platform": "",
            "platform_version": "",
            "namespaces": [],
            "exclude_namespaces": [],
            "domain_reports": [],
            "causal_chains": [],
            "uncorrelated_findings": [],
            "health_report": None,
            "phase": "pre_flight",
            "re_dispatch_count": 0,
            "re_dispatch_domains": [],
            "data_completeness": 0.0,
            "error": None,
        }

        # Pre-flight: detect platform
        platform_info = await cluster_client.detect_platform()
        initial_state["platform"] = platform_info.get("platform", "kubernetes")
        initial_state["platform_version"] = platform_info.get("version", "")

        ns_result = await cluster_client.list_namespaces()
        initial_state["namespaces"] = ns_result.data

        await emitter.emit("cluster_supervisor", "phase_change", "Starting cluster diagnostics", {"phase": "collecting_context"})

        config = {
            "configurable": {
                "cluster_client": cluster_client,
                "emitter": emitter,
            }
        }

        result = await asyncio.wait_for(
            graph.ainvoke(initial_state, config=config),
            timeout=180,
        )

        async with lock:
            if session_id in sessions:
                sessions[session_id]["state"] = result
                sessions[session_id]["phase"] = result.get("phase", "complete")
                sessions[session_id]["confidence"] = int(result.get("data_completeness", 0) * 100)

        await emitter.emit("cluster_supervisor", "phase_change", "Cluster diagnostics complete", {"phase": "diagnosis_complete"})

    except asyncio.TimeoutError:
        logger.error("Cluster diagnosis timed out", extra={"session_id": session_id})
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit("cluster_supervisor", "error", "Cluster diagnosis timed out after 180s")
    except asyncio.CancelledError:
        logger.info("Cluster diagnosis cancelled for session %s", session_id)
    except Exception as e:
        logger.error("Cluster diagnosis failed", extra={"session_id": session_id, "action": "cluster_error", "extra": str(e)})
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit("cluster_supervisor", "error", f"Cluster diagnosis failed: {str(e)}")
    finally:
        _diagnosis_tasks.pop(session_id, None)
        await cluster_client.close()


async def run_diagnosis(session_id: str, supervisor: SupervisorAgent, initial_input: dict, emitter: EventEmitter):
    # M10: Store current task for cancellation on cleanup
    try:
        _diagnosis_tasks[session_id] = asyncio.current_task()  # type: ignore[assignment]
    except RuntimeError:
        pass

    lock = session_locks.get(session_id, asyncio.Lock())
    try:
        state = await supervisor.run(initial_input, emitter)
        # C1: Acquire lock for state mutation
        async with lock:
            if session_id in sessions:
                sessions[session_id]["state"] = state
                sessions[session_id]["phase"] = state.phase.value
                sessions[session_id]["confidence"] = state.overall_confidence
        _push_to_v5(session_id, state)
    except asyncio.CancelledError:
        logger.info("Diagnosis cancelled for session %s", session_id)
    except Exception as e:
        logger.error("Diagnosis failed", extra={"session_id": session_id, "action": "diagnosis_error", "extra": str(e)})
        async with lock:
            if session_id in sessions:
                sessions[session_id]["phase"] = "error"
        await emitter.emit("supervisor", "error", f"Diagnosis failed: {str(e)}")
    finally:
        _diagnosis_tasks.pop(session_id, None)


CLUSTER_CHAT_HISTORY_CAP = 20


async def _handle_cluster_chat(session: dict, message: str) -> str:
    """Handle chat for cluster diagnostics sessions using full cluster state as context."""
    state = session.get("state")
    if not state:
        return "Diagnostics are still starting. Please wait for initial results before asking questions."

    chat_history = session.setdefault("chat_history", [])

    # Build system prompt with cluster state context
    state_context = json.dumps(state, indent=2, default=str)
    if len(state_context) > 8000:
        state_context = state_context[:8000] + "\n... (truncated)"

    system_prompt = f"""You are a cluster diagnostics assistant for an AI-powered SRE platform.
You have access to the full diagnostic state below. Use it to answer questions accurately.

Answer questions about diagnostic findings, help interpret causal chains, explain domain-specific
issues (control plane, node health, networking, storage), guide remediation steps, and suggest
re-analysis when the user provides new context.

Be concise. Reference specific findings from the state when answering.

## Current Cluster Diagnostic State
{state_context}"""

    # Build messages list from history + new user message
    messages = [{"role": m["role"], "content": m["content"]} for m in chat_history]
    messages.append({"role": "user", "content": message})

    # Call LLM
    try:
        llm = AnthropicClient(agent_name="cluster_chat")
        response = await llm.chat(
            prompt=message,
            system=system_prompt,
            messages=messages,
            max_tokens=1024,
        )
        response_text = response.text
    except Exception as e:
        logger.error("Cluster chat LLM call failed", extra={"error": str(e)})
        return "I couldn't process your question. Please try again."

    # Append to history and cap
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response_text})
    if len(chat_history) > CLUSTER_CHAT_HISTORY_CAP:
        session["chat_history"] = chat_history[-CLUSTER_CHAT_HISTORY_CAP:]

    return response_text


@router_v4.post("/session/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest):
    _validate_session_id(session_id)
    logger.info("Chat message received", extra={"session_id": session_id, "action": "chat"})

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Branch by capability
    if session.get("capability") == "cluster_diagnostics":
        response_text = await _handle_cluster_chat(session, request.message)
        return ChatResponse(
            response=response_text,
            phase=session.get("phase", "initial"),
            confidence=session.get("confidence", 0),
        )

    # App diagnostics — existing supervisor flow
    supervisor = supervisors.get(session_id)
    if not supervisor:
        raise HTTPException(status_code=404, detail="Session supervisor not found")

    state = session.get("state")
    if state:
        response_text = await supervisor.handle_user_message(request.message, state)
    else:
        response_text = "Analysis is still starting up. Please wait a moment."

    return ChatResponse(
        response=response_text,
        phase=session.get("phase", "initial"),
        confidence=session.get("confidence", 0),
    )


@router_v4.get("/sessions", response_model=list[SessionSummary])
async def list_sessions():
    return [
        SessionSummary(
            session_id=sid,
            service_name=data["service_name"],
            incident_id=data.get("incident_id"),
            phase=data["phase"],
            confidence=data["confidence"],
            created_at=data["created_at"],
        )
        for sid, data in sessions.items()
    ]


@router_v4.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")

    result = {
        "session_id": session_id,
        "incident_id": session.get("incident_id"),
        "service_name": session["service_name"],
        "phase": session["phase"],
        "confidence": session["confidence"],
        "created_at": session.get("created_at", datetime.now(timezone.utc).isoformat()),
        "updated_at": session.get("updated_at", session.get("created_at", datetime.now(timezone.utc).isoformat())),
        "breadcrumbs": [],
        "findings_count": 0,
        "token_usage": [],
    }

    # Cluster sessions: state is a plain dict
    if session.get("capability") == "cluster_diagnostics":
        if state and isinstance(state, dict):
            result["findings_count"] = len(state.get("domain_reports", []))
            result["data_completeness"] = state.get("data_completeness", 0)
        return result

    # App sessions: state is a SupervisorAgent state object
    if state:
        result["incident_id"] = state.incident_id
        result["agents_completed"] = state.agents_completed
        result["findings_count"] = len(state.all_findings)
        result["token_usage"] = [t.model_dump() for t in state.token_usage]
        if state.all_breadcrumbs:
            result["breadcrumbs"] = [b.model_dump(mode="json") for b in state.all_breadcrumbs]

    return result


@router_v4.get("/session/{session_id}/findings")
async def get_findings(session_id: str):
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Cluster diagnostics: return cluster-specific findings
    if session.get("capability") == "cluster_diagnostics":
        state = session.get("state", {})
        if isinstance(state, dict) and state:
            return {
                "diagnostic_id": session_id,
                "platform": state.get("platform", ""),
                "platform_version": state.get("platform_version", ""),
                "platform_health": state.get("health_report", {}).get("platform_health", "UNKNOWN") if state.get("health_report") else "PENDING",
                "data_completeness": state.get("data_completeness", 0.0),
                "causal_chains": state.get("causal_chains", []),
                "uncorrelated_findings": state.get("uncorrelated_findings", []),
                "domain_reports": state.get("domain_reports", []),
                "blast_radius": state.get("health_report", {}).get("blast_radius", {}) if state.get("health_report") else {},
                "remediation": state.get("health_report", {}).get("remediation", {}) if state.get("health_report") else {},
                "execution_metadata": state.get("health_report", {}).get("execution_metadata", {}) if state.get("health_report") else {},
            }
        return {"diagnostic_id": session_id, "platform_health": "PENDING", "domain_reports": []}

    state = session.get("state")
    logger.info("Findings requested", extra={"session_id": session_id, "action": "findings_requested", "extra": {"findings_count": len(state.all_findings) if state else 0}})
    if not state:
        return {
            "session_id": session_id,
            "findings": [],
            "negative_findings": [],
            "critic_verdicts": [],
            "error_patterns": [],
            "metric_anomalies": [],
            "correlated_signals": [],
            "event_markers": [],
            "pod_statuses": [],
            "k8s_events": [],
            "trace_spans": [],
            "impacted_files": [],
            "diff_analysis": [],
            "suggested_fix_areas": [],
            "root_cause_location": None,
            "code_call_chain": [],
            "code_dependency_graph": {},
            "code_shared_resource_conflicts": [],
            "code_cross_repo_findings": [],
            "code_mermaid_diagram": "",
            "code_overall_confidence": 0,
            "change_correlations": [],
            "change_summary": None,
            "change_high_priority_files": [],
            "blast_radius": None,
            "severity_recommendation": None,
            "past_incidents": [],
            "service_flow": [],
            "flow_source": None,
            "flow_confidence": 0,
            "patient_zero": None,
            "inferred_dependencies": [],
            "reasoning_chain": [],
            "suggested_promql_queries": [],
            "time_series_data": {},
            "fix_data": None,
            "closure_state": None,
            "evidence_pins": session.get("evidence_pins", []),
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

    diff_analysis = []
    suggested_fix_areas = []
    if state.code_analysis:
        diff_analysis = [da.model_dump(mode="json") for da in state.code_analysis.diff_analysis]
        suggested_fix_areas = [fa.model_dump(mode="json") for fa in state.code_analysis.suggested_fix_areas]

    root_cause_location = None
    code_call_chain = []
    code_dependency_graph = {}
    code_shared_resource_conflicts = []
    code_cross_repo_findings = []
    code_mermaid_diagram = ""
    code_overall_confidence = 0
    if state.code_analysis:
        root_cause_location = state.code_analysis.root_cause_location.model_dump(mode="json")
        code_call_chain = state.code_analysis.call_chain
        code_dependency_graph = state.code_analysis.dependency_graph
        code_shared_resource_conflicts = state.code_analysis.shared_resource_conflicts
        code_cross_repo_findings = state.code_analysis.cross_repo_findings
        code_mermaid_diagram = state.code_analysis.mermaid_diagram
        code_overall_confidence = state.code_analysis.overall_confidence

    # Extract time series data with LTTB downsampling (max 150 points per metric)
    from src.utils.lttb import lttb_downsample, MAX_POINTS
    ts_data_raw = {}
    if state.metrics_analysis and state.metrics_analysis.time_series_data:
        for key, points in state.metrics_analysis.time_series_data.items():
            if len(points) > MAX_POINTS:
                ts_tuples = [(dp.timestamp.timestamp(), dp.value) for dp in points]
                downsampled = lttb_downsample(ts_tuples, MAX_POINTS)
                ts_data_raw[key] = [
                    {"timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "value": val}
                    for ts, val in downsampled
                ]
            else:
                ts_data_raw[key] = [dp.model_dump(mode="json") for dp in points]

    # Extract change analysis fields (handles both typed model and raw dict)
    ca = state.change_analysis
    if ca is not None and isinstance(ca, BaseModel):
        change_correlations = _dump_list(ca.change_correlations)
        change_summary = ca.summary
        change_high_priority_files = _dump_list(ca.high_priority_files)
    elif ca is not None and isinstance(ca, dict):
        change_correlations = ca.get("change_correlations", [])
        change_summary = ca.get("summary")
        change_high_priority_files = ca.get("high_priority_files", [])
    else:
        change_correlations = []
        change_summary = None
        change_high_priority_files = []

    return {
        "session_id": session_id,
        "incident_id": state.incident_id,
        "target_service": session["service_name"],
        "findings": [f.model_dump(mode="json") for f in state.all_findings],
        "negative_findings": [nf.model_dump(mode="json") for nf in state.all_negative_findings],
        "critic_verdicts": [cv.model_dump(mode="json") for cv in state.critic_verdicts],
        "error_patterns": [ep.model_dump(mode="json") for ep in error_patterns],
        "metric_anomalies": [ma.model_dump(mode="json") for ma in metric_anomalies],
        "correlated_signals": [cs.model_dump(mode="json") for cs in (state.metrics_analysis.correlated_signals if state.metrics_analysis else [])],
        "event_markers": [em.model_dump(mode="json") for em in (state.metrics_analysis.event_markers if state.metrics_analysis else [])],
        "pod_statuses": [ps.model_dump(mode="json") for ps in pod_statuses],
        "k8s_events": [ke.model_dump(mode="json") for ke in k8s_events],
        "trace_spans": [ts.model_dump(mode="json") for ts in trace_spans],
        "impacted_files": [ci.model_dump(mode="json") for ci in impacted_files],
        "diff_analysis": diff_analysis,
        "suggested_fix_areas": suggested_fix_areas,
        "root_cause_location": root_cause_location,
        "code_call_chain": code_call_chain,
        "code_dependency_graph": code_dependency_graph,
        "code_shared_resource_conflicts": code_shared_resource_conflicts,
        "code_cross_repo_findings": _dump_list(code_cross_repo_findings),
        "code_mermaid_diagram": code_mermaid_diagram,
        "code_overall_confidence": code_overall_confidence,
        "change_correlations": change_correlations,
        "change_summary": change_summary,
        "change_high_priority_files": change_high_priority_files,
        "blast_radius": state.blast_radius_result.model_dump(mode="json") if state.blast_radius_result else None,
        "severity_recommendation": state.severity_result.model_dump(mode="json") if state.severity_result else None,
        "past_incidents": _dump_list(state.past_incidents),
        "service_flow": _dump_list(state.service_flow),
        "flow_source": state.flow_source,
        "flow_confidence": state.flow_confidence,
        "patient_zero": _dump(state.patient_zero),
        "inferred_dependencies": _dump_list(state.inferred_dependencies),
        "reasoning_chain": _dump_list(state.reasoning_chain),
        "suggested_promql_queries": _dump_list(state.suggested_promql_queries),
        "time_series_data": ts_data_raw,
        "fix_data": state.fix_result.model_dump(mode="json") if state.fix_result else None,
        "closure_state": state.closure_state.model_dump(mode="json") if state.closure_state else None,
        "campaign": _dump_campaign(state.campaign) if state.campaign else None,
        # Manual evidence pins from live investigation steering (user_chat / quick_action)
        "evidence_pins": session.get("evidence_pins", []),
    }


class PromQLRequest(BaseModel):
    query: str
    start: str
    end: str
    step: str = "60s"


@router_v4.post("/promql/query")
async def proxy_promql_query(request: PromQLRequest):
    """Proxy a PromQL range query to Prometheus for the frontend Run button."""
    import httpx

    prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    url = f"{prometheus_url}/api/v1/query_range"
    params = {
        "query": request.query,
        "start": request.start,
        "end": request.end,
        "step": request.step,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "success":
            return {"data_points": [], "current_value": 0, "error": data.get("error", "Unknown Prometheus error")}

        results = data.get("data", {}).get("result", [])
        if not results:
            return {"data_points": [], "current_value": 0, "error": "No data returned"}

        # Take first result series, apply LTTB downsampling (max 150 points)
        from src.utils.lttb import lttb_downsample, MAX_POINTS as LTTB_MAX
        values = results[0].get("values", [])
        if len(values) > LTTB_MAX:
            ts_tuples = [(float(v[0]), float(v[1])) for v in values]
            downsampled = lttb_downsample(ts_tuples, LTTB_MAX)
        else:
            downsampled = [(float(v[0]), float(v[1])) for v in values]
        data_points = [
            {"timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "value": val}
            for ts, val in downsampled
        ]
        current_value = float(downsampled[-1][1]) if downsampled else 0

        return {"data_points": data_points, "current_value": current_value}
    except httpx.HTTPStatusError as e:
        logger.warning("Prometheus query failed: %s", e)
        return {"data_points": [], "current_value": 0, "error": f"Prometheus returned {e.response.status_code}"}
    except Exception as e:
        logger.warning("PromQL proxy error: %s", e)
        return {"data_points": [], "current_value": 0, "error": str(e)}


# ── Resource API (Surgical Telescope) ─────────────────────────────────


@router_v4.get("/session/{session_id}/resource/{namespace}/{kind}/{name}")
async def get_resource_details(session_id: str, namespace: str, kind: str, name: str):
    """Fetch K8s resource YAML + events for the Surgical Telescope drawer."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from src.tools.tool_executor import ToolExecutor
    config = session.get("connection_config", {})
    executor = ToolExecutor(connection_config=config)

    loop = asyncio.get_event_loop()

    yaml_result, events = await asyncio.gather(
        loop.run_in_executor(None, executor.get_resource_yaml, kind, name, namespace),
        loop.run_in_executor(None, executor.get_resource_events, kind, name, namespace),
    )

    return {
        "yaml": yaml_result.get("yaml"),
        "events": events,
        "error": yaml_result.get("error"),
    }


@router_v4.get("/session/{session_id}/resource/{namespace}/{kind}/{name}/logs")
async def get_resource_logs(
    session_id: str,
    namespace: str,
    kind: str,
    name: str,
    tail_lines: int = 500,
    container: Optional[str] = None,
):
    """Fetch pod logs for the Surgical Telescope LOGS tab."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if kind.lower() != "pod":
        raise HTTPException(status_code=400, detail="Logs are only available for pods")

    # Clamp tail_lines on the route level as well
    tail_lines = max(1, min(tail_lines, 5000))

    from src.tools.tool_executor import ToolExecutor
    config = session.get("connection_config", {})
    executor = ToolExecutor(connection_config=config)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: executor.get_pod_logs(name, namespace, tail_lines=tail_lines, container=container),
    )

    return {
        "logs": result.get("logs"),
        "error": result.get("error"),
    }


# ── Attestation Gate ──────────────────────────────────────────────────


class AttestationDecision(BaseModel):
    gate_type: str
    decision: str
    decided_by: str


@router_v4.post("/session/{session_id}/attestation")
async def submit_attestation(session_id: str, request: AttestationDecision):
    """Submit attestation decision — gates fix generation."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    supervisor = supervisors.get(session_id)
    if not supervisor:
        raise HTTPException(status_code=400, detail="Session not ready")

    response_text = supervisor.acknowledge_attestation(request.decision)
    return {"status": "recorded", "response": response_text}


# ── Fix Pipeline Endpoints ────────────────────────────────────────────


@router_v4.post("/session/{session_id}/fix/generate")
async def generate_fix(session_id: str, request: FixRequest, background_tasks: BackgroundTasks):
    """Start fix generation for a completed diagnosis."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    supervisor = supervisors.get(session_id)
    emitter = session.get("emitter")

    if not state or not supervisor or not emitter:
        raise HTTPException(status_code=400, detail="Session not ready")

    from src.models.schemas import DiagnosticPhase, FixStatus, FixResult
    if state.phase != DiagnosticPhase.DIAGNOSIS_COMPLETE and state.phase != DiagnosticPhase.FIX_IN_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail=f"Fix generation requires DIAGNOSIS_COMPLETE phase, current: {state.phase.value}",
        )

    # Guard: require attestation before fix generation
    if not supervisor._attestation_acknowledged:
        raise HTTPException(
            status_code=403,
            detail="Attestation required — approve diagnosis findings before generating a fix",
        )

    # Guard against parallel fix generation — block all active/in-flight states
    _active_statuses = (
        FixStatus.GENERATING, FixStatus.VERIFICATION_IN_PROGRESS,
        FixStatus.AWAITING_REVIEW, FixStatus.VERIFIED, FixStatus.PR_CREATING,
        FixStatus.HUMAN_FEEDBACK,
    )
    if state.fix_result and state.fix_result.fix_status in _active_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Fix generation already in progress (status: {state.fix_result.fix_status.value})",
        )

    # Set GENERATING immediately in the route handler to close TOCTOU gap
    # before the background task starts. start_fix_generation will reset this.
    state.fix_result = FixResult(fix_status=FixStatus.GENERATING)

    background_tasks.add_task(
        supervisor.start_fix_generation, state, emitter, request.guidance,
    )

    return {"status": "started"}


@router_v4.get("/session/{session_id}/fix/status", response_model=FixStatusResponse)
async def get_fix_status(session_id: str):
    """Get current fix generation status."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    if not state or not state.fix_result:
        return FixStatusResponse(fix_status="not_started")

    fr = state.fix_result
    return FixStatusResponse(
        fix_status=fr.fix_status.value if hasattr(fr.fix_status, 'value') else str(fr.fix_status),
        target_file=fr.target_file,
        diff=fr.diff,
        fix_explanation=fr.fix_explanation,
        fixed_files=[
            FixStatusFileEntry(file_path=ff.file_path, diff=ff.diff)
            for ff in (fr.fixed_files or [])
        ],
        verification_result=_dump(fr.verification_result),
        pr_url=fr.pr_url,
        pr_number=fr.pr_number,
        attempt_count=fr.attempt_count,
    )


@router_v4.post("/session/{session_id}/fix/decide")
async def fix_decide(session_id: str, request: FixDecisionRequest):
    """Submit a fix decision (approve/reject/feedback)."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    supervisor = supervisors.get(session_id)
    state = session.get("state")

    if not supervisor or not state:
        raise HTTPException(status_code=400, detail="Session not ready")

    if not request.decision or not request.decision.strip():
        raise HTTPException(status_code=400, detail="Decision cannot be empty")

    # Verify fix is actually awaiting review
    from src.models.schemas import FixStatus
    if not state.fix_result or state.fix_result.fix_status != FixStatus.AWAITING_REVIEW:
        current = state.fix_result.fix_status.value if state.fix_result else "not_started"
        raise HTTPException(
            status_code=400,
            detail=f"No fix awaiting review (current status: {current})",
        )

    response_text = await supervisor.handle_user_message(request.decision, state)
    return {"status": "ok", "response": response_text}


@router_v4.get("/session/{session_id}/events")
async def get_events(session_id: str):
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    emitter = session.get("emitter")
    if not emitter:
        return {"events": []}

    return {"events": [e.model_dump(mode="json") for e in emitter.get_all_events()]}


# ── Campaign (Multi-Repo) Endpoints ──────────────────────────────────


@router_v4.get("/session/{session_id}/campaign/status", response_model=CampaignStatusResponse)
async def get_campaign_status(session_id: str):
    """Get campaign status for multi-repo fix orchestration."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    if not state or not state.campaign:
        raise HTTPException(status_code=404, detail="No active campaign")

    campaign = state.campaign
    repos = []
    for repo_url, repo_fix in campaign.repos.items():
        repos.append(CampaignRepoStatusResponse(
            repo_url=repo_url,
            service_name=repo_fix.service_name,
            status=repo_fix.status.value if hasattr(repo_fix.status, 'value') else str(repo_fix.status),
            causal_role=repo_fix.causal_role,
            diff=repo_fix.diff,
            fix_explanation=repo_fix.fix_explanation,
            fixed_files=[
                FixStatusFileEntry(file_path=f.get("file_path", ""), diff=f.get("diff", ""))
                for f in repo_fix.fixed_files
            ],
            pr_url=repo_fix.pr_url,
            pr_number=repo_fix.pr_number,
            error_message=repo_fix.error_message,
        ))

    return CampaignStatusResponse(
        campaign_id=campaign.campaign_id,
        overall_status=campaign.overall_status,
        approved_count=campaign.approved_count,
        total_count=campaign.total_count,
        repos=repos,
    )


@router_v4.post("/session/{session_id}/campaign/generate")
async def start_campaign_generation(session_id: str, background_tasks: BackgroundTasks):
    """Start multi-repo campaign fix generation."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    supervisor = supervisors.get(session_id)
    emitter = session.get("emitter")

    if not state or not supervisor or not emitter:
        raise HTTPException(status_code=400, detail="Session not ready")

    from src.models.schemas import DiagnosticPhase
    if state.phase not in (DiagnosticPhase.DIAGNOSIS_COMPLETE, DiagnosticPhase.FIX_IN_PROGRESS):
        raise HTTPException(
            status_code=400,
            detail=f"Campaign requires DIAGNOSIS_COMPLETE phase, current: {state.phase.value}",
        )

    if not supervisor._attestation_acknowledged:
        raise HTTPException(
            status_code=403,
            detail="Attestation required before campaign generation",
        )

    background_tasks.add_task(supervisor.start_campaign_fix_generation, state, emitter)
    return {"status": "started"}


@router_v4.post("/session/{session_id}/campaign/{repo_url:path}/decide")
async def campaign_repo_decide(session_id: str, repo_url: str, request: CampaignRepoDecisionRequest):
    """Per-repo approve/reject/revoke decision within a campaign."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    supervisor = supervisors.get(session_id)
    if not state or not supervisor or not state.campaign:
        raise HTTPException(status_code=400, detail="No active campaign")

    # URL decode the repo_url path param
    import urllib.parse
    decoded_repo_url = urllib.parse.unquote(repo_url)

    if decoded_repo_url not in state.campaign.repos:
        raise HTTPException(status_code=404, detail=f"Repo not in campaign: {decoded_repo_url}")

    orchestrator = getattr(supervisor, '_campaign_orchestrator', None)
    if not orchestrator:
        raise HTTPException(status_code=400, detail="Campaign orchestrator not initialized")

    if request.decision == "approve":
        await orchestrator.approve_repo(state.campaign, decoded_repo_url, state)
    elif request.decision == "reject":
        await orchestrator.reject_repo(state.campaign, decoded_repo_url)
    elif request.decision == "revoke":
        await orchestrator.revoke_repo(state.campaign, decoded_repo_url)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {request.decision}")

    return {"status": "ok", "repo_status": state.campaign.repos[decoded_repo_url].status.value}


@router_v4.get("/session/{session_id}/campaign/{repo_url:path}/telescope")
async def campaign_telescope(session_id: str, repo_url: str):
    """Get full diff + file contents for Surgical Telescope overlay."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    if not state or not state.campaign:
        raise HTTPException(status_code=400, detail="No active campaign")

    import urllib.parse
    decoded_repo_url = urllib.parse.unquote(repo_url)
    repo_fix = state.campaign.repos.get(decoded_repo_url)
    if not repo_fix:
        raise HTTPException(status_code=404, detail="Repo not in campaign")

    files = []
    for f in repo_fix.fixed_files:
        files.append({
            "file_path": f.get("file_path", ""),
            "original_code": f.get("original_code", ""),
            "fixed_code": f.get("fixed_code", ""),
            "diff": f.get("diff", ""),
        })

    return {
        "repo_url": decoded_repo_url,
        "service_name": repo_fix.service_name,
        "files": files,
    }


@router_v4.post("/session/{session_id}/campaign/execute", response_model=CampaignExecuteResponse)
async def execute_campaign(session_id: str):
    """Master Gate: coordinated PR creation/merge for all approved repos."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    supervisor = supervisors.get(session_id)
    if not state or not supervisor or not state.campaign:
        raise HTTPException(status_code=400, detail="No active campaign")

    campaign = state.campaign
    if campaign.approved_count < campaign.total_count:
        raise HTTPException(
            status_code=400,
            detail=f"Not all repos approved ({campaign.approved_count}/{campaign.total_count})",
        )

    orchestrator = getattr(supervisor, '_campaign_orchestrator', None)
    if not orchestrator:
        raise HTTPException(status_code=400, detail="Campaign orchestrator not initialized")

    result = await orchestrator.execute_campaign(campaign, state)
    return CampaignExecuteResponse(**result)


# ── Live Investigation Steering Endpoints ─────────────────────────────


async def _run_critic_delta(session_id: str, pin_id: str) -> None:
    """Background task: delta-validate a new evidence pin via the CriticAgent."""
    try:
        lock = session_locks.get(session_id)
        if lock is None:
            logger.warning("Critic delta: session lock missing (session expired?)", extra={"session_id": session_id, "pin_id": pin_id})
            return

        critic = CriticAgent()

        # Snapshot evidence_pins under lock to avoid reading during concurrent mutation
        async with lock:
            state = sessions.get(session_id)
            if not state or "evidence_pins" not in state:
                logger.warning("Critic delta: session or pins missing", extra={"session_id": session_id, "pin_id": pin_id})
                return
            raw_pins = list(state["evidence_pins"])
            causal_chains = state.get("causal_chains", [])

        # Find the new pin and reconstruct EvidencePin objects
        new_pin_data = None
        existing_pins = []
        for rp in raw_pins:
            if rp.get("id") == pin_id:
                new_pin_data = rp
            else:
                try:
                    existing_pins.append(EvidencePin(**rp))
                except Exception as exc:
                    logger.debug("Skipping malformed pin during critic delta", extra={
                        "pin_id": rp.get("id", "unknown"), "error": str(exc),
                    })

        if not new_pin_data:
            logger.warning("Critic delta: pin not found in session", extra={"session_id": session_id, "pin_id": pin_id})
            return

        new_pin = EvidencePin(**new_pin_data)

        # Run delta validation (slow LLM call — outside lock)
        result = await critic.validate_delta(new_pin, existing_pins, causal_chains=causal_chains)

        # B6: Validate causal_role from critic before storing
        causal_role = result["causal_role"]
        if causal_role not in _VALID_CAUSAL_ROLES:
            causal_role = "informational"

        # Update pin in session state under lock
        async with lock:
            current_state = sessions.get(session_id)
            if current_state and "evidence_pins" in current_state:
                for pin_data in current_state["evidence_pins"]:
                    if pin_data.get("id") == pin_id:
                        pin_data["validation_status"] = result["validation_status"]
                        pin_data["causal_role"] = causal_role
                        break

        # Emit WebSocket event for the update
        try:
            await manager.send_message(session_id, {
                "type": "task_event",
                "data": {
                    "session_id": session_id,
                    "agent_name": "critic",
                    "event_type": "evidence_pin_updated",
                    "message": f"Pin {pin_id} delta-validated: {result['validation_status']}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "details": {
                        "pin_id": pin_id,
                        "validation_status": result["validation_status"],
                        "causal_role": causal_role,
                        "confidence": result["confidence"],
                        "reasoning": result["reasoning"],
                        "contradictions": result["contradictions"],
                    },
                },
            })
        except Exception as e:
            logger.warning("WebSocket broadcast failed for critic delta", extra={"error": str(e)})

    except Exception as e:
        logger.error("Critic delta revalidation failed", extra={
            "session_id": session_id, "pin_id": pin_id, "error": str(e),
        })


@router_v4.post("/session/{session_id}/investigate")
async def investigate(session_id: str, request: InvestigateRequest):
    """Manual investigation: slash command, quick action, or natural language."""
    _validate_session_id(session_id)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    investigation_router = _get_investigation_router(session_id)
    response, pin = await investigation_router.route(request)

    if pin:
        # B6: Validate causal_role before storing
        _validate_causal_role(pin)

        # Merge pin into session state under lock
        lock = session_locks.get(session_id)
        if lock:
            async with lock:
                state = sessions[session_id]
                if "evidence_pins" not in state:
                    state["evidence_pins"] = []
                # B5: Skip duplicate pins (same source_tool + claim within 60s)
                if _is_duplicate_pin(state["evidence_pins"], pin):
                    logger.debug("Skipping duplicate pin", extra={
                        "source_tool": pin.source_tool, "claim": pin.claim,
                    })
                    return response.model_dump()
                state["evidence_pins"].append(pin.model_dump(mode="json"))

        # Emit WebSocket event
        try:
            await manager.send_message(session_id, {
                "type": "task_event",
                "data": {
                    "session_id": session_id,
                    "agent_name": "investigation_router",
                    "event_type": "evidence_pin_added",
                    "message": pin.claim,
                    "timestamp": pin.timestamp.isoformat(),
                    "details": {
                        "pin_id": pin.id,
                        "domain": pin.domain,
                        "severity": pin.severity,
                        "validation_status": pin.validation_status,
                        "evidence_type": pin.evidence_type,
                        "source_tool": pin.source_tool,
                        "raw_output": pin.raw_output,
                    },
                },
            })
        except Exception as e:
            logger.warning("WebSocket broadcast failed for evidence pin", extra={"error": str(e)})

        # Dispatch background critic delta revalidation
        task = asyncio.create_task(_run_critic_delta(session_id, pin.id))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        # B3: Track critic delta task for cancellation on session cleanup
        task_list = _critic_delta_tasks.setdefault(session_id, [])
        _critic_delta_tasks[session_id] = [t for t in task_list if not t.done()]
        _critic_delta_tasks[session_id].append(task)

    return response.model_dump()


@router_v4.get("/session/{session_id}/tools")
async def get_tools(session_id: str):
    """Return available investigation tools for this session."""
    _validate_session_id(session_id)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    enriched = []
    for tool in TOOL_REGISTRY:
        tool_copy = {**tool}
        enriched.append(tool_copy)

    return {"tools": enriched}
