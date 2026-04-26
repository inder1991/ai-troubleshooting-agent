# Introduce Q19 typecheck_policy check (mypy + tsc baseline diff)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

Sprint H.0b Story 12 seeded `mypy_baseline.json` and `tsc_baseline.json`
under `.harness/baselines/`, but nothing in the harness yet diffed live
mypy/tsc output against those baselines. New type errors could land
silently as long as `mypy --strict` and `tsc --noEmit` were never run by
CI. Q19 closes that loop.

## Decision

Add `.harness/checks/typecheck_policy.py` enforcing five rules:

- **Q19.new-typecheck-finding** — mypy/tsc reports a finding NOT present in the
  committed baseline. Baseline match uses (file, line, code, message) tuple.
- **Q19.baseline-schema-violation** — baseline file is neither a JSON array nor
  an object containing a `violations` array of `{file, line, code, message}`
  entries. Both shapes accepted to support pre-existing wrapped baselines.
- **Q19.baseline-grew-without-adr** — git diff vs HEAD shows
  `.harness/baselines/(mypy|tsc)_baseline.json` modified AND no
  `docs/decisions/<YYYY-MM-DD>-*.md` is staged.
- **Q19.upstream-tool-missing** — mypy or tsc binary not on PATH (degraded
  WARN, not ERROR; CI installs them).
- **(reserved)** Q19.mypy-config-missing / Q19.tsc-config-missing — staged for
  future expansion when policy yaml grows.

The check supports four invocation modes:

- default — run mypy + tsc, diff, ERROR new findings.
- `--replay-output {mypy|tsc} --target <recorded.txt>` — test-only bypass.
- `--validate-baseline-only --target <baseline.json>` — schema gate alone.
- `--regen-baseline` — delegate to `tools/generate_typecheck_baseline.py`.

**Performance gate:** typecheck_policy runs mypy + tsc subprocesses
(~1 minute on this repo). It is excluded from the auto-glob in
`tools/run_validate.py` and dispatched only in `--full` mode via a dedicated
`run_typecheck(full=...)` runner. It is also excluded from
`output_format_conformance` scanning because output_format_conformance would
shell out to it 1× per fixture target. Its dedicated tests under
`tests/harness/checks/test_typecheck_policy.py` exercise every code path
in <2s using replay mode (no mypy/tsc required).

## Consequences

- Positive — no new mypy/tsc finding can land silently; baseline drift
  requires an explicit ADR; pre-existing object-wrapped baseline shape stays
  valid (no forced regen).
- Positive — `--replay-output` makes the diff machinery testable in
  hermetic milliseconds.
- Negative — the check is invisible in `make validate-fast` (lives only in
  `--full`). Pre-commit hook runs `--fast` so locally a developer who skips
  `make validate-full` could land a typecheck regression. CI must enforce
  `--full`.
- Negative — tsc baseline path normalization is heuristic (prepends
  `frontend/` when missing). If someone hand-edits the baseline with absolute
  paths, the diff would silently miss matches. Acceptable; regen via
  `make harness-typecheck-baseline` reseeds the canonical shape.
- Neutral — `tools/run_validate.py` and `output_format_conformance.py` grow
  small SKIP lists.

## Alternatives considered

- **Run mypy + tsc inside `validate-fast`** — rejected: ~60–90s wall, blows
  H-17's 30s budget. Pre-commit would become unusable.
- **Bake `--watch`-mode mypy/tsc daemons into the harness** — rejected as
  over-engineered for a check; daemon lifecycle complicates pre-commit on
  fresh clones and CI.
- **Strip path prefixes by editing `tools/generate_typecheck_baseline.py`** —
  rejected: would force a one-time baseline regen affecting every existing
  baselined entry. The normalization-on-load approach is reversible.
