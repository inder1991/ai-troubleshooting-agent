# Orchestration Swap — Verification Gate

Date: 2026-04-18
Branch: `hardening/2026-04-18-orchestration-swap`
Plan: `docs/plans/2026-04-18-run-v5-orchestration-swap.md`

## What shipped

| Stage | Commit | Status |
|---|---|---|
| Plan | `c5ebfe12` | 594-line deep-dive doc |
| A.1 | `544474a0` | state_adapters (planner_inputs + eval_gate_inputs) |
| A.2 | `e76b27e8` | signal_extractor for fast-path matcher |
| A.3 | `99b9d38c` | confidence_adapter with env-flag mode |
| B | `5ff2f25a` | Dispatcher owns parallel fan-out in run() |
| C | `556d0efa` | Reducer summarises each round for stall detection |
| D | `a7ab1045` | EvalGate drives the loop + explicit stop_reason on API |
| E | `030ddcdb` | Planner swap gated by DIAGNOSTIC_PLANNER_MODE |
| F | `75158e29` | Deterministic confidence (default) + legacy fallback |
| G | (sha) | CriticEnsemble behind DIAGNOSTIC_CRITIC_MODE |
| H | (sha) | Signature fast-path at run() entry |
| I | (sha) | winning_agents wired through DAG snapshot |
| J | (sha) | self_consistency state field + API surface |
| K subset | (sha) | record_step_completion + prompt-registry boot + resume scan |
| L | this doc | Verification gate |

## Env flags introduced

| Flag | Values | Default |
|---|---|---|
| `DIAGNOSTIC_PLANNER_MODE` | `legacy` \| `deterministic` | `legacy` |
| `DIAGNOSTIC_CONFIDENCE_MODE` | `deterministic` \| `legacy` | `deterministic` |
| `DIAGNOSTIC_CRITIC_MODE` | `legacy` \| `ensemble` | `legacy` |
| `DIAGNOSTIC_SIGNATURE_FAST_PATH` | `off` \| `on` | `off` |
| `DIAGNOSTIC_RESUME_ON_STARTUP` | `off` \| `on` | `off` |
| `AGENT_DISPATCH_TIMEOUT_S` | float seconds | `120.0` |

Rollback = flip an env var. Zero code revert needed.

## Gate evidence

### Focused regression — 546 tests

Command (from `backend/`):

```
DATABASE_URL='postgresql+asyncpg://diagnostic:diagnostic@localhost:5432/diagnostic_dev' \
  python3 -m pytest \
    tests/agents tests/api tests/database/test_engine.py \
    tests/workflows/test_outbox_writer.py tests/workflows/test_schema_version.py \
    tests/workflows/test_run_lock.py tests/workflows/test_resume.py \
    tests/test_supervisor_v5.py tests/test_pipeline_integration.py \
    tests/test_idempotency.py tests/test_phase1_verification_gate.py \
    tests/test_causal_engine.py tests/tools \
    tests/integrations/test_http_clients.py tests/integrations/test_backend_audit.py \
    tests/network tests/patterns tests/prompts tests/observability \
    tests/eval tests/learning \
    -q
```

Result: **546 passed** — no regressions across any hardening-track surface.

Pre-existing `tests/workflows/test_investigation_executor_idempotency.py` excluded from full-run (fails to import due to a `from backend.tests...` path — pollution documented in Phase 1/2/3 gate docs; not introduced by this branch).

### API response shape — new fields confirmed

`/api/v4/session/{id}/findings` now returns:
- `coverage_gaps` (Phase-1)
- `diagnosis_stop_reason` (Stage D)
- `signature_match` (Stage H)
- `winning_agents` (Stage I)
- `self_consistency` (Stage J)

All five are optional / backward-compatible. UI components from PR #26 read them when present.

### Behaviour matrix — default vs opt-in

| Component | Default behaviour | Opt-in behaviour |
|---|---|---|
| Loop structure | `EvalGate → Planner → Dispatcher → Reducer` | same |
| Planner | Legacy `_decide_next_agents` state-machine | `Planner.next()` with `DIAGNOSTIC_PLANNER_MODE=deterministic` |
| Confidence | Deterministic formula (`compute_state_confidence`) | Legacy running-average with `DIAGNOSTIC_CONFIDENCE_MODE=legacy` |
| Critic | Legacy `CriticAgent._evaluate_finding` | `CriticEnsemble.evaluate()` with `DIAGNOSTIC_CRITIC_MODE=ensemble` |
| Signature fast-path | Off | On with `DIAGNOSTIC_SIGNATURE_FAST_PATH=on` |
| `stop_reason` | Always populated at loop exit | — |
| `winning_agents` | Always populated at finalize (seed = agents_completed) | — |
| `signature_match` | Only when fast-path flag is on AND pattern matches | — |
| `self_consistency` | `None` unless a route-layer wrapper runs N-shot | — |
| Step-latency metrics | Always recorded | — |
| Prompt registry boot | Always runs on startup (idempotent) | — |
| Resume scan | Log-only scan if `DIAGNOSTIC_RESUME_ON_STARTUP=on`, otherwise off | — |

## Carry-forward / deferred

### Phase-3 call-site migrations — status

Originally listed as a 14-item follow-up block. The branch has since knocked most of them off:

| Migration | Status in PR #27 |
|---|---|
| K.1 `@with_circuit_breaker` on agent outbound calls | ✅ Shipped at the tool_executor layer (cleaner boundary than per-agent decoration) |
| K.2 `BackendAudit.timed_call` in `tool_executor.execute` | ✅ Shipped |
| K.3 `InvestigationBudget.charge_tool_call` in `tool_executor.execute` | ✅ Shipped |
| K.4 `ResultCache.get_or_compute` in `tool_executor.execute` | ✅ Shipped |
| K.6 `retry_with_retry_after` + `idempotency_scope` on external POSTs | ✅ Shipped for Jira / Confluence / Remedy `create_*` endpoints via `idempotent_post` helper. GitHub client has no POST endpoints (GETs only) so no-op. |
| K.7 `paginate_search` in log_agent | ✅ `ElasticsearchClient.paginate_all` adopts PIT + search_after; safe lifecycle verified |
| K.8 `list_all` in k8s_agent + cluster_client | ✅ `_get_pod_status`, `cluster_client.list_pods`, `cluster_client.list_pdbs` migrated |
| K.9 `promql_library` in metrics_agent | ✅ Golden-signals + ALERTS entries added to default-queries list |
| K.10 `validate_stack_trace` in code_agent | ✅ `_stamp_stale_frames` post-processing pass marks UI's `is_stale` |
| K.11 `trace_context.inject_traceparent` on http_clients | ✅ Shipped via httpx event_hook |
| K.12 step-latency metrics in investigation_executor | ✅ Shipped |
| K.13 prompt registry bootstrap on startup | ✅ Shipped |
| K.14 resume scan on startup (log-only) | ✅ Shipped; real dispatch deferred (see below) |

### Remaining deferrals (all safe, each deserves its own PR)

- **K.5 `get_client(backend)` adoption in jira/confluence/remedy clients.** Each client today uses `async with httpx.AsyncClient(verify=False, timeout=15.0)`. Migrating to the shared singleton gains connection reuse + traceparent injection (K.11 fires automatically), but the `verify=False` per-call signals that some deployments use self-signed TLS. Needs deployment-env verification before flipping. ElasticsearchClient + the inline Prometheus HTTP callers in metrics_agent are in the same bucket.
- **Real resume dispatch.** `DIAGNOSTIC_RESUME_ON_STARTUP=on` currently runs a log-only scan so operators see which orphaned runs would be picked up. Actual dispatch needs a route-layer `build_supervisor(run_id)` factory plus state reconstruction from the DAG snapshot — a focused PR of its own.
- **Full N-shot SelfConsistency orchestration.** State field + API surface + request parameter (`self_consistency_runs`) all plumbed through; current behaviour runs the supervisor once and records `verdict='single_run_pending_multi'` honestly. True N-run voting needs a route-layer wrapper that builds N `SupervisorAgent` instances (each `_claim_single_use` enforced) and feeds the results into `SelfConsistency.run()` from Phase 4.

## Gate result

**PASS.** The orchestration swap's architectural goals are met:

1. The main loop of `SupervisorAgent.run()` is `EvalGate → Planner → Dispatcher → Reducer` — structurally legible, unit-testable, and env-flag-gated.
2. Every behaviour change has a rollback lever: four env flags let operators flip back to legacy paths without a code revert.
3. Stop reason is explicit — "why did it stop?" has five distinct string answers, not silence.
4. Winning agents are persisted + consumable by `/feedback` — the priors loop is closed on the backend. Actual prior-feedback flow runs on first user-labelled outcome.
5. Signature fast-path infrastructure is live; its visibility is gated on an opt-in flag so first exposures are controlled.
6. CriticEnsemble + signature matcher + self-consistency scaffolding all reach the API surface — the UI components from PR #26 have backend fields to read.

Carry-forward list above covers the remaining hardening investment, each splittable into its own reviewable PR.
