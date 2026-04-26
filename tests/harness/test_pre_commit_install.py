"""Sprint H.0a Story 7 — `make harness-install` writes an idempotent
pre-commit hook that runs `make validate-fast`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "tools/install_pre_commit.sh"
HOOK = REPO_ROOT / ".git/hooks/pre-commit"


@pytest.fixture
def saved_hook():
    """Save and restore the existing pre-commit hook so the test is non-destructive."""
    backup = HOOK.read_text() if HOOK.exists() else None
    backup_mode = HOOK.stat().st_mode if HOOK.exists() else None
    yield
    if backup is None:
        HOOK.unlink(missing_ok=True)
    else:
        HOOK.write_text(backup)
        if backup_mode is not None:
            HOOK.chmod(backup_mode)


def test_installer_exists() -> None:
    assert INSTALLER.is_file()


def test_installer_writes_hook(saved_hook) -> None:
    HOOK.unlink(missing_ok=True)
    result = subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, f"installer failed: {result.stderr}"
    assert HOOK.exists()
    assert "make validate-fast" in HOOK.read_text()


def test_installer_is_idempotent(saved_hook) -> None:
    HOOK.unlink(missing_ok=True)
    subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, check=True)
    first = HOOK.read_text()
    subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, check=True)
    second = HOOK.read_text()
    assert first == second, "second run changed the hook unexpectedly"


def test_installer_refuses_overwrite_without_force(saved_hook) -> None:
    HOOK.write_text("#!/bin/sh\necho 'pre-existing hook from another tool'\n")
    HOOK.chmod(0o755)
    result = subprocess.run(["bash", str(INSTALLER)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert "exists" in (result.stderr + result.stdout).lower()
    # Hook should still be the pre-existing content.
    assert "pre-existing" in HOOK.read_text()


def test_installer_force_overwrites(saved_hook) -> None:
    HOOK.write_text("#!/bin/sh\necho 'old'\n")
    HOOK.chmod(0o755)
    result = subprocess.run(
        ["bash", str(INSTALLER), "--force"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "make validate-fast" in HOOK.read_text()
