"""Phase 3 non-impact assertion.

Ensures Phase 3 (frontend-only builder UI) did NOT modify backend code
outside the documented exceptions:
  1. GET /workflows/:id/versions endpoint (routes_workflows.py)
  2. WORKFLOW_RUNNERS_STUB env flag (runners/__init__.py + _stub_testing.py)
  3. Workflow repository + service changes (repository.py, service.py)
  4. Workflow version listing test (test_workflows_list_versions.py)
"""
from __future__ import annotations
import subprocess

def test_backend_non_impact():
    """No backend changes outside the two documented exceptions."""
    result = subprocess.run(
        ["git", "diff", "main..HEAD", "--name-only", "--", "backend/"],
        capture_output=True, text=True
    )
    changed = [f for f in result.stdout.strip().splitlines() if f]

    allowed = {
        "backend/src/api/routes_workflows.py",
        "backend/src/workflows/runners/__init__.py",
        "backend/src/workflows/runners/_stub_testing.py",
        "backend/src/workflows/repository.py",
        "backend/src/workflows/service.py",
        "backend/tests/test_workflows_list_versions.py",
        "backend/tests/test_phase3_non_impact.py",
    }

    unexpected = [f for f in changed if f not in allowed]
    assert not unexpected, f"Unexpected backend changes: {unexpected}"


def test_investigation_ui_non_impact():
    """Investigation UI components untouched by Phase 3."""
    result = subprocess.run(
        ["git", "diff", "main..HEAD", "--name-only", "--",
         "frontend/src/components/Investigation/"],
        capture_output=True, text=True
    )
    changed = [f for f in result.stdout.strip().splitlines() if f]
    assert not changed, f"Investigation UI changed: {changed}"
