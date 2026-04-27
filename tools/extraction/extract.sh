#!/usr/bin/env bash
# H.3.2 — git-filter-repo extraction.
#
# One-shot script that mirrors DebugDuck to /tmp/ai-harness-mirror, applies the
# carve manifest via git filter-repo (preserves history + authorship for every
# commit that touched any manifest path), moves the result to /tmp/ai-harness,
# and seeds a placeholder README at the new repo root.
#
# Prerequisites:
#   brew install git-filter-repo   # one-time, macOS
#
# Idempotent: re-running wipes /tmp/ai-harness-mirror and /tmp/ai-harness first.
#
# Manual follow-up (H.3.3):
#   cd /tmp/ai-harness
#   git remote add origin git@github.com:<owner>/ai-harness.git
#   git push -u origin main
#   git tag -a v1.0.0 -m "..."
#   git push origin v1.0.0
#
# H-25:
#   Missing input    — exit 2 if git-filter-repo binary not installed.
#   Malformed input  — exit non-zero on any unset variable (set -u).
#   Upstream failed  — set -e so any failed step aborts the whole run.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIRROR="/tmp/ai-harness-mirror"
TARGET="/tmp/ai-harness"
MANIFEST="${REPO_ROOT}/tools/extraction/manifest.txt"

if ! command -v git-filter-repo >/dev/null 2>&1; then
    echo "[ERROR] git-filter-repo not installed. Run: brew install git-filter-repo" >&2
    exit 2
fi

if [[ ! -f "${MANIFEST}" ]]; then
    echo "[ERROR] manifest not found at ${MANIFEST}" >&2
    echo "        Run: python3 tools/extraction/build_manifest.py" >&2
    exit 2
fi

echo "[INFO] mirroring ${REPO_ROOT} → ${MIRROR}"
rm -rf "${MIRROR}" "${TARGET}"
git clone --no-local "${REPO_ROOT}" "${MIRROR}"

echo "[INFO] applying carve manifest (${MANIFEST})"
cd "${MIRROR}"
git filter-repo --paths-from-file "${MANIFEST}" --force

echo "[INFO] moving ${MIRROR} → ${TARGET}"
mv "${MIRROR}" "${TARGET}"

echo "[INFO] seeding standalone README at ${TARGET}/README.md"
cat > "${TARGET}/README.md" <<'EOF'
# ai-harness

Repo-level scaffolding that makes AI-assisted development productive in any
codebase. Two consumers, one contract — humans in IDE + autonomous CI agents.

## Bootstrap a new project

```bash
git clone https://github.com/<owner>/ai-harness /tmp/ai-harness
python3 /tmp/ai-harness/tools/init_harness.py \
  --target /path/to/your/project \
  --owner "@your-team" \
  --tech-stack polyglot
cd /path/to/your/project
make harness-install
make harness
make validate-fast
```

See `docs/plans/2026-04-26-ai-harness.md` for the full design — 25 H-rules,
19 stack-decision Q-rules, 7-sprint implementation history.
EOF

echo "[INFO] copying release notes template → ${TARGET}/RELEASES.md"
cp "${REPO_ROOT}/tools/init_harness_templates/RELEASES.md" "${TARGET}/RELEASES.md"

cd "${TARGET}"
git add README.md RELEASES.md
git -c user.email="harness@local" -c user.name="harness extraction" \
    commit -m "docs: standalone repo README + RELEASES.md + bootstrap quickstart"

echo
echo "[INFO] extraction complete: ${TARGET}"
echo "[INFO] $(git log --oneline | wc -l | tr -d ' ') commits in extracted history"
echo
echo "Next steps (H.3.3):"
echo "  cd ${TARGET}"
echo "  gh repo create <owner>/ai-harness --private --description \"AI development harness\""
echo "  git remote add origin git@github.com:<owner>/ai-harness.git"
echo "  git push -u origin main"
echo "  git tag -a v1.0.0 -m \"ai-harness v1.0.0 — initial release\""
echo "  git push origin v1.0.0"
