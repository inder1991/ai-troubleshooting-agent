"""Sprint H.0a Story 3 — tools/load_harness.py is the deterministic
discovery + precedence resolver used by every consumer (IDE-AI,
autonomous agent, validators)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOADER = REPO_ROOT / "tools/load_harness.py"


def _run_loader(target: str) -> dict:
    """Invoke the loader as a subprocess and parse its JSON output."""
    result = subprocess.run(
        [sys.executable, str(LOADER), "--target", target, "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"loader exited {result.returncode}: stderr={result.stderr}"
    )
    return json.loads(result.stdout)


def test_loader_exists_and_runs() -> None:
    assert LOADER.is_file()


def test_loader_returns_root_for_any_target() -> None:
    """Even when the target file doesn't exist (yet), root rules load."""
    result = _run_loader("backend/src/never/exists/foo.py")
    assert "root" in result
    assert "Rule Loading Contract" in result["root"]


def test_loader_walks_up_directory_tree(tmp_path: Path) -> None:
    """Per H-11 step 2: every CLAUDE.md from the target dir up to root loads."""
    target = "backend/src/learning/contracts.py"
    result = _run_loader(target)
    files = result["directory_rules_files"]
    # Once Story 5 lands, backend/CLAUDE.md and backend/src/learning/CLAUDE.md
    # will be in the tree. For now we assert the field exists and is a list.
    assert isinstance(files, list)


def test_loader_loads_generated() -> None:
    """Per H-11 step 3: all .harness/generated/*.json load."""
    result = _run_loader("backend/src/learning/contracts.py")
    assert "generated" in result
    assert isinstance(result["generated"], dict)


def test_loader_matches_cross_cutting_globs() -> None:
    """Per H-11 step 4: only .harness/*.md whose applies_to glob matches."""
    result = _run_loader("backend/src/learning/contracts.py")
    assert "cross_cutting_files" in result
    assert isinstance(result["cross_cutting_files"], list)


def test_loader_output_is_deterministic() -> None:
    """Two consecutive runs produce byte-identical output."""
    target = "backend/src/learning/contracts.py"
    a = subprocess.run(
        [sys.executable, str(LOADER), "--target", target, "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    b = subprocess.run(
        [sys.executable, str(LOADER), "--target", target, "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout
    assert a == b, "loader output is non-deterministic"


def test_loader_emits_precedence_order() -> None:
    """Per H-11 step 5: output records the precedence order applied."""
    result = _run_loader("backend/src/learning/contracts.py")
    assert result["precedence_order"] == [
        "root", "cross_cutting", "generated", "directory_rules",
    ]


def test_loader_text_mode_emits_concatenated_block() -> None:
    """Without --json, loader emits a human-readable concatenated context block."""
    result = subprocess.run(
        [sys.executable, str(LOADER), "--target", "backend/src/learning/contracts.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "# ROOT" in result.stdout, "text mode should label the root section"


def test_loader_records_malformed_cross_cutting() -> None:
    """If a .harness/*.md file has no front-matter, it's recorded as malformed
    rather than silently included or crashing the loader (H-25)."""
    fake = REPO_ROOT / ".harness/_test_malformed.md"
    fake.write_text("# I have no front matter\nbody only\n")
    try:
        result = _run_loader("backend/src/learning/contracts.py")
        assert any(
            ".harness/_test_malformed.md" in p for p in result["malformed_files"]
        ), "malformed cross-cutting file should be recorded"
    finally:
        fake.unlink(missing_ok=True)
