# Introduce Q15 documentation_policy check (docstrings + JSDoc + ADR triggers)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

The harness lacked enforcement for documentation discipline. Spine modules (API,
storage gateway, agent runners, harness checks/generators, tools) frequently
shipped public functions and classes with no docstrings, and frontend service
hooks/utilities shipped without JSDoc — so AI-generated diffs landed without the
"why" any future reader needs. We also had no mechanism to require an ADR when
policy files or harness checks themselves change.

## Decision

Add `.harness/checks/documentation_policy.py` enforcing three rules under Q15:

- **Q15.spine-docstring-required** — every public function/class in spine paths
  (configured in `.harness/documentation_policy.yaml`) must have a non-empty
  docstring. AST-based; private (`_`-prefixed) names are exempt.
- **Q15.frontend-jsdoc-required** — every `export const|function|class` under
  `frontend/src/{hooks,lib,services}/**` must have a `/** ... */` comment in
  the 400 chars immediately preceding the declaration.
- **Q15.adr-required-on-change** — when any path matching
  `adr_required_on_change` globs is in the working-tree diff vs HEAD, the same
  diff must add a new `docs/decisions/<YYYY-MM-DD>-*.md` (anything except
  `_TEMPLATE.md`).

Existing violations (766: 424 docstring + 342 JSDoc) are grandfathered into
`.harness/baselines/documentation_policy_baseline.json`. New code must comply.

## Consequences

- Positive — public spine APIs grow purpose/contract docs as they're touched;
  reviewers can rely on JSDoc for frontend service surface; policy/check
  changes carry their own decision record so reviewers see *why*.
- Positive — scoped walk (derive prefixes from policy globs) keeps the check
  under 1.5s, well within the H-17 fast-path budget.
- Negative — touching any harness check or `.harness/*.yaml` now forces an ADR
  even for trivial mechanical edits. Acceptable: those files are load-bearing.
- Neutral — baseline grows by 766 entries, paid down opportunistically as code
  is edited.

## Alternatives considered

- **Block legacy debt instead of grandfathering** — rejected: would require a
  forced ~800-entry doc-writing pass before any other harness work could ship.
- **Require ADR only on `.harness/*.yaml` (not on check code)** — rejected:
  check logic is the policy in practice; behavior changes there matter as much
  as YAML edits.
- **Skip JSDoc rule, lean on TS types** — rejected: types describe shape, not
  intent or invariants; service-layer surface is exactly where intent matters.
