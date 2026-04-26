"""Sprint H.0a Story 1 — Skeleton smoke tests.

Asserts that the harness directory layout, Makefile entry points, and
README warning files all exist. This is the earliest red test in the
sprint; everything else assumes the skeleton is present.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


REQUIRED_DIRS = [
    "tools",
    ".harness",
    ".harness/checks",
    ".harness/generators",
    ".harness/generated",
    "tests/harness",
]

REQUIRED_FILES = [
    "Makefile",
    "tools/__init__.py",
    ".harness/README.md",
    ".harness/checks/__init__.py",
    ".harness/checks/_common.py",
    ".harness/generators/__init__.py",
    ".harness/generators/_common.py",
    ".harness/generated/README.md",
    "tests/harness/__init__.py",
]

REQUIRED_MAKE_TARGETS = [
    "validate-fast",
    "validate-full",
    "validate",
    "harness",
    "harness-install",
]


@pytest.mark.parametrize("rel", REQUIRED_DIRS)
def test_required_directory_exists(rel: str) -> None:
    assert (REPO_ROOT / rel).is_dir(), f"missing directory: {rel}"


@pytest.mark.parametrize("rel", REQUIRED_FILES)
def test_required_file_exists(rel: str) -> None:
    assert (REPO_ROOT / rel).is_file(), f"missing file: {rel}"


def test_make_dry_run_lists_required_targets() -> None:
    """`make -n <target>` exits 0 for every required target."""
    if shutil.which("make") is None:
        pytest.skip("make not on PATH")
    for target in REQUIRED_MAKE_TARGETS:
        result = subprocess.run(
            ["make", "-n", target],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"make -n {target} failed: stderr={result.stderr.strip()}"
        )


def test_generated_readme_warns_no_handediting() -> None:
    text = (REPO_ROOT / ".harness/generated/README.md").read_text()
    assert "DO NOT EDIT" in text, "generated/README.md must warn against hand-editing"


def test_agents_md_alias_exists() -> None:
    """AGENTS.md aliases CLAUDE.md for cross-vendor AI tools."""
    agents_md = REPO_ROOT / "AGENTS.md"
    assert agents_md.exists(), "AGENTS.md missing (cross-vendor alias for CLAUDE.md)"
    if agents_md.is_symlink():
        assert agents_md.resolve().name == "CLAUDE.md"
    else:
        text = agents_md.read_text()
        assert "CLAUDE.md" in text, (
            "AGENTS.md is not a symlink and doesn't reference CLAUDE.md"
        )


def test_cursorrules_pointer_exists() -> None:
    cursorrules = REPO_ROOT / ".cursorrules"
    assert cursorrules.is_file()
    text = cursorrules.read_text()
    assert "CLAUDE.md" in text
    assert "load_harness" in text or "tools/load_harness" in text
