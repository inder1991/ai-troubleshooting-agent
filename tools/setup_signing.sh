#!/usr/bin/env bash
# Point 5 — set up GPG signing so sync_harness.py's verify-tag gate works.
#
# Run once per machine. Does:
#   1. Installs gnupg via brew if missing.
#   2. Generates a passphrase-less Ed25519 signing key (default details:
#      "ai-harness signer" <ai-harness@local>) IF no signing key exists.
#      Override via SIGNING_NAME / SIGNING_EMAIL env vars.
#   3. Configures git globally:
#        user.signingkey  = the new fingerprint
#        commit.gpgsign   = false (we sign tags, not commits)
#        tag.gpgsign      = true
#   4. Prints the public key so you can paste it into the standalone repo's
#      docs (so consumers can `gpg --import` it).
#
# Idempotent: re-running with an existing key reuses it; re-running with
# git already configured leaves it alone.
#
# H-25:
#   Missing input    — prompts/aborts if brew/gpg can't be installed.
#   Malformed input  — gpg's own validation handles bad batch params.
#   Upstream failed  — set -e aborts on any step.

set -euo pipefail

SIGNING_NAME="${SIGNING_NAME:-ai-harness signer}"
SIGNING_EMAIL="${SIGNING_EMAIL:-ai-harness@local}"

# 1. gnupg
if ! command -v gpg >/dev/null 2>&1; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "[ERROR] neither gpg nor brew on PATH; install GPG manually" >&2
        exit 2
    fi
    echo "[INFO] installing gnupg via brew"
    brew install gnupg
fi

# 2. signing key
EXISTING="$(gpg --list-secret-keys --keyid-format=long --with-colons 2>/dev/null \
    | awk -F: '$1=="sec" {print $5; exit}')"

if [[ -n "${EXISTING}" ]]; then
    echo "[INFO] using existing signing key: ${EXISTING}"
    KEYID="${EXISTING}"
else
    echo "[INFO] generating new Ed25519 signing key for ${SIGNING_NAME} <${SIGNING_EMAIL}>"
    BATCH_FILE="$(mktemp -t gpg-batch.XXXXXX)"
    trap 'rm -f "${BATCH_FILE}"' EXIT
    cat > "${BATCH_FILE}" <<EOF
%no-protection
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: sign
Name-Real: ${SIGNING_NAME}
Name-Email: ${SIGNING_EMAIL}
Expire-Date: 2y
%commit
EOF
    gpg --batch --gen-key "${BATCH_FILE}"
    KEYID="$(gpg --list-secret-keys --keyid-format=long --with-colons \
        | awk -F: '$1=="sec" {print $5; exit}')"
    echo "[INFO] generated key: ${KEYID}"
fi

# 3. git config
git config --global user.signingkey "${KEYID}"
git config --global commit.gpgsign false   # we sign tags, not commits
git config --global tag.gpgsign true
echo "[INFO] git configured: tag.gpgsign=true, signingkey=${KEYID}"

# 4. public key block (for inclusion in standalone repo docs)
echo
echo "=== PUBLIC KEY (paste into the standalone repo's docs/keys.md) ==="
echo
gpg --armor --export "${KEYID}"
echo
echo "=== END PUBLIC KEY ==="
echo
echo "Next: bash tools/sign_release.sh v1.0.2"
