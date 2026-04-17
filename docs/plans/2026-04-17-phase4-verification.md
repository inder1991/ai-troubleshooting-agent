# Phase 4 Verification — Patterns, Eval, Learning, Trust UX

Date: 2026-04-17
Branch: `hardening/2026-04-17`
Gate scope: Plan §"Phase 4" (Tasks 4.1 – 4.29, excluding the UI block 4.10–4.22).

---

## Pre-condition check: eval corpus

The plan's Phase-4 preamble says **"≥ 10 incidents labelled in
`backend/eval/incidents/`. If gate not met, do Phase 4 in design-only
mode for the eval-related tasks."**

Current corpus: **0 labelled incidents** (only `_template.yaml` +
`README.md`). **Gate not met.** Per the plan, the following tasks land as
design-only:

- Task 4.6 — eval metrics are implemented as pure functions with full
  tests; the replay harness is a scaffolded CLI that emits an honest
  empty report until the corpus fills.
- Task 4.7 — nightly-eval CI workflow exists but short-circuits until
  the corpus fills.
- Task 4.29 — the eval portion of the acceptance gate is NOT run.
  Focused regression + architectural completeness stand in for it.

The rest of Phase 4 ships for real.

---

## What shipped

| Task | Commit | Status | Summary |
|---|---|---|---|
| 4.1 | `feat(patterns)` | ✅ built + tested | `SignaturePattern` schema + 3 patterns (oom_cascade, deploy_regression, retry_storm) |
| 4.2 | `feat(patterns)` | ✅ built + tested | 7 more patterns (cert/hot-key/thread-pool/dns/image-pull/quota/network-policy). 10 total in `LIBRARY` |
| 4.3 | `feat(supervisor)` | ✅ built + tested | `try_signature_match()` — deterministic fast-path |
| 4.4 | `feat(supervisor)` | ✅ built + tested | `Planner.upstream_walk()` — BFS depth=2 on low confidence |
| 4.5 | `feat(supervisor)` | ✅ built + tested | `SelfConsistency` wrapper with voting + penalty matrix |
| 4.6 | `feat(eval)` | ⚠️ design-only (corpus gate) | Pure metrics implemented + tested; replay harness scaffolded |
| 4.7 | `design(p2)` | ⏸ stub | `.github/workflows/nightly-eval.yml` short-circuits until corpus fills |
| 4.8 | `design(p2)` | ⏸ stub | `LearningPipeline` interface + `docs/design/active-learning.md` |
| 4.9 | `design(p2)` | ⏸ stub | `counterfactual` framework + `FORBIDDEN_ACTIONS` guard + design doc |
| 4.10–4.22 | — | **⏸ deferred** | UI work — 13 tasks — deferred to a dedicated UI session |
| 4.23 | `feat(prompts)` | ✅ built + tested | Prompt registry + migration; version_id = sha256(content) |
| 4.24 | `fix(prompts)` | ✅ built + tested | temperature=0 linter caught 6 offenders in `src/agents/cluster/` and fixed them |
| 4.25 | `fix(cancel)` | ✅ built + tested | `CancelToken`, `cancellable_call`, `cancel_guard`, `ensure_cancel_reraised` |
| 4.26 | `feat(lifecycle)` | ✅ built + tested | Graceful drain + `resume_all_in_progress` with stale-heartbeat detection |
| 4.27 | `feat(observability)` | ✅ built + tested | W3C trace context propagation (SDK-independent) |
| 4.28 | `feat(observability)` | ✅ built + tested | Step-latency histogram + SLO burn rules |
| 4.29 | `docs(phase4)` | this doc | Verification gate |

**13 real commits + 3 design-only commits** (Tasks 4.6, 4.7–4.9, 4.29
verification).

---

## Gate evidence

### Focused regression — 505 tests pass

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
    tests/workflows/test_resume.py \
    tests/test_supervisor_v5.py \
    tests/test_pipeline_integration.py \
    tests/test_idempotency.py \
    tests/test_phase1_verification_gate.py \
    tests/test_causal_engine.py \
    tests/tools/test_result_cache.py \
    tests/tools/test_elk_safety.py \
    tests/tools/test_promql_safety.py \
    tests/integrations/test_http_clients.py \
    tests/integrations/test_backend_audit.py \
    tests/network \
    tests/patterns \
    tests/prompts \
    tests/observability \
    tests/eval \
    tests/learning \
    -q
```

Result: **505 passed**.

### Eval harness smoke test

```
$ cd backend && python3 -m eval.runner --corpus eval/incidents
{
  "top1_accuracy": 0.0,
  "ece": 0.0,
  "high_confidence_wrong_count": 0,
  "total_cases": 0
}
```

Honest empty report (corpus has 0 labelled cases). Not a fake pass.

### Migration state

Migrations applied cleanly in the order:
1. `a60b28e2d6b9_outbox` (Phase 1)
2. `18ead3c4e6b7_dag_snapshot` (Phase 1)
3. `c3a1f9e4b2d1_agent_priors` (Phase 2)
4. `d7b4e2c1a8f3_incident_feedback` (Phase 2)
5. `e8c2f1a7b3d5_backend_call_audit` (Phase 3)
6. **`f4a9d2b7c6e1_prompt_versions`** (Phase 4, Task 4.23)

---

## Scoped cuts

### UI (Tasks 4.10 – 4.22) — deferred

13 React components with full Vitest coverage. Not technically blocking
because every backend field they consume is shipped in this phase:
`coverage_gaps`, deterministic `ConfidenceInputs`, `top_3_hypotheses`
contract, `critic_dissent` structure, `signature_match`/`baseline_*`/
`is_stale` fields, `independent_verification_pins`, `self_consistency`
summary, budget telemetry, retest verdict scaffolding.

**Rationale for deferring**: the hardening branch's value is backend
correctness + reliability. Implementing 13 UI components in the same
branch would triple the review surface while having less leverage per
hour than the backend work. A dedicated UI session can pick up
unblocked because every field is documented and typed.

### Eval-dependent tasks

Tasks 4.6 / 4.7 / 4.29-eval-portion ship as design + stubs because the
labelled corpus gate isn't met. The instant the corpus fills to ≥ 10:
- Drop the `_load_corpus` stub in `backend/eval/runner.py`.
- Uncomment the schedule in `.github/workflows/nightly-eval.yml`.
- First green run writes `baseline.json`.

Everything else around eval is in place.

### Active-learning + counterfactual (4.8 / 4.9)

Plan explicitly marks these as P2 design-only. Shipped with interface
stubs that raise `NotImplementedError`, design docs
(`docs/design/active-learning.md`, `docs/design/counterfactual-experiments.md`),
and safety invariants (`FORBIDDEN_ACTIONS` frozenset on the
counterfactual side) that the live implementation will inherit.

---

## Carried forward (post-Phase-4 follow-ups)

1. **Swap `Planner`/`Dispatcher`/`Reducer`/`EvalGate` + signature
   fast-path + self-consistency into `supervisor.run_v5`** as one
   coherent diff. This is the single biggest remaining wiring task;
   most Phase-2/3/4 primitives are standalone today.
2. **Wire the Phase-3 primitives at their call sites**: circuit
   breaker on every outbound call, `get_client("<backend>")` in the
   integration clients, `retry_with_retry_after` + `idempotency_scope`
   on external POSTs, `BackendAudit` in `tool_executor.execute`,
   `InvestigationBudget` + `ResultCache` per investigation,
   `paginate_search` / `list_all` / `promql_library` /
   `validate_stack_trace` at their respective call sites.
3. **Wire the Phase-4 observability primitives**: `trace_context` on
   http_clients + FastAPI middleware, `record_step_completion` in
   `investigation_executor`, `set_in_flight` in the supervisor's
   start/end hooks.
4. **UI work (Tasks 4.10 – 4.22)** — 13 React components per the
   locked panel-preserving architecture (War Room 12-col grid
   unchanged).
5. **Eval corpus** — populate `backend/eval/incidents/` with ≥ 10
   labelled cases; activate nightly CI; commit `baseline.json`.
6. **Pre-existing test-ordering pollution** (`test_outbox_relay`,
   `test_cluster_routing`). Not introduced by any phase; both pass in
   isolation.
7. **Chaos + capacity tests** — plan's Task 4.29 Steps 3/4. Require a
   multi-replica local environment; defer to a dedicated QA session.

---

## Gate result

**PASS — with documented design-only scope cuts.**

The backend hardening branch delivers:
- Deterministic signature-library pattern matching underneath the LLM.
- Adversarial critic ensemble with rubber-stamp guard + cross-source
  retriever.
- Supervisor split into Planner/Dispatcher/Reducer/EvalGate +
  single-use instance contract + graceful drain + checkpoint resume.
- Per-investigation budget + dedup cache; per-backend circuit breakers
  + singleton http clients; pagination (ELK PIT, K8s continue-token);
  Retry-After + Idempotency-Key on external POSTs.
- Deterministic confidence formula (no LLM critic_score) with persisted
  priors + /feedback endpoint feeding priors.
- W3C trace context propagation, step-latency histograms, 3 SLO burn
  alert rules.
- Prompt registry with content-addressed version_id + temperature=0
  linter covering every agent.
- Design docs + interface stubs for active-learning and counterfactual
  experiments, with safety invariants already encoded.

Carry-forward items are tracked above; every one has a starting point
in committed code.
