import json
import os
import re
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ValidationError
from typing import Dict, Any, Literal, Optional

from src.api.models import (
    ChatRequest, ChatResponse, StartSessionRequest, StartSessionResponse, SessionSummary,
    FixRequest, FixStatusResponse, FixStatusFileEntry, FixDecisionRequest,
    CampaignStatusResponse, CampaignRepoStatusResponse, CampaignRepoDecisionRequest,
    CampaignExecuteResponse,
)
from src.agents.supervisor import SupervisorAgent
from src.agents.cluster.graph import build_cluster_diagnostic_graph
from src.agents.cluster.state import DiagnosticScope
from src.utils.event_emitter import EventEmitter
from src.utils.llm_client import AnthropicClient
from src.api.websocket import manager
from src.utils.logger import get_logger
from src.utils.llm_budget import get_budget_for_mode, adapt_budget
from src.utils.llm_telemetry import SessionTelemetryCollector
from src.tools.router_models import InvestigateRequest, InvestigateResponse
from src.tools.tool_registry import TOOL_REGISTRY
from src.agents.critic_agent import CriticAgent
from src.models.schemas import EvidencePin
from src.agents.cluster_client.k8s_client import KubernetesClient
from src.agents.cluster.prometheus_detector import detect_prometheus_endpoint
from src.agents.metrics_agent import PrometheusClient
from src.agents.log_agent import ElasticsearchClient
from src.utils.fix_job_queue import FixJobQueue
from src.integrations.cicd.base import DeliveryItem
from src.integrations.cicd.resolver import resolve_cicd_clients
from src.integrations.github_client import GitHubClient, GitHubClientError
from src.utils.attestation_log import AttestationLogger

logger = get_logger(__name__)

# C1: Per-session locks — in-memory fallback when Redis is unavailable
session_locks: Dict[str, asyncio.Lock] = {}


def _get_session_store():
    """Return the RedisSessionStore from app state, or None if unavailable."""
    try:
        from src.api.main import app
        return getattr(app.state, "session_store", None)
    except Exception:
        return None


def _get_attestation_logger():
    """Get AttestationLogger from app state."""
    try:
        from src.api.main import app
        redis_client = getattr(app.state, 'redis', None)
        if not redis_client:
            return None
        return AttestationLogger(redis_client)
    except Exception:
        return None


async def _persist_session(session_id: str, data: dict) -> None:
    """Persist serializable session fields to Redis (best-effort)."""
    store = _get_session_store()
    if store is None:
        return
    # Only persist JSON-safe scalar/dict/list fields
    _NON_SERIALIZABLE = {"emitter", "graph", "cluster_client", "connection_config", "supervisor"}
    safe = {}
    for k, v in data.items():
        if k in _NON_SERIALIZABLE:
            continue
        try:
            json.dumps(v)  # quick serialisability check
            safe[k] = v
        except (TypeError, ValueError):
            continue
    try:
        await store.save(session_id, safe)
    except Exception as e:
        logger.warning("Redis persist failed for session %s: %s", session_id, e)


async def _load_session(session_id: str) -> dict | None:
    """Load session from in-memory dict; fall back to Redis if missing."""
    data = sessions.get(session_id)
    if data is not None:
        return data
    store = _get_session_store()
    if store is None:
        return None
    try:
        return await store.load(session_id)
    except Exception:
        return None


async def _delete_session_redis(session_id: str) -> None:
    """Remove session from Redis (best-effort)."""
    store = _get_session_store()
    if store is None:
        return
    try:
        await store.delete(session_id)
    except Exception:
        pass


def _acquire_lock(session_id: str):
    """Return a Redis distributed lock, falling back to an in-memory asyncio.Lock."""
    store = _get_session_store()
    if store is not None:
        return store.acquire_lock(session_id)
    return session_locks.setdefault(session_id, asyncio.Lock())

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


async def _get_or_reconstruct_orchestrator(session_id: str, supervisor: "SupervisorAgent"):
    """Return the campaign orchestrator, reconstructing from Redis if lost (e.g. after restart)."""
    orchestrator = getattr(supervisor, '_campaign_orchestrator', None)
    if orchestrator:
        return orchestrator

    # Orchestrator not in memory — try to reconstruct from persisted campaign data
    session_store = _get_session_store()
    if not session_store:
        return None

    campaign_data = await session_store.load_campaign(session_id)
    if not campaign_data:
        return None

    # Campaign data exists in Redis — reconstruct a fresh orchestrator
    from src.agents.agent3.campaign_orchestrator import CampaignOrchestrator
    orchestrator = CampaignOrchestrator(
        llm_client=supervisor.llm_client,
        event_emitter=supervisor._event_emitter or EventEmitter(manager),
        connection_config=supervisor._connection_config,
    )
    supervisor._campaign_orchestrator = orchestrator
    logger.info("Reconstructed campaign orchestrator from Redis", extra={"session_id": session_id})
    return orchestrator


def _link_sessions(session_a: str, session_b: str):
    """Bidirectionally link two sessions."""
    for src, dst in [(session_a, session_b), (session_b, session_a)]:
        sess = sessions.get(src)
        if sess:
            related = sess.setdefault("related_sessions", [])
            if dst not in related:
                related.append(dst)


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


def start_cleanup_task():
    """Launch background loop that evicts stale in-memory sessions every 5 minutes."""
    asyncio.ensure_future(_session_cleanup_loop())
    logger.info("Session cleanup loop started (TTL=%dh)", SESSION_TTL_HOURS)


async def _session_cleanup_loop():
    while True:
        await asyncio.sleep(300)
        now = datetime.now(timezone.utc)
        stale_ids = []
        for sid, sess in sessions.items():
            created = sess.get("created_at")
            if created:
                try:
                    age = (now - datetime.fromisoformat(created)).total_seconds()
                    if age > SESSION_TTL_HOURS * 3600:
                        stale_ids.append(sid)
                except (ValueError, TypeError):
                    pass
        for sid in stale_ids:
            sessions.pop(sid, None)
            session_locks.pop(sid, None)
            _investigation_routers.pop(sid, None)
            supervisors.pop(sid, None)
        if stale_ids:
            logger.info("Cleaned up %d stale sessions", len(stale_ids))


def create_cluster_client(connection_config=None):
    """
    Create a cluster client from connection config.
    Returns (client, temp_kubeconfig_path_or_None).

    Resolution order:
    0. DEBUGDUCK_MODE=demo → MockClusterClient (skip real cluster)
    1. bearer token (cluster_url + cluster_token)
    2. kubeconfig content written to temp file
    3. KUBECONFIG env var or ~/.kube/config
    4. MockClusterClient fallback
    """
    import tempfile
    from pathlib import Path
    from src.agents.cluster_client.mock_client import MockClusterClient

    temp_path = None
    cluster_url = getattr(connection_config, "cluster_url", "") if connection_config else ""
    cluster_token = getattr(connection_config, "cluster_token", "") if connection_config else ""
    auth_method = getattr(connection_config, "auth_method", "token") if connection_config else "token"
    kubeconfig_content = getattr(connection_config, "kubeconfig_content", "") if connection_config else ""
    verify_ssl = getattr(connection_config, "verify_ssl", False) if connection_config else False

    # If no explicit credentials provided, use mock client directly
    has_explicit_creds = bool(cluster_url or cluster_token or kubeconfig_content)
    if not has_explicit_creds:
        logger.info("No explicit cluster credentials provided, using MockClusterClient")
        return MockClusterClient(platform="openshift"), None

    # 1. Bearer token
    if cluster_url or cluster_token:
        try:
            return KubernetesClient(
                api_url=cluster_url or None,
                token=cluster_token or None,
                verify_ssl=verify_ssl,
            ), None
        except Exception as e:
            logger.warning("Failed to create KubernetesClient with bearer token: %s", e)

    # 2. Kubeconfig content (temp file)
    if auth_method == "kubeconfig" and kubeconfig_content:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                f.write(kubeconfig_content)
                temp_path = f.name
            return KubernetesClient(kubeconfig_path=temp_path), temp_path
        except Exception as e:
            logger.warning("Failed to create KubernetesClient from kubeconfig content: %s", e)
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
                temp_path = None

    # 3. Mock fallback
    logger.info("No cluster credentials found, using MockClusterClient")
    return MockClusterClient(platform="openshift"), None


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

    from src.observability.store import get_store as _get_store
    emitter = EventEmitter(session_id=session_id, websocket_manager=manager, store=_get_store())

    # C1: Create per-session lock (in-memory fallback; Redis lock used when available)
    session_locks[session_id] = asyncio.Lock()

    capability = request.capability

    # ── Cluster Diagnostics capability ──
    if capability == "cluster_diagnostics":
        # Build connection config: prefer profile, fall back to ad-hoc fields
        if not connection_config and request.clusterUrl:
            try:
                from src.integrations.connection_config import ResolvedConnectionConfig
                connection_config = ResolvedConnectionConfig(
                    cluster_url=request.clusterUrl or "",
                    cluster_token=request.authToken or "",
                    auth_method=request.authMethod or "token",
                    kubeconfig_content=request.kubeconfig_content or "",
                    role=request.role or "",
                    verify_ssl=False,
                )
            except Exception as e:
                logger.warning("Could not build ad-hoc connection config: %s", e)

        # Always use MockClusterClient for cluster diagnostics (demo mode).
        # connection_config is still passed through for Prometheus/ELK resolution.
        from src.agents.cluster_client.mock_client import MockClusterClient
        cluster_client, kubeconfig_temp_path = MockClusterClient(platform="openshift"), None
        graph = build_cluster_diagnostic_graph()

        # Build diagnostic scope from request
        if request.scan_mode == "guard" and request.scope and request.scope.get("level") != "cluster":
            raise HTTPException(400, "Guard mode requires cluster-level scope")

        if request.scope:
            try:
                scope = DiagnosticScope(**request.scope)
            except ValidationError as e:
                raise HTTPException(422, detail=f"Invalid diagnostic scope: {e}")
        elif request.namespace:
            scope = DiagnosticScope(level="namespace", namespaces=[request.namespace])
        else:
            scope = DiagnosticScope()

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
            "scan_mode": request.scan_mode,
            "diagnostic_scope": scope.model_dump(mode="json"),
            "kubeconfig_temp_path": kubeconfig_temp_path,
            "elk_index": request.elkIndex or "",
        }

        await _persist_session(session_id, sessions[session_id])

        background_tasks.add_task(
            run_cluster_diagnosis, session_id, graph, cluster_client, emitter, request.scan_mode,
            connection_config=connection_config
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

    # ── Network Troubleshooting capability ──
    if capability == "network_troubleshooting":
        sessions[session_id] = {
            "service_name": request.serviceName or "Network Troubleshooting",
            "incident_id": incident_id,
            "phase": "initial",
            "confidence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "emitter": emitter,
            "state": None,
            "profile_id": profile_id,
            "capability": "network_troubleshooting",
            "chat_history": [],
        }
        await _persist_session(session_id, sessions[session_id])
        return StartSessionResponse(
            session_id=session_id,
            incident_id=incident_id,
            status="started",
            message="Network troubleshooting session created — use /api/v4/network/diagnose for diagnosis",
            service_name=request.serviceName or "Network Troubleshooting",
            created_at=sessions[session_id]["created_at"],
        )

    # ── Database Diagnostics capability (delegated to db_session_endpoints) ──
    if capability == "database_diagnostics":
        from src.api.db_session_endpoints import create_db_session
        return await create_db_session(session_id, request, incident_id, emitter, background_tasks)

    # ── Pipeline Troubleshooting capability ──
    if capability == "troubleshoot_pipeline":
        sessions[session_id] = {
            "service_name": request.serviceName or "Pipeline Troubleshooting",
            "incident_id": incident_id,
            "phase": "initial",
            "confidence": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "emitter": emitter,
            "state": None,
            "profile_id": profile_id,
            "capability": "troubleshoot_pipeline",
            "chat_history": [],
        }
        await _persist_session(session_id, sessions[session_id])
        logger.info("Pipeline session created", extra={"session_id": session_id, "action": "session_created", "extra": "troubleshoot_pipeline"})
        return StartSessionResponse(
            session_id=session_id,
            incident_id=incident_id,
            status="started",
            message="Pipeline troubleshooting session created — use /api/v4/cicd/stream for live analysis",
            service_name=request.serviceName or "Pipeline Troubleshooting",
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
    await _persist_session(session_id, sessions[session_id])
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
        "elk_index": request.elkIndex or "",
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


async def get_or_create_cluster_client(session_id: str):
    """Return cached cluster client from session, or create a new one from stored config."""
    session = sessions.get(session_id, {})
    client = session.get("cluster_client")
    if client is not None:
        return client
    connection_config = session.get("connection_config")
    if connection_config:
        new_client, temp_path = create_cluster_client(connection_config)
        sessions[session_id]["cluster_client"] = new_client
        if temp_path:
            sessions[session_id]["kubeconfig_temp_path"] = temp_path
        return new_client
    return None


async def run_cluster_diagnosis(session_id, graph, cluster_client, emitter, scan_mode="diagnostic", connection_config=None):
    """Background task: run LangGraph cluster diagnostic."""
    from src.observability.store import get_store as _obs_store

    try:
        _diagnosis_tasks[session_id] = asyncio.current_task()
    except RuntimeError:
        pass

    lock = _acquire_lock(session_id)
    try:
        sessions[session_id]["cluster_client"] = cluster_client
        scope_data = sessions[session_id].get("diagnostic_scope", {})

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
            "scan_mode": scan_mode,
            "cluster_url": getattr(connection_config, "cluster_url", "") if connection_config else "",
            "cluster_type": getattr(connection_config, "cluster_type", "") if connection_config else "",
            "cluster_role": getattr(connection_config, "role", "") if connection_config else "",
            "topology_graph": {},
            "topology_freshness": {},
            "issue_clusters": [],
            "causal_search_space": {},
            "guard_scan_result": None,
            "previous_scan": None,
            "diagnostic_scope": scope_data,
            "scoped_topology_graph": None,
            "dispatch_domains": scope_data.get("domains", ["ctrl_plane", "node", "network", "storage", "rbac"]),
            "scope_coverage": 1.0,
            "proactive_findings": [],
            # Pre-flight RBAC check result
            "rbac_check": {"status": "pass", "granted": [], "denied": [], "warnings": []},
            "rbac_skipped": [],
            # Critic validation result
            "critic_result": {},
            # Diagnostic intelligence pipeline
            "normalized_signals": [],
            "pattern_matches": [],
            "temporal_analysis": {},
            "diagnostic_graph": {},
            "diagnostic_issues": [],
            "ranked_hypotheses": [],
            "hypotheses_by_issue": {},
            "hypothesis_selection": {},
            "_trace": [],
        }

        # Pre-flight: detect platform
        await emitter.emit("cluster_supervisor", "started", "Detecting cluster platform...", {"phase": "pre_flight"})
        platform_info = await cluster_client.detect_platform()
        initial_state["platform"] = platform_info.get("platform", "kubernetes")
        initial_state["platform_version"] = platform_info.get("version", "")
        await emitter.emit("cluster_supervisor", "progress", f"Detected {initial_state['platform']} {initial_state['platform_version']}", {"phase": "pre_flight"})

        ns_result = await cluster_client.list_namespaces()
        initial_state["namespaces"] = ns_result.data

        # Create LLM budget and telemetry collector
        budget = get_budget_for_mode(scan_mode)
        telemetry = SessionTelemetryCollector(session_id, scan_mode)

        # Adapt budget based on cluster size
        nodes_result = await cluster_client.list_nodes()
        cluster_size = {
            "nodes": len(nodes_result.data),
            "namespaces": len(ns_result.data),
        }
        budget = adapt_budget(budget, cluster_size)
        await emitter.emit("cluster_supervisor", "progress", f"Cluster: {cluster_size['nodes']} nodes, {cluster_size['namespaces']} namespaces", {"phase": "pre_flight"})

        # Resolve Prometheus URL: profile first, then auto-detect from cluster
        prometheus_url = getattr(connection_config, "prometheus_url", "") if connection_config else ""
        if not prometheus_url:
            prometheus_url = await detect_prometheus_endpoint(cluster_client, initial_state["platform"])
            if prometheus_url:
                logger.info("Auto-detected Prometheus at %s", prometheus_url)
                sessions[session_id]["prometheus_url"] = prometheus_url

        await emitter.emit("cluster_supervisor", "phase_change", "Pre-flight complete — dispatching domain agents", {"phase": "collecting_context"})

        # Resolve ELK index and URL
        elk_index = sessions.get(session_id, {}).get("elk_index", "")
        elk_url = getattr(connection_config, "elasticsearch_url", "") if connection_config else ""

        if elk_index and not elk_url:
            # Try global integrations store
            try:
                from src.integrations.profile_store import ProfileStore
                store = ProfileStore()
                integrations = getattr(store, "list_global_integrations", lambda: [])()
                elk_integration = next(
                    (i for i in integrations if getattr(i, "service_type", "") in ("elk", "elasticsearch")),
                    None
                )
                elk_url = getattr(elk_integration, "url", "") if elk_integration else ""
            except Exception as exc:
                logger.warning("Failed to resolve ELK URL from global integrations: %s", exc)

            if not elk_url:
                logger.info("ELK index provided but no ELK endpoint configured — skipping log analysis")
                elk_index = ""  # Clear index so elk_client is not created

        # Build prometheus_client and elk_client
        cluster_token = getattr(connection_config, "cluster_token", "") if connection_config else ""
        cluster_verify_ssl = getattr(connection_config, "verify_ssl", False) if connection_config else False

        prometheus_client = None
        if prometheus_url:
            try:
                prom_token = getattr(connection_config, "prometheus_credentials", "") if connection_config else ""
                prometheus_client = PrometheusClient(
                    url=prometheus_url,
                    token=prom_token,
                    verify_ssl=cluster_verify_ssl,
                )
            except Exception as exc:
                logger.warning("Failed to create PrometheusClient: %s", exc)

        elk_client = None
        if elk_index and elk_url:
            try:
                elk_auth = getattr(connection_config, "elasticsearch_auth_method", "none") if connection_config else "none"
                elk_creds = getattr(connection_config, "elasticsearch_credentials", "") if connection_config else ""
                elk_client = ElasticsearchClient(
                    url=elk_url,
                    auth_method=elk_auth,
                    credentials=elk_creds,
                    verify_ssl=cluster_verify_ssl,
                )
            except Exception as exc:
                logger.warning("Failed to create ElasticsearchClient: %s", exc)

        config = {
            "configurable": {
                "cluster_client": cluster_client,
                "prometheus_client": prometheus_client,
                "elk_client": elk_client,
                "elk_index": elk_index,
                "emitter": emitter,
                "budget": budget,
                "telemetry": telemetry,
                "store": _obs_store(),
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
                sessions[session_id]["state"]["llm_summary"] = telemetry.get_summary(budget.budget_used_pct()).to_dict()
                await _persist_session(session_id, sessions[session_id])

        await emitter.emit("cluster_supervisor", "phase_change", "Cluster diagnostics complete", {"phase": "diagnosis_complete"})

    except asyncio.TimeoutError:
        logger.error("Cluster diagnosis timed out", extra={"session_id": session_id})
        # Build partial report from whatever state was checkpointed before timeout
        from src.agents.cluster.graph import _build_partial_health_report
        partial_state = sessions.get(session_id, {}).get("state") or {}
        if partial_state.get("domain_reports"):
            partial_report = _build_partial_health_report(partial_state)
            async with lock:
                sessions[session_id]["state"]["health_report"] = partial_report
                sessions[session_id]["state"]["phase"] = "partial_timeout"
        await emitter.emit(
            "cluster_supervisor", "warning",
            "Diagnosis timed out — partial results available",
            {"phase": "partial_timeout",
             "data_completeness": partial_state.get("data_completeness", 0.0)},
        )
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
        # Clean up temp kubeconfig file if present (safety net — DELETE endpoint also cleans up)
        temp_path = sessions.get(session_id, {}).get("kubeconfig_temp_path")
        if temp_path:
            from pathlib import Path
            Path(temp_path).unlink(missing_ok=True)
            sessions.get(session_id, {}).pop("kubeconfig_temp_path", None)


async def run_diagnosis(session_id: str, supervisor: SupervisorAgent, initial_input: dict, emitter: EventEmitter):
    # M10: Store current task for cancellation on cleanup
    try:
        _diagnosis_tasks[session_id] = asyncio.current_task()  # type: ignore[assignment]
    except RuntimeError:
        pass

    lock = _acquire_lock(session_id)
    try:
        state = await supervisor.run(
            initial_input, emitter,
            # Callback to expose state immediately after creation so the
            # findings endpoint can read partial results mid-investigation.
            on_state_created=lambda s: sessions[session_id].__setitem__("state", s),
        )
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



# run_db_diagnosis moved to src.api.db_session_endpoints


CLUSTER_CHAT_HISTORY_CAP = 20


def _build_chat_context(state: dict) -> str:
    """Extract clean, structured context from graph state for LLM chat."""
    parts = []

    # Health report summary
    health = state.get("health_report") or {}
    if health:
        parts.append(f"Overall Health: {health.get('overall_status', 'unknown')}")
        if health.get("critical_findings"):
            parts.append(f"Critical Findings: {len(health['critical_findings'])}")

    # Domain reports summary
    domain_reports = state.get("domain_reports") or []
    if domain_reports:
        parts.append(f"\nDomain Reports ({len(domain_reports)}):")
        for report in domain_reports:
            domain = report.get("domain", "unknown")
            anomalies = report.get("anomalies") or []
            confidence = report.get("confidence", 0)
            parts.append(f"  - {domain}: {len(anomalies)} anomalies, confidence={confidence}%")
            for a in anomalies[:3]:  # top 3
                parts.append(f"    * {a.get('description', '')[:100]}")

    # Proactive findings
    proactive = state.get("proactive_findings") or []
    if proactive:
        parts.append(f"\nProactive Findings ({len(proactive)}):")
        for f in proactive[:5]:
            parts.append(f"  - [{f.get('severity', '')}] {f.get('title', '')[:80]}")

    return "\n".join(parts) if parts else "No diagnostic data available."


async def _handle_cluster_chat(session: dict, message: str) -> str:
    """Handle chat for cluster diagnostics sessions using full cluster state as context."""
    state = session.get("state")
    if not state:
        return "Diagnostics are still starting. Please wait for initial results before asking questions."

    chat_history = session.setdefault("chat_history", [])

    # Build system prompt with cluster state context
    state_context = _build_chat_context(state)

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
        try:
            response_text = await supervisor.handle_user_message(request.message, state)
        except Exception:
            logger.exception("Chat handler failed for session %s", session_id)
            response_text = "Something went wrong processing your message. Please try again."
    else:
        response_text = "Analysis is still starting up. Please wait a moment."

    return ChatResponse(
        response=response_text,
        phase=session.get("phase", "initial"),
        confidence=session.get("confidence", 0),
    )


@router_v4.get("/session/{session_id}/chat-history")
async def get_chat_history(session_id: str):
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        session_store = _get_session_store()
        if session_store:
            persisted = await session_store.load(session_id)
            if persisted and "chat_history" in persisted:
                return {"messages": persisted["chat_history"]}
        return {"messages": []}
    return {"messages": session.get("chat_history", [])}


@router_v4.get("/sessions", response_model=list[SessionSummary])
async def list_sessions():
    seen_ids: set[str] = set()
    result = []

    def _build_summary(sid: str, data: dict) -> SessionSummary:
        findings_count = 0
        critical_count = 0
        state = data.get("state")
        if state:
            if isinstance(state, dict):
                findings = state.get("findings", [])
                findings_count = len(findings)
                critical_count = sum(1 for f in findings if f.get("severity") == "critical")
            elif hasattr(state, "all_findings"):
                findings_count = len(state.all_findings)
                critical_count = sum(1 for f in state.all_findings if getattr(f, "severity", "") == "critical")
        return SessionSummary(
            session_id=sid,
            service_name=data.get("service_name", "unknown"),
            incident_id=data.get("incident_id"),
            phase=data.get("phase", "unknown"),
            confidence=data.get("confidence", 0),
            created_at=data.get("created_at", ""),
            capability=data.get("capability"),
            investigation_mode=data.get("investigation_mode"),
            related_sessions=data.get("related_sessions", []),
            findings_count=findings_count,
            critical_count=critical_count,
        )

    # In-memory sessions (authoritative — they're live)
    for sid, data in sessions.items():
        seen_ids.add(sid)
        result.append(_build_summary(sid, data))

    # Merge Redis-persisted sessions not already in memory
    store = _get_session_store()
    if store:
        try:
            redis_ids = await store.list_session_ids()
            for sid in redis_ids:
                if sid in seen_ids:
                    continue
                persisted = await store.load(sid)
                if persisted:
                    seen_ids.add(sid)
                    result.append(_build_summary(sid, persisted))
        except Exception:
            pass  # Redis unavailable — return in-memory only

    result.sort(key=lambda s: s.created_at or "", reverse=True)
    return result


@router_v4.post("/session/{session_id}/cancel")
async def cancel_session(session_id: str):
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session["phase"] = "cancelled"
    session["_cancelled"] = True
    emitter = session.get("emitter")
    if emitter and hasattr(emitter, 'emit'):
        asyncio.create_task(emitter.emit("supervisor", "warning", "Investigation cancelled by user"))
    return {"status": "cancelled"}


class FeedbackRequest(BaseModel):
    outcome: str  # fix_worked | fix_failed | issue_recurred | wrong_diagnosis | not_applicable
    root_cause_category: Optional[str] = None
    fix_type: Optional[str] = None
    notes: Optional[str] = None


@router_v4.post("/session/{session_id}/feedback")
async def submit_feedback(session_id: str, body: FeedbackRequest):
    """Record whether a diagnosis/fix was accurate."""
    _validate_session_id(session_id)
    session = await _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from src.database.feedback_store import FeedbackStore
    store = FeedbackStore()
    row_id = store.record_feedback(
        session_id=session_id,
        service_name=session.get("service_name", "unknown"),
        outcome=body.outcome,
        root_cause_category=body.root_cause_category,
        fix_type=body.fix_type,
        notes=body.notes,
    )
    return {"status": "recorded", "feedback_id": row_id}


@router_v4.get("/service/{service_name}/feedback")
async def get_service_feedback(service_name: str, limit: int = 10):
    """Get historical diagnosis feedback for a service."""
    from src.database.feedback_store import FeedbackStore
    store = FeedbackStore()
    return store.get_service_feedback(service_name, limit=min(limit, 50))


@router_v4.delete("/session/{session_id}")
async def delete_session(session_id: str):
    _validate_session_id(session_id)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Cancel running diagnosis task
    task = _diagnosis_tasks.pop(session_id, None)
    if task and not task.done():
        task.cancel()
        logger.info("Cancelled diagnosis task for deleted session", extra={"session_id": session_id, "action": "diagnosis_cancelled"})

    # Cancel critic delta tasks
    critic_tasks = _critic_delta_tasks.pop(session_id, [])
    for ct in critic_tasks:
        if not ct.done():
            ct.cancel()

    # Remove investigation router
    _investigation_routers.pop(session_id, None)

    # Clean up cluster client and temp kubeconfig
    client = sessions[session_id].get("cluster_client")
    if client:
        try:
            await client.close()
        except Exception:
            pass
    temp_path = sessions[session_id].get("kubeconfig_temp_path")
    if temp_path:
        from pathlib import Path
        Path(temp_path).unlink(missing_ok=True)

    # Clear topology cache
    try:
        from src.agents.cluster.topology_resolver import clear_topology_cache
        clear_topology_cache(session_id)
    except Exception:
        pass

    # Disconnect SSE
    manager.disconnect(session_id)

    # Delete from diagnostic store
    try:
        from src.observability.store import get_store
        await get_store().delete_session(session_id)
    except Exception as e:
        logger.warning("Failed to delete session from store: %s", e)

    sessions.pop(session_id, None)
    session_locks.pop(session_id, None)
    await _delete_session_redis(session_id)
    return {"status": "deleted", "session_id": session_id}


@router_v4.get("/session/{session_id}/status")
async def get_session_status(session_id: str):
    _validate_session_id(session_id)
    session = await _load_session(session_id)
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
        "capability": session.get("capability"),
        "investigation_mode": session.get("investigation_mode"),
        "related_sessions": session.get("related_sessions", []),
    }

    # Load pending action (shared across all capabilities)
    session_store = _get_session_store()
    if session_store:
        pending = await session_store.load_pending_action(session_id)
        result["pending_action"] = pending.to_dict() if pending else None
    else:
        result["pending_action"] = None

    # Cluster sessions: state is a plain dict
    if session.get("capability") == "cluster_diagnostics":
        if state and isinstance(state, dict):
            result["findings_count"] = len(state.get("domain_reports", []))
            result["data_completeness"] = state.get("data_completeness", 0)
        return result

    # Database sessions: state is a plain dict
    if session.get("capability") == "database_diagnostics":
        if state and isinstance(state, dict):
            result["findings_count"] = len(state.get("findings", []))
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
    session = await _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Cluster diagnostics: return cluster-specific findings
    if session.get("capability") == "cluster_diagnostics":
        state = session.get("state", {})
        scan_mode = session.get("scan_mode", "diagnostic")

        # Common fields required by V4Findings
        common = {
            "session_id": session_id,
            "findings": [],
            "scan_mode": scan_mode,
            "issue_clusters": state.get("issue_clusters", []) if isinstance(state, dict) else [],
            "causal_search_space": state.get("causal_search_space") if isinstance(state, dict) else None,
            "topology_snapshot": state.get("topology_graph") if isinstance(state, dict) else None,
            "diagnostic_scope": state.get("diagnostic_scope") if isinstance(state, dict) else None,
            "scope_coverage": state.get("scope_coverage", 1.0) if isinstance(state, dict) else 1.0,
        }

        # Guard mode: return guard scan result
        if scan_mode == "guard" and isinstance(state, dict) and state.get("guard_scan_result"):
            return {
                **common,
                "guard_scan_result": state["guard_scan_result"],
            }

        # Diagnostic mode (existing behavior)
        if isinstance(state, dict) and state:
            health_report = state.get("health_report")
            return {
                **common,
                "platform": state.get("platform", ""),
                "platform_version": state.get("platform_version", ""),
                "platform_health": health_report.get("platform_health", "UNKNOWN") if health_report else "PENDING",
                "data_completeness": state.get("data_completeness", 0.0),
                "causal_chains": state.get("causal_chains", []),
                "uncorrelated_findings": state.get("uncorrelated_findings", []),
                "domain_reports": state.get("domain_reports", []),
                "blast_radius": health_report.get("blast_radius") if health_report else None,
                "remediation": health_report.get("remediation", {}) if health_report else {},
                "execution_metadata": health_report.get("execution_metadata", {}) if health_report else {},
                "diagnostic_issues": state.get("diagnostic_issues", []),
                "issue_lifecycle_summary": state.get("issue_lifecycle_summary", {}),
                "ranked_hypotheses": state.get("ranked_hypotheses", []),
                "critical_incidents": health_report.get("critical_incidents", []) if health_report else [],
                "other_findings": health_report.get("other_findings", []) if health_report else [],
                "symptom_map": health_report.get("symptom_map", {}) if health_report else {},
                "hypothesis_selection": health_report.get("hypothesis_selection") if health_report else None,
            }
        return {**common, "platform": "", "platform_version": "", "platform_health": "PENDING", "data_completeness": 0.0, "domain_reports": []}

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
            "causal_forest": [],
            "evidence_graph": None,
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

    response = {
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
        "causal_forest": [ct.model_dump(mode="json") for ct in state.causal_forest] if state.causal_forest else [],
        "evidence_graph": state.evidence_graph,
        "agent_statuses": state.agent_statuses,
    }

    if state.hypotheses:
        response["hypotheses"] = [
            {
                "hypothesis_id": h.hypothesis_id,
                "category": h.category,
                "status": h.status,
                "confidence": h.confidence,
                "evidence_for_count": len(h.evidence_for),
                "evidence_against_count": len(h.evidence_against),
                "downstream_effects": h.downstream_effects,
                "elimination_reason": h.elimination_reason,
                "elimination_phase": h.elimination_phase,
            }
            for h in state.hypotheses
        ]
    if state.hypothesis_result:
        response["hypothesis_result"] = {
            "status": state.hypothesis_result.status,
            "winner_id": state.hypothesis_result.winner.hypothesis_id if state.hypothesis_result.winner else None,
            "elimination_log": state.hypothesis_result.elimination_log,
            "recommendations": state.hypothesis_result.recommendations,
        }

    return response


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


class AttestationDecisionRequest(BaseModel):
    gate_type: str
    decision: str
    decided_by: str


@router_v4.post("/session/{session_id}/attestation")
async def submit_attestation(session_id: str, request: AttestationDecisionRequest, raw_request: Request):
    """Submit attestation decision — gates fix generation."""
    _validate_session_id(session_id)

    # ── Idempotency check ──────────────────────────────────────────
    idem_key = raw_request.headers.get("idempotency-key")
    session_store = _get_session_store()
    if idem_key and session_store:
        cached = await session_store.check_idempotency(idem_key)
        if cached:
            return {"status": "recorded", "response": cached}

    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    supervisor = supervisors.get(session_id)
    if not supervisor:
        raise HTTPException(status_code=400, detail="Session not ready")

    response_text = await supervisor.acknowledge_attestation(request.decision, session_id)

    # Resume pipeline in background if approved
    state = session.get("state")
    emitter = session.get("emitter")
    if state and emitter and request.decision == "approve":
        import asyncio
        asyncio.create_task(supervisor.resume_pipeline(session_id, state, emitter))

    # ── Cache idempotency result ───────────────────────────────────
    if idem_key and session_store:
        await session_store.save_idempotency(idem_key, response_text or "recorded")

    return {"status": "recorded", "response": response_text}


# ── Fix Pipeline Endpoints ────────────────────────────────────────────


@router_v4.post("/session/{session_id}/fix/generate")
async def generate_fix(session_id: str, request: FixRequest):
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

    from src.models.schemas import DiagnosticPhase
    if state.phase != DiagnosticPhase.DIAGNOSIS_COMPLETE and state.phase != DiagnosticPhase.FIX_IN_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail=f"Fix generation requires DIAGNOSIS_COMPLETE phase, current: {state.phase.value}",
        )

    try:
        job_id = await supervisor.start_fix_generation(state, emitter, request.guidance)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    return {"status": "queued", "job_id": job_id}


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
async def fix_decide(session_id: str, request: FixDecisionRequest, raw_request: Request):
    """Submit a fix decision (approve/reject/feedback)."""
    _validate_session_id(session_id)

    # ── Idempotency check ──────────────────────────────────────────
    idem_key = raw_request.headers.get("idempotency-key")
    session_store = _get_session_store()
    if idem_key and session_store:
        cached = await session_store.check_idempotency(idem_key)
        if cached:
            return {"status": "ok", "response": cached}

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

    try:
        response_text = await supervisor.handle_user_message(request.decision, state)
    except Exception:
        logger.exception("Fix decision handler failed for session %s", session_id)
        raise HTTPException(status_code=500, detail="Failed to process fix decision. Please try again.")

    # ── Cache idempotency result ───────────────────────────────────
    if idem_key and session_store:
        await session_store.save_idempotency(idem_key, response_text or "ok")

    return {"status": "ok", "response": response_text}


@router_v4.delete("/session/{session_id}/fix/cancel")
async def cancel_fix(session_id: str):
    """Cancel a running or queued fix generation job."""
    _validate_session_id(session_id)
    queue = FixJobQueue.get_instance()
    cancelled = queue.cancel_for_session(session_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="No active fix job for this session")
    return {"status": "cancelled"}


@router_v4.get("/session/{session_id}/dossier")
async def get_session_dossier(session_id: str):
    """Return the synthesizer's dossier and fix recommendations for a DB session."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    if not state or not isinstance(state, dict):
        return {"dossier": None, "fixes": []}

    dossier = state.get("dossier")
    fixes = state.get("fix_recommendations", [])

    return {"dossier": dossier, "fixes": fixes}


@router_v4.get("/session/{session_id}/cluster-dossier")
async def get_cluster_dossier(session_id: str):
    """Return a formatted cluster diagnostic dossier for export."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if session.get("capability") != "cluster_diagnostics":
        raise HTTPException(400, "Not a cluster diagnostics session")

    state = session.get("state", {})
    if not isinstance(state, dict):
        return {"dossier": None}

    health_report = state.get("health_report", {})
    if not health_report:
        return {"dossier": None}

    # Build structured dossier
    domain_reports = health_report.get("domain_reports", [])
    causal_chains = health_report.get("causal_chains", [])
    remediation = health_report.get("remediation", {})
    blast_radius = health_report.get("blast_radius", {})
    execution_metadata = health_report.get("execution_metadata", {})

    # Build domain findings sections
    domain_sections = []
    for report in domain_reports:
        domain_sections.append({
            "domain": report.get("domain", ""),
            "status": report.get("status", ""),
            "confidence": report.get("confidence", 0),
            "anomaly_count": len(report.get("anomalies", [])),
            "anomalies": report.get("anomalies", []),
            "ruled_out": report.get("ruled_out", []),
            "truncation_flags": report.get("truncation_flags", {}),
            "duration_ms": report.get("duration_ms", 0),
        })

    dossier = {
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": {
            "platform": health_report.get("platform", ""),
            "platform_version": health_report.get("platform_version", ""),
            "health_status": health_report.get("platform_health", "UNKNOWN"),
            "data_completeness": health_report.get("data_completeness", 0),
            "total_anomalies": sum(len(r.get("anomalies", [])) for r in domain_reports),
            "causal_chains_found": len(causal_chains),
            "scan_mode": health_report.get("scan_mode", "diagnostic"),
        },
        "domain_reports": domain_sections,
        "causal_analysis": {
            "chains": causal_chains,
            "uncorrelated_findings": health_report.get("uncorrelated_findings", []),
        },
        "blast_radius": blast_radius,
        "remediation": remediation,
        "issue_clusters": state.get("issue_clusters", []),
        "execution_metadata": execution_metadata,
    }

    return {"dossier": dossier}


@router_v4.get("/session/{session_id}/events")
async def get_session_events(
    session_id: str,
    after_sequence: int = 0,
):
    """Return session events. Use after_sequence for replay (returns events after that seq)."""
    _validate_session_id(session_id)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    from src.observability.store import get_store
    store = get_store()
    try:
        events = await store.get_events(session_id, after_sequence=after_sequence)
        return {"events": events}
    except Exception:
        # Fallback to in-memory events if store unavailable
        emitter = sessions[session_id].get("emitter")
        if emitter:
            all_events = emitter.get_all_events()
            event_dicts = [e.model_dump(mode="json") for e in all_events
                           if (e.sequence_number or 0) > after_sequence]
            return {"events": event_dicts}
        return {"events": []}


@router_v4.get("/session/{session_id}/llm-calls")
async def get_session_llm_calls(session_id: str):
    """Return LLM call metadata for a session. For debugging wrong causal chains."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    from src.observability.store import get_store
    calls = await get_store().get_llm_calls(session_id)
    return {"llm_calls": calls}


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

    orchestrator = await _get_or_reconstruct_orchestrator(session_id, supervisor)
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

    attestation_logger = _get_attestation_logger()
    if attestation_logger:
        await attestation_logger.log_decision(
            session_id=session_id,
            finding_id=f"campaign_repo:{decoded_repo_url}",
            decision=request.decision,
            decided_by="user",
            confidence=0.0,
            finding_summary=f"Campaign repo {request.decision}: {decoded_repo_url}",
        )

    # Persist campaign state to Redis after each repo decision
    session_store = _get_session_store()
    if session_store:
        campaign_dict = state.campaign.model_dump() if hasattr(state.campaign, 'model_dump') else state.campaign.__dict__
        await session_store.save_campaign(session_id, campaign_dict)

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
async def execute_campaign(session_id: str, raw_request: Request):
    """Master Gate: coordinated PR creation/merge for all approved repos."""
    _validate_session_id(session_id)

    # ── Idempotency check ──────────────────────────────────────────
    idem_key = raw_request.headers.get("idempotency-key")
    session_store_idem = _get_session_store()
    if idem_key and session_store_idem:
        cached = await session_store_idem.check_idempotency(idem_key)
        if cached:
            import json as _json
            try:
                return _json.loads(cached)
            except Exception:
                return {"status": "ok", "response": cached}

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

    # ── Campaign confirmation gate ──────────────────────────────────
    session_store = _get_session_store()
    if session_store:
        pending = await session_store.load_pending_action(session_id)
        if pending and pending.type == "campaign_execute_confirm":
            await session_store.clear_pending_action(session_id)
            # Confirmed — fall through to execute
        elif pending and pending.type != "campaign_execute_confirm":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot execute campaign — another action is pending: {pending.type}",
            )
        elif not pending:
            # First call — create confirmation gate, don't execute yet
            from src.models.pending_action import PendingAction
            repo_list = list(campaign.repos.keys()) if campaign.repos else []
            confirm_action = PendingAction(
                type="campaign_execute_confirm",
                blocking=True,
                actions=["confirm", "cancel"],
                expires_at=None,
                context={"repo_count": len(repo_list), "repos": repo_list},
                version=1,
            )
            await session_store.save_pending_action(session_id, confirm_action)
            return {"status": "confirmation_required", "message": "Confirm execution to proceed"}

    orchestrator = await _get_or_reconstruct_orchestrator(session_id, supervisor)
    if not orchestrator:
        raise HTTPException(status_code=400, detail="Campaign orchestrator not initialized")

    result = await orchestrator.execute_campaign(campaign, state)

    # ── Cache idempotency result ───────────────────────────────────
    if idem_key and session_store_idem:
        await session_store_idem.save_idempotency(idem_key, json.dumps(result))

    return CampaignExecuteResponse(**result)


# ── Live Investigation Steering Endpoints ─────────────────────────────


async def _run_critic_delta(session_id: str, pin_id: str) -> None:
    """Background task: delta-validate a new evidence pin via the CriticAgent."""
    try:
        lock = _acquire_lock(session_id)

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
    try:
        response, pin = await investigation_router.route(request)
    except Exception:
        logger.exception("Investigation route failed for session %s", session_id)
        raise HTTPException(status_code=500, detail="Investigation command failed. Please try again.")

    if pin:
        # B6: Validate causal_role before storing
        _validate_causal_role(pin)

        # Merge pin into session state under lock
        lock = _acquire_lock(session_id)
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


# ── Causal Forest Triage ──────────────────────────────────────────────


class TriageStatusUpdate(BaseModel):
    status: Literal["untriaged", "acknowledged", "mitigated", "resolved"]


@router_v4.patch("/session/{session_id}/causal-tree/{tree_id}/triage")
async def update_triage_status(session_id: str, tree_id: str, update: TriageStatusUpdate):
    """Update triage status of a CausalTree."""
    _validate_session_id(session_id)
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    state = session.get("state")
    if not state or not state.causal_forest:
        raise HTTPException(status_code=404, detail="No causal forest data")

    for tree in state.causal_forest:
        if tree.id == tree_id:
            tree.triage_status = update.status
            return {"status": "updated", "tree_id": tree_id, "triage_status": update.status}

    raise HTTPException(status_code=404, detail=f"CausalTree {tree_id} not found")


@router_v4.get("/session/{session_id}/llm-summary")
async def get_llm_summary(session_id: str):
    """Return LLM usage summary for a session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    state = session.get("state", {})
    if not isinstance(state, dict):
        return {"llm_summary": None}

    llm_summary = state.get("llm_summary")
    return {"llm_summary": llm_summary}


@router_v4.get("/cluster/lifecycle-config")
async def get_lifecycle_config():
    """Return default lifecycle thresholds."""
    from src.agents.cluster.state import LifecycleThresholds
    return LifecycleThresholds().model_dump()


@router_v4.put("/cluster/lifecycle-config")
async def update_lifecycle_config(thresholds: dict):
    """Update lifecycle thresholds (stored in-memory)."""
    # For now just validate and return
    from src.agents.cluster.state import LifecycleThresholds
    validated = LifecycleThresholds(**thresholds)
    return {"status": "updated", "thresholds": validated.model_dump()}


# ---------------------------------------------------------------------------
# Cluster Registry & Recommendations
# ---------------------------------------------------------------------------

# In-memory store for recommendation snapshots (replace with DB in production)
_recommendation_snapshots: Dict[str, Any] = {}

@router_v4.get("/clusters")
async def list_clusters():
    """List all connected clusters with health and recommendation summaries."""
    clusters = []
    # Derive from integration profiles and recent sessions
    seen_clusters: dict[str, dict] = {}

    for sid, session in sessions.items():
        if session.get("capability") != "cluster_diagnostics":
            continue
        cluster_url = session.get("connection_config", {}).get("cluster_url", "") if isinstance(session.get("connection_config"), dict) else ""
        cluster_name = session.get("service_name", cluster_url or sid[:8])

        if cluster_name not in seen_clusters:
            state = session.get("state", {})
            health = "UNKNOWN"
            if isinstance(state, dict):
                hr = state.get("health_report", {})
                if hr:
                    health = hr.get("platform_health", "UNKNOWN")

            # Check for cached recommendation snapshot
            snapshot = _recommendation_snapshots.get(cluster_name)

            seen_clusters[cluster_name] = {
                "cluster_id": cluster_name,
                "cluster_name": cluster_name,
                "provider": state.get("platform", "kubernetes") if isinstance(state, dict) else "kubernetes",
                "node_count": 0,
                "pod_count": 0,
                "health_status": health,
                "monthly_cost": snapshot.get("cost_summary", {}).get("current_monthly_cost", 0) if snapshot else 0,
                "idle_pct": snapshot.get("cost_summary", {}).get("idle_cpu_pct", 0) if snapshot else 0,
                "recommendation_count": len(snapshot.get("scored_recommendations", [])) if snapshot else 0,
                "critical_count": snapshot.get("critical_count", 0) if snapshot else 0,
                "last_scan_at": snapshot.get("scanned_at", "") if snapshot else "",
                "total_savings_usd": snapshot.get("total_savings_usd", 0) if snapshot else 0,
            }

    return {"clusters": list(seen_clusters.values())}


@router_v4.get("/clusters/{cluster_id}/recommendations")
async def get_cluster_recommendations(cluster_id: str):
    """Get full recommendations for a cluster."""
    snapshot = _recommendation_snapshots.get(cluster_id)
    if not snapshot:
        return {"snapshot": None, "message": "No recommendations available. Run a refresh."}
    return {"snapshot": snapshot}


@router_v4.post("/clusters/{cluster_id}/recommendations/refresh")
async def refresh_cluster_recommendations(cluster_id: str, background_tasks: BackgroundTasks):
    """Trigger a fresh recommendation scan for a cluster."""
    from src.agents.cluster_client.mock_client import MockClusterClient
    from src.agents.cluster.proactive_analyzer import run_proactive_analysis
    from src.agents.cluster.cost_analyzer import run_cost_analysis
    from src.agents.cluster.workload_optimizer import run_workload_optimization
    from src.agents.cluster.recommendation_engine import build_recommendation_snapshot

    # For now, use mock client. In production, look up real client from integrations.
    cluster_client = MockClusterClient()

    async def _run_refresh():
        try:
            # Run all analyzers
            proactive = await run_proactive_analysis(cluster_client)
            cost_result = await run_cost_analysis(cluster_client)
            workload_recs = await run_workload_optimization(cluster_client)

            cost_summary = cost_result.get("cost_summary")
            cost_optimization = cost_result.get("optimization")

            provider = "aws"  # Detect from client
            platform = await cluster_client.detect_platform()

            snapshot = build_recommendation_snapshot(
                cluster_id=cluster_id,
                cluster_name=cluster_id,
                provider=provider,
                proactive_findings=proactive,
                cost_summary=cost_summary,
                cost_recommendation=cost_optimization,
                workload_recommendations=workload_recs,
            )

            _recommendation_snapshots[cluster_id] = snapshot.model_dump(mode="json")
            logger.info("Recommendation refresh complete for %s: %d findings",
                       cluster_id, len(snapshot.scored_recommendations))
        except Exception as e:
            logger.error("Recommendation refresh failed for %s: %s", cluster_id, e)

    background_tasks.add_task(_run_refresh)
    return {"status": "refresh_started", "cluster_id": cluster_id}


@router_v4.get("/clusters/{cluster_id}/cost")
async def get_cluster_cost(cluster_id: str):
    """Get cost breakdown for a cluster."""
    snapshot = _recommendation_snapshots.get(cluster_id)
    if not snapshot:
        return {"cost_summary": None}
    return {"cost_summary": snapshot.get("cost_summary")}


# ---------------------------------------------------------------------------
# CI/CD unified stream endpoint (Task 16)
# ---------------------------------------------------------------------------


def _event_to_delivery_item(ev, source_instance: str) -> DeliveryItem:
    kind = "sync" if ev.source == "argocd" else "build"
    duration = None
    if ev.finished_at:
        duration = int((ev.finished_at - ev.started_at).total_seconds())
    return DeliveryItem(
        kind=kind,
        id=ev.source_id,
        title=ev.name,
        source=ev.source,
        source_instance=source_instance,
        status=ev.status,
        author=ev.triggered_by,
        git_sha=ev.git_sha,
        git_repo=ev.git_repo,
        target=ev.target,
        timestamp=ev.started_at,
        duration_s=duration,
        url=ev.url,
    )


def _commit_to_delivery_item(commit: dict, repo: str) -> DeliveryItem:
    ts_raw = commit.get("date") or ""
    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
    except ValueError:
        ts = datetime.now(tz=timezone.utc)
    sha = commit.get("sha", "")
    msg_raw = commit.get("message") or ""
    msg = msg_raw.splitlines()[0] if msg_raw else ""
    return DeliveryItem(
        kind="commit",
        id=sha,
        title=msg or sha,
        source="github",
        source_instance=repo,
        status="committed",
        author=commit.get("author"),
        git_sha=sha,
        git_repo=repo,
        target=None,
        timestamp=ts,
        duration_s=None,
        url=f"https://github.com/{repo}/commit/{sha}",
    )


@router_v4.get("/cicd/stream")
async def cicd_stream(
    cluster_id: str,
    since: datetime,
    git_repo: str | None = None,
    limit: int = 100,
):
    """Unified deploy + commit feed for the Live Board.

    cluster_id is required — resolves all linked Jenkins/ArgoCD instances.
    git_repo (owner/repo) optionally mixes recent commits from GitHub.
    """
    tz = since.tzinfo or timezone.utc
    until = datetime.now(tz=tz)

    resolved = await resolve_cicd_clients(cluster_id)
    all_clients = list(resolved.jenkins) + list(resolved.argocd)

    async def safe_list(client):
        try:
            evs = await client.list_deploy_events(since, until)
            return {"ok": True, "name": client.name, "source": client.source, "events": evs}
        except Exception as exc:
            return {"ok": False, "name": client.name, "source": client.source, "error": str(exc)}

    deploy_results = await asyncio.gather(*[safe_list(c) for c in all_clients])

    commits: list[dict] = []
    if git_repo:
        try:
            since_hours = max(1, int((until - since).total_seconds() / 3600))
            commits = await GitHubClient().get_commits(git_repo, since_hours=since_hours)
        except GitHubClientError as exc:
            logger.warning("cicd_stream: github commits fetch failed: %s", exc)

    items: list[DeliveryItem] = []
    source_errors: list[dict] = [
        {"name": e.name, "source": e.source, "message": e.message}
        for e in resolved.errors
    ]
    for r in deploy_results:
        if not r["ok"]:
            source_errors.append({
                "name": r["name"], "source": r["source"], "message": r["error"],
            })
            continue
        for ev in r["events"]:
            items.append(_event_to_delivery_item(ev, r["name"]))

    if git_repo:
        for c in commits:
            items.append(_commit_to_delivery_item(c, git_repo))

    items.sort(key=lambda i: i.timestamp, reverse=True)
    return {
        "items": [i.model_dump(mode="json") for i in items[:limit]],
        "source_errors": source_errors,
        "server_ts": datetime.now(tz=timezone.utc).isoformat(),
    }


@router_v4.get("/cicd/commit/{owner}/{repo}/{sha}")
async def cicd_commit_detail(owner: str, repo: str, sha: str):
    """Fetch full commit detail + file diffs for the Live Board drawer."""
    try:
        return await GitHubClient().get_commit_diff(f"{owner}/{repo}", sha)
    except GitHubClientError as exc:
        msg = str(exc).lower()
        if "rate limit" in msg:
            raise HTTPException(status_code=429, detail="GitHub rate limit reached")
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=str(exc))
        if "authentication" in msg or "401" in msg:
            raise HTTPException(status_code=401, detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))


@router_v4.get("/health")
async def health_check():
    checks = {}
    checks["redis"] = await check_redis()
    checks.update(check_circuit_breakers())
    statuses = [c.get("status") for c in checks.values()]
    if all(s == "up" for s in statuses):
        overall = "healthy"
    elif any(s == "down" for s in statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"
    return {"status": overall, "checks": checks}


async def check_redis():
    import time
    try:
        from src.api.main import app
        start = time.monotonic()
        await app.state.redis.ping()
        return {"status": "up", "latency_ms": round((time.monotonic() - start) * 1000)}
    except Exception:
        return {"status": "down"}


def check_circuit_breakers():
    return {}


@router_v4.get("/audit/attestations")
async def get_attestation_log(request: Request, session_id: str | None = None, decided_by: str | None = None, since: str | None = None):
    redis_client = getattr(request.app.state, "redis", None)
    if not redis_client:
        raise HTTPException(status_code=503, detail="Audit log requires Redis")
    attestation_logger = AttestationLogger(redis_client)
    return await attestation_logger.query(session_id=session_id, decided_by=decided_by, since=since)


@router_v4.get("/audit/attestation-lifecycle")
async def get_attestation_lifecycle(session_id: str | None = None):
    logger = _get_attestation_logger()
    if not logger:
        return {"events": []}
    events = await logger.query_lifecycle(session_id=session_id)
    return {"events": events}


@router_v4.get("/session/{session_id}/replay")
async def get_session_replay(session_id: str):
    _validate_session_id(session_id)
    logger = _get_attestation_logger()
    if not logger:
        return {"timeline": []}
    from src.utils.session_replayer import SessionReplayer
    replayer = SessionReplayer(logger)
    timeline = await replayer.replay(session_id)
    return {"timeline": timeline}
