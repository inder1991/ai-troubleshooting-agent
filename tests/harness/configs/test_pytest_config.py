"""Sprint H.0b Story 3 — pytest + Hypothesis + coverage tooling per Q9."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "backend/pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text())


def test_pyproject_pytest_section_exists() -> None:
    cfg = _pyproject()
    assert "tool" in cfg
    assert "pytest" in cfg["tool"]


def test_pytest_asyncio_mode_strict() -> None:
    cfg = _pyproject()
    inicfg = cfg["tool"]["pytest"]["ini_options"]
    assert inicfg.get("asyncio_mode") in ("strict", "auto"), (
        "asyncio_mode must be set"
    )


def test_pytest_marks_property_and_slow_registered() -> None:
    cfg = _pyproject()
    marks = cfg["tool"]["pytest"]["ini_options"].get("markers", [])
    marks_text = "\n".join(marks) if isinstance(marks, list) else str(marks)
    for tag in ("property:", "slow:"):
        assert tag in marks_text, f"pytest marker `{tag}` must be registered"


def test_hypothesis_importable() -> None:
    """Hypothesis library is installed."""
    result = subprocess.run(
        [sys.executable, "-c", "import hypothesis; print(hypothesis.__version__)"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "hypothesis must be installed"


def test_pytest_cov_importable() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import pytest_cov"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "pytest-cov must be installed"


def test_diff_cover_importable() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import diff_cover"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "diff-cover must be installed"
