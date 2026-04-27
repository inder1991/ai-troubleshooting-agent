"""B18 (v1.2.0) — run_validate.run_tests claims to run vitest; make it true.

Pre-v1.2.0 the docstring said `Backend pytest + frontend vitest` but
the body only invoked pytest. v1.2.0 wires vitest in, gated on
frontend/package.json + node_modules existing so Python-only consumers
don't fail.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def test_run_tests_invokes_vitest_when_frontend_present(tmp_path, monkeypatch):
    """If frontend/package.json + node_modules exist, run_tests must
    invoke `npx vitest run`."""
    fake_repo = tmp_path / "repo"
    (fake_repo / "backend").mkdir(parents=True)
    (fake_repo / "frontend" / "node_modules").mkdir(parents=True)
    (fake_repo / "frontend" / "package.json").write_text('{"name":"x"}')

    from tools import run_validate
    monkeypatch.setattr(run_validate, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(run_validate, "_have", lambda cmd: True)

    invocations: list[list[str]] = []

    def fake_run(label, cmd, cwd=None):  # noqa: ARG001
        invocations.append(list(cmd))
        return 0

    monkeypatch.setattr(run_validate, "_run", fake_run)
    rc = run_validate.run_tests()
    assert rc == 0
    assert any("vitest" in " ".join(c) for c in invocations), (
        f"vitest never invoked. invocations={invocations}"
    )


def test_run_tests_skips_vitest_when_no_frontend(tmp_path, monkeypatch):
    """Python-only consumers (no frontend/) must not fail."""
    fake_repo = tmp_path / "repo"
    (fake_repo / "backend").mkdir(parents=True)

    from tools import run_validate
    monkeypatch.setattr(run_validate, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(run_validate, "_have", lambda cmd: True)

    invocations: list[list[str]] = []

    def fake_run(label, cmd, cwd=None):  # noqa: ARG001
        invocations.append(list(cmd))
        return 0

    monkeypatch.setattr(run_validate, "_run", fake_run)
    rc = run_validate.run_tests()
    assert rc == 0
    assert not any("vitest" in " ".join(c) for c in invocations), (
        "vitest must NOT be invoked when frontend/ is missing"
    )


def test_run_tests_skips_vitest_when_node_modules_missing(tmp_path, monkeypatch):
    """If frontend/package.json exists but node_modules doesn't, skip
    vitest (don't fail with `npx: vitest not found`)."""
    fake_repo = tmp_path / "repo"
    (fake_repo / "frontend").mkdir(parents=True)
    (fake_repo / "frontend" / "package.json").write_text('{"name":"x"}')
    # No node_modules directory.

    from tools import run_validate
    monkeypatch.setattr(run_validate, "REPO_ROOT", fake_repo)
    monkeypatch.setattr(run_validate, "_have", lambda cmd: True)

    invocations: list[list[str]] = []

    def fake_run(label, cmd, cwd=None):  # noqa: ARG001
        invocations.append(list(cmd))
        return 0

    monkeypatch.setattr(run_validate, "_run", fake_run)
    rc = run_validate.run_tests()
    assert rc == 0
    assert not any("vitest" in " ".join(c) for c in invocations)
