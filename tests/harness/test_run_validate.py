"""Sprint H.0a Story 4 — tools/run_validate.py orchestrates lint + typecheck
+ custom checks and emits H-16/H-23 conformant output.

In Sprint H.0a there are no custom checks yet (those land in Sprint H.1),
so the orchestrator's primary job is: invoke ruff, invoke mypy, invoke
the harness-self-check `claude_md_size_cap.py` (which lands in Story 6),
aggregate exit codes, exit 0 if all pass.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_VALIDATE = REPO_ROOT / "tools/run_validate.py"


def test_run_validate_exists() -> None:
    assert RUN_VALIDATE.is_file()


def test_run_validate_fast_smoke() -> None:
    """Smoke: --fast runs at all, produces output (may pass or fail
    depending on repo state). Just asserts it doesn't crash."""
    result = subprocess.run(
        [sys.executable, str(RUN_VALIDATE), "--fast"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode in (0, 1), (
        f"orchestrator crashed (exit {result.returncode}): {result.stderr}"
    )


def test_run_validate_emits_summary_line() -> None:
    """Output must include a final summary line (machine-parseable)."""
    result = subprocess.run(
        [sys.executable, str(RUN_VALIDATE), "--fast"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "VALIDATE_SUMMARY" in result.stdout + result.stderr


def test_run_validate_exits_nonzero_on_check_failure(tmp_path: Path) -> None:
    """If any wrapped check exits non-zero, orchestrator exits non-zero."""
    pytest.skip("Exercised in Story 6 once claude_md_size_cap.py exists.")
