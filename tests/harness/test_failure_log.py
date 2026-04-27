"""Point #25 — rolling failure log tests.

Verifies that tools/run_validate.py writes to .harness/.failure-log.jsonl
when a check emits an [ERROR] line, that the entries parse cleanly, and
that the rotation logic at the size cap works.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_VALIDATE = REPO_ROOT / "tools" / "run_validate.py"
LOG_PATH = REPO_ROOT / ".harness" / ".failure-log.jsonl"
ROTATED_PATH = REPO_ROOT / ".harness" / ".failure-log.jsonl.1"


@pytest.fixture
def isolated_log():
    """Save + restore the failure log so tests don't pollute the real one."""
    backup = LOG_PATH.read_bytes() if LOG_PATH.exists() else None
    rotated_backup = ROTATED_PATH.read_bytes() if ROTATED_PATH.exists() else None
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    if ROTATED_PATH.exists():
        ROTATED_PATH.unlink()
    yield
    if LOG_PATH.exists():
        LOG_PATH.unlink()
    if ROTATED_PATH.exists():
        ROTATED_PATH.unlink()
    if backup is not None:
        LOG_PATH.write_bytes(backup)
    if rotated_backup is not None:
        ROTATED_PATH.write_bytes(rotated_backup)


def test_run_validate_appends_to_failure_log(isolated_log, tmp_path: Path) -> None:
    """When a check emits [ERROR], run_validate must append a JSONL entry.

    Strategy: install a synthetic check script that always emits one ERROR,
    invoke run_validate via the public --fast entrypoint, then read the log.
    """
    # Stage a synthetic check at .harness/checks/ that emits a known [ERROR].
    fake_check = REPO_ROOT / ".harness" / "checks" / "_failure_log_test_check.py"
    fake_check.write_text(
        "import sys\n"
        'print(\'[ERROR] file=fake/path.py:99 rule=TEST.fake-rule '
        'message="synthetic" suggestion="ignore"\')\n'
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [sys.executable, str(RUN_VALIDATE), "--fast"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
        )
        assert LOG_PATH.exists(), f"failure log not created at {LOG_PATH}"
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        # Find at least one entry from our synthetic check.
        matching = [
            json.loads(line) for line in lines
            if "TEST.fake-rule" in line
        ]
        assert matching, (
            f"no entry for TEST.fake-rule in log. Sample entries: {lines[:3]}"
        )
        entry = matching[-1]
        # Schema sanity.
        assert entry["rule"] == "TEST.fake-rule"
        assert entry["file"] == "fake/path.py"
        assert entry["line"] == 99
        assert "ts" in entry and entry["ts"]
        assert "session" in entry
        assert "host" in entry
    finally:
        fake_check.unlink(missing_ok=True)


def test_failure_log_rotation_at_cap(isolated_log) -> None:
    """When the log exceeds 10 MB, run_validate rotates it to .1 (drops older .1)."""
    # Pre-fill the log past the 10 MB cap with junk so the next run rotates it.
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = ("x" * 1024 + "\n").encode("utf-8")
    with LOG_PATH.open("wb") as fh:
        for _ in range(10 * 1024 + 100):  # > 10 MB
            fh.write(payload)
    pre_size = LOG_PATH.stat().st_size
    assert pre_size > 10 * 1024 * 1024

    # Pre-existing rotated file should be deleted by the rotation step.
    ROTATED_PATH.write_bytes(b"old-rotation-content\n")

    # Run validate-fast (any invocation triggers rotation check before writes).
    subprocess.run(
        [sys.executable, str(RUN_VALIDATE), "--fast"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )

    # After rotation, the OLD log is now .1 (still ~10 MB) and the live log
    # holds only fresh entries from this run (much smaller than the pre-rotated size).
    assert ROTATED_PATH.exists()
    assert ROTATED_PATH.stat().st_size > 10 * 1024 * 1024
    # Live log either doesn't exist (if no errors fired) or is tiny.
    if LOG_PATH.exists():
        assert LOG_PATH.stat().st_size < 1024 * 1024  # well under 1 MB

    # The OLD .1 backup we wrote was overwritten — content is the rotated log,
    # not "old-rotation-content".
    assert b"old-rotation-content" not in ROTATED_PATH.read_bytes()
