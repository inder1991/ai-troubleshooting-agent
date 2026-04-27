# AI Harness — SDET Production-Readiness Audit (post-v1.1.0)

**Date:** 2026-04-27
**Scope:** `.harness/`, `tools/`, `.github/workflows/`, `tests/harness/`,
extraction + signing tooling. Audited at commit `65e82576` immediately
after the v1.1.0 batch (B1–B6) merged.

**Method:** Read every shipping tool top-to-bottom; cross-checked the
v1.1.0 default-scope change against every consumer of `git config`;
hunted for unbounded subprocesses, TOCTOU races, hand-maintained
fields that drift from machine-derived sources, and CI/local divergence.

**Status of v1.0.x audit:**

| ID  | Title | State |
|-----|-------|-------|
| B1  | Baseline `file` paths absolute → CI ≠ local | **Closed (v1.1.0)** |
| B2  | `.failure-log.jsonl` writes race | **Closed (v1.1.0)** |
| B3  | `init_harness --target <self>` overwrites source | **Closed (v1.1.0)** |
| B4  | `setup_signing.sh` mutates `--global` git config | **Closed (v1.1.0)** |
| B5  | Three regex copies parse the H-16 line | **Closed (v1.1.0)** |
| B6  | `\n` in check message corrupts emit format | **Closed (v1.1.0)** |

This pass found **21 new bugs** post-v1.1.0: 4 **P0**, 8 **P1**, 9 **P2**.
None are exploitable, but two (B7, B8) silently weaken behaviors the
v1.1.0 docs claim are working.

---

## P0 — fix in v1.1.1

### B7 — `sign_release.sh` checks `--global` signing key after we made `--local` the default

**File:** `tools/sign_release.sh:34`

```bash
if ! git config --global user.signingkey >/dev/null 2>&1; then
    echo "[ERROR] git user.signingkey not set; run tools/setup_signing.sh first" >&2
    exit 2
fi
```

A user who runs `bash tools/setup_signing.sh` (no args → `--local` per
B4) and then runs `bash tools/sign_release.sh v1.1.1` hits this guard
and is told to run setup again. The "fix" creates a duplicate key and
still fails the guard. Silent regression introduced by B4.

**Fix:** drop `--global`. Let `git config user.signingkey` fall through
the standard `--local → --global → --system` resolution.

**Acceptance:** in a fresh repo, `setup_signing.sh && sign_release.sh
v1.1.1` no longer hits the guard.

---

### B8 — CI gate runs `validate-fast`, not `validate-full` (silently weaker than design)

**File:** `.github/workflows/validate.yml:44`

The workflow comment says: `# H-17 / point #28 — CI gate that runs
\`make validate-full\` on every PR`. The actual command is
`make validate-fast`. That skips `FULL_ONLY_CHECKS` (5 checks:
`output_format_conformance.py`, `backend_testing.py`,
`frontend_testing.py`, `backend_async_correctness.py`,
`backend_db_layer.py`) plus `typecheck_policy.py` (the dedicated
mypy + tsc runner).

A merge can land that fails any of these 6 enforcers without CI ever
catching it.

**Fix:** swap to `make validate-full` in the workflow. Bump
`timeout-minutes` if needed (currently 10; full runs ~3 min on the
local machine for this repo).

**Acceptance:** CI invokes `validate-full`; a deliberately-broken commit
in one of the FULL_ONLY checks fails the workflow.

---

### B9 — `_resolve_latest_tag` lexical-sorts version strings

**File:** `tools/init_harness.py:115`

```python
return sorted(tags)[-1] if tags else "main"
```

Python's `sorted()` on strings is lexical: `["v1.10.0","v1.2.0","v1.0.4"]`
sorts to `['v1.0.4', 'v1.10.0', 'v1.2.0']` → `[-1] == 'v1.2.0'`. Once
the harness ships v1.10.x (or v1.x.10), `init_harness --from-git` will
pin a stale ref.

**Fix:** parse with `packaging.version.parse` (already a transitive dep
via pyyaml/jsonschema), or hand-roll `tuple(int(p) for p in
tag[1:].split("."))`. Reject tags that don't match `v\d+\.\d+\.\d+$`.

**Acceptance:** `_resolve_latest_tag` returns `v1.10.0` from a fixture
list `[v1.0.4, v1.10.0, v1.2.0]`.

---

### B10 — `_rotate_failure_log` is TOCTOU-racy across concurrent validate runs

**File:** `tools/run_validate.py:71-89`

```python
def _rotate_failure_log() -> None:
    if not FAILURE_LOG_PATH.exists(): return
    if FAILURE_LOG_PATH.stat().st_size <= FAILURE_LOG_MAX_BYTES: return
    rotated = FAILURE_LOG_PATH.with_suffix(...".1")
    if rotated.exists(): rotated.unlink()
    FAILURE_LOG_PATH.rename(rotated)
```

Two concurrent `make validate-fast` invocations can both observe
`size > 10 MB`, both rename onto `.1`. The second rename clobbers the
first, losing its rotated entries. B2's `fcntl.LOCK_EX` covers
*append*, not *rotate*; rotate runs once per process at the top of
`run_custom_checks` *before* any lock is taken.

**Fix:** wrap the rotate in the same `LOCK_EX` (open the file, take
the lock, re-check size under lock, rename). Or rotate via
`os.rename(...., "...timestamp.bak")` so concurrent rotates don't
collide on a single `.1` slot.

**Acceptance:** stress test (10 parallel run_validate processes against
a >10 MB log) loses zero entries.

---

## P1 — schedule for v1.2.0

### B11 — `init_harness.py` skips `.gitattributes`

**File:** `tools/init_harness.py:51-110` (`_copy_skeleton`)

The bootstrapper copies `.harness/`, `tools/*`, `.claude/settings.json`,
`tests/harness/`. It does **not** copy `.gitattributes`. v1.0.4 added
`.gitattributes` specifically to keep Windows checkouts from breaking
the byte-deterministic `make harness` regen gate. Bootstrapped repos
miss this protection silently.

**Fix:** add `.gitattributes` to the copy list (after CLAUDE.md, before
`.cursorrules`).

### B12 — `init_harness.py` doesn't write `.harness-version`

`sync_harness.py:142-145` exits 2 if `.harness-version` is missing and
`--ref` not supplied. Bootstrapped repos don't get one — the next
`make harness-sync` fails. Either bootstrap should write the version it
was instantiated from, or the docstring should explicitly say "run
sync first with `--ref <pin>`".

**Fix:** at end of `init_harness.main`, write `args.from_git or
"main"` to `target/.harness-version`.

### B13 — git network operations have no timeout

**Files:** `tools/init_harness.py:115` (`git ls-remote`),
`tools/init_harness.py:132` (`git clone`),
`tools/sync_harness.py:151` (`git clone`).

All use `subprocess.check_call` / `check_output` with no `timeout=`.
A hung remote (DNS issue, partition, dead host) hangs the bootstrap
indefinitely. CI step timeout (10 min) catches it eventually but local
runs do not.

**Fix:** wrap each in `subprocess.run(..., timeout=120, check=True)`
with a clear error on `TimeoutExpired`.

### B14 — check invocations in `run_validate._run` have no timeout

**File:** `tools/run_validate.py:147,165`

`subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)` —
no timeout. A check with an infinite loop (or a generator subprocess
that hangs) stalls validate-fast forever. `refresh_baselines._refresh_one`
*does* take `timeout=180`; `_run` should match.

**Fix:** add `timeout=180` (matches refresh_baselines), catch
`TimeoutExpired`, emit a synthetic `[ERROR] file=<check> rule=harness.timeout`
line.

### B15 — `sync_harness._verify_tag` accepts ANY key in the consumer keyring

**File:** `tools/sync_harness.py:112-115`

```python
verify = subprocess.run(["git", "verify-tag", ref], ...)
```

`git verify-tag` succeeds for any signature against any key in the
consumer's local keyring. A consumer who has imported many keys (open
source maintainers often have hundreds) downgrades the trust model: an
attacker who controls *any* of those keys + write access to the
upstream repo can ship overlay code.

**Fix:** add `--trust-key <FPR>` (or `HARNESS_TRUST_KEY` env). When
set, parse `verify.stderr` for the `using ... key <FPR>` line and
require the fingerprint to match. Document the v1.1.0 source key
fingerprint in `init_harness_templates/keys.md`.

### B16 — `HARNESS_CARD.yaml.version` is hand-maintained; drifts from `.harness-version`

Currently shows `version: 1.0.4` even though v1.1.0 is the in-flight
release. There's no check that flags drift between the card's `version`
field and the consumer's `.harness-version`.

**Fix:** add a check `harness_card_version.py` that asserts
`HARNESS_CARD.yaml.version == .harness-version` (stripped of the `v`
prefix). Bake into `validate-fast`.

### B17 — `extract.sh` ships extractions without smoke-testing them

**File:** `tools/extraction/extract.sh`

Carves to `/tmp/ai-harness`, commits a README, and exits. Doesn't run
`pytest tests/harness/ -q --tb=short` against the extracted repo. A
broken extraction (missing file, non-importable check, manifest skew)
ships unnoticed. The `extraction/README.md` documents a manual smoke
test but it's easy to forget.

**Fix:** at the end of `extract.sh`, `cd "$TARGET" && python3 -m
pytest tests/harness/ -q --tb=short` and abort the release path if it
fails.

### B18 — `run_validate.run_tests` claims to run vitest but only invokes pytest

**File:** `tools/run_validate.py:243-253`

Docstring: `"""Backend pytest + frontend vitest. Only in --full mode."""`
Body only runs pytest. Either wire vitest in (`npx vitest run --reporter=dot`
when `frontend/package.json` exists and `node_modules` is present) or
correct the docstring.

---

## P2 — quality polish

### B19 — `_read_existing_count` returns 0 on JSON parse error → growth warning misfires

**File:** `tools/refresh_baselines.py:45-53`

If the previous baseline is corrupt, `_read_existing_count` returns 0;
the subsequent growth check (`old_count > 0`) skips the warning; the
new baseline silently replaces the corrupt one. Should at least log
`[WARN] {path}: previous baseline unreadable; treating growth check as
inapplicable`.

### B20 — `load_harness._read_file_safe` swallows OSError silently

**File:** `tools/load_harness.py:54-59`

Returns empty string on any `OSError`. A permission error or stale
NFS handle becomes "this file is empty," which the AI session sees as
"no rules apply." Should surface via the existing
`malformed_files` channel in `build_context`.

### B21 — `extract.sh` swallows `find -delete` errors

**File:** `tools/extraction/extract.sh:67-68`

`find ... -delete 2>/dev/null || true` — both the redirect and the
`|| true` mask any failure. Should at least log when the find returns
non-zero.

### B22 — `setup_signing.sh` generates passphrase-less keys with no opt-out

**File:** `tools/setup_signing.sh:88` (`%no-protection`)

Acceptable for CI runners; risky for human signers (raw key material on
disk). Add `--protect` flag that prompts for a passphrase, and
mention the trade-off in `--help`.

### B23 — `install_pre_commit.sh` hardcodes `make`

**File:** `tools/install_pre_commit.sh:27` (`exec make validate-fast`)

Falls over on Windows / minimal Docker. Fall back to `python3 tools/run_validate.py
--fast` if `make` isn't on PATH.

### B24 — `load_harness.collect_cross_cutting` uses `fnmatch.fnmatch` (OS-case-sensitivity-dependent)

**File:** `tools/load_harness.py:122`

`fnmatch.fnmatch` follows OS case-sensitivity (insensitive on macOS,
sensitive on Linux per Python docs). Glob results differ across
machines. Switch to `fnmatch.fnmatchcase` for determinism.

### B25 — `refresh_baselines._refresh_one` can erase a baseline if a check returns no findings due to a bug

If a check produces zero `[ERROR]` lines (because a bug made it skip
its scan, not because nothing's wrong), the new baseline is `[]` and
the previous suppression is gone. Next run surfaces every formerly-baselined
finding. Need a sentinel: require the check to emit
`# HARNESS_OK <count>` (or similar) for the writer to treat empty as
intentional. P2 because it's a self-inflicted footgun, not exploitable.

### B26 — `_session_start_hook.sh` lacks `set -eo pipefail`

**File:** `tools/_session_start_hook.sh`

Sets `set +e` / `set -e` around the loader call but never enables
`pipefail`. A failing `head -c 800 "${LOADER_ERR_FILE}"` would silently
emit empty preview. Cosmetic; failure path already advertises non-zero
loader rc.

### B27 — `harness_policy_schema.py` may not cover `HARNESS_CARD.yaml`

Need to confirm the schema check picks up the card. If it doesn't,
there's no guard against a typo in `coverage.covered:` etc. Verify;
add schema if missing.

---

## Suggested rollout

**v1.1.1 (this week)** — B7 (signing flag), B8 (CI gate), B9 (semver
sort), B10 (rotate race). All four are small, all four widen something
the v1.1.0 docs claim is working. Cut a signed v1.1.1 right after.

**v1.2.0 (next sprint)** — B11–B18. Bigger surface (network timeouts,
trust pinning, smoke-test gate). Worth a design pass before
implementing. Can ship a pre-release for early consumers.

**v1.2.x or backlog** — B19–B27. Polish; no consumer-visible breakage.

## Method notes

I limited this pass to the harness substrate. Did NOT audit:
- Consumer-side `backend/`, `frontend/`, or `docs/` content
- The 29 individual check rules' semantics (only their emit/parse
  contracts)
- The 20 generators' output shape (only their orchestration via
  `run_harness_regen.py`)

A second-pass audit covering rule semantics would likely surface 10–20
more findings (incomplete AST coverage, false positives in regex-only
checks, etc.). Out of scope here.
