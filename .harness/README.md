---
owner: '@inder'
---
# AI Harness — Contributor's Guide

This directory is the spine of how AI-assisted development works in this repo.
See `docs/plans/2026-04-26-ai-harness.md` for the full design.

## What lives here

- `*.yaml` — policy files (one per domain: dependencies, performance_budgets,
  security_policy, accessibility_policy, documentation_policy, logging_policy,
  error_handling_policy, typecheck_policy, plus `rule_coverage_exemptions.yaml`).
- `*.md` — cross-cutting rule files (loaded by the AI when their `applies_to:`
  glob matches the file the AI is editing).
- `checks/` — Python scripts that enforce rules. Each emits structured findings
  per H-16 (`[SEVERITY] file=… rule=… message=… suggestion=…`). Auto-discovered
  by `tools/run_validate.py`.
- `generators/` — Python scripts that produce machine-readable truth files
  under `generated/`. Auto-derived from source code; never hand-edited.
- `generated/` — JSON truth files. Read by the loader and by checks.
- `schemas/` — JSON Schemas for every policy yaml and every generated file.
- `baselines/` — `mypy_baseline.json` + `tsc_baseline.json` + per-rule
  baselines that grandfather pre-existing violations. See `_TICKETS.md` for
  ownership of each grandfathered debt list.

## Daily flow

1. Make a code change.
2. `make validate-fast` (< 30s) — runs lint + every check in `checks/*.py`
   that's in the fast tier.
3. If anything fails, the output is structured; read the `suggestion=` field
   and apply the fix (the AI does this automatically).
4. Commit. The pre-commit hook (installed via `make harness-install`) re-runs
   `validate-fast`.
5. Push. CI runs `make validate-full` — adds tests + heavyweight checks
   (`backend_testing`, `frontend_testing`, `output_format_conformance`,
   `backend_async_correctness`, `backend_db_layer`, `typecheck_policy`).

## Adding a new rule

1. Add a check at `.harness/checks/<rule_id>.py`. Follow the template:
   - H-25 docstring: state what happens on missing/malformed/upstream-failed
     inputs.
   - Output conforms to H-16/H-23: emit via
     `_common.emit("ERROR"|"WARN"|"INFO", path, rule, message, suggestion, line=N)`.
   - Honor the per-rule baseline via `_common.load_baseline(rule_stem)`.
2. Add paired fixtures: `tests/harness/fixtures/<rule_id>/violation/` (≥ 1 file)
   and `tests/harness/fixtures/<rule_id>/compliant/` (≥ 1 file). H.1d.3 enforces
   this pairing.
3. Add a test at `tests/harness/checks/test_<rule_id>.py` using
   `_helpers.assert_check_fires` + `assert_check_silent`.
4. If the rule has tunable knobs, add them to a `.harness/<topic>_policy.yaml`
   AND `.harness/schemas/<topic>_policy.schema.json`.
5. If the rule is documentation-only, add it to
   `.harness/rule_coverage_exemptions.yaml` with a `reason:`.
6. Add an ADR under `docs/decisions/` (Q15 enforces).

## Adding a new generator

1. Add `.harness/generators/extract_<name>.py`. Use
   `write_generated(name, payload)` from `_common.py` for deterministic output.
2. Add `.harness/schemas/generated/<name>.schema.json`.
3. Add a smoke test under `tests/harness/generators/`.
4. Run `make harness` (alias for `python3 tools/run_harness_regen.py`) to
   invoke the orchestrator and ensure the generator participates.

## Interpreting findings

Every finding has four fields:
- `file=<path>:<line>` — where to look.
- `rule=<id>` — what was violated.
- `message="..."` — what's wrong, in human language.
- `suggestion="..."` — concrete fix for the AI to apply.

If the AI applies the suggestion and the same rule fires again, that's a
signal the rule has a false positive — file an issue rather than fight it.

## Self-tests

The harness checks itself:
- `harness_rule_coverage` — every plan rule has a check or an exemption.
- `harness_fixture_pairing` — every check has paired fixtures.
- `harness_policy_schema` — every yaml + generated JSON validates against its
  schema.
- `output_format_conformance` — every check emits H-16-conformant output.

## Entry points

- `make validate-fast` — inner-loop gate (< 30s, H-17 enforced).
- `make validate-full` — pre-commit / CI gate (adds tests + heavy checks).
- `make harness` — regenerate `generated/*.json` from source.
- `make harness-install` — install the pre-commit hook (idempotent).
- `make harness-baseline-refresh` — re-snapshot every per-rule baseline.
- `make harness-typecheck-baseline` — re-snapshot mypy + tsc baselines.
