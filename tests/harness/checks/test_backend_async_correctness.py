"""H.1a.1 — backend_async_correctness check tests.

Each violation fixture must produce >= 1 ERROR with the matching rule id.
Each compliant fixture must produce zero ERRORs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "backend_async_correctness"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule",
    [
        ("uses_requests.py", "Q7.no-requests"),
        ("uses_aiohttp.py", "Q7.no-aiohttp"),
        ("asyncio_run_in_handler.py", "Q7.no-asyncio-run-in-handler"),
        ("sync_httpx_client.py", "Q7.no-sync-httpx"),
        ("blocking_sleep_in_async.py", "Q7.no-blocking-sleep-in-async"),
    ],
)
def test_violation_fixture_fires(fixture_name: str, expected_rule: str) -> None:
    pretend = (
        "backend/src/api/routes_v4.py" if "asyncio_run_in_handler" in fixture_name
        else f"backend/src/services/{fixture_name}"
    )
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path=pretend,
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "clean.py",
        "async_with_to_thread.py",
    ],
)
def test_compliant_fixture_silent(fixture_name: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path=f"backend/src/services/{fixture_name}",
    )
