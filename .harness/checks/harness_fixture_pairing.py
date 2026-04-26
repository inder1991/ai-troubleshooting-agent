#!/usr/bin/env python3
"""H-24 self-test — every check has paired violation + compliant fixtures.

One rule:
  H24.fixture-pairing-missing — `.harness/checks/<rule>.py` lacks a paired
                                tests/harness/fixtures/<rule>/violation OR
                                tests/harness/fixtures/<rule>/compliant
                                directory containing >= 1 file.

Exclusions: _common.py, __init__.py, output_format_conformance.py,
harness_*.py self-tests, typecheck_policy.py.

H-25:
  Missing input    — exit 2 if --checks-dir absent.
  Malformed input  — none.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit  # noqa: E402

DEFAULT_CHECKS_DIR = REPO_ROOT / ".harness" / "checks"
DEFAULT_FIXTURES_DIR = REPO_ROOT / "tests" / "harness" / "fixtures"

EXEMPT_NAMES = {
    "_common.py", "__init__.py",
    "output_format_conformance.py",
    "harness_rule_coverage.py",
    "harness_fixture_pairing.py",
    "harness_policy_schema.py",
    "typecheck_policy.py",
}


def _has_at_least_one_file(directory: Path) -> bool:
    if not directory.exists():
        return False
    return any(p.is_file() for p in directory.iterdir())


def scan(checks_dir: Path, fixtures_dir: Path) -> int:
    """For each non-exempt check, require violation/ and compliant/ fixture dirs."""
    if not checks_dir.exists():
        emit("ERROR", checks_dir, "harness.target-missing",
             f"checks dir does not exist: {checks_dir}",
             "pass --checks-dir <path>", line=0)
        return 2
    total_errors = 0
    for check in sorted(checks_dir.glob("*.py")):
        if check.name in EXEMPT_NAMES:
            continue
        rule = check.stem
        violation_dir = fixtures_dir / rule / "violation"
        compliant_dir = fixtures_dir / rule / "compliant"
        if not _has_at_least_one_file(violation_dir):
            emit("ERROR", check, "H24.fixture-pairing-missing",
                 f"`{check.name}` missing violation fixtures at {violation_dir}",
                 "add at least one file under that directory", line=0)
            total_errors += 1
        if not _has_at_least_one_file(compliant_dir):
            emit("ERROR", check, "H24.fixture-pairing-missing",
                 f"`{check.name}` missing compliant fixtures at {compliant_dir}",
                 "add at least one file under that directory", line=0)
            total_errors += 1
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: scan checks-dir/fixtures-dir for missing pairs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path,
                        help="Ignored; provided for orchestrator compatibility.")
    parser.add_argument("--checks-dir", type=Path, default=DEFAULT_CHECKS_DIR)
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES_DIR)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    return scan(args.checks_dir, args.fixtures_dir)


if __name__ == "__main__":
    sys.exit(main())
