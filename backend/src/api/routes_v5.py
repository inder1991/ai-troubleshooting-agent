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


class AttestationRequest(BaseModel):
    gate_type: str
    decision: str
    decided_by: str
    notes: Optional[str] = None


@router.get("/session/{session_id}/evidence-graph")
async def get_evidence_graph(session_id: str):
    session = _v5_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"evidence_pins": session.get("evidence_pins", []), "nodes": [], "edges": []}


@router.get("/session/{session_id}/confidence")
async def get_confidence(session_id: str):
    session = _v5_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("confidence_ledger", {})


@router.get("/session/{session_id}/reasoning")
async def get_reasoning(session_id: str):
    session = _v5_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.get("reasoning_manifest", {"session_id": session_id, "steps": []})


@router.post("/session/{session_id}/attestation")
async def submit_attestation(session_id: str, request: AttestationRequest):
    session = _v5_sessions.get(session_id)
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
    session = _v5_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"events": session.get("timeline_events", [])}


# --- Integration CRUD endpoints ---


class CreateIntegrationRequest(BaseModel):
    name: str
    cluster_type: str
    cluster_url: str
    auth_method: str
    auth_data: str
    prometheus_url: Optional[str] = None
    elasticsearch_url: Optional[str] = None
    jaeger_url: Optional[str] = None


@router.post("/integrations")
async def add_integration(request: CreateIntegrationRequest):
    config = IntegrationConfig(**request.model_dump())
    stored = get_integration_store().add(config)
    return stored.model_dump()


@router.get("/integrations")
async def list_integrations():
    return [c.model_dump() for c in get_integration_store().list_all()]


@router.get("/integrations/{integration_id}")
async def get_integration(integration_id: str):
    config = get_integration_store().get(integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    return config.model_dump()


@router.put("/integrations/{integration_id}")
async def update_integration(integration_id: str, request: CreateIntegrationRequest):
    store = get_integration_store()
    existing = store.get(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")
    updated = existing.model_copy(update=request.model_dump())
    store.update(updated)
    return updated.model_dump()


@router.delete("/integrations/{integration_id}")
async def delete_integration(integration_id: str):
    store = get_integration_store()
    existing = store.get(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")
    store.delete(integration_id)
    return {"status": "deleted"}


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
    return result.model_dump()


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
