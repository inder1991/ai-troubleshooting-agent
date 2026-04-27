"""B8 (v1.1.1) — CI workflow must run validate-full, not validate-fast.

The fast tier silently skips FULL_ONLY_CHECKS (output_format_conformance,
backend_testing, frontend_testing, backend_async_correctness,
backend_db_layer) plus typecheck_policy. Six gates that should run in
CI but didn't before this fix.
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/validate.yml"


def test_ci_workflow_runs_validate_full():
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["validate"]["steps"]
    run_steps = [s for s in steps if "run" in s]
    full_step = next(
        (s for s in run_steps if "validate-full" in s["run"]), None,
    )
    assert full_step is not None, (
        "CI must invoke `make validate-full` — fast tier skips "
        "FULL_ONLY_CHECKS + typecheck_policy"
    )
    fast_only = [
        s for s in run_steps
        if "validate-fast" in s["run"] and "validate-full" not in s["run"]
    ]
    assert not fast_only, f"validate-fast still appears: {fast_only}"


def test_ci_workflow_timeout_accommodates_full_tier():
    wf = yaml.safe_load(WORKFLOW.read_text())
    timeout = wf["jobs"]["validate"].get("timeout-minutes", 0)
    assert timeout >= 20, (
        f"validate-full needs ~3-15 min wall; bump timeout-minutes to >=20 "
        f"(currently {timeout})"
    )
