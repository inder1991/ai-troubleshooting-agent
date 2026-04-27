"""B16 (v1.2.0) — Q21.harness-card-version-mismatch fires on drift.

The check runs in a sandboxed copy of the repo (so it doesn't depend
on the live HARNESS_CARD.yaml + .harness-version pair).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / ".harness/checks/harness_card_version.py"
COMMON = REPO_ROOT / ".harness/checks/_common.py"


def _stage_repo(tmp_path: Path, pin: str, card_version: str) -> Path:
    fake = tmp_path / "fake_repo"
    fake_checks = fake / ".harness" / "checks"
    fake_checks.mkdir(parents=True)
    # Mirror the layout the check expects (parents[2] resolves to
    # `fake/`).
    shutil.copy2(CHECK, fake_checks / "harness_card_version.py")
    shutil.copy2(COMMON, fake_checks / "_common.py")
    (fake_checks / "__init__.py").write_text("")
    (fake / ".harness-version").write_text(pin + "\n")
    (fake / ".harness/HARNESS_CARD.yaml").write_text(
        f"name: ai-harness\nversion: {card_version}\n"
    )
    return fake / ".harness/checks/harness_card_version.py"


def test_check_passes_when_versions_match(tmp_path):
    check = _stage_repo(tmp_path, pin="v1.2.0", card_version="1.2.0")
    result = subprocess.run(
        [sys.executable, str(check)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"check should pass on match. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def test_check_fails_when_versions_drift(tmp_path):
    check = _stage_repo(tmp_path, pin="v1.2.0", card_version="1.0.4")
    result = subprocess.run(
        [sys.executable, str(check)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1, (
        f"check should fail on drift. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "Q21.harness-card-version-mismatch" in result.stdout
    assert "1.0.4" in result.stdout
    assert "1.2.0" in result.stdout


def test_check_silently_passes_when_files_missing(tmp_path):
    """Early bootstrap: HARNESS_CARD.yaml or .harness-version missing
    should not be a check failure."""
    fake = tmp_path / "fake_repo"
    fake_checks = fake / ".harness" / "checks"
    fake_checks.mkdir(parents=True)
    shutil.copy2(CHECK, fake_checks / "harness_card_version.py")
    shutil.copy2(COMMON, fake_checks / "_common.py")
    (fake_checks / "__init__.py").write_text("")
    # Neither file exists.
    result = subprocess.run(
        [sys.executable, str(fake_checks / "harness_card_version.py")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
