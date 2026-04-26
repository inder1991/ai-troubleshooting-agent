"""H.1d.4 — harness_policy_schema check tests."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "harness_policy_schema"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK
SCHEMA = FIXTURE_ROOT / "_test_schema.json"


def test_violation_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "missing_required_key.yaml",
        expected_rule="H21.policy-schema-violation",
        extra_args=["--schema", str(SCHEMA)],
    )


def test_compliant_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "valid_policy.yaml",
        extra_args=["--schema", str(SCHEMA)],
    )
