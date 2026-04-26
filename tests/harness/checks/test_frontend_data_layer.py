"""H.1b.2 — frontend_data_layer check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "frontend_data_layer"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule,pretend_path",
    [
        ("imports_redux.tsx", "Q2.no-redux", "frontend/src/store.ts"),
        ("imports_zustand_outside_stores.tsx", "Q2.zustand-quarantine", "frontend/src/components/Foo.tsx"),
        ("imports_axios.tsx", "Q3.no-axios", "frontend/src/services/http.ts"),
        ("raw_fetch_in_component.tsx", "Q3.no-raw-fetch-in-ui", "frontend/src/components/Foo.tsx"),
        ("component_imports_services_api.tsx", "Q3.component-no-direct-services-api", "frontend/src/components/Foo.tsx"),
        ("usequery_with_raw_fetch.tsx", "Q3.queryfn-must-use-apiclient", "frontend/src/hooks/useFoo.ts"),
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
        ("uses_query_hook.tsx", "frontend/src/components/Foo.tsx"),
        ("justified_zustand.tsx", "frontend/src/stores/useLayoutStore.ts"),
    ],
)
def test_compliant_silent(fixture_name: str, pretend_path: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=pretend_path,
    )
