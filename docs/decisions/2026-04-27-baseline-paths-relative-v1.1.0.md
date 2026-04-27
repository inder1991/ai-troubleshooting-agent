# Store baseline `file` entries as repo-relative POSIX paths (v1.1.0)

Status: Accepted
Date: 2026-04-27
Owner: @inder

## Context

The v1.0.x harness wrote `.harness/baselines/*.json` entries with whatever
string the check passed to `emit()` — which, for any check that called it
with a `Path` object resolved against `REPO_ROOT`, was an *absolute* path
("/Users/gunjanbhandari/Projects/ai-troubleshooting-systetm/backend/...").

Two failure modes followed:

1. **CI ≠ local.** A baseline snapshotted on a developer's MacBook stops
   suppressing anything in GitHub Actions because `/runner/work/...` !=
   `/Users/.../`. Every previously-suppressed finding becomes a CI fail
   the moment the baseline lands.
2. **Cross-developer churn.** Two devs on the same branch produce
   byte-different baselines; merges become noise.

The SDET audit catalogued this as bug **B1** (P0). Of 7,748 baseline
entries shipped in v1.0.4, 7,747 were absolute.

## Decision

1. `_common.normalize_path(file)` returns a repo-relative POSIX string
   (`backend/foo.py`) for any path inside `REPO_ROOT`, and the
   POSIX-form path verbatim for paths outside.
2. `_common.emit()` runs `file` through `normalize_path()` before
   formatting the H-16 line — *unless* `file` is one of the harness's
   pseudo-path sentinels (`gitleaks`, `mypy`, `tsc`, `git`, `--target`,
   anything ending in `/`, anything containing `://`).
3. `_common.load_baseline()` runs every entry's `file` through
   `normalize_path()` at READ time (migrate-on-read). Foreign-machine
   absolute entries — those whose prefix is not this repo's `REPO_ROOT`
   and that do not resolve into the repo — are dropped with a `[WARN]`
   to stderr telling the user how to re-snapshot.
4. Each check's per-violation suppression (`sig = (... , line, rule)`)
   uses `normalize_path(file)` instead of `str(file)`, so the key shape
   matches what `load_baseline()` returns. (25 sites migrated.)
5. `tools/refresh_baselines.py` grew a `--migrate-paths` flag for
   in-place conversion of legacy v1.0.x baselines without re-running
   every check (which would also pick up new findings — a separate
   decision deserving its own changelog entry).

## Consequences

- Positive — baselines are deterministic across machines and OSes;
  CI / local diverge no more; merges across worktrees stop fighting
  the format.
- Positive — `make harness-baseline-refresh` and
  `--migrate-paths` produce byte-identical output on a clean run.
- Negative — **breaking change for v1.0.x baselines.** Consumers MUST
  either re-snapshot (`make harness-baseline-refresh`) or run
  `python3 tools/refresh_baselines.py --migrate-paths` once after
  upgrading to v1.1.0. Foreign-machine absolute entries get dropped
  loudly; same-machine absolute entries migrate silently on next
  load.
- Neutral — pseudo-path sentinels (`gitleaks`, `mypy`, etc.) keep
  their verbatim shape; no consumer-visible change there.

## Alternatives considered

- **Normalize at write time only.** Rejected: leaves v1.0.x baselines
  loaded by v1.1.0 broken until someone re-snapshots, which can take
  weeks in slow-moving consumer repos.
- **Keep absolute paths; normalize at compare time.** Rejected: every
  check would have to re-implement the same compare; the bug surface
  shifts but doesn't shrink.
- **Two-baseline-format compatibility (read both shapes forever).**
  Rejected: format compatibility shims are exactly the kind of debt
  this harness exists to prevent in *consumer* code.
