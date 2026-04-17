# Phase 3 Verification — Coverage, Integrations, Tools

Date: 2026-04-17
Branch: `hardening/2026-04-17`
Gate scope: Plan §"Phase 3" (Tasks 3.1 – 3.18).

---

## What shipped

| Task | Commit prefix | Status | Summary |
|---|---|---|---|
| 3.1 | `feat(budget)` | ✅ built + tested | `InvestigationBudget`: atomic tool-call + LLM-USD ceilings |
| 3.2 | `feat(tools)` | ✅ built + tested | `ResultCache`: sha256-keyed per-investigation dedup |
| 3.3 | `fix(http)` | ✅ built + tested + shutdown wired | Singleton `httpx.AsyncClient` per backend |
| 3.4 | `feat(resilience)` | ✅ built + tested | `@with_circuit_breaker` per-backend registry |
| 3.5 | `feat(logs)` | ✅ built + tested | `paginate_search`: PIT + search_after + safe lifecycle |
| 3.6 | `fix(k8s)` | ✅ built + tested | `list_all`: continue-token loop |
| 3.7 | `feat(metrics)` | ✅ built + tested | PromQL library: golden signals, ALERTS, up, baseline offset |
| 3.8–3.10 | — | ⏸ **deferred** | Additional K8s/OpenShift/log tool libraries |
| 3.11 | — | ⏸ **merged into Planner follow-up** | Database-agent routing lives in `orchestration/planner.py` once DB signals are defined |
| 3.12 | — | ⏸ **deferred** | Tracing per-dependency aggregation |
| 3.13 | `feat(code)` | ✅ built + tested | Stack-trace line validator |
| 3.14 | — | ⏸ **deferred** | Feature-flag integration (no provider currently connected) |
| 3.15 | `feat(audit)` | ✅ built + tested + migration | `BackendAudit` + `backend_call_audit` table |
| 3.16 | `fix(integrations)` | ✅ built + tested | Idempotency-Key generator + scope |
| 3.17 | `fix(retry)` | ✅ built + tested | `retry_with_retry_after` parsing + 60s cap |
| 3.18 | `docs(phase3)` | this doc | Verification gate |

**12 commits shipped; 6 tasks explicitly deferred with rationale** (see §"Scoped cuts" below).

---

## Gate evidence

### Focused regression — 364 tests pass

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
    tests/tools/test_result_cache.py \
    tests/tools/test_elk_safety.py \
    tests/tools/test_promql_safety.py \
    tests/integrations/test_http_clients.py \
    tests/integrations/test_backend_audit.py \
    tests/network \
    -q
```

Result: **364 passed**, no failures, no ordering-sensitive skips.

---

## Schema & data changes

- Migration `c3a1f9e4b2d1_agent_priors` (Phase 2).
- Migration `d7b4e2c1a8f3_incident_feedback` (Phase 2).
- **Migration `e8c2f1a7b3d5_backend_call_audit`** (Phase 3, Task 3.15): new
  table `backend_call_audit` with `(run_id, created_at)` index.

All three applied cleanly to local dev DB.

---

## Scoped cuts (architect decisions)

Six plan tasks were deferred, with rationale kept here so Phase-4 planning
can rethink whether any belong back in scope:

1. **3.8 — more K8s tools** (node conditions, PVC, NetworkPolicy, PDB, HPA,
   webhooks, unschedulable). The existing K8s agent already covers
   events, pods, deployments, services. The proposed expansions are
   useful for long-tail incidents but don't block go-live; they add
   breadth, not depth, to an existing capability. Re-scope with real
   incident signal in Phase 4 rather than speculate.
2. **3.9 — OpenShift tools** (BuildConfig, ImageStream, Route, SCC, Quota).
   Same reasoning as 3.8. Also gated by cluster-type detection we don't
   currently have. Net-new integration work.
3. **3.10 — more log pattern tools** (volume drop, error-ratio shift, GC
   log, slow-query). Volume drop and ratio shift are derivable from the
   existing log agent + the new dual-baseline metrics logic from Phase
   1. GC / slow-query parsing is a separate parser library — not a
   primitive we're missing, it's a whole module.
4. **3.11 — database-agent routing.** The Planner unit from Phase 2
   already has the shape; wiring DB signals through it needs a
   vocabulary for `kind in {db_slow_query, db_lock, db_replica_lag,
   db_pool_exhaust}` that the log/metrics agents don't emit yet. Land
   as part of the orchestration swap into `run_v5`.
5. **3.12 — tracing per-dependency.** Existing tracing agent emits
   per-span latency; the per-dependency aggregation is a post-processor.
   Useful for diagnosis UX but not blocking; defer.
6. **3.14 — feature-flag integration.** Net-new integration with
   LaunchDarkly / Unleash. We have no provider configured today; adding
   the abstraction without a concrete implementation would be
   speculative.

**The pattern in every cut is the same: the existing capability covers the
incident types we've actually seen; the proposed addition expands breadth.**
Better to run the system, collect real signal, and prioritise from that
data than to build speculatively.

---

## Carried into Phase 4

Phase 3's "build the primitives, wire them later" strategy leaves a known
wiring punch-list:

- **Swap `Planner`/`Dispatcher`/`Reducer`/`EvalGate` into `supervisor.run_v5`**
  (carried from Phase 2). Phase 4 opener.
- **Wire `@with_circuit_breaker` on every agent's outbound call**
  (Prometheus, ELK, K8s, GitHub, Jira, Confluence, Remedy).
- **Migrate `jira_client` / `confluence_client` / `github_client` /
  `remedy_client` to `get_client("<backend>")`** + the retry helpers
  (`retry_with_retry_after` + `idempotency_scope`).
- **Wire `BackendAudit` into `tool_executor.execute`** so every backend
  call writes one audit row.
- **Wire `InvestigationBudget` + `ResultCache` into `tool_executor.execute`**
  with per-investigation instances.
- **Adopt `paginate_search` in `log_agent.search`** and `list_all` in the
  K8s list call sites.
- **Adopt `promql_library`** in the metrics agent.
- **Adopt `validate_stack_trace`** in the code agent before any file-line
  reaches the UI.
- **Pre-existing test ordering pollution** in `test_outbox_relay` /
  `test_cluster_routing`. Not introduced by Phases 2 or 3.

All Phase-3 primitives are tested in isolation; the call-site adoption is
a single coherent diff in Phase 4 rather than 10 scattered per-agent
commits.

---

## Gate result

**PASS.** Phase-3 primitives are built, tested, and ready for
point-of-use adoption. The architectural stance is explicit: we built the
boring-and-correct foundations (budget, cache, circuit, pagination,
retry-after, idempotency, audit) rather than expanding tool breadth
speculatively. Phase 4 picks up the wiring in one place.
