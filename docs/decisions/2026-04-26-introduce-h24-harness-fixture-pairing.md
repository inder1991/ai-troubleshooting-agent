# Introduce H-24 harness_fixture_pairing check

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

H-24 in the harness plan requires every check to ship with paired
violation + compliant fixtures so its behavior is testable in isolation
and so future contributors have a clear template. Until now the convention
was unenforced — the H.0a substrate checks (`claude_md_size_cap`,
`owners_present`) had landed without paired fixtures and nothing flagged it.

## Decision

Add `.harness/checks/harness_fixture_pairing.py` enforcing one rule:

- **H24.fixture-pairing-missing** — every `.harness/checks/<rule>.py` (except
  the documented EXEMPT_NAMES list) must have both
  `tests/harness/fixtures/<rule>/violation/` and
  `tests/harness/fixtures/<rule>/compliant/` directories, each containing at
  least one file.

EXEMPT_NAMES: `_common.py`, `__init__.py`, `output_format_conformance.py`,
`harness_rule_coverage.py`, `harness_fixture_pairing.py`,
`harness_policy_schema.py`, `typecheck_policy.py`. These are either
substrate (no per-rule logic) or self-tests that would be circular to
fixture-pair against themselves.

Backfill: paired fixtures created for `claude_md_size_cap` (oversized.md /
within_limit.md) and `owners_present` (no_owner.md / has_owner.md) so the
convention applies retroactively to the H.0a substrate checks.

## Consequences

- Positive — every new check now requires at least two fixture files before
  it can land. Forces the author to think through both the violation case and
  the silent-pass case.
- Positive — runs in <0.1s; fast enough to live in `validate-fast`.
- Negative — adds 4 backfilled fixture files (claude_md_size_cap +
  owners_present pairs) that were never strictly necessary because those
  checks already had dedicated unit tests under `tests/harness/checks/`.
  Acceptable — the convention is the point.
- Neutral — EXEMPT_NAMES grows whenever a new "self-test" check lands
  (rule_coverage, fixture_pairing, policy_schema). Must be kept in sync.

## Alternatives considered

- **Allow checks to declare "no fixtures needed" via frontmatter** —
  rejected as a complexity escape hatch; future contributors would over-use
  it. Hard rule with a small exempt list is cleaner.
- **Auto-generate placeholder fixture stubs at check creation time** —
  rejected; would generate empty files that pass the cardinality check but
  fail the actual unit tests. Forcing the author to write meaningful
  fixtures is the goal.
