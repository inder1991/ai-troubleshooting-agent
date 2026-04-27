#!/usr/bin/env bash
# B26 (v1.2.1): pipefail so a failed `head -c` in the warning preview
# surfaces instead of silently emitting empty bytes. The hook itself
# always exits 0 (final `exit 0` line) so loader bugs don't abort the
# Claude Code session — this just tightens intermediate error handling.
set -o pipefail
# Session-start wrapper: invokes the harness loader against the repo root.
# Stdout is consumed by Claude Code as system context per its hook contract.
#
# Per H-2/H-4: load_harness.py reads .harness/* (canonical state) plus the
# generated/* files (auto-derived inventories) and emits a single bundled
# context block describing the project's contracts to the AI session.
#
# Failure mode (point 4 hardening): when load_harness.py exits non-zero,
# we MUST surface a visible warning into the session context — silent
# degradation means the AI starts blind without any signal that its
# context is missing. We capture stdout, check the exit code, and
# either pass the output through (success) or emit a loud warning
# (failure). The hook itself ALWAYS exits 0 so a transient loader bug
# doesn't abort the Claude Code session start entirely.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOADER="${REPO_ROOT}/tools/load_harness.py"

# Capture stdout AND stderr separately. We need stderr's content for the
# warning message but want only stdout to reach Claude Code on success.
LOADER_OUT_FILE="$(mktemp -t harness-loader-stdout.XXXXXX)"
LOADER_ERR_FILE="$(mktemp -t harness-loader-stderr.XXXXXX)"
trap 'rm -f "${LOADER_OUT_FILE}" "${LOADER_ERR_FILE}"' EXIT

set +e
python3 "${LOADER}" >"${LOADER_OUT_FILE}" 2>"${LOADER_ERR_FILE}"
LOADER_RC=$?
set -e

if [[ ${LOADER_RC} -eq 0 ]]; then
    cat "${LOADER_OUT_FILE}"
else
    # Truncate stderr to a manageable size in the context; full traceback
    # is still on disk for the developer to re-run manually.
    err_preview="$(head -c 800 "${LOADER_ERR_FILE}")"
    cat <<EOF
[HARNESS_WARN] tools/load_harness.py exited ${LOADER_RC}; session starting WITHOUT harness context.
[HARNESS_WARN] The AI does NOT have policy yamls, generated truth files, or rule references this session.
[HARNESS_WARN] Re-run manually to see the full error: python3 tools/load_harness.py
[HARNESS_WARN] Loader stderr (first 800 chars):
${err_preview}
EOF
fi
exit 0
