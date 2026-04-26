"""H.2.8 — init_harness bootstrap test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "init_harness.py"


def test_bootstrap_creates_expected_files(tmp_path: Path) -> None:
    target = tmp_path / "new_repo"
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--target", str(target),
         "--owner", "@bootstrap-test",
         "--tech-stack", "python"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "CLAUDE.md").exists()
    assert (target / "Makefile").exists()
    assert (target / "AGENTS.md").exists()
    assert (target / ".cursorrules").exists()
    assert (target / "tools" / "load_harness.py").exists()
    assert (target / "tools" / "run_validate.py").exists()
    assert (target / "tools" / "run_harness_regen.py").exists()
    # CLAUDE.md template substitutions occurred
    claude_text = (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@bootstrap-test" in claude_text
    assert "{{OWNER}}" not in claude_text
    assert "python" in claude_text


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "new_repo"
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--target", str(target),
             "--owner", "@x",
             "--tech-stack", "python"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
    # second run did not error AND did not corrupt files
    assert "{{OWNER}}" not in (target / "CLAUDE.md").read_text(encoding="utf-8")


def test_bootstrap_skips_baseline_and_generated_jsons(tmp_path: Path) -> None:
    """Bootstrap should not copy source-specific baseline or generated truth files."""
    target = tmp_path / "new_repo"
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--target", str(target),
         "--owner", "@x",
         "--tech-stack", "polyglot"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    baselines_dir = target / ".harness" / "baselines"
    if baselines_dir.exists():
        json_files = list(baselines_dir.glob("*.json"))
        assert json_files == [], f"baseline JSONs leaked: {json_files}"
    generated_dir = target / ".harness" / "generated"
    if generated_dir.exists():
        json_files = list(generated_dir.glob("*.json"))
        assert json_files == [], f"generated JSONs leaked: {json_files}"
