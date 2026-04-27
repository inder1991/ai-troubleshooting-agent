"""B17 (v1.2.0) — extract.sh must smoke-test the carved repo.

A broken extraction (missing file, manifest skew, non-importable
check) used to ship unnoticed because extract.sh exited cleanly after
the carve commit. This test asserts the script body now runs
`pytest tests/harness` against /tmp/ai-harness and aborts on failure.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools/extraction/extract.sh"


def test_extract_sh_smoke_tests_the_target():
    text = SCRIPT.read_text()
    assert "pytest tests/harness" in text, (
        "extract.sh must invoke `pytest tests/harness` against the carved repo"
    )
    # The smoke test must run AFTER the move to TARGET (not the
    # in-progress mirror), and it must abort the script on failure
    # (otherwise a broken extraction still gets pushed).
    smoke_idx = text.find("pytest tests/harness")
    move_idx = text.find('mv "${MIRROR}" "${TARGET}"')
    assert move_idx >= 0 and smoke_idx > move_idx, (
        "smoke test must run AFTER `mv MIRROR TARGET`"
    )
    # Look for an explicit non-zero exit guarding the smoke result.
    smoke_window = text[smoke_idx: smoke_idx + 500]
    assert "exit" in smoke_window, (
        "smoke-test block must abort on failure (exit non-zero)"
    )
