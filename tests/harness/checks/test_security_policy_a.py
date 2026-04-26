"""H.1c.1 — security_policy_a check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "security_policy_a"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("has_eval.py", "Q13.dangerous-pattern", "backend/src/services/x.py"),
        ("has_shell_true.py", "Q13.dangerous-pattern", "backend/src/services/x.py"),
        ("yaml_load_unsafe.py", "Q13.dangerous-pattern", "backend/src/services/x.py"),
        ("dangerously_set_inner_html.tsx", "Q13.dangerous-pattern", "frontend/src/components/Foo.tsx"),
        ("verify_false_httpx.py", "Q13.tls-verify-required", "backend/src/services/fetch.py"),
        ("timeout_none_httpx.py", "Q13.outbound-timeout-required", "backend/src/services/fetch.py"),
        ("logger_leaks_secret.py", "Q13.log-secret-leak", "backend/src/services/auth.py"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
        extra_args=["--no-gitleaks"],
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("safe_shell.py", "backend/src/services/x.py"),
        ("yaml_safe_load.py", "backend/src/services/x.py"),
        ("inner_text.tsx", "frontend/src/components/Foo.tsx"),
        ("redacted_logger.py", "backend/src/services/auth.py"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
        extra_args=["--no-gitleaks"],
    )
