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
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"evidence_pins": session.get("evidence_pins", []), "nodes": [], "edges": []}


@router.get("/session/{session_id}/confidence")
async def get_confidence(session_id: str):
    session = _get_session_or_empty(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("confidence_ledger", {})


@router.get("/session/{session_id}/reasoning")
async def get_reasoning(session_id: str):
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
    return {"status": "recorded", "gate": gate}


@router.get("/session/{session_id}/timeline")
async def get_timeline(session_id: str):
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
    # Placeholder — in production this would look up the session and create a fingerprint
    return {"similar_incidents": []}


# --- Remediation endpoints ---


@router.post("/session/{session_id}/remediation/propose")
async def propose_remediation(session_id: str, data: dict):
    return {"status": "proposed", "session_id": session_id, "decision": data}


@router.post("/session/{session_id}/remediation/dry-run")
async def dry_run_remediation(session_id: str, data: dict):
    return {"status": "dry_run_complete", "output": f"Dry run: {data.get('action', 'unknown')}"}


@router.post("/session/{session_id}/remediation/execute")
async def execute_remediation(session_id: str, data: dict):
    return {"status": "executed", "output": f"Executed: {data.get('action', 'unknown')}"}


@router.post("/session/{session_id}/remediation/rollback")
async def rollback_remediation(session_id: str):
    return {"status": "rolled_back"}
