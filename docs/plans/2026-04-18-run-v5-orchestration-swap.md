# Run_v5 Orchestration Swap — Deep-Dive Plan

Date: 2026-04-18
Author: hardening branch author
Target branch: `hardening/2026-04-18-orchestration-swap` (off `main`)

---

## 1. Problem statement

The hardening branch (PR #24 merged) built six standalone orchestration units:
`Planner`, `Dispatcher`, `Reducer`, `EvalGate`, `SignatureMatcher`, `SelfConsistency`.
Plus adjacent units: `compute_confidence`, `CriticEnsemble`, `CriticRetriever`,
`ConfidenceCalibrator` (priors), `validate_stack_trace`, `InvestigationBudget`,
`ResultCache`, `@with_circuit_breaker`, `retry_with_retry_after`,
`idempotency_scope`, `BackendAudit`, `trace_context`, metrics registry, prompt
registry, cancellation primitives, `resume_all_in_progress`.

All are unit-tested. **None are called from `SupervisorAgent.run()` in
production.**

This plan rewires the supervisor to use them, so the hardening work actually
reaches investigations.

## 2. Current reality (code inventory)

### 2.1 Two entry points — naming clarification

`SupervisorAgent` exposes two run methods:

| Method | LOC | State type | Caller | Status |
|---|---|---|---|---|
| `run()` | ~260 | `DiagnosticState` | `routes_v4.py:886` | **Production path.** |
| `run_v5()` | ~65 | `DiagnosticStateV5` | `tests/test_supervisor_v5.py` | Test-only smoke path. |

The plan's "run_v5 swap" is shorthand; the actual swap target is **`run()`**.
`run_v5()` stays as a thin wrapper for the v5 smoke test.

### 2.2 What `run()` currently does (high-level phases)

```
run(initial_input, event_emitter, websocket_manager, on_state_created, investigation_executor):
  1. _claim_single_use()                        # Task 2.10, already wired
  2. Construct DiagnosticState from initial_input
  3. Expose state via on_state_created
  4. Loop up to max_rounds=10:
     a. next_agents = _decide_next_agents(state)     # ← Planner territory
     b. if empty → finalize (step 5)
     c. Dispatch (parallel via asyncio.gather OR    # ← Dispatcher territory
        sequential for mocked agents)
     d. Per result:
        - update_state_with_result                   # ← Reducer territory
          (~580 LOC of typed-state mutation)
        - evaluate_hypotheses_after_agent
        - emit summary
        - run critic validation (CriticAgent)        # ← CriticEnsemble territory
        - trigger re_investigation if challenged
     e. _update_phase + mocked-delay
     f. _enrich_reasoning_chain (after metrics)
     g. Human-in-loop repo confirmation (before change_agent)
  5. Finalize:
     a. _run_impact_analysis
     b. _query_past_incidents
     c. pick_winner_or_inconclusive(state.hypotheses)
     d. Emit hypothesis_winner | hypothesis_inconclusive
     e. Emit attestation_required (or auto_approved)
     f. Save PendingAction to Redis
  6. Compile token usage
```

### 2.3 Crosscutting concerns (must preserve)

These do NOT live in the 4 orchestration units today — they must be kept:

- **Mocked-agent demo pacing** (sequential dispatch, thinking messages, delays)
- **Re-investigation loop** (critic-driven, max 1 cycle)
- **Phase transitions** (`_update_phase`) driving UI state machine
- **Reasoning manifest** (`add_reasoning_step`)
- **Hypothesis tracker** (`HypothesisTracker`, `evaluate_hypotheses`, `pick_winner_or_inconclusive`)
- **Attestation / auto-approval** at completion
- **PendingAction** for Redis-backed resume
- **Human-in-the-loop** channels (repo confirmation, repo mismatch, fix approval, code_agent questions)
- **Impact analysis + past-incident query** at finalize
- **Token usage compilation**

**None of these belong in `Planner`/`Dispatcher`/`Reducer`/`EvalGate`.**
They are orchestrated *around* the inner loop.

### 2.4 Contract shape — new units vs existing code

| New unit | Expects | Current supervisor produces | Gap |
|---|---|---|---|
| `Planner.next(PlannerInputs)` | `list[str]` agent names | `_decide_next_agents` returns `list[str]` | Need a `_planner_inputs_from_state(state)` adapter. |
| `Dispatcher.dispatch_round([AgentSpec])` | `list[StepResult]` | `asyncio.gather(*_dispatch_agent(...))` | Wrap `_dispatch_agent` as the executor callable. |
| `Reducer.reduce([StepResult])` | `ReducedRound` (pins, completed, failed, new_signal) | `_update_state_with_result` (580 LOC per-agent typed state) | Reducer handles the bookkeeping half; `_update_state_with_result` stays as post-reduce per-agent adapter. |
| `EvalGate.is_done(EvalGateInputs)` | `(is_done, reason)` | `next_agents == []` | Adapter `_eval_gate_inputs_from_state(state, round)`. |
| `try_signature_match(signals)` | `SignatureHypothesis \| None` | Not called | Call at entry of `run()`. |
| `SelfConsistency.run(...)` | `SelfConsistencyResult` | Not called | Optional outer wrapper when `initial_input["self_consistency"]=True`. |

### 2.5 Confidence path today

```
per-agent pin:
  pin.confidence (set by agent)
per finding:
  CriticAgent._evaluate_finding → CriticVerdict
  finding.confidence (raw 0..1)
  finding.critic_verdict → critic_verdict_count
per state:
  update_confidence_ledger(state.confidence_ledger, state.evidence_pins)
    → averages per-evidence-type → weighted_final
  state.overall_confidence = … some blend …
```

**Today `compute_confidence(ConfidenceInputs)` is never called.** The
deterministic confidence formula shipped in Phase 2 is dead code in
production.

### 2.6 Critic path today

```
SupervisorAgent(__init__):
  self._critic = CriticAgent()   # src/agents/critic_agent.py — legacy, single-role
run() per finding:
  self._critic._evaluate_finding(finding, metrics_context, k8s_context)
    → CriticVerdict {verdict, confidence_in_verdict, reasoning}
```

**The new `CriticEnsemble` (advocate/challenger/retriever/judge) is never
called.** Phase-2 adversarial-roles work is dead code in production.

## 3. Target architecture

### 3.1 New `run()` shape

```python
async def run(self, initial_input, event_emitter, websocket_manager=None,
              on_state_created=None, investigation_executor=None):
    self._claim_single_use()
    self._event_emitter = event_emitter
    self._investigation_executor = investigation_executor

    state = self._build_initial_state(initial_input)
    if on_state_created:
        on_state_created(state)

    await self._announce_start(state, event_emitter)

    # Fast-path: signature match (Task 4.3)
    sig_hypothesis = try_signature_match(self._extract_signals_from_state(state))
    if sig_hypothesis and sig_hypothesis.confidence >= 0.80:
        state = await self._fast_path_verify(state, sig_hypothesis, event_emitter)
        await self._finalize(state, event_emitter)
        return state

    # Main loop: Planner → Dispatcher → Reducer → EvalGate
    planner = Planner()
    dispatcher = Dispatcher(
        executor=lambda spec: self._dispatch_agent(spec.agent, state, event_emitter),
        timeout_per_agent_s=60.0,
    )
    reducer = Reducer()
    gate = EvalGate()

    round_num = 0
    rounds_since_new_signal = 0
    while True:
        gate_decision = gate.is_done(self._eval_gate_inputs(state, round_num, rounds_since_new_signal))
        if gate_decision.is_done:
            state.diagnosis_stop_reason = gate_decision.reason
            break

        planner_inputs = self._planner_inputs(state)
        agent_names = planner.next(planner_inputs)
        if not agent_names:
            state.diagnosis_stop_reason = "planner_empty"
            break

        specs = [AgentSpec(agent=a) for a in agent_names]
        results = await dispatcher.dispatch_round(specs)
        reduced = reducer.reduce(results)

        # Fold per-agent typed state (retained from legacy path)
        for r in results:
            if r.status == "ok" and r.value:
                await self._update_state_with_result(state, r.agent, r.value, event_emitter)
                await self._evaluate_hypotheses_after_agent(state, r.agent, r.value, event_emitter)
                await self._run_critic_ensemble_for_new_findings(state, event_emitter)

        state.agents_completed.extend(reduced.agents_completed)
        for failed in reduced.failed_agents:
            record_coverage_gap(state, failed, "dispatch failed")

        rounds_since_new_signal = 0 if reduced.new_signal else rounds_since_new_signal + 1
        round_num += 1

        self._update_phase(state, event_emitter)
        await self._maybe_enrich_reasoning(state, event_emitter, results)
        await self._maybe_request_repo_confirmation(state, event_emitter)

    await self._finalize(state, event_emitter)
    return state
```

~80 lines vs ~260 today. Every crosscutting concern has a dedicated helper; the
loop is a clean Planner→Dispatcher→Reducer→EvalGate cycle.

### 3.2 Confidence rewire

Replace `update_confidence_ledger` + `state.overall_confidence` blend with:

```python
def _compute_state_confidence(self, state) -> float:
    inputs = ConfidenceInputs(
        evidence_pin_count=len(state.evidence_pins),
        source_diversity=len({p.evidence_type for p in state.evidence_pins}),
        baseline_delta_pct=self._max_baseline_delta(state.evidence_pins),
        contradiction_count=sum(1 for cv in state.critic_verdicts if cv.verdict == "challenged"),
        signature_match=state.signature_match is not None,
        topology_path_length=len(state.evidence_graph.root_causes or []),
    )
    return compute_confidence(inputs)
```

Stored per-round on `state.overall_confidence`. Emitted in every breadcrumb so
the UI shows the deterministic value.

### 3.3 Critic rewire

Replace `CriticAgent._evaluate_finding` (per-finding, single-role LLM) with
`CriticEnsemble.evaluate(finding, evidence_pins)` (advocate + challenger +
retriever + judge). One ensemble call per finding on first encounter; results
cached on the finding.

`state.critic_verdicts` stays for UI compatibility; each row now carries
`advocate_verdict` / `challenger_verdict` / `judge_verdict` for the
`winner_critic_dissent` field the UI consumes.

### 3.4 Winning-agents wiring

When finalize elects a winner:

```python
state.winning_agents = self._agents_that_contributed_to(state.hypothesis_result.winner, state)
# persisted into the DAG snapshot payload via OutboxWriter
```

Closes the `/feedback` priors-update loop.

### 3.5 SelfConsistency as opt-in wrapper

```python
if initial_input.get("self_consistency_runs", 1) > 1:
    state = await self._run_with_self_consistency(initial_input, event_emitter, ...)
else:
    state = await self._run_single(initial_input, event_emitter, ...)
```

### 3.6 Prompt versioning

Each agent's `__init__` calls `PromptRegistry().get(self.agent_name)` and
stamps `finding.prompt_version_id = pinned.version_id` on every finding it
produces. Supervisor calls `await registry.ensure_persisted(name)` for each
registered agent on first use so the row exists.

### 3.7 Call-site migrations (Phase-3 primitives)

| Primitive | Site | Change |
|---|---|---|
| `InvestigationBudget` | `routes_v4._execute_investigation` | Construct per investigation; inject into `SupervisorAgent.__init__` via context. `tool_executor.execute` calls `await budget.charge_tool_call(name)` before dispatch. |
| `ResultCache` | `tool_executor.execute` | Wrap each tool call; cache HIT bypasses budget. |
| `@with_circuit_breaker` | Per-agent outbound wrappers (log_agent, metrics_agent, k8s_agent, tracing_agent) | Decorate the method that actually makes an HTTP call. |
| `get_client(backend)` | `jira_client`, `confluence_client`, `github_client`, `remedy_client`, `ElasticsearchClient`, `PrometheusClient` | Replace `httpx.AsyncClient()` construction with `get_client(...)`. |
| `retry_with_retry_after` + `idempotency_scope` | External-POST paths in integration clients | Wrap `client.post(...)` with both. |
| `BackendAudit.timed_call` | `tool_executor.execute` | Wrap every dispatch with `async with timed_call(audit, ...)`. |
| `paginate_search` | `log_agent.search` | Replace the `from/size` call with an async iteration. |
| `list_all` | `k8s_agent` list call sites | Replace each `list_namespaced_pod(...)` with `await list_all(client.list_namespaced_pod, ...)`. |
| `promql_library` | `metrics_agent.analyze` | Use `build_golden_signals`, `query_alerts_firing`, etc. |
| `validate_stack_trace` | `code_agent` before returning frames | Fail stale frames to `is_stale=True` so the UI's StackTraceTelescope warning fires. |
| `trace_context.inject_traceparent` | `integrations/http_clients.get_client` default headers | Inject on every outbound request via an httpx `event_hook`. |
| `record_step_completion` | `investigation_executor.run_step` | Record on success / timeout / error. |
| `set_in_flight` | supervisor start/end | +1 on start, -1 on finalize. |
| SIGTERM handler + `resume_all_in_progress` | `api/main.py` | Wire into the lifespan shutdown + startup hooks. |

## 4. Risks + mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Loop-shape change breaks existing pipeline tests (there are ~13 tests exercising `run()` end-to-end). | High | **Commit-by-commit TDD.** Every swap commit lands with no test regressions. Use test_supervisor_v5 + test_pipeline_integration as the harness. |
| `_update_state_with_result` is 580 LOC of typed state; calling it with bad inputs corrupts state. | High | Do NOT refactor `_update_state_with_result` in this plan. Treat it as an opaque post-reduce step called exactly once per successful result. |
| Critic swap changes verdict shape → UI breaks. | Medium | Ship `CriticVerdict` compatibility shim: `CriticEnsemble.evaluate` → legacy `CriticVerdict` with `advocate_verdict`/`challenger_verdict`/`judge_verdict` additive fields. UI reads optional fields gracefully. |
| Confidence value shifts visibly during rollout (deterministic formula ≠ Bayesian blend). | Medium | Feature-flag via env var `DIAGNOSTIC_CONFIDENCE_MODE=deterministic\|legacy`. Default `deterministic`. Keep legacy for one release as safety net. |
| Priors updates via `/feedback` cause non-determinism across runs. | Medium | Priors today influence NOTHING (they're persisted but unread). Stay read-only in this swap; wire priors into scoring in a follow-up so the rollout is reviewable. |
| `_dispatch_agent` has mock/InvestigationExecutor/prerequisites/error-handling paths. Wrapping as Dispatcher executor must preserve every path. | High | Executor callable delegates to existing `_dispatch_agent` verbatim. Dispatcher just drives the loop. |
| HiTL repo confirmation needs to interleave with the loop (today it's inside `for round_num`). | Medium | Keep `_maybe_request_repo_confirmation` inside the new loop body post-reduce. Unchanged semantics. |
| SelfConsistency wrapper triples LLM cost. | Low | Opt-in via request flag. Default off. |
| The rewritten loop runs signature fast-path on empty signals → degenerate match. | Low | Guard `try_signature_match` call with `if signals and len(signals) >= 2`. |

## 5. Staged plan (TDD, one commit per step)

### Stage A — Adapters (no behaviour change)

**A.1.** Add `_planner_inputs(state)` + `_eval_gate_inputs(state, round, rss)` helpers on SupervisorAgent. Private methods. Unit test: given a state, returns the expected dataclass. Zero effect on `run()`.

**A.2.** Add `_extract_signals_from_state(state) -> list[Signal]` — translates
state evidence into the `Signal` enum vocabulary the signature library uses.
Unit test: OOM events → `oom_killed` + `memory_pressure`; deploy events → `deploy`.

**A.3.** Add `_compute_state_confidence(state) -> float` wrapping
`compute_confidence` with the legacy fallback path. Env-flagged:

```python
if os.getenv("DIAGNOSTIC_CONFIDENCE_MODE", "deterministic") == "legacy":
    return self._legacy_compute_confidence(state)
return compute_confidence(self._confidence_inputs(state))
```

Unit test both branches.

**Gate:** existing `run()` still works unmodified. New helpers have tests but
no call sites yet.

### Stage B — Dispatcher swap (lowest risk)

**B.1.** Introduce a Dispatcher in `run()`'s inner loop. Replace the
`asyncio.gather` block with `await dispatcher.dispatch_round(specs)`. Keep
sequential-mocked-agent fallback as a branch that skips the Dispatcher.
Executor callable = wrapper around existing `_dispatch_agent`. Every test
that touches `run()` must stay green.

**B.2.** Map `StepResult` back to the existing `agent_results = list(zip(names,
values_or_exceptions))` shape the rest of the loop expects. No downstream
behaviour change.

**Gate:** full pipeline tests green. Supervisor observably identical.

### Stage C — Reducer swap

**C.1.** Introduce a `Reducer` instance. Feed it the `StepResult` list.
Consume `ReducedRound.agents_completed` / `failed_agents` / `new_signal`.
Keep the existing `_update_state_with_result` call — runs per successful
result as before.

**C.2.** Add `rounds_since_new_signal` tracking using
`reduced.new_signal`. Not yet used by anything (EvalGate comes in D).

**Gate:** full pipeline tests green.

### Stage D — EvalGate swap + stop reasons

**D.1.** Replace the `for round_num in range(max_rounds)` + `if not
next_agents` exit with `while not gate.is_done(...)`. Stop reason stored on
`state.diagnosis_stop_reason`. Surface via event emitter and API response.

**D.2.** Update `/api/v4/session/{id}/findings` response to include
`stop_reason`. Frontend types extended; UI badge renders it (trivially via
CriticDissentBanner pattern — new optional field).

**Gate:** full pipeline tests green + 1 new test asserting `stop_reason`
appears and takes legal values.

### Stage E — Planner swap

**E.1.** Replace `_decide_next_agents(state)` call with
`planner.next(self._planner_inputs(state))`. **Keep `_decide_next_agents` as a
fallback** under `DIAGNOSTIC_PLANNER_MODE=legacy`.

**E.2.** Compare outputs in a pytest side-by-side test: for 20 synthetic
states, `planner.next(...)` must return a subset (or equal) of
`_decide_next_agents(...)`. No unexpected additions.

**Gate:** full pipeline tests green with `DIAGNOSTIC_PLANNER_MODE=deterministic`.

### Stage F — Confidence formula swap (behind flag)

**F.1.** Wire `_compute_state_confidence` into the loop, replacing
`update_confidence_ledger` + `state.overall_confidence` blend.

**F.2.** Record both values in telemetry for a release: legacy value and
deterministic value side-by-side so operators can see the delta.

**Gate:** full pipeline tests green. Pipeline-integration tests updated to
assert the new formula's output where they check confidence.

### Stage G — Critic ensemble swap

**G.1.** Replace `CriticAgent._evaluate_finding` call with
`CriticEnsemble.evaluate`. Adapter builds `CriticVerdict` for UI compatibility
plus attaches `advocate_verdict` / `challenger_verdict` / `judge_verdict`.

**G.2.** Wire `winner_critic_dissent` onto `findings.hypothesis_result` so the
UI banner lights up.

**G.3.** Add `CriticRetriever` injection when tool_executor is available.

**Gate:** full pipeline tests green.

### Stage H — Signature fast-path

**H.1.** At the top of `run()`, call `try_signature_match(signals)`. If match
≥ 0.80 confidence: run **one** `CriticEnsemble.evaluate` pass to verify;
if confirmed, set `state.hypothesis_result` directly and skip to finalize.

**H.2.** Emit `signature_matched_<name>` stop reason so the UI shows the
pattern pill + the "why did it stop?" answer.

**Gate:** new test — a synthetic state with OOM signals matches `oom_cascade`
and returns without entering the main loop.

### Stage I — Winning agents wiring

**I.1.** Compute `state.winning_agents` at finalize from the evidence pins
backing `state.hypothesis_result.winner`.

**I.2.** Persist it in the DAG snapshot payload (OutboxWriter already UPSERTs
snapshots per step; add field to payload). `/feedback` endpoint now finds real
agents to update priors for.

**Gate:** test for `/feedback` priors update — now the `priors_updated` list
is non-empty for a real investigation run.

### Stage J — Self-consistency opt-in

**J.1.** Request accepts `self_consistency_runs` param. When set > 1,
supervisor runs `SelfConsistency.run` as outer wrapper; final state merges the
result. UI badge renders the outcome.

**Gate:** explicit test — opt-in with 3 runs returns
`self_consistency.n_runs=3`.

### Stage K — Call-site migrations (Phase-3 primitives)

One commit per primitive, in this order (highest-ROI first):

**K.1.** `@with_circuit_breaker` on every agent's outbound call — protects
against backend outages. Test: simulated Prom-down produces an "open" breaker;
supervisor continues with `coverage_gaps` populated.

**K.2.** `BackendAudit` in `tool_executor.execute`. Test: one tool call →
one audit row with non-zero duration.

**K.3.** `InvestigationBudget` in `tool_executor.execute`. Test: 101st tool
call raises BudgetExceeded; supervisor catches it and records a coverage gap.

**K.4.** `ResultCache` in `tool_executor.execute`. Test: duplicate tool call
within one investigation is served from cache and doesn't count against
budget.

**K.5.** `get_client(backend)` in integration clients. Test: two investigations
share the same underlying connection pool.

**K.6.** `retry_with_retry_after` + `idempotency_scope` on external POSTs.
Test: Jira 429 with `Retry-After: 2` sleeps 2s then retries with same key.

**K.7.** `paginate_search` in `log_agent.search`. Test: 12k-hit corpus returns
all 12k hits with PIT cleanup.

**K.8.** `list_all` in k8s list call sites. Test: 2300-pod namespace returns
all 2300 via continue-token loop.

**K.9.** `promql_library` in `metrics_agent`. Test: golden-signals query
generation passes the safety middleware.

**K.10.** `validate_stack_trace` in `code_agent`. Test: stale line flagged;
the UI's stale-line warning appears.

**K.11.** `trace_context` on `http_clients`. Test: outbound call carries a
`traceparent` header.

**K.12.** `record_step_completion` + `set_in_flight` in
`investigation_executor`. Test: histogram samples emitted per step.

**K.13.** `PromptRegistry` on agent init + `prompt_version_id` on findings.
Test: every finding has a non-empty `prompt_version_id`.

**K.14.** SIGTERM + `resume_all_in_progress` in `api/main.py`. Test:
simulated stale snapshot is picked up on startup.

### Stage L — Verification gate

**L.1.** Full suite green.

**L.2.** 30-minute soak test against local Postgres/Redis: 50 concurrent
investigations. Assert:
- No `BudgetExceeded` on healthy runs.
- Circuit breakers stay closed.
- Audit rows: ≥ 1 per tool call, 0 drops on `_drops` counter.
- Step-latency p95 < 30s.

**L.3.** Chaos: kill Prometheus for 60s mid-soak. Assert:
- Breaker opens within the configured threshold.
- Investigations complete (with reduced confidence).
- Coverage gaps list `metrics_agent: prometheus circuit open`.

**L.4.** Cancellation: mid-investigation user cancel. Assert: tear-down within
2s; no orphaned Redis locks.

**L.5.** Resume: kill supervisor pod mid-investigation. Assert: next pod
picks up the run from the last outbox event within 60s.

**L.6.** Document + commit.

## 6. Effort estimate

| Stage | Commits | Est. time |
|---|---|---|
| A — Adapters | 3 | 1 h |
| B — Dispatcher swap | 2 | 1 h |
| C — Reducer swap | 2 | 1 h |
| D — EvalGate + stop reasons | 2 | 1 h |
| E — Planner swap | 2 | 1 h |
| F — Confidence swap | 2 | 1 h |
| G — Critic ensemble swap | 3 | 2 h |
| H — Signature fast-path | 2 | 1 h |
| I — Winning agents wiring | 2 | 1 h |
| J — Self-consistency | 1 | 30 min |
| K — Call-site migrations | 14 | 5 h |
| L — Verification | 1 | 2 h |

**Total:** ~36 commits, ~17 hours focused work.

Can be split across 2 sessions:
- **Session 1 (Stages A–J):** the supervisor rewire. ~10 h.
- **Session 2 (Stages K–L):** call-site migrations + verification. ~7 h.

## 7. Rollback plan

Every swap stage is flag-gated via env var:

```
DIAGNOSTIC_PLANNER_MODE=deterministic|legacy
DIAGNOSTIC_CONFIDENCE_MODE=deterministic|legacy
DIAGNOSTIC_CRITIC_MODE=ensemble|legacy
DIAGNOSTIC_SIGNATURE_FAST_PATH=on|off
```

Rollback = flip the env var on the deployment. No code revert required for
the first 2 weeks post-merge. After 2 weeks of clean telemetry, the flags and
legacy code paths are deleted.

## 8. Open questions for review

1. **`_update_state_with_result` (580 LOC)** — keep it verbatim, or split per
   agent? **Recommendation:** keep it verbatim in this swap; refactor in a
   dedicated follow-up.
2. **Confidence formula migration** — cut over fully, or A/B for a release?
   **Recommendation:** A/B behind env flag; flip deterministic after 1 week
   of comparison telemetry.
3. **Critic ensemble retriever** — injected only when `tool_executor`
   available (production)? Or always? **Recommendation:** only in production;
   tests use a fake.
4. **SelfConsistency default** — off (opt-in per request) or on (default 3
   runs)? **Recommendation:** off; enable per request via UI toggle. Enabling
   by default triples LLM cost.
5. **Priors influence on scoring** — wire priors into `compute_confidence` in
   this swap, or defer? **Recommendation:** DEFER. Priors read-only in this
   swap; follow-up PR wires them in once feedback data accumulates.

## 9. Success criteria (visible to users)

After the swap lands:

- Investigations have an explicit **stop reason** (`max_rounds_reached`,
  `high_confidence_no_challenges`, `coverage_saturated_no_new_signal`,
  `signature_matched_<name>`, `planner_empty`).
- **Signature fast-path** skips the full ReAct loop for recognised patterns —
  OOM-cascade-shaped incidents complete in seconds, not minutes.
- **Deterministic confidence** — same inputs, same number, always.
- **Critic dissent** surfaces in the UI when the winning hypothesis is
  contested.
- **Coverage gaps** are populated for every skipped/failed agent with
  precise reasons.
- **Audit table** has ≥ 1 row per external call.
- **Priors move** when users submit `/feedback` for a completed investigation.
- **Budget + dedup cache + circuit breakers** are enforced on every tool
  call.
- **Cancel propagates** end-to-end in ≤ 2 s.
- **Pod restart resumes** investigations from the last checkpoint.
- **Retry-After + Idempotency-Key** on every external POST — no duplicate
  Jira/GitHub issues on retry.

## 10. Not in scope

Deferred to follow-up PRs:

- UI wiring for `stop_reason` / `winning_agents` / ensemble dissent (done in
  PR #26 components, but the render-site in Investigator/EvidenceFindings/
  Navigator needs Stage D-J fields to actually arrive).
- Priors feeding back into `compute_confidence` (open-question 5).
- `_update_state_with_result` refactor (open-question 1).
- Eval corpus + nightly CI activation (gated on ≥ 10 labelled incidents).
- Additional signature patterns beyond the 10 shipped (Phase-4 carry-over).
- OpenShift tools (Phase-3 scoped cut).
- Feature-flag integration (Phase-3 scoped cut).
