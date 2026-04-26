"""Sprint H.0a Story 8 — convention tests that the harness applies to itself.

Per H-24: every check in .harness/checks/ MUST have paired violation +
compliant fixtures under tests/harness/fixtures/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".harness/checks"
FIXTURES_DIR = REPO_ROOT / "tests/harness/fixtures"


def _check_rule_ids() -> list[str]:
    """Return the file-stem (rule id) of every check, excluding helpers."""
    if not CHECKS_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in CHECKS_DIR.glob("*.py")
        if p.stem not in ("__init__", "_common")
    )


@pytest.mark.parametrize("rule_id", _check_rule_ids())
def test_check_has_violation_fixture(rule_id: str) -> None:
    """H-24 — every check has at least one violation fixture."""
    violation_dir = FIXTURES_DIR / "violation" / rule_id
    assert violation_dir.is_dir() and any(violation_dir.iterdir()), (
        f"check `{rule_id}` has no fixtures at {violation_dir.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize("rule_id", _check_rule_ids())
def test_check_has_compliant_fixture(rule_id: str) -> None:
    """H-24 — every check has at least one compliant fixture."""
    compliant_dir = FIXTURES_DIR / "compliant" / rule_id
    assert compliant_dir.is_dir() and any(compliant_dir.iterdir()), (
        f"check `{rule_id}` has no compliant fixtures at "
        f"{compliant_dir.relative_to(REPO_ROOT)}"
    )


def test_convention_test_self_check() -> None:
    """Sanity: validate the validator picks up the H.0a.6 checks."""
    rules = _check_rule_ids()
    assert "claude_md_size_cap" in rules
    assert "owners_present" in rules
