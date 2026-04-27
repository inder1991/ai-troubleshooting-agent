# H.3.6 fixes — init_harness ships tests/harness/, dependency_policy silent on missing target

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

Sprint H.3.6's end-to-end smoke (bootstrap an empty `/tmp/playground` from
the live harness via `--from-git` then run `make validate-fast`) surfaced
two design gaps that didn't appear when the harness was used in-place
inside DebugDuck.

## Decision

Two fixes:

1. **`tools/init_harness.py`** now also overlays `tests/harness/` (fixtures
   + helpers + check tests) into the consumer's working tree. Without
   this, H-24 (`harness_fixture_pairing`) fires on every check because
   the consumer has no `tests/harness/fixtures/<rule>/` pairs.

2. **`.harness/checks/dependency_policy.py`** — when the default target
   (`backend/pyproject.toml`) doesn't exist, silently skip instead of
   emitting `harness.target-missing` ERROR. Rationale: the default targets
   don't exist in every consumer (Python-only or JS-only or empty
   playground). Explicit `--target` to a real path still gets validated
   normally; the 7 unit tests for dependency_policy continue to pass
   because they always pass `--target` to a real fixture.

## Consequences

- Positive — `init_harness --from-git ... && make harness-baseline-refresh
  && make validate-fast` now succeeds on an empty bootstrap. Sprint H.3.6
  acceptance criterion ("empty repo, no violations") met.
- Positive — the consumer ships with the H.1d.3 fixture-pairing
  convention already satisfied; new check authors see real templates.
- Negative — `tests/harness/` adds 60+ files to the bootstrap
  payload. Acceptable; they're small and documentation-grade.
- Negative — silent skip in dependency_policy means a typo in the
  default target list goes unflagged. Mitigated: typo would surface as
  "no findings ever" which is a different (more recoverable) failure
  mode than "every commit blocked".
- Neutral — `dependency_policy.scan` becomes more permissive on default
  invocation; explicit-target invocation is unchanged.

## Alternatives considered

- **Document "consumer must seed tests/harness/ themselves"** — rejected:
  fails the H.3.6 smoke test out of the box; first-time users wouldn't
  understand why H-24 is firing.
- **Make `harness.target-missing` a WARN instead of ERROR globally** —
  rejected: ERROR is correct when the user explicitly passed a path that
  doesn't exist; only the implicit-default case should be silent.
