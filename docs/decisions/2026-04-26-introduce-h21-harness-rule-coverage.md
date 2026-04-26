# Introduce H-21 harness_rule_coverage check

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

The harness plan (`docs/plans/2026-04-26-ai-harness.md`) names many H-rules
and Q-decisions, but nothing automatically verifies that each one is
actually implemented (or explicitly waived). New rules could land in the
plan without ever being enforced — the worst kind of harness drift, because
the AI thinks they're enforced and acts accordingly.

## Decision

Add `.harness/checks/harness_rule_coverage.py` enforcing one rule:

- **H21.rule-not-covered** — every `H-N` or `Q<N>[.suffix]` reference in
  `--plans` must be enforced (rule id appears in some `.harness/checks/*.py`)
  OR exempted in `.harness/rule_coverage_exemptions.yaml` with a `reason:`.

Bare `Q<N>` references are satisfied by any `Q<N>.<suffix>` reference in
checks (so e.g. `Q13.route-needs-auth` covers a plan reference to "Q13").

`.harness/rule_coverage_exemptions.yaml` is seeded with exemptions for the
substrate rules (H-2 through H-15, H-17, H-18, H-20, H-26) — these are
enforced implicitly by the loader, orchestrator, baseline machinery, or
output-format gate rather than by per-rule checks. Each exemption carries a
one-line reason.

## Consequences

- Positive — adding a new H-rule to the plan now forces either a check or a
  documented exemption. Closes the "rule on paper but not in code" failure
  mode.
- Positive — surfaces in seconds (~0.1s wall) on every pre-commit.
- Negative — the regex-based reference detector is loose: any `H-N` substring
  in the plan body (even inside an unrelated quote) counts. Acceptable; false
  positives would require an explicit exemption, not a code change.
- Neutral — exemptions yaml is a new artifact future contributors must keep
  in mind. Documented inline at the top of the file.

## Alternatives considered

- **Require every plan rule to ship with its own check** — rejected: many
  rules are substrate (e.g. H-14 single-orchestrator), enforced by the
  harness wiring rather than by a discrete check file. Forcing per-rule
  checks would turn substrate into busywork.
- **Embed coverage assertion inside each check's docstring** — rejected:
  duplicates information already in the plan, and a check covering N rules
  would have to enumerate each in its docstring.
