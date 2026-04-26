# Introduce H-21 harness_policy_schema check (JSON Schema validation)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

`.harness/*.yaml` policy files drive seven different checks (Q11 deps, Q13
security, Q14 a11y, Q15 docs, Q16 logging, Q17 errors, plus rule coverage
exemptions). A typo in any of those yamls — wrong key spelling, wrong type,
unintended top-level field — silently turned off the rule it described. We
need a hard validation gate so policy edits surface failures at commit time
rather than at the next check run.

## Decision

Add `.harness/checks/harness_policy_schema.py` enforcing two rules:

- **H21.policy-schema-missing** — yaml exists in `.harness/` but no matching
  schema file at `.harness/schemas/<topic>.schema.json`.
- **H21.policy-schema-violation** — yaml fails JSON Schema (draft 2020-12)
  validation against its schema.

The check supports two modes:

- default — walk the explicit `POLICY_YAML_NAMES` map (yaml → schema basename)
  and validate each pair.
- `--target <yaml> --schema <json>` — single-file validation (used by tests).

Schemas seeded for: dependencies, performance_budgets, security_policy,
accessibility_policy, documentation_policy, logging_policy,
error_handling_policy, rule_coverage_exemptions. All start permissive
(`additionalProperties: true`, minimal `required:`) so existing YAMLs validate
clean. Tighten in follow-up PRs as patterns stabilize.

`jsonschema>=4.21` added as a dev dependency (installed via pip).

## Consequences

- Positive — typos and shape regressions in policy yamls now surface at
  pre-commit, not at the next check invocation.
- Positive — `rule_coverage_exemptions.schema.json` enforces the
  `{rule, reason}` contract — future contributors can't add exemptions
  without a reason.
- Negative — schemas are intentionally permissive today. Validation catches
  obvious shape regressions but does not yet enforce per-key constraints.
- Negative — adds `jsonschema` to runtime imports of one harness check.
  Degrades gracefully (WARN, not ERROR) if missing.
- Neutral — `POLICY_YAML_NAMES` map must be updated whenever a new policy
  yaml lands.

## Alternatives considered

- **Generic `*_policy.yaml` glob with `<basename>.schema.json` lookup** —
  rejected: would skip `dependencies.yaml` and other non-`_policy`-suffixed
  files. Explicit map is more discoverable.
- **PyYAML-based schema** (e.g. cerberus) — rejected: JSON Schema is more
  portable and the `jsonschema` python lib has no recursive deps that
  conflict with our spine allowlist.
- **Wait until policies grow before adding validation** — rejected: every
  un-validated yaml edit since H.0a was a silent risk; backfilling the gate
  costs less than living with the risk longer.
