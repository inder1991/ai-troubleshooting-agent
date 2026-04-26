"""Sprint H.0b Story 2 — Alembic scaffolded for Q8 migrations."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "backend/alembic.ini"
ENV_PY = REPO_ROOT / "backend/alembic/env.py"
VERSIONS_DIR = REPO_ROOT / "backend/alembic/versions"


def test_alembic_ini_exists() -> None:
    assert ALEMBIC_INI.is_file()


def test_alembic_env_exists() -> None:
    assert ENV_PY.is_file()


def test_alembic_versions_dir_exists() -> None:
    assert VERSIONS_DIR.is_dir()


def test_alembic_baseline_migration_exists() -> None:
    """At least one migration file under versions/ named *_baseline.py."""
    candidates = list(VERSIONS_DIR.glob("*_baseline.py"))
    assert candidates, "expected a baseline migration in alembic/versions/"


def test_alembic_history_runs_cleanly() -> None:
    """`alembic history` exits 0 once env.py is wired correctly."""
    result = subprocess.run(
        ["alembic", "history"],
        cwd=REPO_ROOT / "backend",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic history failed: stderr={result.stderr}"
    )
