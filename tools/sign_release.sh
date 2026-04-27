#!/usr/bin/env bash
# Point 5 — re-extract + sign + push a new harness release.
#
# Usage:
#   bash tools/setup_signing.sh    # one-time, generates signing key
#   bash tools/sign_release.sh v1.0.2
#
# Does:
#   1. Re-runs tools/extraction/extract.sh to produce a fresh /tmp/ai-harness.
#   2. Adds origin (if missing), force-pushes main.
#   3. Creates a SIGNED annotated tag (`git tag -s`) — this requires
#      the signing key from setup_signing.sh.
#   4. Pushes the tag.
#   5. Cuts a GitHub release via gh.
#
# H-25:
#   Missing input    — exit 2 if version arg missing or signing key absent.
#   Malformed input  — extract.sh + git own their own validation.
#   Upstream failed  — set -e aborts.

set -euo pipefail

VERSION="${1:-}"
if [[ -z "${VERSION}" ]]; then
    echo "[ERROR] usage: $0 <version> (e.g. v1.0.2)" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/tmp/ai-harness"
REMOTE_URL="${HARNESS_REMOTE_URL:-https://github.com/inder1991/ai-harness.git}"

# 1. signing key sanity check.
# B7 (v1.1.1): use git's standard local→global→system resolution. v1.1.0's B4
# made setup_signing.sh default to --local, so probing --global only would
# falsely refuse on a clean install.
if ! git config user.signingkey >/dev/null 2>&1; then
    echo "[ERROR] git user.signingkey not set; run tools/setup_signing.sh first" >&2
    echo "        (default scope is --local; pass --global if you want it system-wide)" >&2
    exit 2
fi

# 2. ensure git-filter-repo is on PATH (the venv has it)
export PATH="${REPO_ROOT}/backend/venv/bin:${PATH}"

# 3. re-extract (extract.sh now regenerates the manifest itself)
echo "[INFO] re-extracting from ${REPO_ROOT}"
bash "${REPO_ROOT}/tools/extraction/extract.sh"

# 4. push
cd "${TARGET}"
if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "${REMOTE_URL}"
fi
echo "[INFO] force-pushing main → ${REMOTE_URL}"
git push --force origin main

# 5. signed tag
TAG_MSG=$(cat <<EOF
ai-harness ${VERSION} — signed release

Re-cut after upstream changes; this tag is GPG-signed so the consumer
sync_harness.py verify-tag gate accepts it without --no-verify-tag.

See RELEASES.md for the full change list.
EOF
)
echo "[INFO] creating signed tag ${VERSION}"
git tag -s "${VERSION}" -m "${TAG_MSG}"
git push origin "${VERSION}"

# 6. github release
if command -v gh >/dev/null 2>&1; then
    REPO="$(echo "${REMOTE_URL}" | sed -E 's|.*github.com[/:]([^/]+/[^.]+)(\.git)?|\1|')"
    echo "[INFO] cutting GitHub release on ${REPO}"
    gh release create "${VERSION}" \
        --repo "${REPO}" \
        --title "${VERSION} — signed release" \
        --notes-file "${TARGET}/RELEASES.md" || true
fi

echo
echo "[INFO] release ${VERSION} pushed + signed"
echo "       Verify with: cd /tmp/verify && git clone ${REMOTE_URL} . && git verify-tag ${VERSION}"
