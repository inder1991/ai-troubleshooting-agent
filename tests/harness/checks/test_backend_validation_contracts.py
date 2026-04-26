"""H.1a.4 — backend_validation_contracts check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "backend_validation_contracts"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("api_request_no_forbid.py", "Q10.api-request-needs-forbid", "backend/src/models/api/incident_request.py"),
        ("api_response_not_frozen.py", "Q10.api-response-needs-frozen", "backend/src/models/api/incident_response.py"),
        ("agent_missing_strict.py", "Q10.agent-needs-forbid-and-frozen", "backend/src/models/agent/log_finding.py"),
        ("confidence_no_bounds.py", "Q10.probability-needs-bounds", "backend/src/models/agent/score.py"),
        ("extra_allow_in_api.py", "Q10.no-extra-allow-in-boundary", "backend/src/models/api/loose_request.py"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("clean_api_request.py", "backend/src/models/api/incident_request.py"),
        ("clean_api_response.py", "backend/src/models/api/incident_response.py"),
        ("clean_agent_schema.py", "backend/src/models/agent/log_finding.py"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
