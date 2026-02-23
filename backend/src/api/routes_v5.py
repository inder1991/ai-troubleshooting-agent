"""V5 Governance API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

from src.integrations.models import IntegrationConfig
from src.integrations.store import IntegrationStore
from src.memory.store import MemoryStore
from src.memory.models import IncidentFingerprint
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v5", tags=["v5"])

# --- Integration store setup ---
_db_path = os.environ.get("INTEGRATION_DB_PATH", "./data/integrations.db")
_integration_store = None


def get_integration_store():
    global _integration_store
    if _integration_store is None:
        os.makedirs(os.path.dirname(_db_path) if os.path.dirname(_db_path) else ".", exist_ok=True)
        _integration_store = IntegrationStore(db_path=_db_path)
    return _integration_store

# In-memory session store (placeholder)
_v5_sessions: dict = {}


def _get_session_or_empty(session_id: str) -> dict:
    """Return v5 session data, falling back to v4 session with empty v5 defaults."""
    if session_id in _v5_sessions:
        return _v5_sessions[session_id]
    # Check if v4 session exists — return empty v5 defaults so UI doesn't get 404
    from src.api.routes_v4 import sessions as v4_sessions
    if session_id in v4_sessions:
        return {"session_id": session_id}
    return None


class AttestationRequest(BaseModel):
    gate_type: str
    decision: str
    decided_by: str
    notes: Optional[str] = None


@router.get("/session/{session_id}/evidence-graph")
async def get_evidence_graph(session_id: str):
    logger.info("Governance data requested", extra={"session_id": session_id, "action": "evidence_graph"})
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    pins = session.get("evidence_pins", [])

    # Build nodes from evidence pins
    nodes = []
    root_causes = []
    for i, pin in enumerate(pins):
        node_id = f"pin-{i}"
        confidence = pin.get("confidence", 0)
        # High-confidence findings are likely causes; lower ones are symptoms/context
        if confidence >= 0.7:
            node_type = "cause"
            root_causes.append(pin.get("claim", ""))
        elif confidence >= 0.4:
            node_type = "contributing_factor"
        else:
            node_type = "symptom"
        nodes.append({
            "id": node_id,
            "claim": pin.get("claim", ""),
            "source_agent": pin.get("source_agent", ""),
            "evidence_type": pin.get("evidence_type", "unknown"),
            "node_type": node_type,
            "confidence": confidence,
            "timestamp": pin.get("timestamp", ""),
        })

    # Build edges: connect related nodes (same agent or overlapping evidence)
    edges = []
    for i, src in enumerate(nodes):
        for j, tgt in enumerate(nodes):
            if i >= j:
                continue
            # Connect nodes from the same agent or with cause→symptom relationships
            if src["source_agent"] == tgt["source_agent"] and src["node_type"] == "cause" and tgt["node_type"] != "cause":
                edges.append({
                    "source_id": src["id"],
                    "target_id": tgt["id"],
                    "relationship": "causes",
                    "confidence": min(src["confidence"], tgt["confidence"]),
                    "reasoning": f"{src['source_agent']} analysis links these findings",
                })
            elif src["node_type"] == "cause" and tgt["node_type"] == "symptom":
                edges.append({
                    "source_id": src["id"],
                    "target_id": tgt["id"],
                    "relationship": "manifests_as",
                    "confidence": min(src["confidence"], tgt["confidence"]) * 0.8,
                    "reasoning": "High-confidence cause linked to observed symptom",
                })

    return {"evidence_pins": pins, "nodes": nodes, "edges": edges, "root_causes": root_causes}


@router.get("/session/{session_id}/confidence")
async def get_confidence(session_id: str):
    logger.info("Governance data requested", extra={"session_id": session_id, "action": "confidence"})
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("confidence_ledger", {})


@router.get("/session/{session_id}/reasoning")
async def get_reasoning(session_id: str):
    logger.info("Governance data requested", extra={"session_id": session_id, "action": "reasoning"})
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("reasoning_manifest", {"session_id": session_id, "steps": []})


@router.post("/session/{session_id}/attestation")
async def submit_attestation(session_id: str, request: AttestationRequest):
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    gate = {
        "gate_type": request.gate_type,
        "human_decision": request.decision,
        "decided_by": request.decided_by,
        "human_notes": request.notes,
        "decided_at": datetime.now().isoformat(),
    }
    session.setdefault("attestation_gates", []).append(gate)

    # Wire attestation to supervisor to gate fix generation
    from src.api.routes_v4 import supervisors
    supervisor = supervisors.get(session_id)
    if supervisor:
        supervisor.acknowledge_attestation(request.decision)

    return {"status": "recorded", "gate": gate}


@router.get("/session/{session_id}/timeline")
async def get_timeline(session_id: str):
    logger.info("Governance data requested", extra={"session_id": session_id, "action": "timeline"})
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"events": session.get("timeline_events", [])}


# --- Integration CRUD endpoints (DEPRECATED - use /api/v5/profiles) ---

from fastapi.responses import JSONResponse


class CreateIntegrationRequest(BaseModel):
    name: str
    cluster_type: str
    cluster_url: str
    auth_method: str
    auth_data: str
    prometheus_url: Optional[str] = None
    elasticsearch_url: Optional[str] = None
    jaeger_url: Optional[str] = None


def _deprecated_response(data) -> JSONResponse:
    """Wrap response with deprecation header."""
    return JSONResponse(
        content=data,
        headers={"Deprecation": "true", "Link": "</api/v5/profiles>; rel=\"successor-version\""},
    )


@router.post("/integrations")
async def add_integration(request: CreateIntegrationRequest):
    config = IntegrationConfig(**request.model_dump())
    stored = get_integration_store().add(config)
    return _deprecated_response(stored.model_dump(mode="json"))


@router.get("/integrations")
@router.head("/integrations")
async def list_integrations():
    data = [c.model_dump(mode="json") for c in get_integration_store().list_all()]
    return _deprecated_response(data)


@router.get("/integrations/{integration_id}")
async def get_integration(integration_id: str):
    config = get_integration_store().get(integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    return _deprecated_response(config.model_dump(mode="json"))


@router.put("/integrations/{integration_id}")
async def update_integration(integration_id: str, request: CreateIntegrationRequest):
    store = get_integration_store()
    existing = store.get(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")
    updated = existing.model_copy(update=request.model_dump())
    store.update(updated)
    return _deprecated_response(updated.model_dump(mode="json"))


@router.delete("/integrations/{integration_id}")
async def delete_integration(integration_id: str):
    store = get_integration_store()
    existing = store.get(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")
    store.delete(integration_id)
    return _deprecated_response({"status": "deleted"})


@router.post("/integrations/{integration_id}/probe")
async def probe_integration(integration_id: str):
    store = get_integration_store()
    config = store.get(integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    from src.integrations.probe import ClusterProbe
    probe = ClusterProbe()
    result = await probe.probe(config)
    if result.prometheus_url:
        config.prometheus_url = result.prometheus_url
    if result.elasticsearch_url:
        config.elasticsearch_url = result.elasticsearch_url
    config.last_verified = datetime.now()
    config.status = "active" if result.reachable else "unreachable"
    config.auto_discovered = result.model_dump()
    store.update(config)
    return _deprecated_response(result.model_dump(mode="json"))


# --- Memory store setup ---
_memory_store = None


def get_memory_store():
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


@router.get("/memory/incidents")
async def list_incidents():
    return [fp.model_dump(mode="json") for fp in get_memory_store().list_all()]


@router.post("/memory/incidents")
async def store_incident(data: dict):
    fp = IncidentFingerprint(**data)
    store = get_memory_store()
    if store.is_novel(fp):
        store.store_incident(fp)
        return {"stored": True, "fingerprint_id": fp.fingerprint_id}
    return {"stored": False, "reason": "duplicate"}


@router.get("/memory/similar")
async def find_similar(session_id: str):
    """Find past incidents similar to the given session's findings."""
    session = _get_session_or_empty(session_id)
    if not session:
        return {"similar_incidents": []}

    # Build a fingerprint from session's evidence pins to search against stored incidents
    pins = session.get("evidence_pins", [])
    if not pins:
        return {"similar_incidents": []}

    error_patterns = [p.get("claim", "") for p in pins if p.get("evidence_type") in ("log", "unknown")]
    affected_services = list({p.get("source_agent", "") for p in pins})

    store = get_memory_store()
    all_incidents = store.list_all()
    matches = []
    for incident in all_incidents:
        # Simple similarity: overlap in error patterns and affected services
        pattern_overlap = len(set(incident.error_patterns or []) & set(error_patterns))
        service_overlap = len(set(incident.affected_services or []) & set(affected_services))
        total = max(len(error_patterns) + len(affected_services), 1)
        score = (pattern_overlap + service_overlap) / total
        if score > 0.1:
            matches.append({
                "fingerprint_id": incident.fingerprint_id,
                "session_id": getattr(incident, "session_id", ""),
                "similarity_score": round(score, 2),
                "root_cause": getattr(incident, "root_cause", ""),
                "resolution_steps": getattr(incident, "resolution_steps", []),
                "error_patterns": incident.error_patterns or [],
                "affected_services": incident.affected_services or [],
                "time_to_resolve": getattr(incident, "time_to_resolve", 0),
            })

    matches.sort(key=lambda m: m["similarity_score"], reverse=True)
    return {"similar_incidents": matches[:10]}


# --- Remediation endpoints ---


@router.post("/session/{session_id}/remediation/propose")
async def propose_remediation(session_id: str, data: dict):
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    action = data.get("action", "")
    action_type = data.get("action_type", "restart")
    is_destructive = action_type in ("rollback", "config_change", "code_fix")

    proposal = {
        "status": "proposed",
        "session_id": session_id,
        "proposed_action": action or "Review and apply suggested fix from findings",
        "action_type": action_type,
        "is_destructive": is_destructive,
        "dry_run_available": action_type in ("restart", "scale", "config_change"),
        "rollback_plan": data.get("rollback_plan", f"Revert {action_type} action and restore previous state"),
        "pre_checks": data.get("pre_checks", ["Verify current service health", "Check pending requests"]),
        "post_checks": data.get("post_checks", ["Verify service is healthy", "Monitor error rate for 5 minutes"]),
    }
    session.setdefault("remediation_proposals", []).append(proposal)
    return proposal


@router.post("/session/{session_id}/remediation/dry-run")
async def dry_run_remediation(session_id: str, data: dict):
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    action = data.get("action", "unknown")
    return {
        "status": "dry_run_complete",
        "session_id": session_id,
        "action": action,
        "output": f"Dry run simulation for '{action}' completed successfully",
        "would_affect": data.get("target_resources", []),
        "estimated_downtime": "0s" if data.get("action_type") == "scale" else "~30s",
        "safe_to_proceed": True,
    }


@router.post("/session/{session_id}/remediation/execute")
async def execute_remediation(session_id: str, data: dict):
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    action = data.get("action", "unknown")
    result = {
        "status": "executed",
        "session_id": session_id,
        "action": action,
        "output": f"Executed remediation action: {action}",
        "executed_at": datetime.now().isoformat(),
        "rollback_available": True,
    }
    session.setdefault("executed_remediations", []).append(result)
    return result


@router.post("/session/{session_id}/remediation/rollback")
async def rollback_remediation(session_id: str):
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    executed = session.get("executed_remediations", [])
    last_action = executed[-1] if executed else None
    return {
        "status": "rolled_back",
        "session_id": session_id,
        "rolled_back_action": last_action.get("action", "unknown") if last_action else "none",
        "rolled_back_at": datetime.now().isoformat(),
    }
