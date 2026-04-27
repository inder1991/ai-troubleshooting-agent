# GPG signing infrastructure (point 5)

Status: Accepted
Date: 2026-04-27
Owner: @inder

## Context

Commit `89d3b70` (point 3) added a tag-verification gate to
`tools/sync_harness.py`: by default, the script refuses to overlay
unless the pinned ref is a GPG-signed annotated tag.

The build machine had no GPG installed when v1.0.0 and v1.0.1 were
pushed, so both tags are unsigned. Consumers who try `make harness-
sync` against either must pass `--no-verify-tag`, which defeats the
gate. v1.0.2 needs to ship signed.

## Decision

Three new artifacts:

### `tools/setup_signing.sh` (one-time per machine)

- Installs `gnupg` via brew if missing.
- If no signing key exists, generates a passphrase-less Ed25519 key
  with default identity `ai-harness signer <ai-harness@local>`
  (override via `SIGNING_NAME` / `SIGNING_EMAIL` env vars). 2-year
  expiry. `%no-protection` for unattended CI use; intended for a
  dedicated release-signing key, not personal long-term identity.
- Configures git globally:
  - `user.signingkey = <fingerprint>`
  - `commit.gpgsign = false` (we sign tags, not commits)
  - `tag.gpgsign = true`
- Prints the public key block for paste into `docs/keys.md`.

Idempotent: re-running with an existing key reuses it; with git
already configured, no-op.

### `tools/sign_release.sh <version>`

End-to-end release runner:

1. Sanity-check that `user.signingkey` is configured.
2. Put `git-filter-repo` on PATH (from the venv).
3. Re-run `tools/extraction/extract.sh` to produce `/tmp/ai-harness`.
4. Add origin if missing; force-push `main`.
5. Create a SIGNED annotated tag (`git tag -s`).
6. Push the tag.
7. Cut a GitHub release via `gh`.

`HARNESS_REMOTE_URL` env var overrides the default
`github.com/inder1991/ai-harness.git`.

### `tools/init_harness_templates/keys.md`

Lists the trusted public keys consumers should `gpg --import` before
running `make harness-sync`. `extract.sh` now copies this file to
`docs/keys.md` in the standalone repo so the key is shipped alongside
the code that requires it.

## Consequences

- Positive — v1.0.2+ tags ship signed; consumers don't need
  `--no-verify-tag`. The verification gate from point 3 actually does
  its job for the first time.
- Positive — the setup is documented + scripted; future maintainers
  can rotate keys via `setup_signing.sh` after `gpg --delete-secret-
  keys` of the old fingerprint.
- Positive — `keys.md` ships in the standalone repo, so consumers
  can `gpg --import` directly from a known location.
- Negative — the default key is passphrase-less. For a personal
  signing identity, generate yours separately with a passphrase and
  point `git config user.signingkey` at it. The auto-generated key is
  intended for the release pipeline, not personal use.
- Negative — Ed25519 keys aren't supported by every old GPG client.
  Consumers on `gpg < 2.1` must upgrade. Acceptable in 2026.
- Neutral — `tools/extraction/extract.sh` now copies one extra file.

## Alternatives considered

- **Sigstore / cosign keyless signing** — rejected for v1: requires
  a public OIDC identity provider (GitHub Actions OIDC, etc.) and
  Fulcio/Rekor infrastructure. Too much rope for a personal repo's
  first signed release. Future v2 upgrade path.
- **GitHub-only signing via `gh attestation`** — rejected: only valid
  inside GitHub's ecosystem; consumers cloning from other Git mirrors
  couldn't verify.
- **SSH signing (`gpg.format = ssh`)** — rejected: works for Git but
  not for `git verify-tag` in the way `sync_harness.py` expects.
  Native GPG is the lowest-friction path that the verify gate
  recognizes today.
