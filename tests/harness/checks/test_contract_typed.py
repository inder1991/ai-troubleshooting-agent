"""H.1a.8 — contract_typed check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "contract_typed"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("optional_any.py", "backend/src/learning/sidecars/observation.py"),
        ("dict_str_any.py", "backend/src/models/agent/finding.py"),
        ("bare_any.py", "backend/src/models/api/incident_response.py"),
    ],
)
def test_violation_fires(fixture_name: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule="SL.contract-typed",
        pretend_path=pretend_path,
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "typed.py",
        pretend_path="backend/src/models/api/incident_response.py",
    )
