# Introduce Q17 error_handling_policy check (no silent swallow, preserve chain, narrow types, detail HTTP)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

The harness lacked enforcement for error-handling discipline. Spine modules
contained handlers that silently swallowed exceptions (`except X: pass`),
re-raised wrapped exceptions without `from exc` (losing the cause chain),
raised the bare `Exception` class (forcing callers to catch broadly), and
raised `HTTPException` with no `detail` (returning empty/generic response
bodies). All of these are detectable via AST without runtime tracing.

## Decision

Add `.harness/checks/error_handling_policy.py` enforcing four rules under Q17:

- **Q17.no-pass-in-except** — except handler whose body is exactly `pass`.
- **Q17.reraise-without-from** — inside `except E as exc:`, a `raise NewE(...)`
  without `from exc` (or `from None`). Bare `raise` is fine.
- **Q17.generic-exception-raised** — `raise Exception(...)` /
  `raise BaseException(...)` (configurable via
  `generic_exception_names` in `.harness/error_handling_policy.yaml`).
- **Q17.http-exception-needs-detail** — `raise HTTPException(...)` /
  `raise StarletteHTTPException(...)` without a `detail=` keyword arg or a
  positional second arg.

Existing violations (140: 85 pass-in-except, 47 reraise-without-from, 6
generic-exception-raised, 2 http-exception-needs-detail) are grandfathered
into `.harness/baselines/error_handling_policy_baseline.json`.

## Consequences

- Positive — new spine code preserves cause chains (better tracebacks),
  narrows except handling to a documented intent, and ships HTTP errors with
  actionable detail. Reduces silent failure modes.
- Positive — pure AST, ~1s wall, no external binaries.
- Negative — `Q17.no-pass-in-except` will sometimes fire on legitimate "best
  effort cleanup" handlers. Address case-by-case via baseline or a `# noqa`
  shim later if frequency warrants it.
- Negative — `Q17.reraise-without-from` does not detect `raise NewE() from None`
  as compliant special-case (intentional chain suppression). Acceptable
  today; no live false positives observed.
- Neutral — baseline grows by 140 entries.

## Alternatives considered

- **Lean on `pylint` plugin `broad-except` family** — rejected for the same
  reason as Q16: harness must be zero-extra-deps and produce H-16 unified
  output; bolting on linters means shape adapters and another binary version
  to manage.
- **Detect `raise Exception` only inside `except` (re-raise pattern)** —
  rejected as too narrow; bare `raise Exception(...)` anywhere is a code
  smell that hampers caller error-handling.
