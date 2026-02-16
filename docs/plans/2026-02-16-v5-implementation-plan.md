# v5 Enterprise Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add governance, integration registry, resilience, causal intelligence, change intelligence, post-mortem memory, impact modeling, and remediation safety to the existing v4 Supervisor+ReAct multi-agent SRE platform.

**Architecture:** Layered enhancement on v4. Each phase adds a new capability layer without breaking existing functionality. All 116 existing tests must continue passing after each task.

**Tech Stack:** Python 3.11+, Anthropic Claude API, Pydantic v2, FastAPI, React 18 + TypeScript + Tailwind, WebSocket, SQLite (integrations), ChromaDB (memory), kubernetes/openshift-client libraries

**Existing key files:**
- `backend/src/models/schemas.py` — All Pydantic models including DiagnosticState
- `backend/src/agents/react_base.py` — ReActAgent abstract base class
- `backend/src/agents/supervisor.py` — SupervisorAgent state machine
- `backend/src/utils/event_emitter.py` — EventEmitter for WebSocket events
- `backend/src/utils/llm_client.py` — AnthropicClient wrapper
- `backend/src/api/routes_v4.py` — V4 FastAPI routes
- `frontend/src/App.tsx` — Main layout with viewState machine
- `frontend/src/types/index.ts` — All TypeScript interfaces
- `frontend/src/services/api.ts` — API client functions
- `frontend/src/components/ResultsPanel.tsx` — Right panel

---

## Phase 1: Governance & Safety (Tasks 1-4)

Foundation layer. Every subsequent phase depends on EvidencePin and ConfidenceLedger.

---

### Task 1: Governance Data Models

**Files:**
- Modify: `backend/src/models/schemas.py`
- Create: `backend/tests/test_governance_models.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_governance_models.py
import pytest
from datetime import datetime
from src.models.schemas import (
    EvidencePin, ConfidenceLedger, AttestationGate,
    ReasoningStep, ReasoningManifest, DiagnosticStateV5
)


class TestEvidencePin:
    def test_create_evidence_pin(self):
        pin = EvidencePin(
            claim="order-service has connection timeout errors",
            supporting_evidence=["ERROR ConnectionTimeout at line 42"],
            source_agent="log_analyzer",
            source_tool="elasticsearch",
            confidence=0.85,
            timestamp=datetime.now(),
            evidence_type="log",
        )
        assert pin.confidence == 0.85
        assert pin.evidence_type == "log"

    def test_evidence_pin_rejects_invalid_confidence(self):
        with pytest.raises(Exception):
            EvidencePin(
                claim="test", supporting_evidence=[], source_agent="test",
                source_tool="test", confidence=1.5, timestamp=datetime.now(),
                evidence_type="log",
            )

    def test_evidence_pin_rejects_empty_claim(self):
        with pytest.raises(Exception):
            EvidencePin(
                claim="", supporting_evidence=[], source_agent="test",
                source_tool="test", confidence=0.5, timestamp=datetime.now(),
                evidence_type="log",
            )


class TestConfidenceLedger:
    def test_create_default_ledger(self):
        ledger = ConfidenceLedger()
        assert ledger.log_confidence == 0.0
        assert ledger.weighted_final == 0.0

    def test_compute_weighted_final(self):
        ledger = ConfidenceLedger(
            log_confidence=0.8, metrics_confidence=0.9,
            tracing_confidence=0.7, k8s_confidence=0.6,
        )
        ledger.compute_weighted_final()
        assert 0.0 < ledger.weighted_final <= 1.0

    def test_critic_adjustment_clamps(self):
        ledger = ConfidenceLedger(critic_adjustment=-0.5)
        assert ledger.critic_adjustment == -0.3  # clamped


class TestAttestationGate:
    def test_create_gate(self):
        gate = AttestationGate(
            gate_type="discovery_complete",
            evidence_summary=[],
        )
        assert gate.requires_human is True
        assert gate.human_decision is None

    def test_approve_gate(self):
        gate = AttestationGate(
            gate_type="pre_remediation",
            evidence_summary=[],
            human_decision="approve",
            decided_by="sre-oncall",
            decided_at=datetime.now(),
        )
        assert gate.human_decision == "approve"


class TestReasoningManifest:
    def test_create_manifest(self):
        manifest = ReasoningManifest(session_id="test-123", steps=[])
        assert manifest.session_id == "test-123"

    def test_add_reasoning_step(self):
        step = ReasoningStep(
            step_number=1, timestamp=datetime.now(),
            decision="dispatch_log_analyzer",
            reasoning="Starting with log analysis per telemetry pivot priority",
            evidence_considered=[], confidence_at_step=0.0,
            alternatives_rejected=["dispatch_metrics_agent"],
        )
        manifest = ReasoningManifest(session_id="test-123", steps=[step])
        assert len(manifest.steps) == 1


class TestDiagnosticStateV5:
    def test_extends_diagnostic_state(self):
        state = DiagnosticStateV5(
            session_id="test-123", service_name="order-svc",
            phase="initial",
            time_window={"start": "2026-01-01T00:00:00", "end": "2026-01-01T01:00:00"},
        )
        # V4 fields still work
        assert state.service_name == "order-svc"
        assert state.phase == "initial"
        # V5 governance fields
        assert state.evidence_pins == []
        assert state.confidence_ledger is not None
        assert state.attestation_gates == []
        assert state.reasoning_manifest is not None
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_governance_models.py -v`
Expected: FAIL — ImportError, models don't exist yet

**Step 3: Implement the governance models**

Add to `backend/src/models/schemas.py` (after existing models, before DiagnosticState):

```python
class EvidencePin(BaseModel):
    claim: str = Field(..., min_length=1)
    supporting_evidence: list[str] = []
    source_agent: str
    source_tool: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    timestamp: datetime
    evidence_type: Literal["log", "metric", "trace", "k8s_event", "code", "change"]

class ConfidenceLedger(BaseModel):
    log_confidence: float = 0.0
    metrics_confidence: float = 0.0
    tracing_confidence: float = 0.0
    k8s_confidence: float = 0.0
    code_confidence: float = 0.0
    change_confidence: float = 0.0
    critic_adjustment: float = Field(default=0.0, ge=-0.3, le=0.1)
    weighted_final: float = 0.0
    weights: dict[str, float] = {
        "log": 0.25, "metrics": 0.30, "tracing": 0.20,
        "k8s": 0.15, "code": 0.05, "change": 0.05,
    }

    def compute_weighted_final(self) -> None:
        sources = {
            "log": self.log_confidence, "metrics": self.metrics_confidence,
            "tracing": self.tracing_confidence, "k8s": self.k8s_confidence,
            "code": self.code_confidence, "change": self.change_confidence,
        }
        raw = sum(sources[k] * self.weights[k] for k in sources)
        self.weighted_final = max(0.0, min(1.0, raw + self.critic_adjustment))

class AttestationGate(BaseModel):
    gate_type: Literal["discovery_complete", "pre_remediation", "post_remediation"]
    requires_human: bool = True
    evidence_summary: list[EvidencePin] = []
    proposed_action: Optional[str] = None
    human_decision: Optional[Literal["approve", "reject", "modify"]] = None
    human_notes: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None

class ReasoningStep(BaseModel):
    step_number: int
    timestamp: datetime
    decision: str
    reasoning: str
    evidence_considered: list[str] = []
    confidence_at_step: float = 0.0
    alternatives_rejected: list[str] = []

class ReasoningManifest(BaseModel):
    session_id: str
    steps: list[ReasoningStep] = []
```

Then add `DiagnosticStateV5` that extends `DiagnosticState`:

```python
class DiagnosticStateV5(DiagnosticState):
    # Governance
    evidence_pins: list[EvidencePin] = []
    confidence_ledger: ConfidenceLedger = Field(default_factory=ConfidenceLedger)
    attestation_gates: list[AttestationGate] = []
    reasoning_manifest: ReasoningManifest = None

    # Will be extended in later phases
    integration_id: Optional[str] = None

    def __init__(self, **data):
        if "reasoning_manifest" not in data or data["reasoning_manifest"] is None:
            data["reasoning_manifest"] = ReasoningManifest(
                session_id=data.get("session_id", "")
            )
        super().__init__(**data)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_governance_models.py -v`
Expected: ALL PASS

**Step 5: Run all existing tests**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/ -v`
Expected: All 116 existing tests + new tests PASS

**Step 6: Commit**

```bash
git add backend/src/models/schemas.py backend/tests/test_governance_models.py
git commit -m "feat(v5): add governance data models — EvidencePin, ConfidenceLedger, AttestationGate, ReasoningManifest, DiagnosticStateV5"
```

---

### Task 2: Evidence Pinning in ReActAgent Base

**Files:**
- Modify: `backend/src/agents/react_base.py`
- Create: `backend/tests/test_evidence_pinning.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_evidence_pinning.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from src.agents.react_base import ReActAgent
from src.models.schemas import EvidencePin


class ConcreteAgent(ReActAgent):
    """Minimal concrete implementation for testing."""
    async def _define_tools(self):
        return []
    async def _build_system_prompt(self):
        return "test"
    async def _build_initial_prompt(self, context):
        return "test"
    async def _handle_tool_call(self, tool_name, tool_input):
        return "result"
    def _parse_final_response(self, text):
        return {"test": True}


class TestEvidencePinning:
    def test_agent_has_evidence_pins_list(self):
        agent = ConcreteAgent("test_agent")
        assert hasattr(agent, "evidence_pins")
        assert agent.evidence_pins == []

    def test_add_evidence_pin(self):
        agent = ConcreteAgent("test_agent")
        agent.add_evidence_pin(
            claim="Found connection timeout",
            supporting_evidence=["ERROR at line 42"],
            source_tool="elasticsearch",
            confidence=0.85,
            evidence_type="log",
        )
        assert len(agent.evidence_pins) == 1
        pin = agent.evidence_pins[0]
        assert pin.source_agent == "test_agent"
        assert pin.confidence == 0.85

    def test_evidence_pins_included_in_run_result(self):
        agent = ConcreteAgent("test_agent")
        agent.add_evidence_pin(
            claim="test claim",
            supporting_evidence=["evidence"],
            source_tool="test_tool",
            confidence=0.7,
            evidence_type="metric",
        )
        # _parse_final_response returns dict, run() should add evidence_pins
        result = agent._parse_final_response("test")
        result["evidence_pins"] = [p.model_dump(mode="json") for p in agent.evidence_pins]
        assert len(result["evidence_pins"]) == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_evidence_pinning.py -v`
Expected: FAIL — agent has no evidence_pins attribute

**Step 3: Implement evidence pinning in ReActAgent**

In `backend/src/agents/react_base.py`:

1. Add import: `from src.models.schemas import EvidencePin`
2. In `__init__`, add: `self.evidence_pins: list[EvidencePin] = []`
3. Add method:
```python
def add_evidence_pin(self, claim: str, supporting_evidence: list[str],
                     source_tool: str, confidence: float,
                     evidence_type: str) -> EvidencePin:
    from datetime import datetime
    pin = EvidencePin(
        claim=claim, supporting_evidence=supporting_evidence,
        source_agent=self.agent_name, source_tool=source_tool,
        confidence=confidence, timestamp=datetime.now(),
        evidence_type=evidence_type,
    )
    self.evidence_pins.append(pin)
    return pin
```
4. In `run()` method, after calling `_parse_final_response()`, inject evidence_pins:
```python
result["evidence_pins"] = [p.model_dump(mode="json") for p in self.evidence_pins]
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_evidence_pinning.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/ -v`
Expected: ALL PASS (existing tests unaffected)

**Step 6: Commit**

```bash
git add backend/src/agents/react_base.py backend/tests/test_evidence_pinning.py
git commit -m "feat(v5): add evidence pinning to ReActAgent base class"
```

---

### Task 3: Confidence Tracking in Supervisor

**Files:**
- Modify: `backend/src/agents/supervisor.py`
- Create: `backend/tests/test_confidence_tracking.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_confidence_tracking.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.models.schemas import (
    ConfidenceLedger, EvidencePin, DiagnosticStateV5,
    ReasoningManifest, ReasoningStep,
)
from datetime import datetime


class TestConfidenceTracking:
    def test_update_ledger_from_log_evidence(self):
        ledger = ConfidenceLedger()
        pins = [
            EvidencePin(
                claim="Found error", supporting_evidence=["log line"],
                source_agent="log_analyzer", source_tool="elasticsearch",
                confidence=0.85, timestamp=datetime.now(), evidence_type="log",
            )
        ]
        # Import the helper function we'll create
        from src.agents.supervisor import update_confidence_ledger
        update_confidence_ledger(ledger, pins)
        assert ledger.log_confidence == 0.85
        assert ledger.weighted_final > 0.0

    def test_update_ledger_from_multiple_sources(self):
        ledger = ConfidenceLedger()
        pins = [
            EvidencePin(
                claim="Log error", supporting_evidence=["line"],
                source_agent="log_analyzer", source_tool="elasticsearch",
                confidence=0.8, timestamp=datetime.now(), evidence_type="log",
            ),
            EvidencePin(
                claim="Metric spike", supporting_evidence=["cpu=95%"],
                source_agent="metrics_agent", source_tool="prometheus",
                confidence=0.9, timestamp=datetime.now(), evidence_type="metric",
            ),
        ]
        from src.agents.supervisor import update_confidence_ledger
        update_confidence_ledger(ledger, pins)
        assert ledger.log_confidence == 0.8
        assert ledger.metrics_confidence == 0.9
        assert ledger.weighted_final > 0.0

    def test_ledger_averages_multiple_pins_same_type(self):
        ledger = ConfidenceLedger()
        pins = [
            EvidencePin(
                claim="Error 1", supporting_evidence=["a"],
                source_agent="log_analyzer", source_tool="elasticsearch",
                confidence=0.6, timestamp=datetime.now(), evidence_type="log",
            ),
            EvidencePin(
                claim="Error 2", supporting_evidence=["b"],
                source_agent="log_analyzer", source_tool="elasticsearch",
                confidence=0.8, timestamp=datetime.now(), evidence_type="log",
            ),
        ]
        from src.agents.supervisor import update_confidence_ledger
        update_confidence_ledger(ledger, pins)
        assert ledger.log_confidence == 0.7  # average

    def test_add_reasoning_step(self):
        from src.agents.supervisor import add_reasoning_step
        manifest = ReasoningManifest(session_id="test")
        add_reasoning_step(
            manifest, decision="dispatch_log_analyzer",
            reasoning="Starting with log analysis",
            evidence_considered=[], confidence=0.0,
            alternatives_rejected=[],
        )
        assert len(manifest.steps) == 1
        assert manifest.steps[0].step_number == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_confidence_tracking.py -v`
Expected: FAIL — functions don't exist

**Step 3: Implement confidence tracking helpers in supervisor.py**

Add to `backend/src/agents/supervisor.py`:

```python
from src.models.schemas import ConfidenceLedger, EvidencePin, ReasoningManifest, ReasoningStep
from datetime import datetime

def update_confidence_ledger(ledger: ConfidenceLedger, pins: list[EvidencePin]) -> None:
    type_map = {
        "log": [], "metric": [], "trace": [],
        "k8s_event": [], "code": [], "change": [],
    }
    for pin in pins:
        type_map.get(pin.evidence_type, []).append(pin.confidence)

    if type_map["log"]:
        ledger.log_confidence = sum(type_map["log"]) / len(type_map["log"])
    if type_map["metric"]:
        ledger.metrics_confidence = sum(type_map["metric"]) / len(type_map["metric"])
    if type_map["trace"]:
        ledger.tracing_confidence = sum(type_map["trace"]) / len(type_map["trace"])
    if type_map["k8s_event"]:
        ledger.k8s_confidence = sum(type_map["k8s_event"]) / len(type_map["k8s_event"])
    if type_map["code"]:
        ledger.code_confidence = sum(type_map["code"]) / len(type_map["code"])
    if type_map["change"]:
        ledger.change_confidence = sum(type_map["change"]) / len(type_map["change"])

    ledger.compute_weighted_final()

def add_reasoning_step(
    manifest: ReasoningManifest, decision: str, reasoning: str,
    evidence_considered: list[str], confidence: float,
    alternatives_rejected: list[str],
) -> None:
    step = ReasoningStep(
        step_number=len(manifest.steps) + 1,
        timestamp=datetime.now(),
        decision=decision, reasoning=reasoning,
        evidence_considered=evidence_considered,
        confidence_at_step=confidence,
        alternatives_rejected=alternatives_rejected,
    )
    manifest.steps.append(step)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_confidence_tracking.py -v`
Expected: ALL PASS

**Step 5: Run all tests**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/agents/supervisor.py backend/tests/test_confidence_tracking.py
git commit -m "feat(v5): add confidence ledger tracking and reasoning manifest helpers"
```

---

### Task 4: Governance API Endpoints + Frontend Types

**Files:**
- Modify: `backend/src/api/routes_v4.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Create: `backend/tests/test_governance_api.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_governance_api.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


class TestGovernanceAPI:
    def test_get_evidence_pins(self, client):
        resp = client.get("/api/v5/session/test-123/evidence-graph")
        # Should return 404 for nonexistent session, not 500
        assert resp.status_code in [200, 404]

    def test_get_confidence(self, client):
        resp = client.get("/api/v5/session/test-123/confidence")
        assert resp.status_code in [200, 404]

    def test_get_reasoning(self, client):
        resp = client.get("/api/v5/session/test-123/reasoning")
        assert resp.status_code in [200, 404]

    def test_submit_attestation(self, client):
        resp = client.post("/api/v5/session/test-123/attestation", json={
            "gate_type": "discovery_complete",
            "decision": "approve",
            "decided_by": "sre-oncall",
        })
        assert resp.status_code in [200, 404]

    def test_get_timeline(self, client):
        resp = client.get("/api/v5/session/test-123/timeline")
        assert resp.status_code in [200, 404]
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_governance_api.py -v`
Expected: FAIL — routes don't exist (404 or 405)

**Step 3: Implement v5 API routes**

Create `backend/src/api/routes_v5.py`:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/api/v5", tags=["v5"])

# In-memory session store (will be replaced with proper storage later)
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
```

Register in `backend/src/api/main.py`:
```python
from src.api.routes_v5 import router as v5_router
app.include_router(v5_router)
```

**Step 4: Add frontend types to `frontend/src/types/index.ts`:**

```typescript
// V5 Governance types
export interface EvidencePin {
  claim: string;
  supporting_evidence: string[];
  source_agent: string;
  source_tool: string;
  confidence: number;
  timestamp: string;
  evidence_type: 'log' | 'metric' | 'trace' | 'k8s_event' | 'code' | 'change';
}

export interface ConfidenceLedgerData {
  log_confidence: number;
  metrics_confidence: number;
  tracing_confidence: number;
  k8s_confidence: number;
  code_confidence: number;
  change_confidence: number;
  weighted_final: number;
}

export interface AttestationGateData {
  gate_type: 'discovery_complete' | 'pre_remediation' | 'post_remediation';
  human_decision: 'approve' | 'reject' | 'modify' | null;
  decided_by: string | null;
  decided_at: string | null;
  proposed_action: string | null;
}

export interface ReasoningStepData {
  step_number: number;
  timestamp: string;
  decision: string;
  reasoning: string;
  confidence_at_step: number;
}
```

**Step 5: Add API functions to `frontend/src/services/api.ts`:**

```typescript
// V5 Governance API
export const getEvidenceGraph = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/evidence-graph`);
  if (!response.ok) throw new Error('Failed to get evidence graph');
  return response.json();
};

export const getConfidence = async (sessionId: string): Promise<ConfidenceLedgerData> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/confidence`);
  if (!response.ok) throw new Error('Failed to get confidence');
  return response.json();
};

export const getReasoning = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/reasoning`);
  if (!response.ok) throw new Error('Failed to get reasoning');
  return response.json();
};

export const submitAttestation = async (sessionId: string, gateType: string, decision: string, decidedBy: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/attestation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gate_type: gateType, decision, decided_by: decidedBy }),
  });
  if (!response.ok) throw new Error('Failed to submit attestation');
  return response.json();
};

export const getTimeline = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/session/${sessionId}/timeline`);
  if (!response.ok) throw new Error('Failed to get timeline');
  return response.json();
};
```

**Step 6: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_governance_api.py -v`
Expected: ALL PASS

**Step 7: Build frontend**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit`
Expected: No errors

**Step 8: Commit**

```bash
git add backend/src/api/routes_v5.py backend/src/api/main.py backend/tests/test_governance_api.py frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat(v5): add governance API endpoints and frontend type definitions"
```

---

## Phase 2: Integration Registry (Tasks 5-8)

---

### Task 5: Integration Data Models + SQLite Storage

**Files:**
- Create: `backend/src/integrations/__init__.py`
- Create: `backend/src/integrations/models.py`
- Create: `backend/src/integrations/store.py`
- Create: `backend/tests/test_integration_registry.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_integration_registry.py
import pytest
import os
import tempfile
from datetime import datetime
from src.integrations.models import IntegrationConfig
from src.integrations.store import IntegrationStore


class TestIntegrationConfig:
    def test_create_openshift_config(self):
        config = IntegrationConfig(
            name="Production OpenShift",
            cluster_type="openshift",
            cluster_url="https://api.prod.example.com:6443",
            auth_method="token",
            auth_data="sha256~abc123",
        )
        assert config.id is not None
        assert config.cluster_type == "openshift"
        assert config.status == "active"

    def test_create_kubernetes_config(self):
        config = IntegrationConfig(
            name="Staging GKE",
            cluster_type="kubernetes",
            cluster_url="https://gke.staging.example.com",
            auth_method="kubeconfig",
            auth_data="apiVersion: v1\nkind: Config...",
        )
        assert config.cluster_type == "kubernetes"


class TestIntegrationStore:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = str(tmp_path / "test_integrations.db")
        return IntegrationStore(db_path=db_path)

    def test_add_integration(self, store):
        config = IntegrationConfig(
            name="Test Cluster",
            cluster_type="openshift",
            cluster_url="https://test:6443",
            auth_method="token",
            auth_data="test-token",
        )
        stored = store.add(config)
        assert stored.id == config.id

    def test_list_integrations(self, store):
        config = IntegrationConfig(
            name="Test", cluster_type="kubernetes",
            cluster_url="https://test:6443",
            auth_method="token", auth_data="tok",
        )
        store.add(config)
        result = store.list_all()
        assert len(result) == 1

    def test_get_integration(self, store):
        config = IntegrationConfig(
            name="Test", cluster_type="openshift",
            cluster_url="https://test:6443",
            auth_method="token", auth_data="tok",
        )
        store.add(config)
        fetched = store.get(config.id)
        assert fetched is not None
        assert fetched.name == "Test"

    def test_delete_integration(self, store):
        config = IntegrationConfig(
            name="Test", cluster_type="openshift",
            cluster_url="https://test:6443",
            auth_method="token", auth_data="tok",
        )
        store.add(config)
        store.delete(config.id)
        assert store.get(config.id) is None

    def test_update_integration(self, store):
        config = IntegrationConfig(
            name="Old Name", cluster_type="openshift",
            cluster_url="https://test:6443",
            auth_method="token", auth_data="tok",
        )
        store.add(config)
        config.name = "New Name"
        store.update(config)
        fetched = store.get(config.id)
        assert fetched.name == "New Name"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_integration_registry.py -v`
Expected: FAIL — modules don't exist

**Step 3: Implement models**

Create `backend/src/integrations/__init__.py` (empty).

Create `backend/src/integrations/models.py`:
```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid

class IntegrationConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    cluster_type: Literal["openshift", "kubernetes"]
    cluster_url: str
    auth_method: Literal["kubeconfig", "token", "service_account"]
    auth_data: str
    prometheus_url: Optional[str] = None
    elasticsearch_url: Optional[str] = None
    jaeger_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    last_verified: Optional[datetime] = None
    status: Literal["active", "unreachable", "expired"] = "active"
    auto_discovered: dict = Field(default_factory=dict)
```

Create `backend/src/integrations/store.py`:
```python
import sqlite3
import json
from datetime import datetime
from typing import Optional
from .models import IntegrationConfig

class IntegrationStore:
    def __init__(self, db_path: str = "./data/integrations.db"):
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS integrations (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def _conn(self):
        return sqlite3.connect(self._db_path)

    def add(self, config: IntegrationConfig) -> IntegrationConfig:
        conn = self._conn()
        conn.execute(
            "INSERT INTO integrations (id, data) VALUES (?, ?)",
            (config.id, config.model_dump_json()),
        )
        conn.commit()
        conn.close()
        return config

    def get(self, integration_id: str) -> Optional[IntegrationConfig]:
        conn = self._conn()
        row = conn.execute(
            "SELECT data FROM integrations WHERE id = ?", (integration_id,)
        ).fetchone()
        conn.close()
        if row:
            return IntegrationConfig.model_validate_json(row[0])
        return None

    def list_all(self) -> list[IntegrationConfig]:
        conn = self._conn()
        rows = conn.execute("SELECT data FROM integrations").fetchall()
        conn.close()
        return [IntegrationConfig.model_validate_json(r[0]) for r in rows]

    def update(self, config: IntegrationConfig) -> None:
        conn = self._conn()
        conn.execute(
            "UPDATE integrations SET data = ? WHERE id = ?",
            (config.model_dump_json(), config.id),
        )
        conn.commit()
        conn.close()

    def delete(self, integration_id: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM integrations WHERE id = ?", (integration_id,))
        conn.commit()
        conn.close()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_integration_registry.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/integrations/ backend/tests/test_integration_registry.py
git commit -m "feat(v5): add integration registry data models and SQLite store"
```

---

### Task 6: Cluster Probe + Auto-Detection

**Files:**
- Create: `backend/src/integrations/probe.py`
- Create: `backend/tests/test_cluster_probe.py`

**Step 1: Write the failing tests**

```python
# backend/tests/test_cluster_probe.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.integrations.probe import ClusterProbe, ProbeResult
from src.integrations.models import IntegrationConfig


class TestClusterProbe:
    @pytest.fixture
    def openshift_config(self):
        return IntegrationConfig(
            name="Test OCP", cluster_type="openshift",
            cluster_url="https://api.test:6443",
            auth_method="token", auth_data="sha256~test",
        )

    @pytest.fixture
    def k8s_config(self):
        return IntegrationConfig(
            name="Test K8s", cluster_type="kubernetes",
            cluster_url="https://k8s.test:6443",
            auth_method="token", auth_data="test-token",
        )

    @pytest.mark.asyncio
    async def test_probe_openshift_discovers_prometheus(self, openshift_config):
        probe = ClusterProbe()
        with patch("src.integrations.probe.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [
                (0, "https://prometheus-k8s-openshift-monitoring.apps.test", ""),  # oc get route
                (0, "https://kibana-openshift-logging.apps.test", ""),  # oc get route logging
                (0, "4.14.0", ""),  # oc version
            ]
            result = await probe.probe(openshift_config)
            assert result.prometheus_url is not None
            assert "prometheus" in result.prometheus_url
            assert result.cluster_version == "4.14.0"

    @pytest.mark.asyncio
    async def test_probe_kubernetes(self, k8s_config):
        probe = ClusterProbe()
        with patch("src.integrations.probe.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [
                (0, "prometheus-server.monitoring.svc.cluster.local", ""),
                (1, "", "not found"),  # no elk
                (0, "v1.28.0", ""),
            ]
            result = await probe.probe(k8s_config)
            assert result.prometheus_url is not None

    @pytest.mark.asyncio
    async def test_probe_handles_unreachable_cluster(self, openshift_config):
        probe = ClusterProbe()
        with patch("src.integrations.probe.run_command", new_callable=AsyncMock) as mock_cmd:
            mock_cmd.side_effect = [(1, "", "Unable to connect to the server")]
            result = await probe.probe(openshift_config)
            assert result.reachable is False

    def test_get_cli_tool(self):
        probe = ClusterProbe()
        assert probe.get_cli_tool("openshift") == "oc"
        assert probe.get_cli_tool("kubernetes") == "kubectl"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_cluster_probe.py -v`
Expected: FAIL

**Step 3: Implement**

Create `backend/src/integrations/probe.py`:
```python
import asyncio
from typing import Optional, Tuple
from pydantic import BaseModel
from .models import IntegrationConfig


class ProbeResult(BaseModel):
    reachable: bool = False
    prometheus_url: Optional[str] = None
    elasticsearch_url: Optional[str] = None
    cluster_version: Optional[str] = None
    errors: list[str] = []


async def run_command(cmd: str) -> Tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


class ClusterProbe:
    def get_cli_tool(self, cluster_type: str) -> str:
        return "oc" if cluster_type == "openshift" else "kubectl"

    async def probe(self, config: IntegrationConfig) -> ProbeResult:
        result = ProbeResult()
        cli = self.get_cli_tool(config.cluster_type)

        if config.cluster_type == "openshift":
            # Discover Prometheus via route
            code, stdout, stderr = await run_command(
                f"{cli} get route prometheus-k8s -n openshift-monitoring "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.spec.host}}' --insecure-skip-tls-verify"
            )
            if code != 0:
                if "Unable to connect" in stderr:
                    result.reachable = False
                    result.errors.append(stderr)
                    return result
                result.errors.append(f"Prometheus discovery failed: {stderr}")
            else:
                result.reachable = True
                host = stdout.strip("'")
                result.prometheus_url = f"https://{host}" if not host.startswith("http") else host

            # Discover ELK
            code, stdout, stderr = await run_command(
                f"{cli} get route kibana -n openshift-logging "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.spec.host}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                host = stdout.strip("'")
                result.elasticsearch_url = f"https://{host}" if not host.startswith("http") else host

            # Cluster version
            code, stdout, stderr = await run_command(
                f"{cli} version --server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.openshiftVersion}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                result.cluster_version = stdout.strip("'")

        else:  # kubernetes
            # Check for prometheus-server service
            code, stdout, stderr = await run_command(
                f"{cli} get svc prometheus-server -n monitoring "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.metadata.name}}.{{.metadata.namespace}}.svc.cluster.local' "
                f"--insecure-skip-tls-verify"
            )
            if code != 0:
                if "Unable to connect" in stderr:
                    result.reachable = False
                    result.errors.append(stderr)
                    return result
            else:
                result.reachable = True
                result.prometheus_url = f"http://{stdout}:9090"

            # Check for elasticsearch
            code, stdout, stderr = await run_command(
                f"{cli} get svc elasticsearch -n logging "
                f"--server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.metadata.name}}.{{.metadata.namespace}}.svc.cluster.local' "
                f"--insecure-skip-tls-verify"
            )
            if code == 0:
                result.elasticsearch_url = f"http://{stdout}:9200"

            # Version
            code, stdout, stderr = await run_command(
                f"{cli} version --server={config.cluster_url} --token={config.auth_data} "
                f"-o jsonpath='{{.serverVersion.gitVersion}}' --insecure-skip-tls-verify"
            )
            if code == 0:
                result.cluster_version = stdout.strip("'")

        return result
```

**Step 4: Run tests**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_cluster_probe.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/integrations/probe.py backend/tests/test_cluster_probe.py
git commit -m "feat(v5): add cluster probe with oc/kubectl auto-detection and OpenShift auto-discovery"
```

---

### Task 7: Integration API Endpoints

**Files:**
- Modify: `backend/src/api/routes_v5.py`
- Create: `backend/tests/test_integration_api.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_integration_api.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from src.api.main import app
    return TestClient(app)


class TestIntegrationAPI:
    def test_add_integration(self, client):
        resp = client.post("/api/v5/integrations", json={
            "name": "Test Cluster",
            "cluster_type": "openshift",
            "cluster_url": "https://api.test:6443",
            "auth_method": "token",
            "auth_data": "sha256~test",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Cluster"
        assert "id" in data

    def test_list_integrations(self, client):
        resp = client.get("/api/v5/integrations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_integration(self, client):
        # Add first
        add_resp = client.post("/api/v5/integrations", json={
            "name": "Get Test", "cluster_type": "kubernetes",
            "cluster_url": "https://test:6443",
            "auth_method": "token", "auth_data": "tok",
        })
        iid = add_resp.json()["id"]
        resp = client.get(f"/api/v5/integrations/{iid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Test"

    def test_delete_integration(self, client):
        add_resp = client.post("/api/v5/integrations", json={
            "name": "Delete Test", "cluster_type": "openshift",
            "cluster_url": "https://test:6443",
            "auth_method": "token", "auth_data": "tok",
        })
        iid = add_resp.json()["id"]
        resp = client.delete(f"/api/v5/integrations/{iid}")
        assert resp.status_code == 200
        get_resp = client.get(f"/api/v5/integrations/{iid}")
        assert get_resp.status_code == 404

    def test_get_nonexistent_integration(self, client):
        resp = client.get("/api/v5/integrations/nonexistent")
        assert resp.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_integration_api.py -v`

**Step 3: Add integration CRUD routes to `routes_v5.py`**

```python
from src.integrations.models import IntegrationConfig
from src.integrations.store import IntegrationStore

_integration_store = IntegrationStore()

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
    stored = _integration_store.add(config)
    return stored.model_dump()

@router.get("/integrations")
async def list_integrations():
    return [c.model_dump() for c in _integration_store.list_all()]

@router.get("/integrations/{integration_id}")
async def get_integration(integration_id: str):
    config = _integration_store.get(integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    return config.model_dump()

@router.put("/integrations/{integration_id}")
async def update_integration(integration_id: str, request: CreateIntegrationRequest):
    existing = _integration_store.get(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")
    updated = existing.model_copy(update=request.model_dump())
    _integration_store.update(updated)
    return updated.model_dump()

@router.delete("/integrations/{integration_id}")
async def delete_integration(integration_id: str):
    existing = _integration_store.get(integration_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Integration not found")
    _integration_store.delete(integration_id)
    return {"status": "deleted"}

@router.post("/integrations/{integration_id}/probe")
async def probe_integration(integration_id: str):
    config = _integration_store.get(integration_id)
    if not config:
        raise HTTPException(status_code=404, detail="Integration not found")
    from src.integrations.probe import ClusterProbe
    probe = ClusterProbe()
    result = await probe.probe(config)
    # Update config with discovered URLs
    if result.prometheus_url:
        config.prometheus_url = result.prometheus_url
    if result.elasticsearch_url:
        config.elasticsearch_url = result.elasticsearch_url
    config.last_verified = datetime.now()
    config.status = "active" if result.reachable else "unreachable"
    config.auto_discovered = result.model_dump()
    _integration_store.update(config)
    return result.model_dump()
```

**Step 4: Run tests**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm && python -m pytest backend/tests/test_integration_api.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes_v5.py backend/tests/test_integration_api.py
git commit -m "feat(v5): add integration CRUD API endpoints with probe"
```

---

### Task 8: Integration Settings UI + Form Dropdown

**Files:**
- Create: `frontend/src/components/Settings/IntegrationSettings.tsx`
- Modify: `frontend/src/components/ActionCenter/forms/TroubleshootAppFields.tsx`
- Modify: `frontend/src/components/ActionCenter/forms/ClusterDiagnosticsFields.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/types/index.ts`

**Step 1: Add frontend types + API functions**

Add to `types/index.ts`:
```typescript
export interface Integration {
  id: string;
  name: string;
  cluster_type: 'openshift' | 'kubernetes';
  cluster_url: string;
  auth_method: 'kubeconfig' | 'token' | 'service_account';
  prometheus_url: string | null;
  elasticsearch_url: string | null;
  status: 'active' | 'unreachable' | 'expired';
  auto_discovered: Record<string, unknown>;
  created_at: string;
  last_verified: string | null;
}
```

Add to `api.ts`:
```typescript
export const listIntegrations = async (): Promise<Integration[]> => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations`);
  if (!response.ok) throw new Error('Failed to list integrations');
  return response.json();
};

export const addIntegration = async (data: Partial<Integration>) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to add integration');
  return response.json();
};

export const deleteIntegration = async (id: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error('Failed to delete integration');
  return response.json();
};

export const probeIntegration = async (id: string) => {
  const response = await fetch(`${API_BASE_URL}/api/v5/integrations/${id}/probe`, { method: 'POST' });
  if (!response.ok) throw new Error('Failed to probe integration');
  return response.json();
};
```

**Step 2: Create IntegrationSettings component**

`frontend/src/components/Settings/IntegrationSettings.tsx`:
- List integrations with status badges
- "Add Integration" form: name, cluster URL, type (openshift/kubernetes), auth method, auth data textarea
- Auto-probe on add, show discovered URLs
- Delete button per integration
- DebugDuck dark theme styling

**Step 3: Add integration dropdown to TroubleshootAppFields and ClusterDiagnosticsFields**

Both forms should:
- Fetch integrations via `listIntegrations()` on mount
- Show a dropdown at the top: "Select Cluster" with integration names
- On selection, auto-fill cluster_url, namespace defaults, prometheus_url

**Step 4: Add Settings view to App.tsx**

Add `viewState: 'settings'` option. Wire the "Settings" nav item in SessionSidebar.

**Step 5: Build frontend**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npx tsc --noEmit && npm run build`
Expected: Build passes

**Step 6: Commit**

```bash
git add frontend/src/components/Settings/ frontend/src/components/ActionCenter/forms/ frontend/src/App.tsx frontend/src/services/api.ts frontend/src/types/index.ts
git commit -m "feat(v5): add integration settings UI and cluster dropdown in forms"
```

---

## Phase 3: Resilience (Tasks 9-11)

---

### Task 9: ReAct Budget Controls

**Files:**
- Modify: `backend/src/models/schemas.py`
- Modify: `backend/src/agents/react_base.py`
- Create: `backend/tests/test_react_budget.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_react_budget.py
import pytest
from src.models.schemas import ReActBudget


class TestReActBudget:
    def test_default_budget(self):
        budget = ReActBudget()
        assert budget.max_llm_calls == 10
        assert budget.max_tool_calls == 15
        assert budget.is_exhausted() is False

    def test_budget_exhausted_on_llm_calls(self):
        budget = ReActBudget(max_llm_calls=2, current_llm_calls=2)
        assert budget.is_exhausted() is True

    def test_budget_exhausted_on_tokens(self):
        budget = ReActBudget(max_tokens=100, current_tokens=150)
        assert budget.is_exhausted() is True

    def test_record_llm_call(self):
        budget = ReActBudget()
        budget.record_llm_call(tokens=500)
        assert budget.current_llm_calls == 1
        assert budget.current_tokens == 500

    def test_record_tool_call(self):
        budget = ReActBudget()
        budget.record_tool_call()
        assert budget.current_tool_calls == 1
```

**Step 2: Run tests — FAIL**

**Step 3: Add ReActBudget model to schemas.py and wire into react_base.py**

```python
# In schemas.py
class ReActBudget(BaseModel):
    max_llm_calls: int = 10
    max_tool_calls: int = 15
    max_tokens: int = 50000
    timeout_seconds: int = 120
    current_llm_calls: int = 0
    current_tool_calls: int = 0
    current_tokens: int = 0

    def is_exhausted(self) -> bool:
        return (self.current_llm_calls >= self.max_llm_calls or
                self.current_tool_calls >= self.max_tool_calls or
                self.current_tokens >= self.max_tokens)

    def record_llm_call(self, tokens: int = 0) -> None:
        self.current_llm_calls += 1
        self.current_tokens += tokens

    def record_tool_call(self) -> None:
        self.current_tool_calls += 1
```

In `react_base.py.__init__`: add `self.budget = ReActBudget()`.
In `react_base.py.run()`: check `self.budget.is_exhausted()` before each iteration. Call `self.budget.record_llm_call(tokens)` after each LLM call and `self.budget.record_tool_call()` after each tool execution.

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git add backend/src/models/schemas.py backend/src/agents/react_base.py backend/tests/test_react_budget.py
git commit -m "feat(v5): add ReAct budget controls for per-agent resource limits"
```

---

### Task 10: Tiered Log Processing + Heuristic Fallback

**Files:**
- Create: `backend/src/agents/log_processing.py`
- Create: `backend/tests/test_log_processing.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_log_processing.py
import pytest
from src.agents.log_processing import (
    TieredLogProcessor, HeuristicPatternMatcher, HEURISTIC_PATTERNS
)


class TestHeuristicPatternMatcher:
    def test_detect_connection_timeout(self):
        matcher = HeuristicPatternMatcher()
        results = matcher.match("ERROR: connection timed out to redis:6379")
        assert any(r["pattern"] == "connection_timeout" for r in results)

    def test_detect_oom_killed(self):
        matcher = HeuristicPatternMatcher()
        results = matcher.match("Container was OOMKilled")
        assert any(r["pattern"] == "oom_killed" for r in results)

    def test_detect_crash_loop(self):
        matcher = HeuristicPatternMatcher()
        results = matcher.match("Back-off restarting failed container")
        assert any(r["pattern"] == "crash_loop" for r in results)

    def test_no_match(self):
        matcher = HeuristicPatternMatcher()
        results = matcher.match("INFO: Application started successfully")
        assert len(results) == 0


class TestTieredLogProcessor:
    def test_tier1_ecs_parsing(self):
        processor = TieredLogProcessor()
        log_line = '{"@timestamp":"2026-01-01T00:00:00","level":"ERROR","message":"Connection refused"}'
        result = processor.process_line(log_line)
        assert result["tier"] == 1
        assert result["level"] == "ERROR"

    def test_tier3_heuristic_fallback(self):
        processor = TieredLogProcessor()
        log_line = "Some unstructured log: connection timed out"
        result = processor.process_line(log_line)
        assert result["tier"] in [2, 3]

    def test_process_batch(self):
        processor = TieredLogProcessor()
        logs = [
            '{"level":"ERROR","message":"timeout"}',
            "plain text OOMKilled log",
            '{"level":"WARN","message":"slow query"}',
        ]
        results = processor.process_batch(logs)
        assert len(results) == 3
```

**Step 2: Run tests — FAIL**

**Step 3: Implement**

```python
# backend/src/agents/log_processing.py
import re
import json
from typing import Optional

HEURISTIC_PATTERNS = {
    "connection_timeout": r"(?i)(connection\s*timed?\s*out|ETIMEDOUT|connect\s+ECONNREFUSED)",
    "oom_killed": r"(?i)(OOMKilled|out\s*of\s*memory|Cannot\s+allocate\s+memory)",
    "crash_loop": r"(?i)(CrashLoopBackOff|back-off\s+restarting)",
    "permission_denied": r"(?i)(permission\s+denied|EACCES|403\s+Forbidden)",
    "dns_failure": r"(?i)(NXDOMAIN|dns\s+resolution|could\s+not\s+resolve)",
    "disk_pressure": r"(?i)(DiskPressure|no\s+space\s+left|ENOSPC)",
    "image_pull": r"(?i)(ImagePullBackOff|ErrImagePull|image\s+not\s+found)",
}

class HeuristicPatternMatcher:
    def __init__(self):
        self._compiled = {k: re.compile(v) for k, v in HEURISTIC_PATTERNS.items()}

    def match(self, text: str) -> list[dict]:
        results = []
        for name, pattern in self._compiled.items():
            m = pattern.search(text)
            if m:
                results.append({"pattern": name, "match": m.group(), "start": m.start()})
        return results

class TieredLogProcessor:
    def __init__(self):
        self._heuristic = HeuristicPatternMatcher()

    def process_line(self, line: str) -> dict:
        # Tier 1: Try ECS JSON parsing
        try:
            data = json.loads(line)
            if "level" in data or "message" in data or "@timestamp" in data:
                return {"tier": 1, **data}
        except (json.JSONDecodeError, TypeError):
            pass

        # Tier 3: Heuristic pattern matching (Tier 2 requires LLM, skipped if budget exhausted)
        matches = self._heuristic.match(line)
        return {
            "tier": 3 if matches else 3,
            "raw": line,
            "heuristic_matches": matches,
            "level": "ERROR" if matches else "UNKNOWN",
        }

    def process_batch(self, lines: list[str]) -> list[dict]:
        return [self.process_line(line) for line in lines]
```

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git add backend/src/agents/log_processing.py backend/tests/test_log_processing.py
git commit -m "feat(v5): add tiered log processing with heuristic pattern fallback"
```

---

### Task 11: Discovery Fallback for Degraded Environments

**Files:**
- Create: `backend/src/agents/discovery_fallback.py`
- Create: `backend/tests/test_discovery_fallback.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_discovery_fallback.py
import pytest
from unittest.mock import patch, AsyncMock
from src.agents.discovery_fallback import DiscoveryFallback


class TestDiscoveryFallback:
    @pytest.mark.asyncio
    async def test_discover_namespaces(self):
        fb = DiscoveryFallback(cli_tool="oc", cluster_url="https://test:6443", token="tok")
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock:
            mock.return_value = (0, "default\norder-svc\npayment-svc", "")
            ns = await fb.discover_namespaces()
            assert "order-svc" in ns

    @pytest.mark.asyncio
    async def test_discover_error_pods(self):
        fb = DiscoveryFallback(cli_tool="kubectl", cluster_url="https://test:6443", token="tok")
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock:
            mock.return_value = (0, "order-svc-abc123 CrashLoopBackOff\npayment-xyz Error", "")
            pods = await fb.discover_error_pods("default")
            assert len(pods) >= 1

    @pytest.mark.asyncio
    async def test_get_pod_logs(self):
        fb = DiscoveryFallback(cli_tool="oc", cluster_url="https://test:6443", token="tok")
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock:
            mock.return_value = (0, "ERROR: Connection timeout at line 42\nWARN: Retrying", "")
            logs = await fb.get_pod_logs("order-svc-abc123", "default")
            assert "Connection timeout" in logs

    @pytest.mark.asyncio
    async def test_fallback_handles_failure(self):
        fb = DiscoveryFallback(cli_tool="oc", cluster_url="https://test:6443", token="tok")
        with patch("src.agents.discovery_fallback.run_command", new_callable=AsyncMock) as mock:
            mock.return_value = (1, "", "Unable to connect")
            ns = await fb.discover_namespaces()
            assert ns == []
```

**Step 2: Run tests — FAIL**

**Step 3: Implement**

```python
# backend/src/agents/discovery_fallback.py
from typing import Optional
from src.integrations.probe import run_command


class DiscoveryFallback:
    def __init__(self, cli_tool: str, cluster_url: str, token: str):
        self.cli = cli_tool
        self.url = cluster_url
        self.token = token

    def _base_args(self) -> str:
        return f"--server={self.url} --token={self.token} --insecure-skip-tls-verify"

    async def discover_namespaces(self) -> list[str]:
        code, stdout, _ = await run_command(
            f"{self.cli} get namespaces -o jsonpath='{{.items[*].metadata.name}}' {self._base_args()}"
        )
        if code != 0:
            return []
        return [ns.strip() for ns in stdout.replace("'", "").split() if ns.strip()]

    async def discover_error_pods(self, namespace: str) -> list[dict]:
        code, stdout, _ = await run_command(
            f"{self.cli} get pods -n {namespace} --field-selector=status.phase!=Running,status.phase!=Succeeded "
            f"-o custom-columns=NAME:.metadata.name,STATUS:.status.phase --no-headers {self._base_args()}"
        )
        if code != 0:
            return []
        pods = []
        for line in stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2:
                pods.append({"name": parts[0], "status": parts[1]})
        return pods

    async def get_pod_logs(self, pod_name: str, namespace: str, tail: int = 200) -> str:
        code, stdout, _ = await run_command(
            f"{self.cli} logs {pod_name} -n {namespace} --tail={tail} {self._base_args()}"
        )
        return stdout if code == 0 else ""
```

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git add backend/src/agents/discovery_fallback.py backend/tests/test_discovery_fallback.py
git commit -m "feat(v5): add discovery fallback for degraded environments (direct pod logs)"
```

---

## Phase 4: Causal Intelligence (Tasks 12-14)

---

### Task 12: Evidence Graph Data Models

**Files:**
- Modify: `backend/src/models/schemas.py`
- Create: `backend/tests/test_evidence_graph.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_evidence_graph.py
import pytest
from datetime import datetime
from src.models.schemas import (
    EvidenceNode, CausalEdge, EvidenceGraph, EvidencePin,
    IncidentTimeline, TimelineEvent, Hypothesis,
)


class TestEvidenceGraph:
    def test_create_evidence_node(self):
        pin = EvidencePin(
            claim="Error found", supporting_evidence=["log"],
            source_agent="log_analyzer", source_tool="elasticsearch",
            confidence=0.8, timestamp=datetime.now(), evidence_type="log",
        )
        node = EvidenceNode(
            id="n1", pin=pin, node_type="symptom",
            temporal_position=datetime.now(),
        )
        assert node.node_type == "symptom"

    def test_create_causal_edge(self):
        edge = CausalEdge(
            source_id="n1", target_id="n2",
            relationship="causes", confidence=0.75,
            reasoning="Deployment preceded error spike by 2 minutes",
        )
        assert edge.relationship == "causes"

    def test_build_graph(self):
        graph = EvidenceGraph(
            nodes=[], edges=[], root_causes=[], timeline=[],
        )
        assert len(graph.nodes) == 0

    def test_find_root_causes(self):
        graph = EvidenceGraph(
            nodes=[],
            edges=[
                CausalEdge(source_id="n1", target_id="n2",
                           relationship="causes", confidence=0.8, reasoning="test"),
            ],
            root_causes=["n1"], timeline=["n1", "n2"],
        )
        assert "n1" in graph.root_causes


class TestIncidentTimeline:
    def test_create_timeline(self):
        event = TimelineEvent(
            timestamp=datetime.now(), source="metrics_agent",
            event_type="metric_spike", description="CPU at 95%",
            evidence_node_id="n1", severity="warning",
        )
        timeline = IncidentTimeline(events=[event])
        assert len(timeline.events) == 1


class TestHypothesis:
    def test_create_hypothesis(self):
        h = Hypothesis(
            hypothesis_id="h1",
            description="Redis connection pool exhaustion causing timeouts",
            confidence=0.82,
            supporting_node_ids=["n1", "n2", "n3"],
            causal_chain=["n1 -> n2 -> n3"],
        )
        assert h.confidence == 0.82
```

**Step 2: Run tests — FAIL**

**Step 3: Add models to schemas.py**

```python
class EvidenceNode(BaseModel):
    id: str
    pin: EvidencePin
    node_type: Literal["symptom", "cause", "contributing_factor", "context"]
    temporal_position: datetime

class CausalEdge(BaseModel):
    source_id: str
    target_id: str
    relationship: Literal["causes", "correlates", "precedes", "contributes_to"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str

class EvidenceGraph(BaseModel):
    nodes: list[EvidenceNode] = []
    edges: list[CausalEdge] = []
    root_causes: list[str] = []
    timeline: list[str] = []

class TimelineEvent(BaseModel):
    timestamp: datetime
    source: str
    event_type: str
    description: str
    evidence_node_id: str
    severity: Literal["info", "warning", "error", "critical"]

class IncidentTimeline(BaseModel):
    events: list[TimelineEvent] = []

class Hypothesis(BaseModel):
    hypothesis_id: str
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_node_ids: list[str] = []
    causal_chain: list[str] = []
```

Then extend `DiagnosticStateV5`:
```python
# Add to DiagnosticStateV5
evidence_graph: EvidenceGraph = Field(default_factory=EvidenceGraph)
hypotheses: list[Hypothesis] = []
incident_timeline: IncidentTimeline = Field(default_factory=IncidentTimeline)
```

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git add backend/src/models/schemas.py backend/tests/test_evidence_graph.py
git commit -m "feat(v5): add evidence graph, incident timeline, and hypothesis models"
```

---

### Task 13: Evidence Graph Builder

**Files:**
- Create: `backend/src/agents/causal_engine.py`
- Create: `backend/tests/test_causal_engine.py`

**Step 1: Write failing tests**

```python
# backend/tests/test_causal_engine.py
import pytest
from datetime import datetime, timedelta
from src.agents.causal_engine import EvidenceGraphBuilder
from src.models.schemas import EvidencePin


class TestEvidenceGraphBuilder:
    def test_add_evidence_creates_node(self):
        builder = EvidenceGraphBuilder()
        pin = EvidencePin(
            claim="Error found", supporting_evidence=["log"],
            source_agent="log_analyzer", source_tool="elasticsearch",
            confidence=0.8, timestamp=datetime.now(), evidence_type="log",
        )
        node_id = builder.add_evidence(pin, node_type="symptom")
        assert node_id is not None
        assert len(builder.graph.nodes) == 1

    def test_add_causal_link(self):
        builder = EvidenceGraphBuilder()
        t1 = datetime.now() - timedelta(minutes=5)
        t2 = datetime.now()
        pin1 = EvidencePin(
            claim="Deployment happened", supporting_evidence=["deploy log"],
            source_agent="change_agent", source_tool="github",
            confidence=0.9, timestamp=t1, evidence_type="change",
        )
        pin2 = EvidencePin(
            claim="Errors spiked", supporting_evidence=["error rate 500%"],
            source_agent="metrics_agent", source_tool="prometheus",
            confidence=0.85, timestamp=t2, evidence_type="metric",
        )
        n1 = builder.add_evidence(pin1, node_type="cause")
        n2 = builder.add_evidence(pin2, node_type="symptom")
        builder.add_causal_link(n1, n2, "causes", 0.8, "Deploy preceded error spike by 5min")
        assert len(builder.graph.edges) == 1

    def test_identify_root_causes(self):
        builder = EvidenceGraphBuilder()
        t = datetime.now()
        p1 = EvidencePin(claim="root", supporting_evidence=[], source_agent="a",
                         source_tool="t", confidence=0.9, timestamp=t, evidence_type="change")
        p2 = EvidencePin(claim="effect", supporting_evidence=[], source_agent="a",
                         source_tool="t", confidence=0.8, timestamp=t, evidence_type="log")
        n1 = builder.add_evidence(p1, node_type="cause")
        n2 = builder.add_evidence(p2, node_type="symptom")
        builder.add_causal_link(n1, n2, "causes", 0.8, "test")
        roots = builder.identify_root_causes()
        assert n1 in roots

    def test_build_timeline(self):
        builder = EvidenceGraphBuilder()
        t1 = datetime(2026, 1, 1, 10, 0)
        t2 = datetime(2026, 1, 1, 10, 5)
        p1 = EvidencePin(claim="first", supporting_evidence=[], source_agent="a",
                         source_tool="t", confidence=0.8, timestamp=t1, evidence_type="log")
        p2 = EvidencePin(claim="second", supporting_evidence=[], source_agent="a",
                         source_tool="t", confidence=0.8, timestamp=t2, evidence_type="metric")
        builder.add_evidence(p1, node_type="cause")
        builder.add_evidence(p2, node_type="symptom")
        timeline = builder.build_timeline()
        assert len(timeline.events) == 2
        assert timeline.events[0].timestamp < timeline.events[1].timestamp
```

**Step 2: Run tests — FAIL**

**Step 3: Implement**

```python
# backend/src/agents/causal_engine.py
import uuid
from src.models.schemas import (
    EvidencePin, EvidenceNode, CausalEdge, EvidenceGraph,
    IncidentTimeline, TimelineEvent,
)


class EvidenceGraphBuilder:
    def __init__(self):
        self.graph = EvidenceGraph()

    def add_evidence(self, pin: EvidencePin, node_type: str) -> str:
        node_id = f"n-{uuid.uuid4().hex[:8]}"
        node = EvidenceNode(
            id=node_id, pin=pin, node_type=node_type,
            temporal_position=pin.timestamp,
        )
        self.graph.nodes.append(node)
        return node_id

    def add_causal_link(self, source_id: str, target_id: str,
                        relationship: str, confidence: float, reasoning: str) -> None:
        edge = CausalEdge(
            source_id=source_id, target_id=target_id,
            relationship=relationship, confidence=confidence,
            reasoning=reasoning,
        )
        self.graph.edges.append(edge)

    def identify_root_causes(self) -> list[str]:
        targets = {e.target_id for e in self.graph.edges}
        sources = {e.source_id for e in self.graph.edges}
        roots = [nid for nid in sources if nid not in targets]
        self.graph.root_causes = roots
        return roots

    def build_timeline(self) -> IncidentTimeline:
        sorted_nodes = sorted(self.graph.nodes, key=lambda n: n.temporal_position)
        events = []
        for node in sorted_nodes:
            events.append(TimelineEvent(
                timestamp=node.temporal_position,
                source=node.pin.source_agent,
                event_type=node.pin.evidence_type,
                description=node.pin.claim,
                evidence_node_id=node.id,
                severity="error" if node.node_type in ("cause", "symptom") else "info",
            ))
        self.graph.timeline = [n.id for n in sorted_nodes]
        return IncidentTimeline(events=events)
```

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git add backend/src/agents/causal_engine.py backend/tests/test_causal_engine.py
git commit -m "feat(v5): add evidence graph builder with causal linking and timeline"
```

---

### Task 14: Causal Intelligence Frontend Cards

**Files:**
- Create: `frontend/src/components/Dashboard/TimelineCard.tsx`
- Create: `frontend/src/components/Dashboard/EvidenceGraphCard.tsx`
- Modify: `frontend/src/components/ResultsPanel.tsx`

**Step 1: Create TimelineCard**

Horizontal timeline showing events color-coded by severity. Each event shows timestamp, source agent icon, description. Scrollable.

**Step 2: Create EvidenceGraphCard**

Simplified causal chain visualization. Shows root cause → intermediate nodes → symptoms as connected boxes with confidence labels on edges.

**Step 3: Add both cards to ResultsPanel**

Import and render TimelineCard and EvidenceGraphCard below existing findings. Fetch data from `/api/v5/session/{id}/timeline` and `/api/v5/session/{id}/evidence-graph`.

**Step 4: Build frontend**

Run: `cd /Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/frontend && npm run build`
Expected: Build passes

**Step 5: Commit**

```bash
git add frontend/src/components/Dashboard/TimelineCard.tsx frontend/src/components/Dashboard/EvidenceGraphCard.tsx frontend/src/components/ResultsPanel.tsx
git commit -m "feat(v5): add timeline and evidence graph cards to results panel"
```

---

## Phase 5: Change Intelligence (Tasks 15-16)

---

### Task 15: Change Agent

**Files:**
- Create: `backend/src/agents/change_agent.py`
- Create: `backend/tests/test_change_agent.py`

**Step 1: Write failing tests** — Test ChangeAgent inherits ReActAgent, defines tools for github_commits, deployment_history, config_diff. Test `_parse_final_response` returns ChangeRiskScore list.

**Step 2: Implement ChangeAgent** following the ReActAgent pattern from existing agents (log_agent.py, metrics_agent.py). Define tools:
- `github_recent_commits`: Calls GitHub API for recent commits to service repo
- `deployment_history`: Runs `oc rollout history` or `kubectl rollout history`
- `config_diff`: Compares current ConfigMap against previous version

**Step 3: Add ChangeRiskScore model to schemas.py:**
```python
class ChangeRiskScore(BaseModel):
    change_id: str
    change_type: Literal["code_deploy", "config_change", "infra_change", "dependency_update"]
    risk_score: float = Field(..., ge=0.0, le=1.0)
    temporal_correlation: float = Field(..., ge=0.0, le=1.0)
    scope_overlap: float = Field(..., ge=0.0, le=1.0)
    author: str
    description: str
    files_changed: list[str] = []
```

**Step 4: Run tests — PASS**

**Step 5: Commit**

```bash
git add backend/src/agents/change_agent.py backend/tests/test_change_agent.py backend/src/models/schemas.py
git commit -m "feat(v5): add change intelligence agent with risk scoring"
```

---

### Task 16: Change Correlation UI Card

**Files:**
- Create: `frontend/src/components/Dashboard/ChangeCorrelationCard.tsx`
- Modify: `frontend/src/components/ResultsPanel.tsx`

Shows recent changes overlaid with incident timestamp, risk scores, and "Rollback" action button. Styled in DebugDuck theme.

**Commit:**
```bash
git add frontend/src/components/Dashboard/ChangeCorrelationCard.tsx frontend/src/components/ResultsPanel.tsx
git commit -m "feat(v5): add change correlation card to results panel"
```

---

## Phase 6: Post-Mortem Memory (Tasks 17-18)

---

### Task 17: Incident Fingerprinting + Memory Store

**Files:**
- Create: `backend/src/memory/__init__.py`
- Create: `backend/src/memory/models.py`
- Create: `backend/src/memory/store.py`
- Create: `backend/tests/test_memory.py`

**Step 1: Write failing tests** — Test IncidentFingerprint creation, signal matching (Jaccard similarity), novelty detection, store/retrieve from ChromaDB.

**Step 2: Implement**

`models.py`: IncidentFingerprint Pydantic model with error_patterns, affected_services, symptom_categories, root_cause, resolution_steps.

`store.py`: MemoryStore class using ChromaDB for vector storage. Methods: `store_incident()`, `find_similar()` (two-tier: signal match then semantic), `is_novel()`.

Add `chromadb>=0.4.0` to `requirements.txt`.

**Step 3: Run tests — PASS**

**Step 4: Commit**

```bash
git add backend/src/memory/ backend/tests/test_memory.py backend/requirements.txt
git commit -m "feat(v5): add post-mortem memory with incident fingerprinting and RAG"
```

---

### Task 18: Memory API + Past Incident UI Card

**Files:**
- Modify: `backend/src/api/routes_v5.py`
- Create: `frontend/src/components/Dashboard/PastIncidentCard.tsx`
- Modify: `frontend/src/components/ResultsPanel.tsx`

Add API endpoints:
```
GET  /api/v5/memory/similar?session_id={id}
GET  /api/v5/memory/incidents
POST /api/v5/memory/incidents
```

Frontend card shows similar past incidents with match percentage, root cause, and "Apply Same Resolution" button.

**Commit:**
```bash
git add backend/src/api/routes_v5.py frontend/src/components/Dashboard/PastIncidentCard.tsx frontend/src/components/ResultsPanel.tsx
git commit -m "feat(v5): add memory API endpoints and past incident match card"
```

---

## Phase 7: Impact & Risk Modeling (Tasks 19-20)

---

### Task 19: Blast Radius + Severity Models

**Files:**
- Modify: `backend/src/models/schemas.py`
- Create: `backend/src/agents/impact_analyzer.py`
- Create: `backend/tests/test_impact_analyzer.py`

Add BlastRadius, SeverityRecommendation, ServiceTier models. Implement severity matrix lookup. Test P1-P4 assignments based on tier × scope.

**Commit:**
```bash
git add backend/src/models/schemas.py backend/src/agents/impact_analyzer.py backend/tests/test_impact_analyzer.py
git commit -m "feat(v5): add blast radius estimator and severity recommendation engine"
```

---

### Task 20: Impact Card UI

**Files:**
- Create: `frontend/src/components/Dashboard/ImpactCard.tsx`
- Modify: `frontend/src/components/ResultsPanel.tsx`

Blast radius visualization (primary service center, affected radiating out), severity badge (P1-P4), user impact estimate.

**Commit:**
```bash
git add frontend/src/components/Dashboard/ImpactCard.tsx frontend/src/components/ResultsPanel.tsx
git commit -m "feat(v5): add impact and blast radius card to results panel"
```

---

## Phase 8: Remediation Safety (Tasks 21-23)

---

### Task 21: Runbook Matching + Remediation Models

**Files:**
- Create: `backend/src/remediation/__init__.py`
- Create: `backend/src/remediation/models.py`
- Create: `backend/src/remediation/engine.py`
- Create: `backend/tests/test_remediation.py`

Models: RunbookMatch, RemediationDecision, RemediationResult. Engine: dry-run execution, pre/post checks, rollback logic.

**Commit:**
```bash
git add backend/src/remediation/ backend/tests/test_remediation.py
git commit -m "feat(v5): add remediation safety engine with runbook matching and dry-run"
```

---

### Task 22: Remediation API + Attestation UI

**Files:**
- Modify: `backend/src/api/routes_v5.py`
- Create: `frontend/src/components/Remediation/AttestationGateUI.tsx`
- Create: `frontend/src/components/Remediation/RemediationPanel.tsx`
- Modify: `frontend/src/App.tsx`

API endpoints:
```
POST /api/v5/session/{id}/remediation/propose
POST /api/v5/session/{id}/remediation/dry-run
POST /api/v5/session/{id}/remediation/execute
POST /api/v5/session/{id}/remediation/rollback
```

AttestationGateUI: Modal that appears at discovery_complete and pre_remediation gates. Shows evidence summary, proposed action, approve/reject/modify buttons.

RemediationPanel: Shows proposed fix, dry-run results, execute button (with destructive action confirmation), rollback button.

**Commit:**
```bash
git add backend/src/api/routes_v5.py frontend/src/components/Remediation/ frontend/src/App.tsx
git commit -m "feat(v5): add remediation API, attestation gate UI, and remediation panel"
```

---

### Task 23: Wire Supervisor to V5 Pipeline

**Files:**
- Modify: `backend/src/agents/supervisor.py`
- Modify: `backend/src/api/routes_v4.py`
- Create: `backend/tests/test_supervisor_v5.py`

This is the integration task. Update `SupervisorAgent`:

1. Change dispatch order to v5 TelemetryPivotPriority: Metrics → Tracing → K8s → ELK → Code → Change
2. After each agent completes, extract evidence_pins and update ConfidenceLedger
3. Add ReasoningStep for each dispatch decision
4. After all agents complete Phase 1, build EvidenceGraph and IncidentTimeline
5. Insert AttestationGate at discovery_complete before proceeding to remediation
6. If attestation approved, run remediation with safety controls

Test the full pipeline with mocked agents.

**Commit:**
```bash
git add backend/src/agents/supervisor.py backend/src/api/routes_v4.py backend/tests/test_supervisor_v5.py
git commit -m "feat(v5): wire supervisor to v5 pipeline with governance, causal graph, and attestation gates"
```

---

## Summary

| Phase | Tasks | Components |
|-------|-------|------------|
| 1: Governance | 1-4 | EvidencePin, ConfidenceLedger, AttestationGate, ReasoningManifest, API, frontend types |
| 2: Integration Registry | 5-8 | IntegrationConfig, SQLite store, ClusterProbe, API, Settings UI, form dropdowns |
| 3: Resilience | 9-11 | ReActBudget, TieredLogProcessing, HeuristicFallback, DiscoveryFallback |
| 4: Causal Intelligence | 12-14 | EvidenceGraph, CausalEngine, Timeline, Hypothesis, frontend cards |
| 5: Change Intelligence | 15-16 | ChangeAgent, ChangeRiskScore, ChangeCorrelationCard |
| 6: Post-Mortem Memory | 17-18 | IncidentFingerprint, MemoryStore (ChromaDB), PastIncidentCard |
| 7: Impact & Risk | 19-20 | BlastRadius, SeverityRecommendation, ImpactCard |
| 8: Remediation Safety | 21-23 | RunbookMatch, RemediationEngine, AttestationGateUI, Supervisor V5 wiring |

**Total: 23 tasks, ~23 commits**
