# Tier 2 completion (#10b + #8b)

Status: Accepted
Date: 2026-04-27
Owner: @inder

## Context

The v1.0.2 batch landed Tier 2 partially:
- **#10** mechanism + 1 PoC migration; 11 checks still hardcoded.
- **#8** 3 of 8 schemas tightened; 5 remained `additionalProperties: true`.

This ADR closes Tier 2.

## Decision

### #10b — migrate the remaining 14 checks to `spine_paths()`

Audit found 14 module-level `DEFAULT_ROOTS` constants + 5 inline path
references hardcoded to `backend/`/`frontend/`. Migrated each to
`spine_paths(role, fallback)`:

| Check | New role(s) |
|---|---|
| `audit_emission` | `backend_storage` |
| `backend_async_correctness` | `backend_src` |
| `backend_db_layer` | `backend_src` |
| `backend_testing` | `backend_src` + `backend_tests` (default), inline `backend_tests` + `backend_tests_learning` |
| `backend_validation_contracts` | `backend_models` |
| `contract_typed` | `backend_models_api` + `backend_models_agent` + `backend_learning_sidecars` |
| `frontend_data_layer` | `frontend_src` |
| `frontend_routing` | `frontend_src` |
| `frontend_style_system` | `frontend_src` |
| `frontend_testing` | `frontend_src` |
| `frontend_ui_primitives` | `frontend_src` |
| `security_policy_a` | `backend_src` + `frontend_src` |
| `security_policy_b` | `backend_api` |
| `storage_isolation` | `backend_src` |
| `todo_in_prod` | `backend_src` + `frontend_src` |
| `conventions_policy` (inline) | `backend_src` + `frontend_src` |
| `dependency_policy` (inline) | `backend_pyproject` + `frontend_package_json` + `backend_src` |
| `performance_budgets` (inline) | `backend_contracts` + `backend_storage_gateway` |

`spine_paths.yaml` now declares 17 roles (was 8). New entries:
`backend_models_api`, `backend_models_agent`, `backend_storage_gateway`,
`backend_contracts`, `backend_learning_sidecars`, `backend_tests_learning`,
`backend_pyproject`, `frontend_package_json`. Each is a single
canonical path that a non-monorepo / Python-only / JS-only consumer can
override in their fork without touching check code.

The lone residual `REPO_ROOT / "backend"` reference in `backend_testing.py`
line 266 is a **sentinel comparison** (`if root == REPO_ROOT / "backend"`),
not a path resolution. Left as-is.

After migration: all 145 check tests pass; `validate-fast` clean.

### #8b — tighten the 5 remaining permissive schemas

Each schema now has `additionalProperties: false` + `required` array
listing every top-level key in the live yaml + per-property type
constraints:

- `dependencies.schema.json` — `version`, `spine_paths`, `whitelist`,
  `blacklist`, `audit`. `whitelist`/`blacklist` are objects whose values
  are string arrays (matches the existing nested-by-tier shape).
- `performance_budgets.schema.json` — `version`, `hard`, `soft`. `hard`
  has known sub-keys (`agent_budgets`, `database`, `frontend_bundle`)
  but stays `additionalProperties: true` internally to permit growth.
  `soft` is freeform metric names → `additionalProperties: true`.
- `security_policy.schema.json` — `auth_dependency_names`,
  `auth_decorator_names`, `rate_limit_exempt`, `csrf_exempt`. The two
  exempt arrays now require `^[A-Z]+:.+$` pattern (`VERB:path` shape).
- `accessibility_policy.schema.json` — `incident_critical`,
  `axe_rules_disabled`, `soft_warn`. All three are simple string arrays.
- `typecheck_policy.schema.json` — `mypy_strict_paths`, `tsc_root`.
  Promoted from permissive → strict.

`harness_policy_schema.py` runs clean against all 9 policy yamls (the
8 listed here plus `rule_coverage_exemptions.yaml` which was already
strict).

## Consequences

- Positive — Tier 2 fully closed. Every check is now path-overridable
  via `.harness/spine_paths.yaml`; every policy yaml has shape
  enforcement.
- Positive — JS-only / Python-only / non-monorepo consumers can adopt
  the harness with no check forks, just one yaml override.
- Positive — schema typos (e.g. `backend_dependencies:` instead of
  `backend_pyproject:`) now fail fast at pre-commit instead of
  silently turning off enforcement.
- Negative — adding a new top-level key to any of the 8 tightened
  policy yamls now requires updating both the yaml AND the schema.
  Acceptable; that's the point.
- Negative — the schema for `performance_budgets.hard` keeps
  `additionalProperties: true` because the sub-key set is still
  evolving. Tighten in a follow-up when stable.
- Neutral — `spine_paths.yaml` grew from 8 to 17 keys. Future check
  authors should reuse existing roles where possible to avoid
  proliferation.

## Alternatives considered

- **Inline single-file paths via per-check yamls** (one yaml per
  check) — rejected: too many small files; consumer override surface
  becomes unwieldy.
- **Defer #8b until `performance_budgets.hard` stabilizes** — rejected:
  6 of 7 schemas are stable today; tightening them now catches typo
  regressions. The one unstable region (`hard.*` sub-keys) is
  preserved as `additionalProperties: true` inside the otherwise-
  strict outer schema.
