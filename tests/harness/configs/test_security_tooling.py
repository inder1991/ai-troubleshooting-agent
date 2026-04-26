"""Sprint H.0b Story 6 — gitleaks + .gitleaks.toml + slowapi (Q13)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
GITLEAKS_TOML = REPO_ROOT / ".gitleaks.toml"


def test_gitleaks_toml_exists() -> None:
    assert GITLEAKS_TOML.is_file()


def test_gitleaks_toml_loads() -> None:
    tomllib.loads(GITLEAKS_TOML.read_text())


def test_gitleaks_toml_has_default_rules_inherited() -> None:
    """We don't redefine the world; we extend gitleaks defaults."""
    text = GITLEAKS_TOML.read_text()
    assert "[extend]" in text or "useDefault" in text


def test_gitleaks_binary_available_or_skipped() -> None:
    """gitleaks may not be on every dev box; this test documents that it's
    expected on CI but not blocking locally."""
    if shutil.which("gitleaks") is None:
        import pytest
        pytest.skip("gitleaks not installed locally; will run in CI")
    result = subprocess.run(["gitleaks", "version"], capture_output=True, text=True)
    assert result.returncode == 0


def test_slowapi_importable() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import slowapi"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "slowapi must be installed"
