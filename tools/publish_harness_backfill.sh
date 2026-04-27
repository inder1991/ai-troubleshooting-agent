#!/usr/bin/env bash
# One-shot backfill: extract + sign + push v1.1.0, v1.1.1, v1.2.0, v1.2.1
# to github.com/inder1991/ai-harness in chronological order.
#
# Why this exists: the v1.1.0–v1.2.1 hardening batch landed first in this
# consumer repo because the source-side ai-harness was still at v1.0.4.
# This script publishes those four releases as proper signed tags on
# their corresponding carved commits, so consumers see real release
# history (not four tags pointing at the same final commit).
#
# After this script lands the four tags, future ai-harness work goes
# DIRECTLY in github.com/inder1991/ai-harness — see
# `~/.claude/.../memory/feedback_ai_harness_dedicated_repo.md`.
#
# Prereqs:
#   - bash tools/setup_signing.sh has been run (signing key configured).
#   - git, gh, git-filter-repo on PATH.
#   - $(git rev-parse HEAD) is at or after the v1.2.1 closeout commit.
#
# Flags:
#   --dry-run   Print what would happen without pushing or tagging.
#   --skip-gh   Skip GitHub release creation (just push tags).
#
# Exit codes:
#   0   all four releases published.
#   2   precondition failed (missing tool, missing signing key, etc.).
#   3   carved-commit lookup failed for at least one version.
#   4   smoke-test (B17) failed in extract.sh — abort before push.

set -euo pipefail

DRY_RUN=0
SKIP_GH=0
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=1 ;;
        --skip-gh) SKIP_GH=1 ;;
        --help|-h)
            sed -n '1,30p' "$0"
            exit 0
            ;;
        *)
            echo "[ERROR] unknown flag: ${arg}" >&2
            exit 2
            ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="/tmp/ai-harness"
REMOTE_URL="${HARNESS_REMOTE_URL:-https://github.com/inder1991/ai-harness.git}"

# Map: tag → consumer-repo commit message substring used to find the
# corresponding carved commit. The carve via filter-repo preserves
# author + commit message, so we can locate the carved equivalent of
# each batch's closeout commit by `git log --grep`.
#
# v1.1.0 → 65e82576 "feat(v1.1.0 batch): P0 hardening — relative baselines..."
# v1.1.1 → dd6aaf34 "docs(v1.1.1): closeout — 5 stories landed..."
# v1.2.0 → 425f39fd "docs(v1.2.0): closeout — 8 P1 stories landed..."
# v1.2.1 → 4ba080c0 "docs(v1.2.1): closeout — entire SDET audit ledger now closed"
# macOS ships bash 3.2 by default (no `declare -A`); use parallel
# indexed arrays so this script runs without homebrew bash.
VERSIONS=(v1.1.0 v1.1.1 v1.2.0 v1.2.1)
GREP_MARKERS=(
    'feat(v1.1.0 batch): P0 hardening'
    'docs(v1.1.1): closeout'
    'docs(v1.2.0): closeout'
    'docs(v1.2.1): closeout'
)
TAG_MSGS=(
    'ai-harness v1.1.0 — production hardening (B1-B6 closed; relative baselines, regex/format unification, lock+signing safety)'
    'ai-harness v1.1.1 — P0 patch (B7-B10 closed; sign_release scope, CI full-tier, semver tag sort, rotate lock)'
    'ai-harness v1.2.0 — P1 hardening (B11-B18 closed; bootstrap completeness, network timeouts, --trust-key pinning, Q21, extract smoke-test, vitest)'
    'ai-harness v1.2.1 — P2 polish (B19-B27 closed; baseline overwrite guards, fnmatchcase, --protect, pipefail, etc.)'
)
CARVED_COMMITS=("" "" "" "")  # filled in step 2

# --- Preconditions ---

_die() { echo "[ERROR] $*" >&2; exit "${2:-2}"; }

command -v git >/dev/null 2>&1 || _die "git not on PATH"
# extract.sh expects git-filter-repo on PATH; mirror sign_release.sh
# and prepend the local venv (which is where pipx-style installs land
# in this repo).
if [[ -x "${REPO_ROOT}/backend/venv/bin/git-filter-repo" ]]; then
    export PATH="${REPO_ROOT}/backend/venv/bin:${PATH}"
fi
command -v git-filter-repo >/dev/null 2>&1 || \
    _die "git-filter-repo not installed (brew install git-filter-repo, or pip install in backend/venv)"
[[ "${SKIP_GH}" -eq 1 ]] || command -v gh >/dev/null 2>&1 || \
    _die "gh CLI not on PATH (use --skip-gh to skip release creation)"
git config user.signingkey >/dev/null 2>&1 || \
    _die "git user.signingkey not set; run tools/setup_signing.sh first"

# Confirm we're at or past the v1.2.1 closeout in the consumer repo.
if ! git -C "${REPO_ROOT}" log --grep='docs(v1.2.1): closeout' --pretty=%H | head -1 | grep -q .; then
    _die "consumer repo HEAD does not contain the v1.2.1 closeout commit"
fi

echo "[INFO] preconditions OK"
echo "[INFO] dry-run=${DRY_RUN} skip-gh=${SKIP_GH} target=${TARGET}"

# --- Step 1: carve once at HEAD ---

echo "[INFO] running tools/extraction/extract.sh (this includes B17 smoke-test)"
if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] would run: bash ${REPO_ROOT}/tools/extraction/extract.sh"
else
    if ! bash "${REPO_ROOT}/tools/extraction/extract.sh"; then
        _die "extract.sh failed (B17 smoke-test or carve)" 4
    fi
fi

# --- Step 2: locate the carved commit for each version ---

cd "${TARGET}" 2>/dev/null || {
    if [[ "${DRY_RUN}" -eq 1 ]]; then
        echo "[DRY-RUN] (skipping commit-resolution; ${TARGET} not produced under --dry-run)"
        # Bail early on dry-run since we can't verify commit lookups.
        echo "[DRY-RUN] would resolve carved commits + create signed tags + push + cut releases for: ${VERSIONS[*]}"
        exit 0
    fi
    _die "${TARGET} missing — extract.sh must run first" 4
}

for i in "${!VERSIONS[@]}"; do
    ver="${VERSIONS[${i}]}"
    marker="${GREP_MARKERS[${i}]}"
    sha="$(git log --grep="${marker}" --pretty=%H | head -1)"
    if [[ -z "${sha}" ]]; then
        _die "could not locate carved commit for ${ver} (grep marker: '${marker}')" 3
    fi
    CARVED_COMMITS[${i}]="${sha}"
    echo "[INFO] ${ver} → ${sha}"
done

# Sanity check: each later version's commit must be a descendant of the
# previous one (so the tags advance forward in time, not backward).
prev_sha=""
for i in "${!VERSIONS[@]}"; do
    ver="${VERSIONS[${i}]}"
    sha="${CARVED_COMMITS[${i}]}"
    if [[ -n "${prev_sha}" ]]; then
        if ! git merge-base --is-ancestor "${prev_sha}" "${sha}"; then
            _die "${ver} (${sha}) is not a descendant of the previous version's commit (${prev_sha})" 3
        fi
    fi
    prev_sha="${sha}"
done
echo "[INFO] carved-commit chronology verified"

# --- Step 3: ensure origin remote, then create signed tags ---

if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "${REMOTE_URL}"
fi

for i in "${!VERSIONS[@]}"; do
    ver="${VERSIONS[${i}]}"
    sha="${CARVED_COMMITS[${i}]}"
    msg="${TAG_MSGS[${i}]}"
    if git rev-parse "${ver}" >/dev/null 2>&1; then
        echo "[WARN] tag ${ver} already exists locally — skipping (delete it manually if you need to re-sign)"
        continue
    fi
    echo "[INFO] creating signed tag ${ver} → ${sha}"
    if [[ "${DRY_RUN}" -eq 1 ]]; then
        echo "[DRY-RUN] would: git tag -s ${ver} ${sha} -m \"${msg}\""
    else
        git tag -s "${ver}" "${sha}" -m "${msg}"
    fi
done

# --- Step 4: push main + tags ---

echo "[INFO] pushing main + tags to ${REMOTE_URL}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] would: git push --force origin main"
    for ver in "${VERSIONS[@]}"; do
        echo "[DRY-RUN] would: git push origin ${ver}"
    done
else
    git push --force origin main
    for ver in "${VERSIONS[@]}"; do
        git push origin "${ver}"
    done
fi

# --- Step 5: cut GitHub releases ---

if [[ "${SKIP_GH}" -eq 0 ]]; then
    REPO="$(echo "${REMOTE_URL}" | sed -E 's|.*github.com[/:]([^/]+/[^.]+)(\.git)?|\1|')"
    for ver in "${VERSIONS[@]}"; do
        echo "[INFO] cutting GitHub release ${ver} on ${REPO}"
        if [[ "${DRY_RUN}" -eq 1 ]]; then
            echo "[DRY-RUN] would: gh release create ${ver} --repo ${REPO} --notes-file RELEASES.md"
        else
            # `gh release create` will fail if the release already exists;
            # `|| true` keeps the loop going so a partial backfill can resume.
            gh release create "${ver}" \
                --repo "${REPO}" \
                --title "${ver} — signed release" \
                --notes-file "${TARGET}/RELEASES.md" || \
                echo "[WARN] gh release create ${ver} failed (already exists?)"
        fi
    done
fi

echo
echo "[INFO] backfill complete: 4 signed tags pushed to ${REMOTE_URL}"
echo
echo "Verify with:"
echo "  cd /tmp/verify && git clone ${REMOTE_URL} ."
echo "  for v in v1.1.0 v1.1.1 v1.2.0 v1.2.1; do git verify-tag \$v; done"
echo
echo "Then bump this consumer repo's .harness-version to v1.2.1 in a follow-up commit."
