"""V5 Governance API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/v5", tags=["v5"])

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
