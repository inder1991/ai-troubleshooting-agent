"""B12 (v1.2.0) — init_harness must write .harness-version pin.

Without it, the next sync_harness.py exits 2 because the pin is
required. Local-source bootstraps pin to "main"; --from-git pins to
the resolved ref.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_init_harness_local_bootstrap_writes_main(tmp_path):
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
    pin = target / ".harness-version"
    assert pin.exists(), "init_harness must write .harness-version"
    assert pin.read_text().strip() == "main", (
        f"local-source bootstrap should pin to 'main', got {pin.read_text()!r}"
    )


def test_init_harness_idempotent_does_not_overwrite_pin(tmp_path):
    """Re-running init_harness without --force must preserve the
    existing pin so a consumer's manual `v1.2.0` pin isn't reset."""
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
    pin = target / ".harness-version"
    pin.write_text("v0.0.42\n", encoding="utf-8")
    subprocess.check_call(
        [
            sys.executable, str(REPO_ROOT / "tools/init_harness.py"),
            "--target", str(target),
            "--owner", "@test",
            "--tech-stack", "polyglot",
        ],
        timeout=30,
    )
    assert pin.read_text().strip() == "v0.0.42", (
        "second run without --force must NOT overwrite the existing pin"
    )
