"""H.2.7 — Claude Code session-start hook config test."""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# settings.json is tracked (per-repo); settings.local.json is gitignored
# (per-user override). The harness ships its hook in the tracked file.
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
SETTINGS_LOCAL = REPO_ROOT / ".claude" / "settings.local.json"
WRAPPER = REPO_ROOT / "tools" / "_session_start_hook.sh"


def test_settings_file_is_valid_json() -> None:
    assert SETTINGS.exists()
    json.loads(SETTINGS.read_text(encoding="utf-8"))


def _all_session_hooks() -> list[dict]:
    invocations: list[dict] = []
    for path in (SETTINGS, SETTINGS_LOCAL):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        hooks = (data.get("hooks") or {}).get("SessionStart") or []
        for entry in hooks:
            invocations.extend(entry.get("hooks") or [])
    return invocations


def test_session_start_hook_is_declared() -> None:
    invocations = _all_session_hooks()
    assert invocations, "no SessionStart hook declared in either settings file"
    assert any(
        "_session_start_hook.sh" in (h.get("command") or "")
        for h in invocations
    ), invocations


def test_wrapper_script_is_executable() -> None:
    assert WRAPPER.exists()
    assert os.access(WRAPPER, os.X_OK), "wrapper not executable"


def test_wrapper_invokes_load_harness() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "load_harness.py" in text


def test_wrapper_surfaces_loader_failure(tmp_path: Path) -> None:
    """Point 4 — when load_harness.py crashes, the wrapper must emit a
    visible HARNESS_WARN block instead of silently degrading the session.

    Approach: copy the wrapper into tmp_path and replace its loader with
    a deliberately failing stub. Run the wrapper and assert the warning
    appears on stdout AND the wrapper itself exits 0.
    """
    import shutil
    import subprocess

    fake_repo = tmp_path / "repo"
    (fake_repo / "tools").mkdir(parents=True)
    (fake_repo / "tools" / "load_harness.py").write_text(
        "import sys\n"
        "print('boom: simulated loader crash', file=sys.stderr)\n"
        "sys.exit(17)\n",
        encoding="utf-8",
    )
    shutil.copy2(WRAPPER, fake_repo / "tools" / "_session_start_hook.sh")
    (fake_repo / "tools" / "_session_start_hook.sh").chmod(0o755)

    result = subprocess.run(
        ["bash", str(fake_repo / "tools" / "_session_start_hook.sh")],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"hook itself must exit 0 even when loader fails; got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "HARNESS_WARN" in result.stdout, (
        f"hook must emit HARNESS_WARN on loader failure. stdout: {result.stdout!r}"
    )
    assert "exited 17" in result.stdout, (
        f"hook must surface the loader exit code. stdout: {result.stdout!r}"
    )
    assert "boom: simulated loader crash" in result.stdout, (
        f"hook must surface the loader stderr preview. stdout: {result.stdout!r}"
    )


def test_wrapper_passes_through_loader_stdout_on_success(tmp_path: Path) -> None:
    """When load_harness.py succeeds, the wrapper passes its stdout through
    unchanged (no HARNESS_WARN noise)."""
    import shutil
    import subprocess

    fake_repo = tmp_path / "repo"
    (fake_repo / "tools").mkdir(parents=True)
    (fake_repo / "tools" / "load_harness.py").write_text(
        "print('CONTEXT_BLOCK_OK')\n",
        encoding="utf-8",
    )
    shutil.copy2(WRAPPER, fake_repo / "tools" / "_session_start_hook.sh")
    (fake_repo / "tools" / "_session_start_hook.sh").chmod(0o755)

    result = subprocess.run(
        ["bash", str(fake_repo / "tools" / "_session_start_hook.sh")],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "CONTEXT_BLOCK_OK" in result.stdout
    assert "HARNESS_WARN" not in result.stdout
