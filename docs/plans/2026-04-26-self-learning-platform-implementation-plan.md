# DebugDuck Self-Learning Platform — Implementation Plan

**Status:** Finalized 2026-04-26
**Scope:** Loops A (signature library / per-tenant memory), D (critic calibration), F (triage / dispatch policy learning), G (unified spine + tenancy productization).
**Approach:** Test-Driven Development (red → green → refactor) on every story.
**Cadence:** 2-week sprints. 11 sprints. ~22 weeks (~5 months) elapsed.

---

## Assumptions baked into this plan

These were the open questions at lock time. Defaults applied; revise with a follow-up plan if any are wrong.

| # | Assumption | Default applied |
|---|---|---|
| 1 | Team capacity | 3 engineers (1 backend lead, 1 backend, 1 full-stack) + part-time platform/design support. ~32 story-points per sprint at 80% load. |
| 2 | Phase 0 acceptance | 2 weeks of "no user-visible work" is acceptable to lock the schema correctly. |
| 3 | Public corpus curation owner | Curator role TBD by sprint 1.3 start; if unassigned, sprint 1.3.5 (50 patterns) is at risk and the seed slips one sprint. |
| 4 | Telemetry source for outcome observer | Existing observability stack (Prometheus, Jaeger, Elasticsearch) is queryable from the backend. |
| 5 | Database | SQLite for v1 (matches current `data/debugduck.db` pattern). PostgreSQL migration is a v2 concern; storage gateway abstracts this. |

---

## 1. Locked architectural baseline

### 1.1 Inviolable design rules (Rules 1–18, binding)

| # | Rule |
|---|---|
| 1 | **Spine = JOIN-required fields only.** If two loops need the field to correlate, it is spine. Otherwise sidecar. |
| 2 | **Sidecars = structured, queryable, intentional.** No raw log dumps. No unbounded JSON blobs. Every column has a typed schema and a read pattern. |
| 3 | **Strict typed contract layer.** All loops read/write `ClosedIncidentRecord` (and its sidecar interfaces) through a typed gateway. No direct SQL outside `storage/`. Schema creep by convenience is prohibited. |
| 4 | **Append-only spine, mutable sidecars.** Spine is the historical record — once written, immutable. Sidecars hold derived state and may be recomputed. |
| 5 | **Discovery rate is a system invariant.** F's exploration % and D's uncalibrated-bucket sample-size threshold are configurable per tenant but always > 0. We never lock a tenant into a closed loop. |
| 6 | **Tenancy is per-tenant, mode-constrained.** No free-form per-loop toggles. Three fixed tiers: **Isolated** / **Fleet-augmented** / **Fleet-intelligent**. Default = Fleet-augmented. |
| 7 | **Provenance is mandatory on every learned output.** Every output carries `provenance: {source: "tenant"\|"fleet"\|"public", sample_size: int, last_updated_at, calibrated: bool}`. |
| 8 | **Sources are never blended.** Retrieval is fan-out + rank, not unified-store query. Source-aware ranking with **tenant > fleet > public** priority when tenant data exists. |
| 9 | **Cross-tenant data must be projection-safe.** Only derived, non-reconstructable representations may leave tenant boundary. Raw evidence, identifiers, reversible transforms are prohibited. |
| 10 | **Every learned loop has a safe-mode fallback.** D → uncalibrated, A → search-only, F → fan-out-all. |
| 11 | **Loop health is a single state machine.** `LoopHealthState ∈ {healthy, canary, degraded, recovering, frozen}`. Canary controls entry, auto-freeze controls runtime, dashboards control manual override. No layer issues conflicting signals. |
| 12 | **Drift detection uses hysteresis.** Asymmetric thresholds (freeze at 15%, unfreeze at 8%) prevent flapping. |
| 13 | **Confidence-in-the-loop is surfaced alongside output confidence.** A confident value from a degraded loop is shown as such. |
| 14 | **Operator overrides are high-weight training signals, not immediate ground truth.** Overrides feed loops with elevated weight but require outcome confirmation (D's loop) before being treated as authoritative. |
| 15 | **Every platform-config change is audited.** Tier switches, threshold adjustments, freezes, and pool opt-ins write an immutable audit row with actor, timestamp, before/after, reason. |
| 16 | **All config knobs have safe bounds.** Every Category-3 control is bounded server-side: `drift_threshold ∈ [0.05, 0.30]`, `discovery_rate ∈ [0.01, 0.20]`, `unfreeze_threshold < freeze_threshold`. |
| 17 | **Config changes require dry-run preview before apply.** Every Category-3 change displays an impact preview before commit. No silent applies. |
| 18 | **Decision-level provenance trace is a first-class compliance primitive.** For any single recommendation: source, inputs used, model version, loop health state at decision time, sample size at decision time. |

### 1.2 Locked decisions Q1–Q7

| Q | Decision |
|---|---|
| **Q1 — Loops to build** | A → D → F → G (in that priority order). |
| **Q2 — Storage architecture** | Spine + thin sidecars (Option 3). |
| **Q3 — Tenancy** | Constrained 3-tier model. Default Tier 2 (Fleet-augmented). Tier 1 = Isolated; Tier 3 = Fleet-intelligent (opt-in). |
| **Q4 — Cold-start** | Hybrid: public seed + opt-in pooled bootstrap + transparent learning UI. Sources never blended. |
| **Q5 — Failure / drift detection** | Composite: auto-freeze + dual canary + dashboards, unified through `LoopHealthState` with hysteresis. Champion/challenger explicitly excluded. |
| **Q6 — Operator surface** | Tiered v1: Cat 1 read-only + Cat 2 per-incident overrides + Cat 3 minimal config (bounded, preview-required) + Cat 5 minimal compliance (data-flow report, fleet deletion, decision provenance trace). Cat 4 (training-data interventions) **deferred to v2**. |
| **Q7 — Build sequencing** | Phase 0 (schema-first) → Phase 1 (A skeleton + public corpus + D in parallel) → Phase 2 (smart A + UI provenance) → Phase 3 (F + drift unification) → Phase 4 / G (tenancy productization + operator surface). |

### 1.3 Tenancy tiers — what flows where

| Loop | Tier 1 (Isolated) | Tier 2 (Fleet-augmented, default) | Tier 3 (Fleet-intelligent) |
|---|---|---|---|
| **A — signatures** | local | local | local + abstracted-signature contribution to fleet |
| **D — calibration** | local | pooled (anonymized) | pooled (anonymized) |
| **F — dispatch** | local | pooled | federated |

Projections that may leave tenant boundary:
- **A (Tier 3):** `signature_hash`, `pattern_type`, `topology_shape`. Never logs, service names, queries, stack traces.
- **D (Tier 2+):** `root_cause_type`, `predicted_confidence`, `actual_correct`. Pure statistical pairs.
- **F (Tier 2+):** `signature_type`, `agent`, `contribution_class`. Behavioral aggregates only.

---

## 2. Foundations

### 2.1 Definition of Ready (DoR)

A story is "Ready" when:
- [ ] Acceptance criteria written as Given/When/Then.
- [ ] Test plan lists at least one failing-first test per acceptance criterion.
- [ ] Dependencies on other stories explicitly named.
- [ ] Estimate (1, 2, 3, 5, 8 points) agreed by the team.
- [ ] Provenance/tenancy/safety implications identified.

### 2.2 Definition of Done (DoD)

A story is "Done" when:
- [ ] Every acceptance criterion has a passing test in CI.
- [ ] Test pyramid respected: unit > integration > e2e for every behavior.
- [ ] No new cyclomatic complexity > 10 in any function.
- [ ] Inviolable Rules 1–18 not violated (PR template checklist).
- [ ] Public APIs documented in OpenAPI / TypeScript types.
- [ ] Audit trail emitted for any state-changing operation (Rule 15).
- [ ] Security review for any cross-tenant code path.
- [ ] No `# TODO` comments in production code paths.

### 2.3 TDD discipline (binding)

Each story is implemented in this order:

1. **Red** — write the failing test. CI must show it failing for the right reason. Commit: `test(red): <story-id> — <test name>`.
2. **Green** — minimum production code to make the test pass. Commit: `feat(green): <story-id> — <change>`.
3. **Refactor** — improve structure without changing behavior. Tests stay green. Commit: `refactor: <story-id> — <description>`.

PRs containing only "green" without a preceding "red" commit are rejected at code review.

### 2.4 Story-point legend

| Points | Meaning |
|---|---|
| 1 | Trivial, < 0.5 day |
| 2 | Single function or schema change, ~0.5–1 day |
| 3 | Multi-file change, no architectural decisions, ~1–2 days |
| 5 | Cross-component change, some design needed, ~2–4 days |
| 8 | Significant feature, may need spike first, ~4–8 days; if higher, split |

Sprint capacity per engineer: ~13 points. Team of 3 = ~40 points/sprint capacity. Plan for 32 (80% load) to absorb interruptions.

### 2.5 Cross-cutting non-negotiables

- **Schema migrations on the spine: prohibited after Phase 0.** Sidecars can migrate.
- **Security review checkpoints:** end of Phase 0, end of Phase 3, end of Phase 4.
- **Performance budgets:** A retrieval p99 < 200ms; D calibration lookup p99 < 5ms; F dispatch decision p99 < 10ms. Budget violation blocks merge.
- **Discovery rate ≥ 1%:** verified by runtime invariant check on every config-write path.

---

## 3. Phase 0 — Schema & Substrate (Sprint 0.1)

**Phase goal:** Lock the spine, sidecar interfaces, and typed contract layer. Zero business logic.

**Phase exit criteria:**
- `ClosedIncidentRecord` typed contract published.
- Spine schema migrated into `data/learning.db` with append-only enforcement.
- Sidecar tables for A/D/F created.
- Storage gateway rejects any non-contract write.
- Audit-log primitive emits row on every state change.
- Safe-bounds enforcement on every config write.

### Sprint 0.1 — Schema & Substrate (32 pts)

| ID | Title | Pts |
|---|---|---|
| 0.1.1 | Define `ClosedIncidentRecord` and sidecar contract types | 3 |
| 0.1.2 | Spine table migration with append-only trigger | 3 |
| 0.1.3 | Sidecar tables: signature_index (A), verdict_outcomes (D), dispatch_decisions (F) | 5 |
| 0.1.4 | Typed StorageGateway — gateway pattern, no direct table access | 5 |
| 0.1.5 | Audit-log primitive (`write_audit_event`) | 3 |
| 0.1.6 | Safe-bounds validator for config knobs | 3 |
| 0.1.7 | Tenancy-mode enforcement at storage layer (Rule 6) | 5 |
| 0.1.8 | CI rule: schema-migration linter | 2 |
| 0.1.9 | PR template with Rule 1–18 checklist | 1 |
| 0.1.10 | Phase 0 security review checkpoint | 2 |

#### Story 0.1.1 — `ClosedIncidentRecord` and sidecar contract types

**As a** loop developer, **I want** a typed contract for the closed-incident object **so that** every loop reads and writes through one source of truth.

**AC:**
- AC-1: `ClosedIncidentRecord` has fields `incident_id, tenant_id, signature, verdict_summary, outcome_label, closed_at, tenancy_mode, provenance` — all typed.
- AC-2: Constructor without `tenant_id` raises `ValidationError`.
- AC-3: `SignatureIndexEntry` (A), `VerdictOutcomeRow` (D), `DispatchDecisionRow` (F) — strict Pydantic, no `Optional[Any]`.
- AC-4: All contract types JSON round-trip equal.

**Test plan:**
1. Red: `test_record_requires_tenant_id`.
2. Green: minimum field set in `backend/src/learning/contracts.py`.
3. Red: `test_record_serializes_round_trip`.
4. Green: configure Pydantic model_config.
5. Red: `test_no_optional_any_in_sidecars` (reflection over field types).
6. Green: define sidecar models with strict types.
7. Refactor: extract `Provenance` and `TenancyMode` to shared module.

**Deps:** none.

#### Story 0.1.2 — Spine append-only migration

**AC:**
- AC-1: `closed_incidents` table exists post-migration.
- AC-2: UPDATE on spine raises (SQLite trigger).
- AC-3: DELETE raises except via `delete_tenant_contributions(tenant_id)` audited stored proc.
- AC-4: Migration is idempotent.

**Test plan:** TDD per AC. Spine triggers tested via sqlite3 in-memory.

**Deps:** 0.1.1.

#### Story 0.1.3 — Sidecar tables

**AC:**
- AC-1: Tables `signature_index`, `verdict_outcomes`, `dispatch_decisions` exist with FK on `incident_id`.
- AC-2: Each has `last_recomputed_at` (datetime).
- AC-3: Sidecars allow UPDATE.
- AC-4: FK violation raises on insert when `incident_id` not in spine.

**Deps:** 0.1.1, 0.1.2.

#### Story 0.1.4 — Typed StorageGateway

**AC:**
- AC-1: `gateway.write_closed_incident(record)` appends to spine.
- AC-2: `gateway.read_signature_sidecar(incident_id)` returns typed entry or `None`.
- AC-3: CI lint rule blocks `cursor.execute()` outside `storage/` package.
- AC-4: Tenant-mismatched write raises `TenancyViolationError`.

**Test plan:**
1. Red: `test_gateway_write_then_read_round_trip`.
2. Green: minimal gateway over sqlite.
3. Red: `test_lint_rule_blocks_external_sql_execute`.
4. Green: AST-based linter in `tools/lint_storage_isolation.py`; wired into `make lint`.
5. Red: `test_tenancy_violation_raised_on_mismatched_tenant`.
6. Green: bind tenant context to gateway constructor.

**Deps:** 0.1.1, 0.1.2, 0.1.3.

#### Story 0.1.5 — Audit-log primitive

**AC:**
- AC-1: `write_audit_event(actor, action, before, after, reason)` writes one row.
- AC-2: `audit_log` is append-only.
- AC-3: Every gateway write method calls `write_audit_event` (verified by spy).
- AC-4: `audit_log_for_tenant(tenant_id, since)` returns chronologically.

**Deps:** 0.1.4.

#### Story 0.1.6 — Safe-bounds validator (Rule 16)

**AC:**
- AC-1: `validate_config(knob, value)` raises `ConfigBoundsViolation` on out-of-bounds.
- AC-2: Registry includes minimum bounds: `drift_threshold ∈ [0.05, 0.30]`, `discovery_rate ∈ [0.01, 0.20]`, `unfreeze_threshold < freeze_threshold`.
- AC-3: Validator invoked on every config-write path (spy contract test).

**Deps:** 0.1.4.

#### Story 0.1.7 — Tenancy-mode enforcement at storage layer

**AC:**
- AC-1: Gateway bound to tenant T returns only `tenant_id = T` rows.
- AC-2: `pooled=True` for D returns rows from D-pooled tenants.
- AC-3: Tier-1 tenant's data not in pooled result set.
- AC-4: Read of pooled data without per-loop opt-in raises `TenancyViolationError`.

**Test plan:** Property-based testing using `hypothesis` — random tenant configs, assert no cross-tenant leakage.

**Deps:** 0.1.4, 0.1.6.

#### Story 0.1.8 — CI rule: schema-migration linter

**AC:**
- AC-1: PR modifying `V1__spine.sql` (alters/drops on `closed_incidents`) fails CI.
- AC-2: PR adding new sidecar table or column passes.
- AC-3: PR adding `V2__*.sql` targeting sidecar passes.

**Deps:** 0.1.2.

#### Story 0.1.9 — PR template with Rule 1–18 checklist

Tactical. PR template with checklist; reviewers cannot approve until boxes are ticked or marked N/A with reason.

#### Story 0.1.10 — Phase 0 security review checkpoint

**AC:**
- AC-1: Security review document published.
- AC-2: Threat model covers spine corruption, cross-tenant read leakage, audit-log tampering, config-bound bypass.
- AC-3: All findings tracked or resolved before Phase 1.

---

## 4. Phase 1 — A skeleton + Public Corpus + D in parallel (Sprints 1.1, 1.2, 1.3)

**Phase goal:** First user-visible value. D earns trust, A begins accumulating, public corpus seeds Day-1 value.

### Sprint 1.1 — Closed-incident write path + outcome observer (32 pts)

| ID | Title | Pts |
|---|---|---|
| 1.1.1 | Hook into closure flow — emit `ClosedIncidentRecord` on incident close | 5 |
| 1.1.2 | Outcome observer service — 48h post-merge telemetry watcher | 8 |
| 1.1.3 | Operator-action signal — rollback / reopen → outcome label | 5 |
| 1.1.4 | Optional dossier "was-this-right?" toggle | 3 |
| 1.1.5 | Outcome label resolution rules with priority precedence | 5 |
| 1.1.6 | Provenance field populated on every record write | 3 |
| 1.1.7 | Integration test — full flow (incident → record → outcome label) | 3 |

#### Story 1.1.1 — Closure-flow hook

**AC:** Incident in `complete` phase triggers gateway write; record contains incident_id, tenant_id, signature, verdict_summary, `outcome_label="pending"`, `closed_at=now()`. Failures don't block UX. Idempotent on duplicate.

**Tests:** TDD per AC; mock storage to verify async write + error swallowing.

**Deps:** 0.1.4, 0.1.5.

#### Story 1.1.2 — Outcome observer service

**AC:**
- AC-1: 48h after closure, observer queries telemetry for signature pattern.
- AC-2: No recurrence → `outcome_label="fix_worked"`.
- AC-3: Recurrence → `outcome_label="fix_regressed"`.
- AC-4: Telemetry failure → retry with backoff (3 retries / 24h, then `not_evaluable`).
- AC-5: Idempotent on duplicate run.

**Tests:**
1. Red: `test_observer_writes_fix_worked_when_no_recurrence`.
2. Green: implement observer with telemetry stub.
3. Red: `test_observer_writes_fix_regressed_on_recurrence`.
4. Green: add recurrence detection.
5. Red: `test_observer_retries_on_telemetry_failure`.
6. Green: exponential backoff.
7. Red: `test_observer_idempotent_on_duplicate_run`.
8. Green: UPSERT with idempotency key.
9. Refactor: telemetry-query interface (Prometheus → Datadog later).

**Deps:** 1.1.1.

#### Story 1.1.3 — Operator-action signals

**AC:** Rollback on fix PR → `verdict_was_wrong`. Reopen → same. Late rollback updates label and preserves original in audit. Operator action overrides telemetry (precedence in 1.1.5).

**Deps:** 1.1.1, 1.1.2.

#### Story 1.1.4 — Dossier "was-this-right?" toggle

**AC:** Toggle appears only when telemetry signals are ambiguous. Three options: `correct / partially_correct / wrong`. Optional.

**Tests:** Component + e2e dossier publish flow.

**Deps:** 1.1.3.

#### Story 1.1.5 — Outcome label resolution rules

**AC:** `resolve_outcome(telemetry, operator_action, dossier_label, age) -> OutcomeLabel`. Precedence: operator_action > dossier_label > telemetry > time-decay. Conflicts persisted in `signal_breakdown` for audit. Pure function, fully unit-tested.

**Tests:** Property-based — exhaustive signal combinations, assert precedence.

**Deps:** 1.1.3, 1.1.4.

#### Story 1.1.6 — Provenance on every write

**AC:** Every record carries `provenance.source="tenant"` (Phase 1). `sample_size` is contributing-record count. Gateway rejects writes missing provenance.

**Deps:** 0.1.1.

#### Story 1.1.7 — Phase 1 e2e integration test

**AC:** Test creates incident, drives close, fast-forwards 48h via clock injection, asserts label. Real sqlite. Runs in < 2s (no wall-clock).

**Deps:** 1.1.1, 1.1.2, 1.1.5.

### Sprint 1.2 — D Calibration Service + UI (32 pts)

| ID | Title | Pts |
|---|---|---|
| 1.2.1 | CalibrationService — per-category isotonic regression on 30d window | 8 |
| 1.2.2 | Reliability-diagram computation per category | 5 |
| 1.2.3 | Calibration lookup API — `calibrate(raw_confidence, category) -> calibrated` | 3 |
| 1.2.4 | LoopHealthState (D only) | 5 |
| 1.2.5 | Hysteresis on drift detection | 3 |
| 1.2.6 | UI — confidence pill with provenance + sample size + calibrated badge | 5 |
| 1.2.7 | Reliability-diagram dashboard for platform team | 3 |

#### Story 1.2.1 — CalibrationService

**AC:**
- AC-1: ≥50 closed incidents in category → fit isotonic regression and persist.
- AC-2: <50 incidents → `InsufficientDataError`, no persist.
- AC-3: Per-category from registry (`payments`, `networking`, `database`, `k8s_infra`, `config_drift`).
- AC-4: 30-day rolling window.
- AC-5: Daily background job per tenant.

**Tests:**
1. Red: `test_fit_raises_on_insufficient_data`.
2. Green: minimum implementation.
3. Red: `test_fit_produces_monotonic_mapping` (isotonic property).
4. Green: `sklearn.isotonic.IsotonicRegression`.
5. Red: `test_fit_excludes_records_older_than_30d`.
6. Green: window filter.
7. Red: `test_fit_persists_to_calibration_table`.
8. Green: persist via gateway.
9. Refactor: configurable window per category.

**Deps:** 1.1.5, 0.1.4.

#### Story 1.2.2 — Reliability-diagram computation

**AC:** `reliability_diagram(category)` returns `[(decile, actual_correctness, n)]`. Deciles 0–10%, 10–20%, ..., 90–100%. Returns Brier score and ECE. Pure function over verdict_outcomes.

**Tests:** Unit tests with synthetic data exercising each decile.

**Deps:** 1.2.1.

#### Story 1.2.3 — Calibration lookup API

**AC:** Returns `{calibrated, raw, sample_size, calibrated_at, calibrated: bool}`. Cold-start returns raw with `calibrated:false`. p99 < 5ms (in-memory tables). Hot-reloads on `fit()`.

**Tests:** Unit + perf benchmark in CI.

**Deps:** 1.2.1.

#### Story 1.2.4 — LoopHealthState (D)

**AC:** `LoopHealth(loop="D", tenant)` returns one of `healthy | canary | degraded | recovering | frozen`. Transitions explicit. Every transition writes audit. Degraded/frozen → `calibrate()` returns safe-mode (raw, `calibrated:false`).

**Tests:** State-machine property tests — random input sequences, assert valid transitions only.

**Deps:** 0.1.5, 1.2.3.

#### Story 1.2.5 — Hysteresis on D drift

**AC:** Freeze at ECE > 0.15; unfreeze at ECE < 0.08. Bounded by Rule 16. Configurable per tenant within bounds. No-flapping under oscillating-ECE fixture.

**Tests:** Simulation — time-series of ECE oscillating around 0.10, assert state stable.

**Deps:** 1.2.4.

#### Story 1.2.6 — UI confidence pill

**AC:**
- AC-1: `92% · n=47 payments · calibrated` when calibrated.
- AC-2: `92% · n=3 · uncalibrated` in different color when not calibrated.
- AC-3: `92% · n=47 · calibration: degraded` when degraded.
- AC-4: Tooltip shows reliability curve.

**Tests:** Component tests + visual regression (Playwright snapshot).

**Deps:** 1.2.3, 1.2.4.

#### Story 1.2.7 — Reliability-diagram dashboard

**AC:** `/admin/learning/calibration`, one panel per category, reliability curve + Brier + ECE + sample size + state badge. Drift threshold band visualized. Read-only.

**Tests:** e2e loads with seeded data, asserts canvas rendered + ARIA-labeled metrics.

**Deps:** 1.2.2, 1.2.4.

### Sprint 1.3 — A skeleton + Public Corpus seed (32 pts)

| ID | Title | Pts |
|---|---|---|
| 1.3.1 | Signature extractor — deterministic fingerprint from incident state | 5 |
| 1.3.2 | Signature index sidecar write path | 3 |
| 1.3.3 | Naive retrieval — exact-match signature lookup per tenant | 3 |
| 1.3.4 | Public corpus schema + curation tooling | 5 |
| 1.3.5 | Public corpus seed — 50 curated patterns | 8 |
| 1.3.6 | Fan-out retrieval API — tenant + public + (later) fleet | 5 |
| 1.3.7 | UI — "matched signature" pill on incident view | 3 |

#### Story 1.3.1 — Signature extractor

**AC:** `extract_signature(incident_state) -> Signature` is pure, deterministic. Includes dominant error class, primary affected service category, top metric anomaly type, hypothesis category — no tenant identifiers. Two structurally-identical incidents → identical signatures. Versioned for stability across releases.

**Tests:** Property-based — generate equivalent-shape incidents, assert signature equality.

**Deps:** 0.1.1.

#### Story 1.3.2 — Signature index write path

Standard write story. Writes `SignatureIndexEntry(incident_id, signature, indexed_at)` after closure.

**Deps:** 1.3.1, 1.1.1.

#### Story 1.3.3 — Naive retrieval

**AC:** `retrieve_local(signature, tenant) -> List[SignatureMatch]` returns matching past incidents. Each result carries `provenance.source="tenant"`. p99 < 200ms.

**Deps:** 1.3.2.

#### Story 1.3.4 — Public corpus schema + tooling

**AC:** `PublicCorpusEntry(signature, pattern_type, source_postmortem_url, baseline_confidence, curator_notes)`. CLI `dd-corpus add --file pattern.yaml` validates and inserts. Validation rejects entries missing source URL or pattern type.

**Deps:** 0.1.1.

#### Story 1.3.5 — 50 curated patterns

Content work. Curate from public post-mortems (Stripe, Cloudflare, GitHub, Square, AWS, Shopify). Each entry engineer-reviewed.

**AC:**
- AC-1: 50 entries committed to `data/public_corpus.yaml`.
- AC-2: Each cites a public post-mortem URL.
- AC-3: Coverage spans ≥5 categories (payments, infra-outage, deploy-related, capacity, security).

**Owner risk:** Sprint 1.3 is at risk if curator unassigned by sprint start (Assumption 3 above).

#### Story 1.3.6 — Fan-out retrieval API

**AC:**
- AC-1: `retrieve(signature, tenant) -> RankedResults` returns `{tenant: [...], public: [...], ranking: ["tenant", "public"]}`.
- AC-2: Tenant results exist → tenant first regardless of confidence.
- AC-3: Tenant empty → fall through to public.
- AC-4: No blended single confidence number ever returned.

**Deps:** 1.3.3, 1.3.4, 1.3.5.

#### Story 1.3.7 — UI matched-signature pill

Frontend component. Renders top match with provenance badge.

**Tests:** Component + visual regression.

**Deps:** 1.3.6.

---

## 5. Phase 2 — A smart retrieval + UI provenance integration (Sprints 2.1, 2.2)

**Phase goal:** Retrieval becomes more than exact-match. Provenance shows up everywhere.

### Sprint 2.1 — Smart retrieval + ranking (32 pts)

| ID | Title | Pts |
|---|---|---|
| 2.1.1 | Embedding-based signature similarity (text-embedding model integration) | 8 |
| 2.1.2 | Top-k retrieval with similarity threshold | 5 |
| 2.1.3 | Outcome-weighted ranking (D's labels feed A's scoring) | 5 |
| 2.1.4 | Source-aware ranking enforced at API layer (Rule 8) | 5 |
| 2.1.5 | Performance test — retrieval p99 < 200ms at 10K incidents | 3 |
| 2.1.6 | Confidence decomposition view (hidden by default, dev-mode toggle) | 3 |
| 2.1.7 | LoopHealthState extended to A | 3 |

Each story: full red-green-refactor, AC-driven tests, deps on Phase 1.

### Sprint 2.2 — UI provenance integration end-to-end (32 pts)

| ID | Title | Pts |
|---|---|---|
| 2.2.1 | War Room — every recommendation card carries provenance pill | 5 |
| 2.2.2 | Hypothesis Evidence Map — each evidence row tagged source | 5 |
| 2.2.3 | Blast-radius card — data-sources footer powered by provenance API | 3 |
| 2.2.4 | Dossier — provenance section showing all sources contributing | 5 |
| 2.2.5 | Visual regression test suite (Playwright) for all pills | 5 |
| 2.2.6 | Accessibility audit — provenance badges have semantic ARIA | 3 |
| 2.2.7 | A loop drift detection — signature retrieval hit-rate dashboard | 3 |
| 2.2.8 | Phase 2 integration test — closed incident → retrievable in 1s | 3 |

---

## 6. Phase 3 — F dispatch policy + drift unification (Sprints 3.1, 3.2, 3.3)

**Phase goal:** Triage policy learns and starts withholding agents — conservatively, with discovery rate intact, dual canary in place.

### Sprint 3.1 — Dispatch decision capture + agent contribution scoring (32 pts)

| ID | Title | Pts |
|---|---|---|
| 3.1.1 | Capture every dispatch decision into `dispatch_decisions` sidecar | 5 |
| 3.1.2 | Agent contribution scorer — did this agent's findings appear in winning verdict? | 5 |
| 3.1.3 | Per-(signature, agent) value table — rolling 90-day aggregate | 5 |
| 3.1.4 | F policy lookup API (cold-start = full fan-out) | 3 |
| 3.1.5 | Discovery rate enforcement — 5% always-fan-out per tenant | 3 |
| 3.1.6 | Override capture — operator force-spawns withheld agent → training signal | 5 |
| 3.1.7 | LoopHealthState extended to F | 3 |
| 3.1.8 | UI — dispatch reasoning shown in supervisor activity feed | 3 |

### Sprint 3.2 — Dual canary + auto-freeze (32 pts)

| ID | Title | Pts |
|---|---|---|
| 3.2.1 | Per-tenant canary — 5% of incidents test new policy first | 5 |
| 3.2.2 | Fleet canary (for opted-in tenants) | 5 |
| 3.2.3 | Promotion logic — canary passes → full rollout | 3 |
| 3.2.4 | Auto-freeze trigger — drift > threshold → safe mode | 5 |
| 3.2.5 | Hysteresis applied to F drift detector | 3 |
| 3.2.6 | LoopHealthState unified across A/D/F (single state machine module) | 5 |
| 3.2.7 | Audit log — every state transition + canary decision | 3 |
| 3.2.8 | Property-based test — state machine has no impossible transitions | 3 |

### Sprint 3.3 — Drift detection completion + cross-loop integration (32 pts)

| ID | Title | Pts |
|---|---|---|
| 3.3.1 | Concept-drift detector — incident-signature distribution shift | 5 |
| 3.3.2 | Pooled-source contamination detector (per-tenant contribution audit) | 5 |
| 3.3.3 | Drift dashboard — unified view of A/D/F health | 5 |
| 3.3.4 | Confidence-in-the-loop surfaced on all UI outputs | 5 |
| 3.3.5 | Operator overrides persisted as high-weight signals (Rule 14) | 3 |
| 3.3.6 | Override → outcome confirmation chain validated | 3 |
| 3.3.7 | Phase 3 e2e — F withholds an agent, operator overrides, signal feeds back | 3 |
| 3.3.8 | Phase 3 security review checkpoint | 3 |

---

## 7. Phase 4 (G) — Tenancy productization + Operator surface (Sprints 4.1, 4.2)

**Phase goal:** The three loops become one product. Tenants onboarded into one of three tiers. Platform team gets the operator surface from Q6.

### Sprint 4.1 — Tenancy tier productization (32 pts)

| ID | Title | Pts |
|---|---|---|
| 4.1.1 | Onboarding flow — tenant chooses tier (Isolated / Fleet-augmented / Fleet-intelligent) | 5 |
| 4.1.2 | Tier-switch API with audit trail and migration semantics | 8 |
| 4.1.3 | Projection-safe extractors — signature anonymization for fleet contribution (Tier 3) | 8 |
| 4.1.4 | Pooled D calibration store (cross-tenant, anonymized) | 5 |
| 4.1.5 | Pooled F dispatch store | 3 |
| 4.1.6 | Migration test — tier change Tier 1 → Tier 2 doesn't lose data | 3 |

### Sprint 4.2 — Operator surface + compliance (32 pts)

| ID | Title | Pts |
|---|---|---|
| 4.2.1 | Per-incident operator overrides API (force-spawn, mark-wrong, suppress-match) | 5 |
| 4.2.2 | Tenant config admin UI — tier switch, freeze/unfreeze, threshold adjust (bounded) | 8 |
| 4.2.3 | "Preview before apply" for every config change | 5 |
| 4.2.4 | Compliance — "what data left this tenant" report | 3 |
| 4.2.5 | Compliance — "delete from fleet pool" workflow | 3 |
| 4.2.6 | Compliance — decision-level provenance trace | 5 |
| 4.2.7 | Phase 4 security review + penetration test | 3 |

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Spine schema wrong, requires migration | Low | Critical | Phase 0 over-invests in schema design; CI lint blocks alterations. |
| Outcome observer mis-labels under partial recurrence | Medium | High | Operator-action signals override; dossier toggle as escape hatch; precedence rules property-tested. |
| Calibration false-positive freezes erode trust | Medium | High | Hysteresis (Rule 12); shadow-mode for first 4 weeks of D in production. |
| F withholds an agent that would have found the bug | Medium | Critical | 5% discovery rate (Rule 5); operator override (Rule 14); withheld agents shown in UI. |
| Cross-tenant data leakage via signature fingerprint | Low | Catastrophic | Phase 0 + Phase 4 security reviews; projection-safe extractors with property-based tests against fingerprinting attacks. |
| Public corpus pattern wrong for a tenant's stack | Medium | Medium | Provenance pill makes source explicit; tenant can suppress public matches. |
| Operator override misused as "for now" → poisons learning | Medium | High | Rule 14: overrides are high-weight, not absolute; outcome confirmation required. |
| Federation attack surface (model inversion, membership inference) | Low (deferred to v2) | Critical | Federation excluded from v1 by design; revisit with formal privacy review. |
| Public corpus curator unassigned | Medium | Medium | Sprint 1.3 slips one sprint without owner; identify curator before sprint 1.2 starts. |

---

## 9. Sprint Roadmap Summary

| Sprint | Phase | Focus | Cumulative outcome |
|---|---|---|---|
| 0.1 | Schema | Substrate locked | Foundation, no user value yet |
| 1.1 | Outcomes | Closed-incident pipeline | Spine populating with data |
| 1.2 | D | Calibration ships | Operators see "earned confidence" |
| 1.3 | A skeleton | Naive retrieval + public corpus | Signature matches appear |
| 2.1 | A smart | Embedding retrieval, ranking | Memory becomes useful |
| 2.2 | UI | Provenance everywhere | Trust UI is complete |
| 3.1 | F capture | Dispatch decisions captured | Data substrate for F ready |
| 3.2 | F policy | Canary + auto-freeze | F starts withholding agents safely |
| 3.3 | Drift | Cross-loop drift detection | System knows when it's degrading |
| 4.1 | Tenancy | 3 tiers productized | Sales motion ready |
| 4.2 | Operator | Admin UI + compliance | Enterprise-ready |

**Total elapsed: ~22 weeks (~5 months) at 2-week sprints, 80% capacity load.**

---

## 10. Glossary

- **Spine** — the append-only `closed_incidents` table; canonical record per closed incident.
- **Sidecar** — per-loop mutable derived-state table (signature_index, verdict_outcomes, dispatch_decisions).
- **Loop** — A (memory), D (calibration), F (dispatch) as independent learning systems; G unifies them.
- **Provenance** — typed metadata on every learned output: source, sample size, calibrated flag, last_updated_at.
- **Tenancy tier** — Isolated (Tier 1) / Fleet-augmented (Tier 2, default) / Fleet-intelligent (Tier 3, opt-in).
- **Projection-safe** — derived, non-reconstructable representation that may leave tenant boundary (Rule 9).
- **Discovery rate** — minimum % of incidents that bypass learned policy (always > 0; Rule 5).
- **LoopHealthState** — `healthy | canary | degraded | recovering | frozen` (Rule 11).
- **Hysteresis** — asymmetric drift thresholds (freeze > unfreeze) preventing flapping (Rule 12).
- **ECE** — Expected Calibration Error; D's primary drift metric.
- **Brier score** — mean squared error of probabilistic predictions; D secondary metric.

---

**Plan finalized 2026-04-26. Next step: per the brainstorming skill terminal flow, invoke `superpowers:writing-plans` to expand any of the 11 sprints into per-task work-breakdown if deeper-than-story-level cuts are needed.**
