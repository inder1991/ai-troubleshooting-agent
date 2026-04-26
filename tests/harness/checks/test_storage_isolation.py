"""H.1a.10 — storage_isolation check tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "storage_isolation"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "uses_session_execute.py",
        expected_rule="storage.execute-outside-gateway",
        pretend_path="backend/src/api/admin.py",
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "inside_storage.py",
        pretend_path="backend/src/storage/gateway.py",
    )
