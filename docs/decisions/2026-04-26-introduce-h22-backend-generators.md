# Backend generators (H.2.2) — backend_routes, db_models, storage_gateway_methods, test_coverage_required_paths, test_inventory

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

H.2.2 lands the five backend generators. Like the H.2.1 frontend
generators, each one collapses an AST/regex scan into a single sorted
JSON file under `.harness/generated/`. Together with the schemas under
`.harness/schemas/generated/`, they form the canonical truth surface
that downstream checks and the AI loader read from.

This story also seeds `.harness/typecheck_policy.yaml` (declared
mypy_strict_paths + tsc_root) with a permissive matching schema, since
`extract_test_coverage_required_paths` consumes it and the H.1d.1
typecheck_policy check expects it to exist.

## Decision

Add five generators under `.harness/generators/`:

- **`extract_backend_routes.py`** — AST-walks `backend/src/api/**/*.py`,
  parses `@router.<verb>("/path")` decorators, extracts handler name,
  body type (annotation on `payload`/`body` arg), return annotation,
  `Depends(callee)` auth dep, `@limiter.limit` flag, and `CsrfProtect`
  annotation flag. Output: `.harness/generated/backend_routes.json`.
- **`extract_db_models.py`** — AST-walks `backend/src/models/db/*.py`,
  finds `class X(SQLModel, table=True)` classes, extracts class name,
  `__tablename__`, and field annotations (`name: type = Field(...)`)
  including `primary_key` and `max_length`.
- **`extract_storage_gateway_methods.py`** — AST-walks
  `backend/src/storage/gateway.py`, finds `class StorageGateway:` body,
  emits per public method: name, kind (`write` if name starts with
  create/update/delete/etc., else `read`), args + types, return type,
  `audited` (true if body calls `self._audit(...)`), `timed` (true if
  `@timed_query` decorator).
- **`extract_test_coverage_required_paths.py`** — reads
  `.harness/typecheck_policy.yaml.mypy_strict_paths` and emits the
  list with `rationale: "Q19"`.
- **`extract_test_inventory.py`** — walks `backend/tests/**/*.py`,
  counts `def test_*` functions and Hypothesis-decorated tests
  (`@given` or `@given(...)`) per file.

Schemas seeded under `.harness/schemas/generated/` with
`additionalProperties: false` on every entry.
`harness_policy_schema.py` updated to also validate
`.harness/typecheck_policy.yaml` against
`.harness/schemas/typecheck_policy.schema.json`.

## Consequences

- Positive — the AI loader now has a single sorted JSON for every
  backend surface (routes, models, gateway methods, test coverage).
- Positive — `audited`/`timed` flags on gateway methods give the AI a
  cheap way to spot missing audit calls without re-scanning code.
- Positive — `extract_test_coverage_required_paths` ties the typecheck
  policy yaml to a generated artifact, surfacing drift if the yaml
  loses entries.
- Negative — `extract_test_inventory` produces a 551-entry JSON for this
  repo (one row per backend test file). Acceptable: file is small JSON,
  emit-time ~1s.
- Negative — AST extraction is sensitive to import shape. A test file
  using `from hypothesis import given as g` would not be detected as
  Hypothesis. Acceptable today.
- Neutral — typecheck_policy.yaml is now a tracked policy file with a
  schema; future edits go through harness_policy_schema validation.

## Alternatives considered

- **Use FastAPI's `app.routes` runtime introspection** — rejected:
  requires importing the live FastAPI app (slow, side-effecty); the AST
  scan is hermetic and faster.
- **Emit a single combined `backend_inventory.json` instead of five files**
  — rejected: per-domain files are easier to diff in PRs and let
  consumers read only the slice they need.
