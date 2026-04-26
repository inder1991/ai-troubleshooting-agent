"""H.1a.9 — todo_in_prod check tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "todo_in_prod"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "has_todo.py",
        expected_rule="discipline.todo-in-prod",
        pretend_path="backend/src/services/ingest.py",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "clean.py",
        pretend_path="backend/src/services/ingest.py",
    )
