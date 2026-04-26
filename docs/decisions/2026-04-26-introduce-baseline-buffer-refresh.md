# Introduce baseline buffer + refresh tool (H.1d.6)

Status: Accepted
Date: 2026-04-26
Owner: @inder

## Context

Sprints H.1a / H.1b / H.1c each landed a check that, on first live-repo
run, surfaced hundreds-to-thousands of pre-existing violations. The pattern
that emerged:

1. Run check.
2. Manually re-snapshot `[ERROR]` lines into
   `.harness/baselines/<rule>_baseline.json`.
3. Commit.

Each sprint did this differently, with hand-rolled inline scripts. The
result was inconsistent baseline shapes (some entries with absolute paths,
some with project-relative; some sorted, some not), no single command to
re-baseline everything after a structural change, and no documented
ownership for the deferred tech debt.

`load_baseline()` in `.harness/checks/_common.py` already exists and every
H.1a/b/c check already filters against its baseline (added incrementally
through prior sprints). What was missing: the regen tool, the docs, and the
ownership log.

## Decision

Add three artifacts:

- **`tools/refresh_baselines.py`** — walks `.harness/checks/*.py`
  (excluding substrate + self-tests + typecheck_policy), runs each check
  with no baseline filter, parses `[ERROR]` lines via the canonical
  `[ERROR] file=<path>:<line> rule=<id> ...` regex, deduplicates,
  sorts, writes `{file, line, rule}` JSON with `sort_keys=True`,
  `indent=2`, trailing newline. Backs up the existing baseline before each
  run so the check sees no filter; restores on crash.
- **`Makefile` target `harness-baseline-refresh`** — `python3
  tools/refresh_baselines.py`.
- **`.harness/baselines/_TICKETS.md`** — table mapping each baseline file
  to (count, owner, tracking, notes). The "AI fix-loop" instructions
  (Sprint H.2) point here so deferred tech debt has a visible home.

The output is **deterministic**: a clean re-run produces a byte-identical
file. Verified empirically.

## Consequences

- Positive — `make harness-baseline-refresh` is now the one command after
  any structural change (e.g. line shifts from a refactor) instead of 22
  hand-rolled snippets.
- Positive — `_TICKETS.md` puts a name on every grandfathered debt list,
  so "we'll get to it" doesn't drift forever.
- Positive — re-snapshots replace any stale absolute-path entries with
  project-relative paths, normalizing prior sprints' inconsistencies.
- Negative — the tool always reads the WHOLE baseline regardless of small
  edits; for a large baseline (e.g. `frontend_style_system_baseline.json`
  at 2528 entries) the disk write is non-trivial. Acceptable.
- Negative — running it accidentally widens the baseline if the check
  itself broke and now silently overlooks rules. Mitigated by Q19's
  baseline-grew-without-adr gate.
- Neutral — six new empty baseline files appear (audit_emission,
  backend_validation_contracts, claude_md_size_cap, contract_typed,
  owners_present, performance_budgets) — checks that genuinely had no
  live violations. They serve as documentation that the rule is enforced
  but currently has nothing to grandfather.

## Alternatives considered

- **Only re-baseline checks whose .py changed since last run** — rejected
  as premature optimization; the perf cost of refreshing every baseline is
  ~20s on this repo.
- **Inline the refresh logic into each check via a `--regen-baseline`
  flag** — rejected: would couple every check to its own baseline writer
  and make the deterministic-output guarantee harder to enforce centrally.
- **Defer `_TICKETS.md` to a follow-up** — rejected: the H.2 fix-loop
  instructions need a single document to point Claude at when it sees a
  baselined finding.
