"""B11 (v1.2.0) — init_harness must copy .gitattributes to bootstrapped repos.

Without it, Windows checkouts break the make-harness byte-deterministic
regen gate (eol=lf protection).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_init_harness_copies_gitattributes(tmp_path):
    target = tmp_path / "consumer"
    subprocess.check_call(
        [
            sys.executable, str(REPO_ROOT / "tools/init_harness.py"),
            "--target", str(target),
            "--owner", "@test",
            "--tech-stack", "polyglot",
        ],
        timeout=30,
    )
    ga = target / ".gitattributes"
    assert ga.exists(), "init_harness must copy .gitattributes"
    assert "eol=lf" in ga.read_text(), (
        ".gitattributes must declare eol=lf — Windows checkout protection"
    )
