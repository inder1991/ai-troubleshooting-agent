# Cross-stack generators (H.2.3) — validation_inventory, dependency_inventory, performance_budgets, security_inventory

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

H.2.3 lands four cross-stack generators that aggregate data the AI loader
needs at session start: every Pydantic boundary model's config and field
bounds; every Python + npm dependency with allow/spine/blacklist status;
the performance-budget caps in a flat shape; and a consolidated security
view that combines policy yaml with the live route inventory.

`extract_security_inventory` introduces the first cross-generator
dependency — it reads `.harness/generated/backend_routes.json` produced
by H.2.2's `extract_backend_routes`. The ordering will be enforced
explicitly by `tools/run_harness_regen.py` in H.2.6.

## Decision

Add four generators:

- **`extract_validation_inventory`** — AST-walks
  `backend/src/models/{api,agent}/**/*.py`, extracts every class's
  `model_config(extra=, frozen=, …)` plus per-field name + annotation +
  `Field(ge=, le=, gt=, lt=, min_length=, max_length=)`.
- **`extract_dependency_inventory`** — parses `backend/pyproject.toml`
  `[project] dependencies` (regex line scan) and `frontend/package.json`
  `dependencies + devDependencies`. Cross-references each with
  `.harness/dependencies.yaml` (whitelist.backend_spine, whitelist.frontend_spine,
  blacklist.global) to set `allowed`/`on_spine` flags.
- **`extract_performance_budgets`** — projects `.harness/performance_budgets.yaml`
  into a flat shape: `{agent_caps, db_query_max_ms, bundle_kb, soft_track}`.
- **`extract_security_inventory`** — combines `.harness/security_policy.yaml`
  (auth_dependency_names, rate_limit_exempt, csrf_exempt) with
  `.harness/generated/backend_routes.json` to compute
  `routes_summary.{total, with_auth, with_rate_limit, with_csrf}`.

All four ship paired schemas under `.harness/schemas/generated/` and a
combined smoke test that runs validation_inventory against a fixture tree
and the other three against the live repo (their inputs are repo-level
yamls/JSON, so a synthetic fixture would not exercise the real shape).

## Consequences

- Positive — the AI loader can now answer "what bounded models exist"
  / "which deps are spine" / "what's the wall-clock budget" / "how
  protected is route X" by reading one JSON each instead of re-scanning.
- Positive — `routes_summary` immediately surfaces the auth/rate-limit/
  csrf coverage ratio without re-parsing 131 route handlers.
- Negative — `extract_dependency_inventory` is regex-based on
  pyproject.toml; structured-comments-style configurations would parse
  oddly. Acceptable today; tighten with `tomllib` in a follow-up.
- Negative — first cross-generator dependency lands here.
  `extract_security_inventory` must run AFTER `extract_backend_routes`.
  H.2.6 orchestrator will sequence them.
- Neutral — live run on this repo: 0 validation models (current code
  doesn't yet group via models/api,models/agent), 0 python deps (extracted
  from pyproject.toml which uses requirements.txt instead), 69 npm deps,
  131 routes summarized.

## Alternatives considered

- **Use `tomllib` for pyproject.toml parsing** — rejected: `tomllib` is
  Python 3.11+ stdlib but the regex approach is simpler and the deps
  list in this repo is a flat array of strings.
- **Skip `routes_summary` and let consumers compute it** — rejected: the
  summary is the most-asked question; pre-computing is cheap.
- **Bundle all four into one `cross_stack_inventory.json`** — rejected:
  same reasoning as H.2.2 — per-domain files diff cleanly in PRs.
