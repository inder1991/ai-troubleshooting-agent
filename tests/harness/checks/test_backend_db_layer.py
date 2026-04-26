"""H.1a.2 — backend_db_layer check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "backend_db_layer"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("sqlmodel_outside_storage.py", "Q8.sqlmodel-quarantine", "backend/src/agents/learning/runner.py"),
        ("asyncsession_outside_storage.py", "Q8.asyncsession-quarantine", "backend/src/api/routes_v4.py"),
        ("raw_sql_unjustified.py", "Q8.raw-sql-unjustified", "backend/src/services/report.py"),
        ("api_model_with_table.py", "Q8.api-model-no-table", "backend/src/models/api/incident_response.py"),
        ("cursor_execute_outside_storage.py", "Q8.execute-quarantine", "backend/src/services/migrate.py"),
    ],
)
def test_violation_fixture_fires(fixture_name: str, expected_rule: str, pretend_path: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend_path,
    )


@pytest.mark.parametrize(
    "fixture_name,pretend_path",
    [
        ("storage_gateway.py", "backend/src/storage/gateway.py"),
        ("api_model.py", "backend/src/models/api/incident_response.py"),
        ("raw_sql_justified.py", "backend/src/storage/analytics.py"),
    ],
)
def test_compliant_fixture_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
