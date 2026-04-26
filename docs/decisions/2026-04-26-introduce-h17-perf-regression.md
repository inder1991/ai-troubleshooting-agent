# Tighten H-17 wall budget via FULL_ONLY_CHECKS partition

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

H-17 caps `make validate-fast` at 30s wall to keep the inner-loop gate
viable for a developer running it on every save. After Sprints H.1a→H.1d
landed 25+ checks, the aggregate wall hit ~50s — pre-commit became too
slow to be habit. The per-check times were each fine (≤ 6s); the issue
was 25 sequential subprocess invocations.

## Decision

Partition `.harness/checks/*.py` in `tools/run_validate.py` into two
tiers:

- **Fast tier** (default — runs in `--fast` and `--full`): cheap rules that
  guard everyday edits.
- **FULL_ONLY_CHECKS** (runs only in `--full`): heavyweight checks whose
  rules don't typically regress on a single commit.

Initial FULL_ONLY_CHECKS:
- `output_format_conformance.py` (6–8s; spawns every check with a fixture)
- `backend_testing.py` (4–5s; deep AST scan)
- `frontend_testing.py` (3–4s; TS scan)
- `backend_async_correctness.py` (4s; AST scan)
- `backend_db_layer.py` (3s; AST scan)

After this partition, `validate-fast` settles at ~18s — well inside H-17's
30s budget with headroom for the H.1d.6 baseline-buffer additions.

`tests/harness/test_run_validate.py` gains
`test_run_validate_fast_holds_budget_with_full_suite`: a perf regression
gate that asserts both the 30s wall AND that >=18 checks ran (catches
silent discovery breakage when FULL_ONLY_CHECKS over-grows or the glob
breaks).

## Consequences

- Positive — pre-commit returns to <20s typical wall, restoring developer
  trust in the gate.
- Positive — the new "suite size floor" assertion catches a class of
  regression where moves to FULL_ONLY_CHECKS quietly hollow out the fast
  tier.
- Negative — five rules now miss every commit and only catch on
  `validate-full` / CI. Acceptable: those rules either describe shape
  invariants (output_format_conformance) or scan code paths the typical
  PR doesn't touch (backend tests).
- Negative — moving a check to FULL_ONLY_CHECKS is a soft rule weakening.
  Each addition should be defensible.
- Neutral — the original H.0a `test_run_validate_fast_under_30_seconds`
  assertion is kept verbatim for backward compatibility.

## Alternatives considered

- **Parallelize check invocations** — rejected as out-of-scope and
  complicates output ordering for the H-16/H-23 line stream. Worth
  revisiting if FULL_ONLY_CHECKS grows past two-thirds of the suite.
- **Relax H-17 to 60s** — rejected: the original 30s number was set with
  pre-commit usability in mind. Relaxing it would allow indefinite drift.
- **Cache check results across commits via mtime** — rejected as
  premature; correctness/coherence concerns outweigh perf gain at this
  suite size.
