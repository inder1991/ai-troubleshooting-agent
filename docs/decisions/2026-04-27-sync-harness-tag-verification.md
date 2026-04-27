# Sign-and-verify gate for sync_harness

Status: Accepted
Date: 2026-04-27
Owner: @inder

## Context

Sprint H.3.5 shipped `tools/sync_harness.py`, which reads
`.harness-version`, shallow-clones the upstream `inder1991/ai-harness`
repo at that ref, and overlays the harness substrate (`.harness/` +
the canonical `tools/*` files) into the consumer's working tree.

The original implementation trusted whatever the tag pointed at. That
is the same threat profile as `curl | bash`: anyone with write access
to the upstream repo (or a man-in-the-middle on the clone) can land
malicious code in a tag and every consumer that runs `make
harness-sync` overlays it. Since the overlay includes executable
Python under `tools/`, this is direct code execution on the
consumer's machine on the next pre-commit run.

## Decision

Add a tag-verification gate to `tools/sync_harness.py`:

- After the shallow clone, run `git cat-file -t $REF` to confirm the
  ref points at an annotated **tag** object (not a branch, not a
  lightweight tag, not an arbitrary commit).
- Run `git verify-tag $REF` against the cloned tempdir. The tag must
  be GPG-signed with a key in the consumer's keyring.
- On failure, exit code 3 (new code, distinct from the existing
  exit 2 for missing-input / clone-failure).
- Provide an explicit `--no-verify-tag` escape hatch for environments
  that don't have GPG configured (CI bootstraps, fresh dev machines).
  When used, the script emits a loud `[WARN] tag verification
  SKIPPED ... Re-enable verification ASAP.` to stderr.

Three new tests (network-free; create local file:// upstream repos):

- `test_unsigned_tag_is_rejected_by_default` — annotated but unsigned
  tag → exit 3.
- `test_lightweight_tag_is_rejected` — non-annotated tag → exit 3.
- `test_no_verify_tag_overlay_proceeds_with_warning` — escape hatch
  works AND the warning is emitted.

## Consequences

- Positive — closes the supply-chain attack vector for harness sync.
  An attacker must now also compromise the upstream signing key, not
  just push a tag.
- Positive — `--no-verify-tag` documents the escape hatch but makes
  it loud, so it's hard to ship a long-lived bypass by accident.
- Positive — exit code 3 is distinct from "couldn't connect" (2),
  giving CI a clear signal to gate on.
- Negative — every consumer must have a GPG keyring configured with
  the upstream signing key before they can sync. Friction on first
  bootstrap.
- Negative — the upstream maintainer must remember to sign tags
  (`git tag -s` instead of `git tag -a`). The current `v1.0.0` tag on
  `inder1991/ai-harness` is unsigned and will not pass verification —
  it must be re-tagged-and-signed before the next consumer sync, OR
  consumers temporarily use `--no-verify-tag` until v1.0.1.
- Neutral — the verification adds ~50 ms to a sync (one `cat-file`
  + one `verify-tag`), trivial against the multi-second clone.

## Alternatives considered

- **Verify-on-push instead of verify-on-pull** — rejected: requires
  an upstream-side hook configuration that consumers can't audit.
  Verify-on-pull puts the trust check in the consumer's hands.
- **Pin a commit SHA instead of a tag** — rejected: SHAs aren't
  human-readable; bumping is opaque; doesn't prove who authorized
  the bump.
- **Use `gh attestation verify` (Sigstore-style)** — rejected for v1:
  requires GitHub-specific tooling and a Sigstore key
  infrastructure. GPG `verify-tag` is the one-tool-everyone-has
  baseline. Sigstore is a v2 upgrade path.
- **Make verification opt-in instead of opt-out** — rejected: the
  default must be safe. `--no-verify-tag` is the loud escape hatch.
