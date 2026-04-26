"""H.1d.1 — typecheck_policy check tests.

Two pairs of fixtures verify the baseline-diff machinery in isolation,
without invoking mypy/tsc. Replay mode exercises the parser + diff via
recorded mypy output; --validate-baseline-only exercises the schema gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "typecheck_policy"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


def test_invalid_baseline_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "baseline_invalid.json",
        expected_rule="Q19.baseline-schema-violation",
        extra_args=["--validate-baseline-only"],
    )


def test_valid_baseline_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "baseline_valid.json",
        extra_args=["--validate-baseline-only"],
    )


def test_new_finding_fires() -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / "mypy_new_finding.txt",
        expected_rule="Q19.new-typecheck-finding",
        extra_args=[
            "--replay-output", "mypy",
            "--baseline", str(FIXTURE_ROOT / "compliant" / "baseline_valid.json"),
        ],
    )


def test_only_baselined_findings_silent() -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / "mypy_only_baselined.txt",
        extra_args=[
            "--replay-output", "mypy",
            "--baseline", str(FIXTURE_ROOT / "compliant" / "baseline_valid.json"),
        ],
    )
