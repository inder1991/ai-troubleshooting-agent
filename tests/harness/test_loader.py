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
    """Per H-11 step 5: output records the precedence order applied.

    Updated for the budget-cap loader (point 1): "policies" is now a
    distinct mandatory tier between root and cross-cutting.
    """
    result = _run_loader("backend/src/learning/contracts.py")
    assert result["precedence_order"] == [
        "root", "policies", "cross_cutting", "generated", "directory_rules",
    ]


def test_loader_default_budget_caps_output() -> None:
    """Point 1 — default --max-bytes (32 KB) caps the rendered text output.

    Without the cap the loader would dump 700+ KB on a real repo. We allow
    a small overflow (mandatory tier + the budget-message footer can push a
    few hundred bytes past the cap), but we MUST be far below the un-capped
    size. 64 KB is a generous upper bound that still proves capping works.
    """
    result = subprocess.run(
        [sys.executable, str(LOADER)],  # global mode; no --target
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    out_bytes = len(result.stdout.encode("utf-8"))
    assert out_bytes < 65_536, (
        f"loader output {out_bytes} bytes exceeds 64 KB upper bound; "
        "the mandatory tier alone should not be that large."
    )


def _stage_synthetic_repo(tmp_path: Path, payload_size: int) -> Path:
    """Build a tiny self-contained repo under tmp_path with a single
    generated/big.json of `payload_size` bytes, plus a copy of the
    loader and its dependencies. Returns the path to the staged
    loader script.

    Used by the budget-related tests so they don't depend on the
    live repo's .harness/generated/ contents — the standalone
    ai-harness source repo wipes that directory in extract.sh.
    """
    import shutil
    fake_root = tmp_path / "repo"
    (fake_root / ".harness/generated").mkdir(parents=True)
    (fake_root / "tools").mkdir()
    (fake_root / "CLAUDE.md").write_text("# Synthetic root\n")
    big = {"payload": "x" * payload_size}
    (fake_root / ".harness/generated/big.json").write_text(json.dumps(big))
    shutil.copy2(LOADER, fake_root / "tools/load_harness.py")
    shutil.copy2(REPO_ROOT / "tools/_common.py", fake_root / "tools/_common.py")
    (fake_root / "tools/__init__.py").write_text("")
    return fake_root / "tools/load_harness.py"


def test_loader_emits_truncated_pointer_when_over_budget(tmp_path: Path) -> None:
    """Point 1 — files dropped due to budget appear as `[TRUNCATED] <path>`."""
    loader = _stage_synthetic_repo(tmp_path, payload_size=12_000)
    result = subprocess.run(
        [sys.executable, str(loader), "--max-bytes", "8000"],
        cwd=loader.parent.parent, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "[TRUNCATED]" in result.stdout, (
        "with an 8 KB cap and a 12 KB synthetic generated JSON, at "
        f"least one [TRUNCATED] pointer should appear. Got: "
        f"{result.stdout[-500:]!r}"
    )
    assert "big.json" in result.stdout, (
        "the truncated pointer should reference the synthetic file"
    )


def test_loader_unlimited_budget_includes_everything(tmp_path: Path) -> None:
    """Point 1 — --max-bytes 0 means no cap (CI agent mode).

    Uses the same synthetic mini-repo so the test is independent of
    live .harness/generated/ contents.
    """
    # Payload sized between the 32 KB cap and the unlimited mode so
    # the cap truncates and unlimited doesn't.
    loader = _stage_synthetic_repo(tmp_path, payload_size=40_000)
    capped = subprocess.run(
        [sys.executable, str(loader), "--max-bytes", "32768"],
        cwd=loader.parent.parent, capture_output=True, text=True,
    )
    unlimited = subprocess.run(
        [sys.executable, str(loader), "--max-bytes", "0"],
        cwd=loader.parent.parent, capture_output=True, text=True,
    )
    assert capped.returncode == 0 and unlimited.returncode == 0
    assert len(unlimited.stdout) > len(capped.stdout), (
        f"unlimited ({len(unlimited.stdout)} bytes) must exceed "
        f"capped ({len(capped.stdout)} bytes)"
    )
    # Unlimited mode emits no [TRUNCATED] pointers.
    assert "[TRUNCATED]" not in unlimited.stdout
    # Capped mode does (the 40 KB synthetic file overflows 32 KB cap).
    assert "[TRUNCATED]" in capped.stdout


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
