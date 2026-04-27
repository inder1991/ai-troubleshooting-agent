"""B14 (v1.2.0) — run_validate must enforce a wall budget on every check.

A check with an infinite loop or a hanging I/O operation must not
stall the validate-fast/full orchestrator forever.
"""
from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_run_validate_kills_runaway_check(tmp_path, monkeypatch):
    """Inject a fake check that sleeps 600s; orchestrator must abort
    within ~the configured cap and report failure."""
    fake_checks = tmp_path / "checks"
    fake_checks.mkdir()
    (fake_checks / "_common.py").write_text("")
    (fake_checks / "hang.py").write_text(textwrap.dedent("""
        import time
        time.sleep(600)
    """))

    sys.path.insert(0, str(REPO_ROOT))
    from tools import run_validate

    monkeypatch.setattr(run_validate, "CHECKS_DIR", fake_checks)
    monkeypatch.setattr(run_validate, "CHECK_TIMEOUT_S", 2)
    monkeypatch.setattr(run_validate, "FAILURE_LOG_PATH", tmp_path / ".failure-log.jsonl")

    start = time.monotonic()
    rc = run_validate.run_custom_checks(full=True)
    elapsed = time.monotonic() - start
    assert elapsed < 30, f"runaway check stalled run_validate ({elapsed:.1f}s)"
    assert rc != 0, "run_validate must report failure on timeout"
