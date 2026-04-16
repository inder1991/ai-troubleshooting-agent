"""Phase 4 non-impact assertion — purely frontend, no backend changes."""
from __future__ import annotations
import subprocess

def test_backend_non_impact():
    result = subprocess.run(
        ["git", "diff", "main..HEAD", "--name-only", "--", "backend/"],
        capture_output=True, text=True,
    )
    changed = [f for f in result.stdout.strip().splitlines() if f]
    allowed = {"backend/tests/test_phase4_non_impact.py"}
    unexpected = [f for f in changed if f not in allowed]
    assert not unexpected, f"Unexpected backend changes: {unexpected}"

def test_investigation_ui_non_impact():
    result = subprocess.run(
        ["git", "diff", "main..HEAD", "--name-only", "--",
         "frontend/src/components/Investigation/"],
        capture_output=True, text=True,
    )
    changed = [f for f in result.stdout.strip().splitlines() if f]
    assert not changed, f"Investigation UI changed: {changed}"
