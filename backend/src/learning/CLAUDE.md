---
scope: backend/src/learning/
owner: "@platform-team"
priority: high
type: directory
---

# Learning subsystem conventions

The self-learning platform (loops A, D, F → G). Cross-reference:
`docs/plans/2026-04-26-self-learning-platform-implementation-plan.md`.

## The 18 inviolable design rules from the self-learning plan apply here

In particular:
- The `ClosedIncidentRecord` typed contract is the only public way data
  flows between loops.
- Spine fields are JOIN-required only; everything else is sidecar.
- Spine is append-only (the SQLite trigger enforces); sidecars mutate.
- Tenancy is per-tenant via fixed 3-tier model.
- Provenance mandatory on every learned output.
- Sources never blended — fan-out + rank, never merged.
- Cross-tenant data is projection-safe.
- Every learned loop has a safe-mode fallback.
- Loop health is a single state machine.
- Drift detection uses hysteresis.

## Specific rules for editing in this directory

- Use `StorageGateway` (`src/storage/gateway.py`) for ALL DB access. Direct
  `select()` / `Session` usage is banned (Q8).
- Hypothesis tests required (Q9) on every `extract_*`, `parse_*`,
  `resolve_*`, `calibrate_*`, `score_*` function.
- Outcome labels follow the precedence rule from Story 1.1.5 of the
  self-learning plan: operator_action > dossier_label > telemetry > time-decay.
- Calibration math is statistically pure — no LLM calls. Any function
  that touches confidence numbers stays deterministic.
- Loop state transitions write audit rows via `write_audit_event()`.

## What lives where
- `contracts.py` — typed contract surfaces (Pydantic models). Phase 0.
- `storage/` — `StorageGateway`, `engine`, sidecar query helpers.
- `services/` — domain services (calibration, signature index, dispatch policy).
- `outcome_observer.py` — background job that labels closed incidents.
