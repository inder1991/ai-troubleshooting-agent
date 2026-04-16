# Phase 5: Supervisor Unification (Hybrid Adapter) — Design

**Goal:** Bridge SupervisorAgent's dynamic decision loop with WorkflowExecutor's reliable execution engine via a new InvestigationExecutor, without touching either system's core logic.

**Architecture:** InvestigationExecutor (conductor) wraps WorkflowExecutor (orchestra). Supervisor keeps its decision loop but dispatches agents through the executor. Each investigation becomes a single append-only virtual DAG with unified events normalized at the adapter layer.

**Tech Stack:** Python, Redis (DAG persistence), existing WorkflowExecutor, existing WebSocket EventEmitter.

---

## 1. Non-goals

- No replacement of SupervisorAgent's decision logic
- No modification of WorkflowExecutor internals
- No War Room UI changes
- No transport unification (WebSocket stays for investigations, SSE stays for workflows)
- No parallel agent dispatch (deferred until hypothesis engine is stable)
- No planner/DAG-generation (Phase 5.2+ evolution)

## 2. Core Boundary

| System | Owns | Does NOT own |
|---|---|---|
| SupervisorAgent | Hypotheses, evidence, confidence, decision logic, human gates | Step execution, retry, event emission |
| InvestigationExecutor | Investigation lifecycle, virtual DAG, step state, event emission, sequence numbers | Reasoning, evidence interpretation, confidence scoring |
| WorkflowExecutor | Step execution, retry/fallback, concurrency | Investigation context, dynamic planning |

This boundary is **hard**. No hypothesis or evidence data leaks into InvestigationExecutor or WorkflowExecutor.

## 3. Execution Flow

```
User starts investigation
    │
    ▼
routes_v4.py creates SupervisorAgent + InvestigationExecutor
    │
    ▼
SupervisorAgent.run(investigation_executor)
    │
    ├─ Round 1: decide → "run log_agent"
    │   │
    │   ▼
    │   investigation_executor.run_step({
    │     step_id: "round-1-log-agent",
    │     agent: "log_agent",
    │     depends_on: [],
    │     metadata: {round: 1, triggered_by: null, reason: "initial triage"}
    │   })
    │   │
    │   ▼
    │   InvestigationExecutor:
    │     1. Appends step to virtual DAG
    │     2. Persists DAG state to Redis
    │     3. Emits step_update event (status: running)
    │     4. Calls WorkflowExecutor with 1-node DAG
    │     5. Receives StepResult
    │     6. Updates step status in DAG
    │     7. Emits step_update event (status: success/failed)
    │     8. Returns typed StepResult to Supervisor
    │   │
    │   ▼
    │   Supervisor processes result, updates hypotheses/confidence
    │
    ├─ Round 2: decide → "run metrics_agent"
    │   │
    │   ▼
    │   investigation_executor.run_step({
    │     step_id: "round-2-metrics-agent",
    │     agent: "metrics_agent",
    │     depends_on: ["round-1-log-agent"],
    │     metadata: {round: 2, triggered_by: "h1", reason: "validate OOM suspicion"}
    │   })
    │   ... same flow ...
    │
    └─ ... up to 10 rounds ...
```

## 4. Canonical Event Envelope

A single envelope type for ALL events across both systems. Payloads are typed.

```python
class EventEnvelope:
    event_type: str           # "step_update" | "run_update" | "error"
    run_id: str
    sequence_number: int      # monotonic per run, assigned at emission time
    timestamp: str            # ISO 8601
    payload: StepPayload | RunPayload | ErrorPayload
```

### Payloads

```python
class StepPayload:
    step_id: str
    parent_step_ids: list[str]
    status: StepStatus        # pending | running | success | failed | skipped | cancelled
    started_at: str | None
    ended_at: str | None
    metadata: StepMetadata | None

class StepMetadata:
    agent: str | None
    round: int | None
    group: str | None         # "validation_phase", etc.
    hypothesis_id: str | None
    reason: str | None
    duration_ms: int | None
    error: ErrorDetail | None

class ErrorDetail:
    message: str
    type: str | None

class RunPayload:
    status: str               # "running" | "completed" | "failed"

class ErrorPayload:
    message: str
    recoverable: bool
```

Events are **idempotent** — each event represents current state, not a delta. Safe for reconnection replay.

## 5. InvestigationExecutor

New file: `backend/src/workflows/investigation_executor.py`

### Interface

```python
class InvestigationExecutor:
    def __init__(self, run_id: str, emitter: EventEmitter, redis: Redis | None):
        ...

    async def run_step(self, spec: InvestigationStepSpec) -> StepResult:
        """Run a single agent step through WorkflowExecutor."""

    async def run_steps(self, specs: list[InvestigationStepSpec]) -> list[StepResult]:
        """Run multiple steps. Currently sequential; batch-ready for future parallelism."""

    def get_dag(self) -> VirtualDag:
        """Return current virtual DAG state (for UI/debugging)."""

    async def cancel(self) -> None:
        """Cancel the current investigation run."""
```

### InvestigationStepSpec

```python
@dataclass
class InvestigationStepSpec:
    step_id: str              # e.g. "round-2-metrics-agent"
    agent: str
    depends_on: list[str]
    input_data: dict | None
    metadata: StepMetadata | None
```

### StepResult (typed, not Any)

```python
@dataclass
class StepResult:
    step_id: str
    status: StepStatus
    output: dict | None       # agent findings
    error: ErrorDetail | None
    started_at: str
    ended_at: str
    duration_ms: int
```

### Internal behavior

1. **Append step** to virtual DAG with status `pending`
2. **Persist** DAG state to Redis
3. **Emit** `step_update` event (status: `running`), increment sequence_number
4. **Call WorkflowExecutor** with a 1-node DAG (completed dependencies marked as resolved)
5. **Receive result**, update step status in DAG
6. **Persist** updated DAG state
7. **Emit** `step_update` event (status: `success` or `failed`)
8. **Return** typed `StepResult`

## 6. Virtual DAG Model

```python
@dataclass
class VirtualStep:
    step_id: str              # "round-2-metrics-agent" — stable, unique, human-readable
    agent: str
    depends_on: list[str]
    status: StepStatus
    round: int
    group: str | None
    triggered_by: str | None  # hypothesis_id
    reason: str | None
    started_at: str | None
    ended_at: str | None
    duration_ms: int | None
    output: dict | None
    error: ErrorDetail | None

@dataclass
class VirtualDag:
    run_id: str
    steps: list[VirtualStep]  # append-only, never mutate past steps
    last_sequence_number: int
    current_round: int
    status: str               # "running" | "completed" | "failed"
```

### Persistence (Redis)

Stored durably to survive process restarts:

- Key: `investigation:{run_id}:dag`
- Value: serialized VirtualDag (JSON)
- Includes: all steps, edges, last sequence number, current round, last emitted status

On process restart, InvestigationExecutor rehydrates from Redis and resumes from last known state.

### Source of Truth

| Question | Source |
|---|---|
| What steps ran and in what order? | Virtual DAG |
| What status is each step? | Virtual DAG |
| What sequence number are we at? | Virtual DAG |
| What dependencies exist? | Virtual DAG |
| What hypotheses are active? | SupervisorAgent |
| What evidence supports them? | SupervisorAgent |
| What confidence level? | SupervisorAgent |
| What to run next? | SupervisorAgent |

## 7. Step ID Convention

Format: `round-{N}-{agent_name}`

Examples:
- `round-1-log-agent`
- `round-2-metrics-agent`
- `round-3-k8s-agent`
- `round-4-code-agent`

Properties:
- **Stable**: same investigation replayed produces same IDs
- **Unique within a run**: round number + agent name
- **Human-readable**: immediately clear what ran and when

If an agent runs twice (e.g., log_agent in round 1 and round 5):
- `round-1-log-agent`
- `round-5-log-agent`

## 8. Supervisor Integration

Modify `SupervisorAgent.run()` signature:

```python
async def run(
    self,
    initial_input: dict,
    emitter: EventEmitter,
    investigation_executor: InvestigationExecutor,  # NEW
    on_state_created=None,
) -> SupervisorState:
```

Inside the round loop, replace direct agent calls:

```python
# BEFORE (direct dispatch)
result = await agent.run(agent_input)

# AFTER (through executor)
step_result = await self.investigation_executor.run_step(
    InvestigationStepSpec(
        step_id=f"round-{round_num}-{agent_name}",
        agent=agent_name,
        depends_on=[prev_step_id] if prev_step_id else [],
        input_data=agent_input,
        metadata=StepMetadata(
            agent=agent_name,
            round=round_num,
            hypothesis_id=current_hypothesis_id,
            reason=decision_reason,
        ),
    )
)
```

Supervisor continues to own all reasoning. It receives `StepResult` and processes findings exactly as before.

## 9. Event Adapter Layer

### Investigation adapter (NEW)

Thin translator: InvestigationExecutor results → EventEnvelope → WebSocket.

```python
class InvestigationEventAdapter:
    def step_to_envelope(self, step: VirtualStep, run_id: str, seq: int) -> EventEnvelope:
        """Translate VirtualStep state into canonical EventEnvelope."""
```

Translates, does not interpret. No business logic in the adapter.

### Workflow adapter (DEFERRED)

A utility function that converts WorkflowExecutor SSE events into the canonical EventEnvelope schema. **Not built until there is a real consumer** (e.g., a unified dashboard that shows both investigation and workflow events side by side).

The schema definition is enough for now — the adapter can be mechanical when needed.

## 10. Route Integration

Modify `routes_v4.py`:

```python
# In session start handler
investigation_executor = InvestigationExecutor(
    run_id=f"investigation-{session_id}",
    emitter=emitter,
    redis=redis_client,
)

# Pass to supervisor
background_tasks.add_task(
    run_diagnosis,
    session_id,
    supervisor,
    initial_input,
    emitter,
    investigation_executor,  # NEW
)
```

### New endpoint: GET investigation DAG

```
GET /api/v4/session/{session_id}/dag
```

Returns current VirtualDag for the investigation. Enables Phase 4 DAG view to render investigations.

## 11. What Changes vs What Stays

| Component | Status |
|---|---|
| `InvestigationExecutor` | **NEW** |
| `InvestigationStepSpec`, `StepResult`, `VirtualDag` | **NEW** types |
| `EventEnvelope`, `StepPayload`, `RunPayload` | **NEW** canonical event schema |
| `InvestigationEventAdapter` | **NEW** thin translator |
| `SupervisorAgent.run()` | **MODIFY** — dispatch through executor |
| `routes_v4.py` | **MODIFY** — create executor, pass to supervisor, add DAG endpoint |
| `WorkflowExecutor` | **UNTOUCHED** |
| War Room UI | **UNTOUCHED** |
| `useWebSocketV4` | **UNTOUCHED** |
| Phase 4 DAG view | **UNTOUCHED** |
| Evidence pins, confidence, human gates | **UNTOUCHED** |
| Investigation router (manual /investigate commands) | **UNTOUCHED** |

## 12. Testing Strategy

Priority order:

1. **InvestigationExecutor unit tests** — append step, dependency tracking, sequence numbering, DAG persistence/rehydration, cancel
2. **StepResult typing** — verify typed results, no Any leakage
3. **Event adapter tests** — both investigation and workflow adapters produce identical EventEnvelope shape
4. **Supervisor integration test** — full loop: decide → run_step → process result → decide again. Verify hypotheses stay in supervisor, step state stays in executor
5. **Redis persistence tests** — DAG survives simulated restart, sequence numbers resume correctly
6. **Non-impact: WorkflowExecutor** — existing workflow tests green, no regressions
7. **Non-impact: routes** — existing session/investigation endpoints unchanged
8. **New endpoint test** — `GET /session/{id}/dag` returns correct VirtualDag

## 13. Exit Criteria

- [ ] InvestigationExecutor dispatches agents via WorkflowExecutor (1-node DAGs)
- [ ] SupervisorAgent uses InvestigationExecutor instead of direct agent calls
- [ ] Virtual DAG grows append-only with round/triggered_by/depends_on metadata
- [ ] Virtual DAG + sequence number persisted durably in Redis
- [ ] Canonical EventEnvelope schema with typed payloads (StepPayload, RunPayload, ErrorPayload)
- [ ] InvestigationEventAdapter emits canonical events over WebSocket
- [ ] StepResult is fully typed (no Any)
- [ ] Step IDs follow `round-{N}-{agent_name}` convention
- [ ] sequence_number monotonic per run, assigned at emission time, stored durably
- [ ] Hypotheses/evidence/confidence stay in Supervisor (no leakage into executor)
- [ ] WorkflowExecutor untouched — existing workflow tests green
- [ ] War Room UI untouched — no frontend changes
- [ ] `run_steps(specs)` interface ready for future batch parallelism
- [ ] `GET /api/v4/session/{id}/dag` endpoint returns VirtualDag
- [ ] InvestigationExecutor rehydrates from Redis on restart

## 14. Future Evolution (Post-Phase 5)

- **Phase 5.2**: Supervisor emits step groups (2-3 parallel agents) → `run_steps` enables concurrent dispatch
- **Phase 5.3**: Supervisor emits mini-DAGs per round → WorkflowExecutor runs them as real DAGs
- **Phase 5.4**: Full planner → DAG → executor pipeline (option (a) endgame)
- **Phase 5.5**: Workflow adapter built when unified dashboard needs it
- **Predefined playbooks** (option (b)): Optional investigation templates for known scenarios (K8s pod crash, DB latency), not core system replacement

## 15. Deferred

- Transport unification (SSE everywhere) — separate phase, requires War Room UI refactor
- Workflow event adapter — build when real consumer exists
- Parallel agent dispatch — after hypothesis engine is stable and safe-parallel steps are identified
- DAG view for investigations — Phase 4 DAG view can consume VirtualDag via new endpoint, but wiring is a separate task
- Investigation replay/time-scrubbing
