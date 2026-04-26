"""H.2.7 — Claude Code session-start hook config test."""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = REPO_ROOT / ".claude" / "settings.local.json"
WRAPPER = REPO_ROOT / "tools" / "_session_start_hook.sh"


def test_settings_file_is_valid_json() -> None:
    assert SETTINGS.exists()
    json.loads(SETTINGS.read_text(encoding="utf-8"))


def test_session_start_hook_is_declared() -> None:
    data = json.loads(SETTINGS.read_text(encoding="utf-8"))
    hooks = (data.get("hooks") or {}).get("SessionStart") or []
    assert hooks, "no SessionStart hook declared"
    invocations = [h for entry in hooks for h in (entry.get("hooks") or [])]
    assert any("_session_start_hook.sh" in (h.get("command") or "") for h in invocations), invocations


def test_wrapper_script_is_executable() -> None:
    assert WRAPPER.exists()
    assert os.access(WRAPPER, os.X_OK), "wrapper not executable"


def test_wrapper_invokes_load_harness() -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "load_harness.py" in text
