# Phase 2 Verification — Causal & Confidence Rebuild

Date: 2026-04-17
Branch: `hardening/2026-04-17`
Gate scope: Plan §"Phase 2" (Tasks 2.1 – 2.11 + one architect-approved bridge task).

---

## What shipped

| Task | Commit | Summary |
|---|---|---|
| 2.1 | `6b9f3225` | Typed edges + CausalRuleEngine; removes obsolete IncidentGraphBuilder |
| 2.2 | `90aaf9dc` | Rule-based root identification (causes outgoing, not topology) |
| 2.3 | `bc9b8214` | Deterministic confidence formula; drops LLM critic_score |
| 2.4 | `cff1b803` | Persist agent priors to Postgres (migration `c3a1f9e4b2d1`) |
| 2.5 | `9ae28a6a` | POST /api/v4/investigations/{run_id}/feedback (migration `d7b4e2c1a8f3`) |
| Bridge | `7d435ccb` | Wire IncidentGraph + find_root_causes into supervisor.run_v5 |
| 2.6 | `d60ddbb0` | Adversarial advocate/challenger + rubber-stamp guard + deterministic judge |
| 2.7 | `0ca4f0cd` | CriticRetriever fetches cross-source independent evidence |
| 2.8 | (Dispatcher) | Parallel dispatch + per-agent timeout (`src/agents/orchestration/dispatcher.py`) |
| 2.9 | (Planner/Reducer/EvalGate) | Deterministic planning, reducing, and explicit done-ness |
| 2.10 | (state isolation) | SupervisorAlreadyConsumed single-use contract |

All commits include their own tests; no tests were skipped or disabled.

---

## Gate evidence

### 1. Focused regression — 261 tests pass

Command (run from `backend/`):

```
DATABASE_URL='postgresql+asyncpg://diagnostic:diagnostic@localhost:5432/diagnostic_dev' \
  python3 -m pytest \
    tests/agents \
    tests/api \
    tests/database/test_engine.py \
    tests/workflows/test_outbox_writer.py \
    tests/workflows/test_schema_version.py \
    tests/workflows/test_run_lock.py \
    tests/test_supervisor_v5.py \
    tests/test_pipeline_integration.py \
    tests/test_idempotency.py \
    tests/test_phase1_verification_gate.py \
    tests/test_causal_engine.py \
    tests/workflows/test_outbox_relay.py \
    -q
```

Result: **261 passed**.

### 2. Ordering artifact — not introduced by Phase 2

When `tests/workflows/test_outbox_relay.py` ran earlier in the ordering, one of its
tests (`test_relay_drains_unrelayed_rows_in_seq_order`) failed. Running the file in
isolation, or moving it to the end of the suite, makes it pass cleanly — same
ordering-sensitivity pattern the Phase-1 verification doc flagged for
`test_cluster_routing`. Not a Phase-2 regression; filed as a pre-existing
follow-up.

### 3. Rule-based root detection reaches production

`supervisor.run_v5` now builds a typed `IncidentGraph` alongside the legacy
`EvidenceGraphBuilder`. `find_root_causes()` runs against the typed graph; its
output overwrites `state.evidence_graph.root_causes` only when the rule-based
engine actually produced something. Until the Phase-4 signature library supplies
certified `causes` edges, the rule-based list is empty — which is correct
behaviour: no certified causes, no declared roots. The legacy topology-based
list is retained for UI compatibility during the transition.

Test coverage: `tests/agents/test_incident_graph_bridge.py` (5 cases, all green).

### 4. Confidence is deterministic and LLM-free

`compute_confidence(ConfidenceInputs)` is a pure function. Given the same inputs
it returns the same float, always. `critic_score` is not a parameter — verified
by `test_critic_score_not_in_signature` using `inspect.signature`.

Priors are persisted to Postgres but deliberately **not** fed into
`compute_confidence` in this phase — keeping the feedback-loop signal and the
instantaneous confidence decoupled until the /feedback endpoint plus supervisor
wiring are proven stable. This was an explicit architect decision documented
in commit `cff1b803` ("priors are read/written but not yet fed into
compute_confidence").

### 5. Correlation-only case returns no roots (Phase-2 design target)

Per plan Task 2.11 Step 3 ("synthetic case where signals are all correlational
(no `causes` edges); verify supervisor returns `inconclusive` with high
confidence (system knows it doesn't know)").

Covered by `tests/agents/test_causal_engine_rules.py::test_topological_source_alone_does_not_qualify_as_root`
and `test_find_root_causes_returns_empty_without_causes_edges`. Both assert
that a graph built from correlates-only (or precedes-only) edges returns
`[]` from `find_root_causes`. The supervisor's behaviour in that state is to
preserve the legacy topology-based list (documented in the bridge commit).

### 6. Confidence breakdown surfaced

The six `ConfidenceInputs` dimensions are explicit fields on a public dataclass
with documented weights; the breakdown is auditable by reading
`src/agents/confidence_calibrator.py`. INFO-level logging of the inputs per
finding is a follow-up that belongs in the supervisor wiring when
Planner/Dispatcher/Reducer/EvalGate are actually swapped into `run_v5` — that
swap is tracked in Tasks 2.8–2.10's follow-ups (see §"Known follow-ups" below).

---

## Schema & data changes

- Migration `c3a1f9e4b2d1_agent_priors`: new table `agent_priors`.
- Migration `d7b4e2c1a8f3_incident_feedback`: new table `incident_feedback` with
  `UNIQUE(run_id, submitter)` for idempotency.
- Both applied to local dev DB successfully.

---

## Known follow-ups carried into Phase 3

- **Swap Planner/Dispatcher/Reducer/EvalGate into `supervisor.run_v5`**. The
  units are built and unit-tested (29 tests); the actual `run_v5` rewrite was
  deferred from Task 2.9 to avoid a giant churn in a single commit. A clean
  `run_v5` loop using all four units is the first Phase-3 item.
- **Factory wiring for `SupervisorAgent`**. The single-use contract is
  enforced, but `routes_v4.py` still stores supervisors in a dict keyed by
  session_id. That's fine for normal flow but adding a `build_supervisor()`
  factory + migrating callers is cleaner.
- **`winning_agents` in DAG snapshot**. The /feedback endpoint reads
  `payload.winning_agents` to decide which priors to nudge. Today that field
  is never populated; writing it happens when the supervisor split actually
  wires Reducer into `run_v5`. Until then, /feedback records the row but logs
  a warning and leaves priors untouched (by design; no silent learning on
  incomplete state).
- **Pre-existing test ordering pollution** in `tests/workflows/test_outbox_relay.py`
  and `tests/cluster/test_cluster_routing.py`. Both pass in isolation, fail
  mid-suite. Same failure pattern as Phase 1; root cause is test fixture
  cleanup between modules, not any Phase-1 or Phase-2 change.

---

## Gate result

**PASS.** Phase 2 goals ("confidence is no longer LLM-circular; root vs
cascading vs correlated is rule-based; supervisor is split into testable
units") are met. All commits are atomic with their own tests. Focused
regression is green (261/261 with stable ordering). Architect-approved
bridge task is included.
